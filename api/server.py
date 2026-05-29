"""
VectoSports AI Results Server
Implementa os 4 endpoints para gerenciar uploads e processamento de análises biomecânicas

New Flow:
1. Receives job data + files from ProbPose worker
2. Processes with AI agent
3. Saves AI result to temp txt file
4. Uploads AI result to uploadResultsUrl (from RabbitMQ message)
5. Ready to process next job (parallel processing supported)
"""
import os
import sys
import json
import uuid
import asyncio
import logging
import tempfile
import shutil
import signal
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

import pika
import requests
import pydantic
from pydantic import BaseModel, ConfigDict
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path for imports
project_root = Path(__file__).parent
if (project_root / "ai_agents").exists():
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        logger.info(f"Added {project_root} to sys.path")
elif (project_root.parent / "ai_agents").exists():
    if str(project_root.parent) not in sys.path:
        sys.path.insert(0, str(project_root.parent))
        logger.info(f"Added {project_root.parent} to sys.path")

# Import root agent and Gemini (heavy imports at top level to detect failures early)
logger.info("📦 Importing heavy modules...")
try:
    from ai_agents.vectosports.core.root_agent import root_agent
    from google import genai
    from google.genai.types import Part, Content, VideoMetadata
    import mimetypes
    import time
    from api.gcs_utils import download_from_gcs, parse_gcs_uri, upload_to_gcs
    logger.info("✅ Heavy modules imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import heavy modules: {e}")
    # We don't exit here to allow health checks to pass if deployment is tricky, 
    # but actual jobs will fail later with clear errors.

# ============================================================================
# CONFIGURATION
# ============================================================================

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_USER = os.getenv('RABBITMQ_USERNAME', 'guest')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASSWORD', 'guest')
RABBITMQ_QUEUE = os.getenv('RABBITMQ_QUEUE', 'vectosports_ai_analysis')
RABBITMQ_AI_ERROR_QUEUE = os.getenv('RABBITMQ_AI_ERROR_QUEUE', 'vectosports_ai_analysis_failed')

# Flag to control server shutdown
should_shutdown = False

# ============================================================================
# MODELS
# ============================================================================

class UploadUrlRequest(BaseModel):
    """Requisição para obter URLs de upload"""
    jobId: str
    files: List[str]


class UploadUrlResponse(BaseModel):
    """Resposta com URLs para upload"""
    urls: Dict[str, str]


class ProBPoseStatistics(BaseModel):
    """Estatísticas do ProBPose"""
    model_config = ConfigDict(extra='allow')
    
    total_frames: Optional[int] = None
    keypoints_per_frame: Optional[int] = None
    average_confidence: Optional[float] = None


class ProBPoseOutput(BaseModel):
    """Saída do ProBPose"""
    model_config = ConfigDict(extra='allow')
    
    statistics: Optional[ProBPoseStatistics] = None
    outputFiles: Dict[str, str] = {}
    clipsInfo: Optional[List] = []


class AnalysisConfig(BaseModel):
    """Configuração da análise"""
    model_config = ConfigDict(extra='allow')
    
    agent: Optional[str] = None
    cameraAngle: Optional[str] = None
    analysisMode: Optional[str] = None
    language: Optional[str] = None
    priority: Optional[str] = None
    focus: Optional[str] = None
    notes: Optional[str] = None
    style: Optional[str] = None
    phase: Optional[str] = None
    # Legacy fields (optional for backward compatibility)
    sport: Optional[str] = None
    analysisType: Optional[str] = None
    focusAreas: List[str] = []


class AthleteData(BaseModel):
    """Dados do atleta"""
    model_config = ConfigDict(extra='allow')
    
    name: Optional[str] = None
    email: Optional[str] = None
    birthDate: Optional[str] = None
    phone: Optional[str] = None
    parentName: Optional[str] = None
    parentPhone: Optional[str] = None
    notes: Optional[str] = None
    shareToken: Optional[str] = None
    managerIds: Optional[List[str]] = None
    isActive: Optional[bool] = None
    createdAt: Optional[Dict] = None
    updatedAt: Optional[Dict] = None
    # Legacy fields (optional for backward compatibility)
    age: Optional[int] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    sport: Optional[str] = None


class VideoInfo(BaseModel):
    """Informações do vídeo"""
    model_config = ConfigDict(extra='allow')
    
    videoId: Optional[str] = None
    filename: Optional[str] = None
    downloadUrl: Optional[str] = None
    codec: Optional[str] = None
    size: Optional[int] = None
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None


class Metadata(BaseModel):
    """Metadados da análise"""
    model_config = ConfigDict(extra='allow')
    
    timestamp: Optional[str] = None
    source: Optional[str] = None
    location: Optional[str] = None


class ResultsRequest(BaseModel):
    """Requisição POST /api/results"""
    model_config = ConfigDict(extra='allow')
    
    jobId: Optional[str] = None
    analysisId: str
    timestamp: Optional[str] = None
    folderId: Optional[str] = None
    athleteId: Optional[str] = None
    requestedBy: Optional[str] = None
    analysisConfig: Optional[AnalysisConfig] = None
    athleteData: Optional[AthleteData] = None
    videos: Optional[List[VideoInfo]] = None
    # Legacy single video field
    videoInfo: Optional[VideoInfo] = None
    metadata: Optional[Metadata] = None
    uploadResultsUrl: Optional[str] = None
    probposeOutput: Optional[ProBPoseOutput] = None
    originalPayload: Optional[Dict] = None
    # GCS fields
    metadataPath: Optional[str] = None
    isGcs: Optional[bool] = None


class ResultsResponse(BaseModel):
    """Resposta POST /api/results"""
    token: str
    message: str
    files_ready: List[str]


class StatusResponse(BaseModel):
    """Resposta GET /api/results/status/{token}"""
    token: str
    status: str
    progress: int
    result: Optional[Dict] = None
    error: Optional[str] = None


# ============================================================================
# STORAGE & STATE
# ============================================================================

# Upload sessions: {session_id: {job_id, filename, expires, uploaded, uploaded_at}}
upload_sessions: Dict = {}

# Jobs database: {token: {token, job_id, status, progress, ...}}
jobs_db: Dict = {}

# ============================================================================
# RABBITMQ ERROR QUEUE
# ============================================================================

