
import os
import json
import logging
import traceback
from pathlib import Path
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def get_gcs_client():
    """Initializes and returns a GCS client."""
    try:
        # Check for key file in env
        key_data = os.getenv('GCS_KEY_FILE') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        
        if key_data:
            # Strip whitespace
            key_data = key_data.strip()
            
            # Check if it's JSON content or a file path
            if key_data.startswith('{'):
                # It's JSON content - parse and use directly
                logger.info("Initializing GCS client with JSON credentials from environment")
                credentials_info = json.loads(key_data)
                credentials = service_account.Credentials.from_service_account_info(credentials_info)
                return storage.Client(credentials=credentials)
            else:
                # It's a file path
                key_file_path = key_data
                
                # Resolve relative path if needed
                if not os.path.isabs(key_file_path):
                    # Try relative to project root (api folder parent)
                    project_root = Path(__file__).parent.parent
                    resolved_path = project_root / key_file_path
                    if resolved_path.exists():
                        key_file_path = str(resolved_path)
                
                if os.path.exists(key_file_path):
                    logger.info(f"Initializing GCS client with key file: {key_file_path}")
                    credentials = service_account.Credentials.from_service_account_file(key_file_path)
                    return storage.Client(credentials=credentials)
        
        logger.info("Initializing GCS client with default credentials")
        return storage.Client()
    except Exception as e:
        logger.error(f"Failed to initialize GCS client: {e}")
        raise

def parse_gcs_uri(uri: str):
    """Parses a GS URI (gs://bucket/path) into bucket and blob name."""
    parsed = urlparse(uri)
    if parsed.scheme != 'gs':
        raise ValueError(f"Invalid GCS URI: {uri}")
    return parsed.netloc, parsed.path.lstrip('/')

def download_from_gcs(uri: str, destination_path: Path):
    """Downloads a file from GCS to the specified path."""
    try:
        client = get_gcs_client()
        bucket_name, blob_name = parse_gcs_uri(uri)
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Ensure directory exists
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Downloading {uri} to {destination_path}")
        blob.download_to_filename(str(destination_path))
        logger.info(f"✓ Download completed: {destination_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to download {uri}: {e}")
        return False

def upload_to_gcs(source_path: Path, gcs_uri: str, content_type: str = None):
    """Uploads a file to GCS."""
    try:
        client = get_gcs_client()
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if content_type:
            blob.content_type = content_type
        
        logger.info(f"Uploading {source_path} to {gcs_uri}")
        blob.upload_from_filename(str(source_path))
        logger.info(f"✓ Upload completed: {gcs_uri}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to upload to {gcs_uri}: {e}")
        return False

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
        # Extract base GCS path from metadataPath (or construct from folderId if metadataPath missing)
        metadata_path = payload.get('metadataPath')
        
        # Fallback: if no metadataPath, look for other GCS indicators
        if not metadata_path:
             # Try to find a GCS path in the video set to reference (hacky but functional fallback)
             # Or check if folderId exists but we don't know the bucket without 'metadataPath' usually provided by the frontend.
             # However, comparison payload often has complex structure.
             return False, "No valid metadataPath found in payload"
             
        if not metadata_path.startswith('gs://'):
            return False, f"metadataPath is not a GCS URI: {metadata_path}"
        
        # Remove /metadata.json to get the base folder path
        base_path = metadata_path.rsplit('/metadata.json', 1)[0]
        
        # Use comparisonId for comparisons, or analysisId for generic jobs
        job_id = payload.get('comparisonId') or payload.get('analysisId') or 'unknown'
        
        reports_gcs_path = f"{base_path}/reports/{job_id}"
        
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
                        "relativePath": f"reports/{job_id}/{report_file.name}",
                        "mimeType": content_type or "application/octet-stream",
                        "createdAt": datetime.now().isoformat(),
                        "metadata": {
                            "jobId": job_id,
                            "type": "comparison" if payload.get('comparisonId') else "analysis",
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
                # Avoid duplicates: remove existing files with same relativePath
                new_relative_paths = {f['relativePath'] for f in uploaded_files}
                metadata['resultFiles'] = [f for f in metadata['resultFiles'] if f.get('relativePath') not in new_relative_paths]
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
