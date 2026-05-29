
import json
import logging
import os
import shutil
import traceback
from pathlib import Path
from typing import Dict, Any
import requests

from api.gcs_utils import download_from_gcs, parse_gcs_uri
from ai_agents.vectosports.models.comparison import ComparisonPayload
from ai_agents.vectosports.workflows.comparison_workflow import comparison_workflow

logger = logging.getLogger("vectosports-comparison-handler")

def handle_comparison_message(payload: Dict[str, Any]):
    """
    RabbitMQ callback for comparison jobs.
    """
    logger.info("📩 Received comparison job message")
    
    try:
        # 1. Parse Payload
        # If payload is already a model, we're good (though consumer sends dict)
        if not isinstance(payload, ComparisonPayload):
            payload = ComparisonPayload(**payload)
        
        comparison_id = payload.comparisonId
        logger.info(f"🔄 Processing Comparison ID: {comparison_id}")
        
        # 2. Setup Workspace
        work_dir = Path(f"/tmp/comparison_{comparison_id}")
        work_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 3. Download Videos
            _download_videos(payload, work_dir)
            
            # 4. Run Workflow
            logger.info("🚀 Running Comparison Workflow...")
            result_markdown = None
            
            # Helper to run async workflow in sync context
            import asyncio
            try:
                # Reuse current loop if possible or create new
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                result_markdown = loop.run_until_complete(comparison_workflow.run(payload))
            except Exception as e:
                logger.error(f"Error running workflow: {e}")
                raise
            
            if not result_markdown:
                raise Exception("Workflow returned empty result")
                
            logger.info(f"✅ Workflow complete. Result length: {len(result_markdown)}")
            
            # 5. Save Result locally
            report_path = work_dir / "comparison_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(result_markdown)
                
            # 6. Upload Result
            # 6. Upload Result (Direct to GCS)
            from api.gcs_utils import save_reports_to_gcs
            
            # Ensure payload has necessary GCS info (metadataPath)
            # The payload might have it if it was passed from the frontend/server
            if not payload.metadataPath:
                 logger.warning("⚠️ No metadataPath provided for GCS upload. Attempting to upload to HTTP callback as fallback.")
                 if payload.uploadResultsUrl:
                    logger.info(f"📤 Uploading result to: {payload.uploadResultsUrl}")
                    with open(report_path, "rb") as f:
                        response = requests.put(
                            payload.uploadResultsUrl, 
                            data=f,
                            headers={"Content-Type": "text/markdown"}
                        )
                        if response.status_code not in range(200, 300):
                            logger.error(f"❌ Upload failed: {response.status_code} - {response.text}")
                        else:
                            logger.info("✅ Upload successful")
                 else:
                     logger.error("❌ No metadataPath AND no uploadResultsUrl. Result cannot be saved.")
            else:
                success, error = save_reports_to_gcs(payload.model_dump(), work_dir, final_status='readyForReview')
                if success:
                    logger.info("✅ Result saved to GCS and metadata updated with status 'readyForReview'.")
                else:
                    logger.error(f"❌ Failed to save to GCS: {error}")

        finally:
            # Cleanup
            if work_dir.exists():
                shutil.rmtree(work_dir)
                logger.info(f"🧹 Cleaned up {work_dir}")

    except Exception as e:
        logger.error(f"❌ Error processing comparison job: {e}")
        logger.error(traceback.format_exc())
        raise # Consumer will handle Nack/DLQ


def _download_videos(payload: ComparisonPayload, work_dir: Path):
    """
    Downloads all videos in the payload to the work directory 
    and updates the payload objects with local paths.
    """
    params = []
    
    # Collect all video objects to download
    for pair in payload.pairs:
        # Baseline videos
        for video in pair.baseline.videos:
            params.append((video, work_dir / "baseline"))
            
        # Current videos
        for video in pair.current.videos:
            params.append((video, work_dir / "current"))
            
    # Execute downloads
    for video, base_dir in params:
        base_dir.mkdir(parents=True, exist_ok=True)
        
        if video.downloadUrl.startswith("gs://"):
             _, blob_name = parse_gcs_uri(video.downloadUrl)
             filename = Path(blob_name).name
             dest_path = base_dir / filename
             
             logger.info(f"📥 Downloading {filename} from GCS...")
             if download_from_gcs(video.downloadUrl, dest_path):
                 video.localPath = str(dest_path.absolute())
             else:
                 logger.error(f"Failed to download {video.downloadUrl}")
        elif video.downloadUrl.startswith("http"):
            # Handle HTTP download if needed
            from urllib.parse import urlparse
            path = urlparse(video.downloadUrl).path
            name = Path(path).name
            if not name or '.' not in name:
                name = f"{video.videoId}.mp4"
            
            dest_path = base_dir / name
            logger.info(f"📥 Downloading {video.downloadUrl} from HTTP...")
            try:
                with requests.get(video.downloadUrl, stream=True) as r:
                    r.raise_for_status()
                    with open(dest_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                video.localPath = str(dest_path.absolute())
            except Exception as e:
                logger.error(f"Failed to download from HTTP: {e}")