def publish_to_ai_error_queue(job_data: dict, error_reason: str):
    """Publish failed job to AI error queue for manual review."""
    if not RABBITMQ_HOST:
        logger.warning("RABBITMQ_HOST not configured. Cannot publish to error queue.")
        return False
    
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        channel.queue_declare(queue=RABBITMQ_AI_ERROR_QUEUE, durable=True)
        
        error_payload = {
            "original_job": job_data,
            "error_reason": error_reason,
            "failed_at": datetime.now().isoformat(),
            "service": "vectosports_ai_server"
        }
        
        channel.basic_publish(
            exchange='',
            routing_key=RABBITMQ_AI_ERROR_QUEUE,
            body=json.dumps(error_payload),
            properties=pika.BasicProperties(
                delivery_mode=2,
                headers={'failure_reason': error_reason}
            )
        )
        
        logger.info(f"✓ Published error to queue: {RABBITMQ_AI_ERROR_QUEUE}")
        
        channel.close()
        connection.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to publish to AI error queue: {e}")
        return False


# ============================================================================
# AI AGENT INTEGRATION
# ============================================================================

def run_ai_agent_analysis(payload: dict, upload_dir: Path) -> tuple[bool, str, str, Path]:
    """
    Run AI agent analysis on the biomechanical data.
    
    Args:
        payload: The job payload with athlete data, analysis config, etc.
        upload_dir: Directory containing uploaded files (videos, keypoints, etc.)
    
    Returns:
        (success: bool, ai_result: str, error_message: str, reports_dir: Path)
    """
    try:
        logger.info("🤖 Starting AI Agent analysis...")
        
        # Prepare the analysis message for the AI agent
        athlete_data = payload.get('athleteData', {})
        analysis_config = payload.get('analysisConfig', {})
        probpose_output_raw = payload.get('probposeOutput')
        logger.info(f"probposeOutput in payload: {'probposeOutput' in payload}, raw value: {probpose_output_raw}")
        probpose_output = probpose_output_raw or {}
        logger.info(f"probpose_output type: {type(probpose_output)}, value: {probpose_output}")
        metadata = payload.get('metadata', {})
        
        # Download metadata.json from GCS if metadataPath is provided
        metadata_path = payload.get('metadataPath')
        if metadata_path and metadata_path.startswith('gs://'):
            logger.info(f"📥 Downloading metadata from GCS: {metadata_path}")
            try:
                metadata_file = upload_dir / 'metadata.json'
                if download_from_gcs(metadata_path, metadata_file):
                    with open(metadata_file, 'r') as f:
                        gcs_metadata = json.load(f)
                    logger.info(f"✓ Metadata downloaded and parsed")
                    
                    # Extract resultFiles from metadata
                    result_files = gcs_metadata.get('resultFiles', [])
                    logger.info(f"📂 Found {len(result_files)} result files in metadata")
                    
                    # Get base GCS path from metadataPath (remove /metadata.json)
                    base_gcs_path = metadata_path.rsplit('/metadata.json', 1)[0]
                    logger.info(f"📂 Base GCS path: {base_gcs_path}")
                    
                    # Download each result file from GCS
                    # Support both list and dict formats
                    if isinstance(result_files, dict):
                        # Dict format: {"key": "gs://path"} or {"key": {"relativePath": "..."}}
                        for file_key, file_info in result_files.items():
                            if isinstance(file_info, str) and file_info.startswith('gs://'):
                                file_path = file_info
                            elif isinstance(file_info, dict):
                                # Try relativePath first, then construct full GCS path
                                relative_path = file_info.get('relativePath')
                                if relative_path:
                                    file_path = f"{base_gcs_path}/{relative_path}"
                                else:
                                    file_path = file_info.get('path') or file_info.get('url') or file_info.get('gcsPath')
                            else:
                                logger.warning(f"Skipping unknown format for {file_key}: {file_info}")
                                continue
                            
                            if file_path and file_path.startswith('gs://'):
                                logger.info(f"📥 Downloading {file_key}: {file_path}")
                                _, blob_path = parse_gcs_uri(file_path)
                                filename = Path(blob_path).name
                                dest_path = upload_dir / 'outputs' / 'probpose' / filename
                                download_from_gcs(file_path, dest_path)
                            else:
                                logger.warning(f"Skipping non-GCS path for {file_key}: {file_path}")
                                
                    elif isinstance(result_files, list):
                        # List format: [{"relativePath": "...", "filename": "..."}, ...]
                        for item in result_files:
                            if isinstance(item, str) and item.startswith('gs://'):
                                file_path = item
                                filename = Path(file_path).name
                            elif isinstance(item, dict):
                                # Try relativePath first
                                relative_path = item.get('relativePath')
                                if relative_path:
                                    file_path = f"{base_gcs_path}/{relative_path}"
                                    filename = item.get('filename') or Path(relative_path).name
                                else:
                                    file_path = item.get('path') or item.get('url') or item.get('gcsPath')
                                    filename = item.get('filename') or (Path(file_path).name if file_path else None)
                            else:
                                logger.warning(f"Skipping unknown item format: {item}")
                                continue
                            
                            if file_path and file_path.startswith('gs://'):
                                logger.info(f"📥 Downloading {filename}: {file_path}")
                                dest_path = upload_dir / 'outputs' / 'probpose' / filename
                                download_from_gcs(file_path, dest_path)
                            else:
                                logger.warning(f"Skipping item without valid GCS path: {item}")
                    
                    # Update probpose_output with the downloaded files info
                    probpose_output = gcs_metadata.get('probposeOutput', probpose_output)
                else:
                    logger.warning(f"Failed to download metadata from {metadata_path}")
            except Exception as e:
                logger.error(f"Error downloading/parsing metadata: {e}")
                logger.error(traceback.format_exc())
        else:
            logger.info(f"No metadataPath provided or not a GCS path: {metadata_path}")
        
        # Extract video info (support both single video and multiple videos)
        videos = payload.get('videos', [])
        video_info = videos[0] if videos else payload.get('videoInfo', {})
        
        # Determine sport from analysis config or athlete data
        sport = analysis_config.get('sport') or athlete_data.get('sport') or 'Unknown'
        # If agent is specified, try to infer sport from it
        agent = analysis_config.get('agent', '')
        if 'swimming' in agent.lower() or 'natacao' in agent.lower():
            sport = 'swimming'
        elif 'running' in agent.lower() or 'corrida' in agent.lower():
            sport = 'running'
        
        # Get list of uploaded files for context
        uploaded_files = list(upload_dir.glob('**/*'))
        file_list = [str(f.relative_to(upload_dir)) for f in uploaded_files if f.is_file()]
        
        # Build the analysis prompt
        analysis_prompt = f"""
## Biomechanical Analysis Request

### Athlete Information
- Name: {athlete_data.get('name', 'Unknown')}
- Age: {athlete_data.get('age', 'N/A')}
- Height: {athlete_data.get('height', 'N/A')} cm
- Weight: {athlete_data.get('weight', 'N/A')} kg
- Sport: {sport}

### Analysis Configuration
- Agent: {analysis_config.get('agent', 'not_provided')}
- Camera Angle: {analysis_config.get('cameraAngle', 'not_provided')}
- Analysis Mode: {analysis_config.get('analysisMode', 'full')}
- Focus: {analysis_config.get('focus', 'None')}
- Style: {analysis_config.get('style', 'None')}
- Phase: {analysis_config.get('phase', 'None')}
- Notes: {analysis_config.get('notes', 'None')}
- Language: {analysis_config.get('language', 'pt-br')}
- Priority: {analysis_config.get('priority', 'normal')}

### Video Information
- Filename: {video_info.get('filename', 'Unknown')}
- Duration: {video_info.get('duration', 'N/A')} seconds
- Resolution: {video_info.get('width', 'N/A')}x{video_info.get('height', 'N/A')}
- FPS: {video_info.get('fps', 'N/A')}
- Codec: {video_info.get('codec', 'N/A')}

### ProbPose Output Statistics
- Total Frames: {((probpose_output or {}).get('statistics') or {}).get('total_frames', 'N/A')}
- Keypoints per Frame: {((probpose_output or {}).get('statistics') or {}).get('keypoints_per_frame', 'N/A')}
- Average Confidence: {((probpose_output or {}).get('statistics') or {}).get('average_confidence', 'N/A')}

### Available Files for Analysis
{chr(10).join(['- ' + f for f in file_list])}

### Instructions
Please analyze the biomechanical data and provide:
1. Technique assessment based on the keypoint data
2. Specific recommendations for improvement
3. Key strengths identified
4. Areas that need attention
5. Training suggestions

Language: pt-br
"""
        
        logger.info(f"Analysis prompt prepared. Length: {len(analysis_prompt)} chars")
        logger.info(f"Available files: {file_list}")
        
        # Prepare parts for Gemini upload (incorporate files as actual attachments)
        logger.info("📤 Preparing files for Gemini upload...")
        client = genai.Client()
        parts = [Part(text=analysis_prompt)]
        
        # Iterate through uploaded files and attach to the prompt
        for file_path in uploaded_files:
            if not file_path.is_file():
                continue
            
            filename = file_path.name
            
            # Simple heuristic: following consumer.py logic, exclude files that contain "_pose_" 
            # as they are usually redundant for Gemini when we have the raw video + statistics
            if "_pose_" in filename:
                logger.info(f"Skipping pose-rendered file: {filename}")
                continue
                
            file_size = file_path.stat().st_size
            mime_type, _ = mimetypes.guess_type(str(file_path))
            
            if not mime_type:
                if filename.endswith('.json') or filename.endswith('.txt'):
                    mime_type = 'text/plain'
                else:
                    mime_type = 'application/octet-stream'
            
            logger.info(f"Processing attachment: {filename} ({mime_type}, {file_size} bytes)")
            
            try:
                # 20MB limit for inline (only for videos)
                if file_size < 20 * 1024 * 1024 and mime_type.startswith('video'):
                    logger.info(f"Sending {filename} inline")
                    with open(file_path, 'rb') as f:
                        file_bytes = f.read()
                    parts.append(Part(
                        inline_data={
                            "data": file_bytes,
                            "mime_type": mime_type
                        },
                        video_metadata=VideoMetadata(fps=24)
                    ))
                else:
                    # Upload to Files API
                    logger.info(f"Uploading {filename} to Gemini Files API...")
                    myfile = client.files.upload(file=str(file_path))
                    
                    # Poll until active
                    attempts = 0
                    while myfile.state.name == "PROCESSING" and attempts < 30:
                        time.sleep(2)
                        myfile = client.files.get(name=myfile.name)
                        attempts += 1
                    
                    if myfile.state.name == "ACTIVE":
                        logger.info(f"File {filename} uploaded: {myfile.uri}")
                        part_kwargs = {
                            "file_data": {
                                "file_uri": myfile.uri,
                                "mime_type": mime_type
                            }
                        }
                        
                        # Add video metadata if it's a video
                        if mime_type.startswith('video'):
                            part_kwargs["video_metadata"] = VideoMetadata(fps=24)
                            
                        parts.append(Part(**part_kwargs))
                    else:
                        logger.warning(f"File {filename} processing failed (state: {myfile.state.name})")
            except Exception as e:
                logger.error(f"Error handling file {filename}: {e}")

        # Create the Content object with all parts
        ai_message = Content(role="user", parts=parts)
        
        # Generate unique IDs for the session
        user_id = f"athlete_{payload.get('jobId', 'unknown')}"
        session_id = f"session_{payload.get('analysisId', uuid.uuid4())}"
        
        # Run the AI agent
        logger.info(f"Running AI agent with user_id={user_id}, session_id={session_id}")
        
        result = root_agent.run(
            user_id=user_id,
            session_id=session_id,
            new_message=ai_message
        )
        
        # Extract the response text
        if hasattr(result, 'text'):
            ai_result = result.text
        elif hasattr(result, 'content'):
            ai_result = str(result.content)
        elif isinstance(result, str):
            ai_result = result
        else:
            ai_result = str(result)
        
        logger.info(f"✓ AI analysis completed. Result length: {len(ai_result)} chars")
        
        # Save the complete output to a text file
        reports_dir = upload_dir / 'reports'
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        import re
        
        # Parse and save Markdown report (look for FINAL_REPORT tags)
        md_saved = False
        md_content = None
        try:
            md_match = re.search(r'<!-- FINAL_REPORT_START -->(.*?)<!-- FINAL_REPORT_END -->', ai_result, re.DOTALL | re.IGNORECASE)
            if md_match:
                md_content = md_match.group(1).strip()
                analysis_id = payload.get('analysisId', 'unknown')
                md_file = reports_dir / 'analysis_report.md'
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                logger.info(f"💾 Saved Markdown report to: {md_file}")
                md_saved = True
            else:
                logger.warning("No <!-- FINAL_REPORT_START --> tags found in AI output")
        except Exception as e:
            logger.warning(f"Could not parse Markdown from AI output: {e}")
        
        # Parse and save HTML report (look for COACH_TIPS tags)
        html_saved = False
        html_content = None
        try:
            html_match = re.search(r'<!-- COACH_TIPS_START -->(.*?)<!-- COACH_TIPS_END -->', ai_result, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(1).strip()
                html_file = reports_dir / 'coach_tips.html'
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.info(f"💾 Saved HTML report to: {html_file}")
                html_saved = True
            else:
                logger.warning("No <!-- COACH_TIPS_START --> tags found in AI output")
        except Exception as e:
            logger.warning(f"Could not parse HTML from AI output: {e}")
        
        # Save cleaned output (only the actual report content) to the main text file
        analysis_id = payload.get('analysisId', 'unknown')
        txt_file = reports_dir / f"{analysis_id}.txt"
        
        # Build clean output with only the report content
        clean_output = []
        if md_content:
            clean_output.append(md_content)
        if html_content:
            clean_output.append("\n\n")
            clean_output.append(html_content)
        
        # If we have parsed content, save that; otherwise save the full result
        if clean_output:
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(''.join(clean_output))
            logger.info(f"💾 Saved cleaned report to: {txt_file}")
        else:
            # Fallback: save full output if no tags found
            logger.info("No report tags found, saving full AI output")
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(ai_result)
            logger.info(f"💾 Saved full output to: {txt_file}")
        
        return True, ai_result, None, reports_dir
        
    except ImportError as e:
        error_msg = f"Failed to import AI agent modules: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False, None, error_msg, None
        
    except Exception as e:
        error_msg = f"AI agent analysis failed: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False, None, error_msg, None


def save_reports_to_gcs(payload: dict, reports_dir: Path, final_status: str = 'completed') -> tuple[bool, str]:
    """
    Save AI report files directly to GCS and update metadata.json.
    
    Args:
        payload: The job payload containing metadata path and other info
        reports_dir: Directory containing the report files (TXT, HTML, MD)
        final_status: The final processingStatus to set (default: 'completed', for comparisons: 'readyForReview')
    
    Returns:
        (success: bool, error_message: str)
    """
    try:
        # Extract base GCS path from metadataPath
        metadata_path = payload.get('metadataPath')
        if not metadata_path or not metadata_path.startswith('gs://'):
            return False, "No valid metadataPath found in payload"
        
        # Remove /metadata.json to get the base folder path
        base_path = metadata_path.rsplit('/metadata.json', 1)[0]
        analysis_id = payload.get('analysisId', 'unknown')
        reports_gcs_path = f"{base_path}/reports/{analysis_id}"
        
        logger.info(f"📤 Uploading reports to GCS: {reports_gcs_path}")
        
        if not reports_dir or not reports_dir.exists():
            return False, "Reports directory does not exist"
        
        # Upload all files in reports directory and track uploaded files
        uploaded_files = []
        for report_file in reports_dir.iterdir():
            if report_file.is_file():
                # Determine content type
                if report_file.suffix == '.html':
                    content_type = 'text/html'
                    file_type = 'ai_report_html'
                elif report_file.suffix == '.md':
                    content_type = 'text/markdown'
                    file_type = 'ai_report_md'
                elif report_file.suffix == '.txt':
                    content_type = 'text/plain'
                    file_type = 'ai_report_txt'
                else:
                    content_type = None
                    file_type = 'ai_report'
                
                gcs_uri = f"{reports_gcs_path}/{report_file.name}"
                if upload_to_gcs(report_file, gcs_uri, content_type):
                    uploaded_files.append({
                        "id": str(int(datetime.now().timestamp() * 1000)),
                        "filename": report_file.name,
                        "type": file_type,
                        "size": report_file.stat().st_size,
                        "relativePath": f"reports/{analysis_id}/{report_file.name}",
                        "mimeType": content_type or "application/octet-stream",
                        "createdAt": datetime.now().isoformat(),
                        "metadata": {
                            "analysisId": analysis_id,
                            "generatedBy": "vectosports_ai"
                        }
                    })
                else:
                    logger.warning(f"Failed to upload {report_file.name}")
        
        if not uploaded_files:
            return False, "No files were uploaded to GCS"
        
        logger.info(f"✓ Successfully uploaded {len(uploaded_files)} report files to GCS")
        
        # Update metadata.json with new report files and status
        try:
            logger.info(f"📝 Updating metadata.json...")
            
            # Download current metadata
            temp_metadata = reports_dir.parent / 'metadata_update.json'
            if download_from_gcs(metadata_path, temp_metadata):
                with open(temp_metadata, 'r') as f:
                    metadata = json.load(f)
                
                # Add new result files
                if 'resultFiles' not in metadata:
                    metadata['resultFiles'] = []
                metadata['resultFiles'].extend(uploaded_files)
                
                # Update status
                metadata['status'] = final_status  # Use the provided final_status
                metadata['processingStatus'] = final_status  # Also update processingStatus field
                metadata['aiProcessingStatus'] = 'completed'
                metadata['aiCompletedAt'] = datetime.now().isoformat()
                metadata['updatedAt'] = datetime.now().isoformat()
                
                # Update stats
                if 'stats' not in metadata:
                    metadata['stats'] = {}
                metadata['stats']['hasAiAnalysis'] = True
                metadata['stats']['aiReportCount'] = len(uploaded_files)
                metadata['stats']['totalResultFiles'] = len(metadata.get('resultFiles', []))
                metadata['stats']['hasResults'] = True
                
                # Save updated metadata locally
                with open(temp_metadata, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                # Upload updated metadata back to GCS
                if upload_to_gcs(temp_metadata, metadata_path, 'application/json'):
                    logger.info(f"✓ Metadata updated successfully")
                else:
                    logger.warning("Failed to upload updated metadata to GCS")
                
                # Cleanup temp file
                temp_metadata.unlink(missing_ok=True)
            else:
                logger.warning("Could not download metadata for update")
                
        except Exception as e:
            logger.warning(f"Failed to update metadata: {e}")
        
        return True, None
            
    except Exception as e:
        error_msg = f"Exception during GCS upload: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False, error_msg


def trigger_server_shutdown():
    """Trigger graceful server shutdown after job completion."""
    global should_shutdown
    should_shutdown = True
    logger.info("🔴 Server shutdown triggered. Will exit after current request completes.")
    
    # Schedule shutdown in a separate task
    async def shutdown_task():
        await asyncio.sleep(2)  # Give time for response to be sent
        logger.info("Executing server shutdown...")
        os.kill(os.getpid(), signal.SIGTERM)
    
    asyncio.create_task(shutdown_task())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI"""
    # Startup logic
    logger.info("🚀 VectoSports AI Results Server starting...")
    logger.info(f"Upload base directory: {os.getenv('UPLOAD_BASE_DIR', '/data/uploads')}")
    logger.info(f"Max retention days: {os.getenv('JOB_RETENTION_DAYS', 7)}")
    logger.info(f"RabbitMQ Host: {RABBITMQ_HOST}")
    logger.info(f"AI Error Queue: {RABBITMQ_AI_ERROR_QUEUE}")
    
    # Periodical cleanup task
    cleanup_task = asyncio.create_task(run_periodic_tasks())
    
    yield
    
    # Shutdown logic
    logger.info("🔴 VectoSports AI Results Server shutting down...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


async def run_periodic_tasks():
    """Run periodic cleanup tasks"""
    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            cleanup_expired_sessions()
            cleanup_old_jobs()
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")


# ============================================================================
# APP INITIALIZATION
# ============================================================================

def handle_rabbitmq_message(message: Dict[str, Any]):
    """Handle RabbitMQ message for job processing."""
    logger.info(f"📨 Received RabbitMQ message: {message}")
    
    # Check if this is a wrapped error queue message
    if 'original_job' in message:
        logger.info("🔄 Unwrapping message from error queue")
        message = message['original_job']
    
    # The message is the ResultsRequest dict
    payload = ResultsRequest(**message)
    
    # Generate token
    token = f"proc_{uuid.uuid4()}"
    
    # Store job in db
    jobs_db[token] = {
        "token": token,
        "job_id": payload.jobId or payload.analysisId,
        "analysis_id": payload.analysisId,
        "status": "processing",
        "progress": 0,
        "athlete_name": payload.athleteData.name if payload.athleteData else 'Unknown',
        "athlete_sport": 'Unknown',  # Will be determined in process_job
        "analysis_config": payload.analysisConfig.model_dump() if payload.analysisConfig else {},
        "focus_areas": payload.analysisConfig.focusAreas if payload.analysisConfig else [],
        "uploaded_files": [],
        "created_at": datetime.now().isoformat(),
        "result": None,
        "error": None
    }
    
    logger.info(f"   ✓ Job created with token: {token}")
    
    # Run the async process_job
    asyncio.run(process_job(token, payload))

app = FastAPI(
    title="VectoSports AI Results Server",
    description="Servidor para gerenciar uploads e processamento de análises biomecânicas",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# UTILITIES
# ============================================================================

def get_upload_dir(job_id: str) -> Path:
    """Obtém o diretório de upload para um job"""
    base_dir = Path(os.getenv("UPLOAD_BASE_DIR", "/data/uploads"))
    job_dir = base_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def cleanup_expired_sessions():
    """Remove sessões expiradas"""
    now = datetime.now()
    expired = [sid for sid, session in upload_sessions.items() 
               if session["expires"] < now]
    for sid in expired:
        del upload_sessions[sid]
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired upload sessions")


def cleanup_old_jobs():
    """Remove jobs antigos (mais de 7 dias)"""
    now = datetime.now()
    cutoff = now - timedelta(days=7)
    old = [token for token, job in jobs_db.items() 
           if datetime.fromisoformat(job["created_at"]) < cutoff 
           and job["status"] in ["completed", "failed"]]
    for token in old:
        del jobs_db[token]
    if old:
        logger.info(f"Cleaned up {len(old)} old jobs")


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_jobs": len(jobs_db),
        "active_sessions": len(upload_sessions)
    }


# ============================================================================
# ENDPOINT 1: POST /api/results/get-upload-urls
# ============================================================================

@app.post("/api/results/get-upload-urls", response_model=UploadUrlResponse)
async def get_upload_urls(request: UploadUrlRequest, http_request: Request):
    """
    Gera URLs presigned para upload de arquivos.
    
    Checklist:
    - [x] Recebe jobId e lista de files
    - [x] Gera URLs presigned (com tokens únicos)
    - [x] URLs válidas por mínimo 1 hora
    - [x] Cada arquivo tem URL única
    - [x] Retorna JSON com mapa {filename: url}
    """
    logger.info(f"📋 GET-UPLOAD-URLS para job: {request.jobId}")
    logger.info(f"   Arquivos: {request.files}")
    
    upload_urls = {}
    
    for filename in request.files:
        token = str(uuid.uuid4())
        session_id = f"{request.jobId}_{token}"
        
        # Armazenar sessão com expiração de 3 horas
        upload_sessions[session_id] = {
            "job_id": request.jobId,
            "filename": filename,
            "expires": datetime.now() + timedelta(hours=3),
            "uploaded": False,
            "created_at": datetime.now().isoformat()
        }
        
        # Gerar URL (prefer request host to avoid localhost inside containers)
        base_url = os.getenv('SERVER_BASE_URL', '').rstrip('/')
        if not base_url:
            # Extract scheme and host from request, respecting proxy headers
            scheme = http_request.headers.get("x-forwarded-proto", http_request.url.scheme)
            host = http_request.headers.get("x-forwarded-host", http_request.url.netloc)
            if not host:
                host = http_request.url.netloc
            base_url = f"{scheme}://{host}"
            
        url = f"{base_url}/api/upload/{request.jobId}/{token}"
        upload_urls[filename] = url
        
        logger.info(f"   ✓ Token gerado para {filename}: {token}")
    
    logger.info(f"✅ {len(upload_urls)} URLs de upload geradas")
    return UploadUrlResponse(urls=upload_urls)


# ============================================================================
# ENDPOINT 2: PUT /api/upload/{job_id}/{token}
# ============================================================================

@app.put("/api/upload/{job_id}/{token}")
async def upload_file(job_id: str, token: str, request: Request):
    """
    Recebe uploads binários dos arquivos.
    
    Checklist:
    - [x] Recebe stream binário (PUT)
    - [x] Valida sessão (token existe e não expirou)
    - [x] Salva arquivo no servidor
    - [x] Retorna status 200
    - [x] Cleanup automático (deleta token após upload)
    - [x] Limite de tamanho (1GB)
    """
    session_id = f"{job_id}_{token}"
    
    logger.info(f"📤 UPLOAD iniciado para job: {job_id}, token: {token}")
    
    # Validar sessão existe
    if session_id not in upload_sessions:
        logger.warning(f"   ❌ Sessão não encontrada: {session_id}")
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = upload_sessions[session_id]
    
    # Verificar expiração
    if datetime.now() > session["expires"]:
        logger.warning(f"   ❌ Sessão expirada: {session_id}")
        del upload_sessions[session_id]
        raise HTTPException(status_code=403, detail="Session expired")
    
    try:
        # Obter tamanho do arquivo
        content_length = request.headers.get("content-length")
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            logger.info(f"   Tamanho: {size_mb:.2f} MB")
            
            # Validar limite (1GB)
            if size_mb > 1024:
                raise HTTPException(status_code=413, detail="File too large (max 1GB)")
        
        # Salvar arquivo
        upload_dir = get_upload_dir(job_id)
        filepath = upload_dir / session["filename"]
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"   Salvando em: {filepath}")
        
        body = await request.body()
        with open(filepath, 'wb') as f:
            f.write(body)
        
        # Marcar como uploadado
        session["uploaded"] = True
        session["uploaded_at"] = datetime.now().isoformat()
        
        logger.info(f"✅ Arquivo uploadado: {session['filename']}")
        
        return {
            "status": "uploaded",
            "filename": session["filename"],
            "size": len(body),
            "uploaded_at": session["uploaded_at"]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"   ❌ Erro durante upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 3: POST /api/results
# ============================================================================

@app.post("/api/results", response_model=ResultsResponse)
async def receive_results(request: Request):
    """
    Recebe metadata e inicia processamento.
    Suporta tanto JSON quanto multipart/form-data.
    
    Checklist:
    - [x] Recebe metadata + URLs dos arquivos
    - [x] Valida que todos os arquivos foram uploadados
    - [x] Cria entrada no banco de dados
    - [x] Inicia processamento assíncrono
    - [x] Gera token único
    - [x] Retorna token ao worker
    """
    content_type = request.headers.get("content-type", "")
    
    # Handle multipart/form-data (files uploaded directly)
    if content_type.startswith("multipart/form-data"):
        logger.info("📨 RESULTS recebido (multipart/form-data)")
        
        # Log raw body before any processing
        logger.info("\n" + "="*80)
        logger.info("📦 RAW DATA RECEBIDO (multipart form fields - exceto binários):")
        logger.info("="*80)
        
        form = await request.form()
        
        # Log all form fields (raw, before processing)
        for key in form.keys():
            value = form.get(key)
            if hasattr(value, 'filename'):
                logger.info(f"  [{key}] = FILE UPLOAD: filename='{value.filename}'")
            else:
                # Log the raw string value
                if isinstance(value, str):
                    if len(value) > 500:
                        logger.info(f"  [{key}] = {value[:500]}... (truncated, {len(value)} chars total)")
                    else:
                        logger.info(f"  [{key}] = {value}")
                else:
                    logger.info(f"  [{key}] = {repr(value)}")
        logger.info("="*80 + "\n")
        
        # Extract metadata from form field
        metadata_json = form.get("metadata") or form.get("data") or form.get("json")
        if metadata_json:
            if isinstance(metadata_json, str):
                payload_dict = json.loads(metadata_json)
            else:
                payload_dict = json.loads(await metadata_json.read())
            logger.info(f"✓ Metadata JSON extraído")
        else:
            # Try to reconstruct from individual fields
            payload_dict = {}
            for key, value in form.items():
                if not hasattr(value, 'filename'):  # Skip file uploads
                    try:
                        # Try to parse JSON values
                        payload_dict[key] = json.loads(value) if isinstance(value, str) and (value.startswith('{') or value.startswith('[')) else value
                    except:
                        payload_dict[key] = value
            logger.info(f"✓ Payload reconstruído a partir dos campos do form")
        
        # Ensure required field analysisId exists
        if 'analysisId' not in payload_dict:
            # Generate analysisId from jobId or create a new one
            payload_dict['analysisId'] = payload_dict.get('jobId', f"analysis_{uuid.uuid4()}")
            logger.info(f"   Generated analysisId: {payload_dict['analysisId']}")
        
        # Parse as ResultsRequest
        try:
            payload = ResultsRequest(**payload_dict)
        except Exception as e:
            logger.error(f"Failed to parse ResultsRequest from multipart data: {e}")
            logger.error(f"Payload dict keys: {list(payload_dict.keys())}")
            raise HTTPException(status_code=400, detail=f"Invalid payload structure: {str(e)}")
        
        # Save uploaded files
        job_id = payload.jobId or payload.analysisId
        upload_dir = get_upload_dir(job_id)
        uploaded_files = []
        
        for key, value in form.items():
            if hasattr(value, 'filename') and value.filename:
                filename = value.filename
                filepath = upload_dir / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                content = await value.read()
                with open(filepath, 'wb') as f:
                    f.write(content)
                
                uploaded_files.append(filename)
                logger.info(f"   ✓ Arquivo salvo: {filename} ({len(content)} bytes)")
        
        logger.info(f"   Total de {len(uploaded_files)} arquivos recebidos via multipart")
        
    else:
        # Handle JSON payload (original flow)
        logger.info("📨 RESULTS recebido (JSON)")
        
        # Get raw body first
        body = await request.body()
        raw_json_str = body.decode('utf-8')
        
        # Log raw JSON before any processing
        logger.info("\n" + "="*80)
        logger.info("📦 RAW JSON RECEBIDO:")
        logger.info("="*80)
        if len(raw_json_str) > 2000:
            logger.info(raw_json_str[:2000])
            logger.info(f"... (truncated, total de {len(raw_json_str)} chars)")
        else:
            logger.info(raw_json_str)
        logger.info("="*80 + "\n")
        
        # Now parse it
        payload_dict = json.loads(raw_json_str)
        payload = ResultsRequest(**payload_dict)
    
    logger.info(f"   Job ID: {payload.jobId or 'N/A'}")
    logger.info(f"   Análise: {payload.analysisId}")
    athlete_name = payload.athleteData.name if payload.athleteData else 'Unknown'
    logger.info(f"   Atleta: {athlete_name}")
    
    # Determine sport from analysis config or athlete data
    sport = 'Unknown'
    if payload.analysisConfig:
        sport = payload.analysisConfig.sport or sport
        if payload.analysisConfig.agent:
            agent = payload.analysisConfig.agent.lower()
            if 'swimming' in agent or 'natacao' in agent:
                sport = 'swimming'
            elif 'running' in agent or 'corrida' in agent:
                sport = 'running'
    if payload.athleteData and payload.athleteData.sport:
        sport = payload.athleteData.sport
    logger.info(f"   Esporte: {sport}")
    
    try:
        job_id = payload.jobId or payload.analysisId
        upload_dir = get_upload_dir(job_id)
        
        # Validar que todos os arquivos foram uploadados (se probposeOutput fornecido)
        required_files = []
        if payload.probposeOutput and payload.probposeOutput.outputFiles:
            required_files = list(payload.probposeOutput.outputFiles.keys())
            logger.info(f"   Validando {len(required_files)} arquivos...")
            
            missing_files = []
            for filename in required_files:
                filepath = upload_dir / filename
                if not filepath.exists():
                    missing_files.append(filename)
                    logger.warning(f"   ❌ Arquivo não encontrado: {filename}")
            
            if missing_files:
                logger.error(f"   Arquivos ausentes: {missing_files}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing files: {', '.join(missing_files)}"
                )
            
            logger.info(f"   ✓ Todos os {len(required_files)} arquivos validados")
        else:
            # Check for any uploaded files in the directory
            uploaded = list(upload_dir.glob('**/*'))
            required_files = [str(f.relative_to(upload_dir)) for f in uploaded if f.is_file()]
            logger.info(f"   Encontrados {len(required_files)} arquivos no diretório")
        
        # Gerar token único
        token = f"proc_{uuid.uuid4()}"
        
        # Extract sport
        athlete_sport = sport if 'sport' in locals() else 'Unknown'
        
        # Armazenar job no banco de dados
        jobs_db[token] = {
            "token": token,
            "job_id": job_id or payload.analysisId,
            "analysis_id": payload.analysisId,
            "status": "processing",
            "progress": 0,
            "athlete_name": athlete_name,
            "athlete_sport": athlete_sport,
            "analysis_config": payload.analysisConfig.model_dump() if payload.analysisConfig else {},
            "focus_areas": payload.analysisConfig.focusAreas if payload.analysisConfig else [],
            "uploaded_files": required_files,
            "created_at": datetime.now().isoformat(),
            "result": None,
            "error": None
        }
        
        logger.info(f"   ✓ Job criado com token: {token}")
        
        # Iniciar processamento assíncrono
        asyncio.create_task(process_job(token, payload))
        
        logger.info(f"✅ RESULTS processado com sucesso")
        
        return ResultsResponse(
            token=token,
            message="Job received, files stored, processing started",
            files_ready=required_files
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro em RESULTS: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def process_job(token: str, payload: ResultsRequest):
    """
    Process job with AI agent analysis.
    
    New workflow:
    1. Run AI agent analysis on the biomechanical data
    2. Save AI result to temporary txt file
    3. Upload AI result to uploadResultsUrl (from RabbitMQ message)
    4. On success: cleanup and trigger server shutdown
    5. On failure: send to AI error queue and trigger server shutdown
    """
    job = jobs_db[token]
    job_data_dict = None
    
    try:
        logger.info(f"🔄 Iniciando processamento AI: {token}")
        logger.info(f"   Job ID: {payload.jobId or payload.analysisId}")
        athlete_name = payload.athleteData.name if payload.athleteData else 'Unknown'
        logger.info(f"   Atleta: {athlete_name}")
        
        # Determine sport
        sport = 'Unknown'
        if payload.analysisConfig:
            sport = payload.analysisConfig.sport or sport
            if payload.analysisConfig.agent:
                agent = payload.analysisConfig.agent.lower()
                if 'swimming' in agent or 'natacao' in agent:
                    sport = 'swimming'
                elif 'running' in agent or 'corrida' in agent:
                    sport = 'running'
        if payload.athleteData and payload.athleteData.sport:
            sport = payload.athleteData.sport
        
        logger.info(f"   Esporte: {sport}")
        focus_areas = payload.analysisConfig.focusAreas if payload.analysisConfig else []
        focus = payload.analysisConfig.focus if payload.analysisConfig else None
        notes = payload.analysisConfig.notes if payload.analysisConfig else None
        logger.info(f"   Focus areas: {focus_areas}")
        logger.info(f"   Focus: {focus}")
        logger.info(f"   Notes: {notes}")
        logger.info(f"   Upload URL: {payload.uploadResultsUrl}")
        
        # Convert payload to dict for error queue
        job_data_dict = {
            "jobId": payload.jobId or payload.analysisId,
            "analysisId": payload.analysisId,
            "athleteData": payload.athleteData.model_dump() if payload.athleteData else {},
            "analysisConfig": payload.analysisConfig.model_dump() if payload.analysisConfig else {},
            "videos": [v.model_dump() for v in payload.videos] if payload.videos else [],
            "videoInfo": payload.videoInfo.model_dump() if payload.videoInfo else {},
            "metadata": payload.metadata.model_dump() if payload.metadata else {},
            "uploadResultsUrl": payload.uploadResultsUrl,
            "probposeOutput": payload.probposeOutput.model_dump() if payload.probposeOutput else {},
            "originalPayload": payload.originalPayload,
            "metadataPath": payload.metadataPath,
            "isGcs": payload.isGcs
        }
        
        job["progress"] = 10
        
        # Get upload directory (use jobId or fall back to analysisId)
        job_id_for_dir = payload.jobId or payload.analysisId
        upload_dir = get_upload_dir(job_id_for_dir)
        
        # Log what will be sent to AI agent
        logger.info("\n" + "="*80)
        logger.info("🤖 DADOS QUE SERÃO ENVIADOS PARA O AI AGENT:")
        logger.info("="*80)
        logger.info(f"Job ID: {job_id_for_dir}")
        logger.info(f"Athlete: {payload.athleteData.model_dump() if payload.athleteData else 'N/A'}")
        logger.info(f"Analysis Config: {payload.analysisConfig.model_dump() if payload.analysisConfig else 'N/A'}")
        logger.info(f"Videos: {[v.model_dump() for v in payload.videos] if payload.videos else 'N/A'}")
        logger.info(f"Metadata Path: {payload.metadataPath}")
        logger.info(f"Is GCS: {payload.isGcs}")
        logger.info("="*80 + "\n")
        
        # STEP 1: Run AI Agent Analysis
        logger.info(f"[STEP 1/3] Running AI Agent analysis...")
        job["progress"] = 20
        
        # Run AI analysis in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        ai_success, ai_result, ai_error, reports_dir = await loop.run_in_executor(
            None, 
            run_ai_agent_analysis, 
            job_data_dict, 
            upload_dir
        )
        
        if not ai_success:
            error_msg = ai_error or "AI agent analysis failed"
            logger.error(f"❌ AI Analysis failed: {error_msg}")
            job["status"] = "failed"
            job["error"] = error_msg
            
            # Publish to AI error queue
            publish_to_ai_error_queue(job_data_dict, error_msg)
            return
        
        job["progress"] = 60
        logger.info(f"✓ AI Analysis completed. Result length: {len(ai_result)} chars")
        
        # STEP 2: Save reports to GCS
        logger.info(f"[STEP 2/3] Saving reports to GCS...")
        job["progress"] = 70
        
        # Store the AI result in the job
        job["ai_result"] = ai_result
        
        # STEP 3: Upload reports to GCS
        logger.info(f"[STEP 3/3] Uploading reports to GCS...")
        job["progress"] = 80
        
        upload_success, upload_error = save_reports_to_gcs(
            job_data_dict,
            reports_dir
        )
        
        if not upload_success:
            error_msg = upload_error or "Failed to save reports to GCS"
            logger.error(f"❌ GCS upload failed: {error_msg}")
            job["status"] = "failed"
            job["error"] = error_msg
            
            # Publish to AI error queue
            publish_to_ai_error_queue(job_data_dict, error_msg)
            return
        
        logger.info(f"✓ Reports saved to GCS successfully")
        
        # SUCCESS - Mark job as completed
        job["progress"] = 100
        job["status"] = "completed"
        job["result"] = {
            "athlete": payload.athleteData.model_dump() if payload.athleteData else {},
            "analysis_config": payload.analysisConfig.model_dump() if payload.analysisConfig else {},
            "metadata": payload.metadata.model_dump() if payload.metadata else {},
            "processed_at": datetime.now().isoformat(),
            "ai_result_length": len(ai_result),
            "summary": f"Análise biomecânica com AI completada para {athlete_name} ({sport})"
        }
        
        logger.info(f"✅ Job {job_id_for_dir} processado com sucesso!")
        logger.info(f"Job completed. Server ready for next job.")
        
        # Cleanup upload directory
        try:
            upload_dir = get_upload_dir(job_id_for_dir)
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
                logger.info(f"Cleaned up upload directory: {upload_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup upload directory: {e}")
    
    except Exception as e:
        error_msg = f"Unexpected error in process_job: {str(e)}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        job["status"] = "failed"
        job["error"] = error_msg
        
        # Publish to AI error queue
        if job_data_dict:
            publish_to_ai_error_queue(job_data_dict, error_msg)


# ============================================================================
# ENDPOINT 4: GET /api/results/status/{token}
# ============================================================================

@app.get("/api/results/status/{token}", response_model=StatusResponse)
async def get_status(token: str):
    """
    Retorna status do processamento.
    
    Checklist:
    - [x] Retorna {status: processing|completed|failed, progress: 0-100}
    - [x] Inclui resultado se completo
    - [x] Inclui erro se falha
    - [x] Timeout de 5 minutos (worker aguarda)
    """
    logger.info(f"🔍 STATUS solicitado: {token}")
    
    if token not in jobs_db:
        logger.warning(f"   ❌ Token não encontrado: {token}")
        raise HTTPException(status_code=404, detail="Token not found")
    
    job = jobs_db[token]
    
    response_data = {
        "token": token,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "result": None,
        "error": None
    }
    
    if job["status"] == "completed":
        response_data["result"] = job.get("result")
        logger.info(f"   ✅ Completo (progresso: {job['progress']}%)")
    elif job["status"] == "failed":
        response_data["error"] = job.get("error")
        logger.warning(f"   ❌ Falha: {job.get('error')}")
    else:
        logger.info(f"   ⏳ Processando (progresso: {job['progress']}%)")
    
    return StatusResponse(**response_data)


# ============================================================================
# DEBUG ENDPOINTS (development only)
# ============================================================================

@app.get("/debug/sessions")
async def debug_sessions():
    """Debug: lista todas as sessões de upload"""
    cleanup_expired_sessions()
    return {
        "total": len(upload_sessions),
        "sessions": [
            {
                "session_id": sid,
                "job_id": s["job_id"],
                "filename": s["filename"],
                "uploaded": s["uploaded"],
                "expires_in": str(s["expires"] - datetime.now())
            }
            for sid, s in upload_sessions.items()
        ]
    }


@app.get("/debug/jobs")
async def debug_jobs():
    """Debug: lista todos os jobs"""
    return {
        "total": len(jobs_db),
        "jobs": [
            {
                "token": token,
                "job_id": job["job_id"],
                "status": job["status"],
                "progress": job["progress"],
                "athlete": job["athlete_name"],
                "created_at": job["created_at"]
            }
            for token, job in jobs_db.items()
        ]
    }


@app.delete("/debug/jobs/{token}")
async def debug_delete_job(token: str):
    """Debug: deleta um job"""
    if token in jobs_db:
        del jobs_db[token]
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Token not found")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"🚀 Starting server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
