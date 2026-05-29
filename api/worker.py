
import os
import sys
import json
import uuid
import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import Dict, Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vectosports-worker")

# Global flag for worker shutdown
should_shutdown_worker = False

# Import utilities from the existing server logic (reusing as much as possible)
# Note: server.py must be importable without starting the FastAPI app automatically
try:
    from api.rabbitmq_consumer import RabbitMQConsumer
    from api.gcs_utils import download_from_gcs
    # We need to import these from server.py, but server.py has uvicorn.run in if __name__ == "__main__"
    from api.server import (
        process_job, 
        handle_rabbitmq_message as server_handle_message,
        trigger_server_shutdown,
        RABBITMQ_QUEUE,
        jobs_db
    )
    logger.info("✅ Successfully imported core logic from server.py")
except ImportError as e:
    logger.error(f"❌ Failed to import from server.py: {e}")
    sys.exit(1)

def shutdown_worker():
    """Callback for idle timeout to shutdown the worker"""
    global should_shutdown_worker
    logger.info("🛑 Worker is idle. Shutting down process...")
    should_shutdown_worker = True

async def main():
    global should_shutdown_worker
    logger.info("🚀 VectoSports AI Worker starting...")
    # Define queue names
    ANALYSIS_QUEUE = RABBITMQ_QUEUE
    COMPARISON_QUEUE = os.getenv('RABBITMQ_COMPARISON_QUEUE', 'vectosports_ai_comparison')
    COMPARISON_ERROR_QUEUE = os.getenv('RABBITMQ_COMPARISON_ERROR_QUEUE', 'vectosports_ai_comparison_failed')
    REVIEW_QUEUE = os.getenv('RABBITMQ_REVIEW_QUEUE', 'vectosports_ai_review')
    
    logger.info(f"Analysis Queue: {ANALYSIS_QUEUE}")
    logger.info(f"Comparison Queue: {COMPARISON_QUEUE}")
    logger.info(f"Review Queue: {REVIEW_QUEUE}")
    
    from api.comparison_handler import handle_comparison_message
    from api.consumers.review_consumer import handle_review_message

    # Start consumers with NO internal shutdown callback (we handle it centrally)
    consumer_analysis = RabbitMQConsumer(
        queue_name=ANALYSIS_QUEUE,
        callback=server_handle_message,
        shutdown_callback=None 
    )
    
    consumer_comparison = RabbitMQConsumer(
        queue_name=COMPARISON_QUEUE,
        callback=handle_comparison_message,
        shutdown_callback=None,
        error_queue=COMPARISON_ERROR_QUEUE
    )

    consumer_review = RabbitMQConsumer(
        queue_name=REVIEW_QUEUE,
        callback=handle_review_message,
        shutdown_callback=None
    )
    
    consumer_analysis.start()
    consumer_comparison.start()
    consumer_review.start()
    
    # Idle configuration
    IDLE_TIMEOUT = 5 # seconds

    
    try:
        while not should_shutdown_worker:
            await asyncio.sleep(1)
            
            # Check for global idle state
            now = time.time()
            analysis_idle = (now - consumer_analysis.last_message_time) > IDLE_TIMEOUT
            comparison_idle = (now - consumer_comparison.last_message_time) > IDLE_TIMEOUT
            review_idle = (now - consumer_review.last_message_time) > IDLE_TIMEOUT
            
            # Only shutdown if ALL are idle AND neither is processing
            if analysis_idle and comparison_idle and review_idle and \
               not consumer_analysis.is_processing and \
               not consumer_comparison.is_processing and \
               not consumer_review.is_processing:
                logger.info(f"🛑 All queues idle for {IDLE_TIMEOUT}s. Shutting down...")
                should_shutdown_worker = True
                
    except asyncio.CancelledError:
        logger.info("Main loop cancelled")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        consumer_analysis.stop()
        consumer_comparison.stop()
        consumer_review.stop()
        logger.info("Worker process finished")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
