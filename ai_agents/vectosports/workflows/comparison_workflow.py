"""Comparison Workflow - Simplified single-agent approach for video analysis and reporting."""

import logging
import asyncio
import os
import re
from datetime import datetime
from typing import Dict, Any

from google.genai.types import Part, Content
from google import genai

from ai_agents.vectosports.models.comparison import ComparisonPayload

logger = logging.getLogger(__name__)

class ComparisonWorkflow:
    """
    Simplified workflow that uses a single powerful agent to:
    1. Analyze the videos directly
    2. Generate the complete Evolution Report
    
    This eliminates the "telephone game" problem where information
    was lost between multiple agents.
    """
    
    def __init__(self):
        # Import the unified agent
        from ai_agents.vectosports.analysts.unified_comparison_agent import unified_comparison_agent
        self.agent = unified_comparison_agent.agent
        
        # Initialize Gemini client
        self.api_key = os.environ.get("GOOGLE_API_KEY")

    async def _upload_video_to_gemini(self, file_path: str, mime_type: str = "video/mp4") -> str:
        """Uploads a video file to Gemini Files API and waits for it to be active."""
        client = genai.Client(api_key=self.api_key)
        logger.info(f"📤 Uploading {file_path} to Gemini...")
        
        myfile = client.files.upload(file=file_path)
        
        # Poll until active
        attempts = 0
        while myfile.state.name == "PROCESSING" and attempts < 30:
            await asyncio.sleep(2)
            myfile = client.files.get(name=myfile.name)
            attempts += 1
            
        if myfile.state.name == "ACTIVE":
            logger.info(f"✅ Video uploaded: {myfile.uri}")
            return myfile.uri
        else:
            raise Exception(f"Failed to process video {file_path}, state: {myfile.state.name}")

    async def run(self, payload: Dict[str, Any]) -> str:
        """
        Main entry point for the comparison workflow.
        Uses a single agent that receives all videos and generates the complete report.
        """
        logger.info("🎬 Starting Simplified Comparison Workflow (Single Agent)")
        
        # 1. Parse Payload
        try:
            if isinstance(payload, ComparisonPayload):
                data = payload
            else:
                data = ComparisonPayload(**payload)
        except Exception as e:
            logger.error(f"Failed to parse payload: {e}")
            raise

        athlete_name = data.athleteData.name if data.athleteData else 'Unknown'
        logger.info(f"Processing comparison for athlete: {athlete_name}")

        # 2. Construct Multimodal Prompt with Videos
        logger.info("🎥 Preparing Multimodal Prompt with Videos...")
        
        prompt_parts = []
        
        # Context Header - More detailed to help the single agent
        context_str = f"""
# CONTEXTO DA ANÁLISE

**Atleta**: {athlete_name}
**Esporte**: {data.globalConfig.agent}
**Data da Análise**: {data.timestamp or datetime.now().strftime('%d/%m/%Y')}
**Notas do Técnico**: {data.globalConfig.notes}

---

# INSTRUÇÕES

Você receberá pares de vídeos abaixo. Para cada par:
- **Vídeo ANTERIOR**: Gravado antes da intervenção técnica
- **Vídeo ATUAL**: Gravado após a intervenção técnica

Sua tarefa é:
1. OBSERVAR cada vídeo com atenção
2. IDENTIFICAR as diferenças técnicas entre ANTERIOR e ATUAL
3. GERAR um Relatório de Evolução Biomecânica completo

**ATENÇÃO**: Cada atleta é único. Baseie sua análise APENAS no que você observa nos vídeos deste atleta específico.

---

# VÍDEOS PARA ANÁLISE
"""
        prompt_parts.append(Part(text=context_str))

        # Track successful video uploads
        videos_uploaded = 0
        
        # Upload Videos and add to prompt
        for i, pair in enumerate(data.pairs):
            logger.info(f"Processing Pair {i+1} videos...")
            
            try:
                # Get first video from each set
                baseline_video = pair.baseline.videos[0] if pair.baseline.videos else None
                current_video = pair.current.videos[0] if pair.current.videos else None

                # Ensure local paths exist
                if not baseline_video or not baseline_video.localPath or not os.path.exists(baseline_video.localPath):
                    logger.warning(f"Baseline video path invalid: {baseline_video.localPath if baseline_video else 'No video'}")
                    continue
                if not current_video or not current_video.localPath or not os.path.exists(current_video.localPath):
                    logger.warning(f"Current video path invalid: {current_video.localPath if current_video else 'No video'}")
                    continue

                # Detect mime type
                import mimetypes
                def get_mime(path):
                    mime, _ = mimetypes.guess_type(path)
                    return mime or "video/mp4"

                b_mime = get_mime(baseline_video.localPath)
                c_mime = get_mime(current_video.localPath)

                # Upload to Gemini
                baseline_uri = await self._upload_video_to_gemini(baseline_video.localPath, mime_type=b_mime)
                current_uri = await self._upload_video_to_gemini(current_video.localPath, mime_type=c_mime)
                
                # Add pair context
                pair_header = f"""
## Par {i+1}: {pair.config.style} - {pair.config.cameraAngle}
**Foco da Análise**: {pair.config.focus}
"""
                prompt_parts.append(Part(text=pair_header))
                
                # Import types for metadata
                from google.genai import types

                # Add videos with clear labels and FPS metadata
                prompt_parts.append(Part(text="\n### 📹 Vídeo ANTERIOR (Antes da intervenção):"))
                prompt_parts.append(Part(
                    file_data={"file_uri": baseline_uri, "mime_type": b_mime},
                    video_metadata=types.VideoMetadata(fps=6)
                ))
                
                prompt_parts.append(Part(text="\n### 📹 Vídeo ATUAL (Após a intervenção):"))
                prompt_parts.append(Part(
                    file_data={"file_uri": current_uri, "mime_type": c_mime},
                    video_metadata=types.VideoMetadata(fps=6)
                ))
                
                videos_uploaded += 2
                logger.info(f"✅ Pair {i+1} videos added to prompt with 6 FPS metadata")
                
            except Exception as e:
                logger.error(f"Failed to upload videos for pair {i+1}: {e}")
                prompt_parts.append(Part(text=f"\n[Erro ao processar vídeos do Par {i+1}: {e}]\n"))

        if videos_uploaded == 0:
            raise Exception("No videos were successfully uploaded. Cannot proceed with analysis.")

        # Add final instruction
        prompt_parts.append(Part(text="""
---

# GERAR RELATÓRIO

Agora, com base nos vídeos acima, gere o Relatório de Evolução Biomecânica completo para este atleta.

Lembre-se:
- Observe CADA vídeo cuidadosamente
- Descreva o que você REALMENTE vê, não suposições genéricas
- Este atleta é único - sua análise deve ser personalizada
- Use a estrutura de relatório definida nas suas instruções
"""))

        # 3. Run Single Agent with Videos
        logger.info(f"🚀 Running Unified Agent with {videos_uploaded} videos...")
        
        # Prepare content object
        initial_input = Content(role="user", parts=prompt_parts)
        
        # Use ADK Runner for the single agent
        from google.adk.sessions import InMemorySessionService
        from google.adk.runners import Runner
        
        # Session IDs
        user_id = data.athleteId or "unknown_athlete"
        session_id = data.comparisonId or f"comp_{datetime.now().timestamp()}"
        
        # Initialize runner
        session_service = InMemorySessionService()
        runner = Runner(
            app_name="comparison_workflow",
            agent=self.agent,
            session_service=session_service
        )
        
        # Create session
        await session_service.create_session(
            user_id=user_id,
            session_id=session_id,
            app_name="comparison_workflow"
        )
        
        # Run and collect events
        events = []
        try:
            logger.info(f"Starting Runner execution for session {session_id}")
            for event in runner.run(
                user_id=user_id,
                session_id=session_id,
                new_message=initial_input
            ):
                events.append(event)
                logger.debug(f"Event received: {type(event).__name__}")
                
            # Extract result
            analysis_parts = []
            for event in events:
                # Try to get content from various attributes
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                analysis_parts.append(str(part.text))
                    elif hasattr(event.content, 'text') and event.content.text:
                        analysis_parts.append(str(event.content.text))
                elif hasattr(event, 'text') and event.text:
                    analysis_parts.append(str(event.text))
                elif hasattr(event, 'message') and event.message:
                    if isinstance(event.message, str):
                        analysis_parts.append(event.message)
            
            final_report = "\n".join(analysis_parts)
            
            # Extract content between tags if present
            match = re.search(r'<!--FINAL_REPORT_STRUCTURE_START-->(.*?)<!--FINAL_REPORT_STRUCTURE_END-->', final_report, re.DOTALL)
            if match:
                final_report = match.group(1).strip()
                logger.info("✅ Extracted structured report from tags")
            else:
                logger.warning("⚠️ Report structure tags not found. Using full output.")
            
            logger.info(f"✅ Comparison Workflow Completed (Report len: {len(final_report)})")
            
            if not final_report:
                logger.warning("Workflow returned empty report, checking events...")
                if events:
                    logger.info(f"Last event: {events[-1]}")
                raise Exception("Empty report generated")

            return final_report

        except Exception as e:
            logger.error(f"Error executing Runner: {e}")
            raise

comparison_workflow = ComparisonWorkflow()
