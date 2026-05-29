
import os
import json
import logging
import threading
import time
import pika
import asyncio
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)

class RabbitMQConsumer:
    def __init__(self, queue_name: str, callback: Callable[[Dict[str, Any]], Any], shutdown_callback: Optional[Callable[[], None]] = None, error_queue: Optional[str] = None):
        self.queue_name = queue_name
        self.callback = callback
        self.shutdown_callback = shutdown_callback
        self.host = os.getenv('RABBITMQ_HOST')
        self.user = os.getenv('RABBITMQ_USERNAME', 'guest')
        self.password = os.getenv('RABBITMQ_PASSWORD', 'guest')
        # Use provided error_queue, or env var, or default
        self.error_queue = error_queue or os.getenv('RABBITMQ_AI_ERROR_QUEUE', 'vectosports_ai_analysis_failed')
        self.connection = None
        self.channel = None
        self.should_stop = False
        self.thread = None
        self.last_message_time = time.time()
        self.idle_timeout = 5 # Seconds to wait before shutting down if no messages
        self.is_processing = False

    def connect(self):
        credentials = pika.PlainCredentials(self.user, self.password)
        parameters = pika.ConnectionParameters(
            host=self.host,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300,
            socket_timeout=10
        )
        return pika.BlockingConnection(parameters)

    def publish_to_error_queue(self, payload: dict, error_reason: str):
        """Publishes a failed message to the error queue"""
        try:
            if not self.channel or self.channel.is_closed:
                logger.warning("Channel closed, cannot publish to error queue")
                return

            # Add error metadata
            payload_copy = payload.copy()
            payload_copy['error'] = error_reason
            payload_copy['failed_at'] = time.time()
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.error_queue,
                body=json.dumps(payload_copy),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                    content_type='application/json'
                )
            )
            logger.info(f"📤 Sent to error queue: {self.error_queue}")
        except Exception as e:
            logger.error(f"❌ Failed to publish to error queue: {e}")

    def run(self):
        """Main consumer loop - blocking"""
        self.last_message_time = time.time()
        
        while not self.should_stop:
            try:
                logger.info(f"🐰 connecting to RabbitMQ at {self.host}...")
                self.connection = self.connect()
                self.channel = self.connection.channel()
                
                # Declare main queue
                self.channel.queue_declare(queue=self.queue_name, durable=True)
                # Declare error queue to ensure it exists
                self.channel.queue_declare(queue=self.error_queue, durable=True)
                
                self.channel.basic_qos(prefetch_count=1)
                
                logger.info(f"🐰 Waiting for messages in {self.queue_name}")
                
                # consume returns an iterator. We use a short inactivity timeout to check for idle.
                for method_frame, properties, body in self.channel.consume(self.queue_name, inactivity_timeout=1):
                    if self.should_stop:
                        break
                        
                    if method_frame is None:
                        # Timeout occurred. Check for idle shutdown.
                        if self.shutdown_callback and (time.time() - self.last_message_time > self.idle_timeout):
                            logger.info(f"🐰 Idle for {self.idle_timeout}s. Requesting shutdown.")
                            self.shutdown_callback()
                            self.should_stop = True
                            break
                        continue
                    
                    # Message received
                    self.last_message_time = time.time()
                    
                    payload = {}
                    try:
                        logger.info(f"🐰 Message received: {len(body)} bytes")
                        payload = json.loads(body)
                        
                        # Retries
                        max_retries = 3
                        success = False
                        last_error = None
                        
                        self.is_processing = True # START PROCESSING
                        
                        for attempt in range(1, max_retries + 1):
                            try:
                                # Process message via callback
                                result = self.callback(payload)
                                
                                # If callback returns a Future (async task), wait for it.
                                if hasattr(result, 'result'): 
                                    result.result(timeout=600) # Wait for completion (10 min timeout?)
                                
                                success = True
                                break 
                                
                            except Exception as e:
                                last_error = e
                                logger.warning(f"⚠️ Attempt {attempt}/{max_retries} failed: {e}")
                                if attempt < max_retries:
                                    time.sleep(2 * attempt) # Backoff
                        
                        self.is_processing = False # END PROCESSING
                        
                        if success:
                            # Acknowledge success
                            self.channel.basic_ack(method_frame.delivery_tag)
                            logger.info("🐰 Message acknowledged (Processed)")
                        else:
                            # All retries failed
                            logger.error(f"❌ Message failed after {max_retries} attempts.")
                            self.publish_to_error_queue(payload, str(last_error))
                            # Ack to remove from main queue
                            self.channel.basic_ack(method_frame.delivery_tag)
                            logger.info("🐰 Message acknowledged (Sent to DLQ)")
                        
                        # Update last message time after processing
                        self.last_message_time = time.time()
                        
                    except Exception as e:
                        logger.error(f"❌ Critical error in consumer loop: {e}")
                        if payload:
                            self.publish_to_error_queue(payload, f"Critical Consumer Error: {e}")
                            self.channel.basic_ack(method_frame.delivery_tag)
                        else:
                            logger.error(f"Discarding unparseable message")
                            self.channel.basic_ack(method_frame.delivery_tag)
                            
                        self.last_message_time = time.time()
                
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ Connection Error: {e}. Retrying in 5s...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"RabbitMQ Unexpected Error: {e}. Retrying in 5s...")
                time.sleep(5)
            finally:
                if self.connection and not self.connection.is_closed:
                    try:
                        self.connection.close()
                    except:
                        pass

    def start(self):
        """Start consumer in a background thread"""
        self.should_stop = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        logger.info("RabbitMQ Consumer thread started")

    def stop(self):
        """Stop the consumer"""
        self.should_stop = True
        if self.thread:
            self.thread.join(timeout=5)
            logger.info("RabbitMQ Consumer thread stopped")
