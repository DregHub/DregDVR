import os
import asyncio
import traceback
import base64
from datetime import datetime, timezone
from typing import Optional
import requests
from utils.file_utils import FileManager
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class CaptionsUploader:
    """Upload caption files to GitHub repository."""
    
    upload_queue_dir = DVR_Config.get_captions_upload_queue_dir()
    completed_uploads_dir = DVR_Config.get_captions_completed_uploads_dir()
    
    # GitHub configuration
    github_token = Account_Config.get_github_token()
    github_repo_owner = Account_Config.get_github_repo_owner()
    github_repo_name = Account_Config.get_github_repo_name()
    github_captions_path = Account_Config.get_github_captions_path()
    
    # GitHub API base URL
    GITHUB_API_BASE = "https://api.github.com"
    
    _upload_execution_lock = asyncio.Lock()
    _poll_interval = 300  # Poll every 5 minutes

    @classmethod
    def _get_github_headers(cls) -> dict:
        """Get standard headers for GitHub API requests."""
        return {
            "Authorization": f"token {cls.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

    @classmethod
    async def upload_caption_file(cls, file_path: str) -> bool:
        """
        Upload a single caption file to GitHub.
        
        Args:
            file_path: Path to the caption file to upload
            
        Returns:
            True if upload was successful, False otherwise
        """
        try:
            file_name = os.path.basename(file_path)
            
            # Read the file content
            try:
                def read_file():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return f.read()
                
                file_content = await asyncio.to_thread(read_file)
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Failed to read caption file {file_name}: {e}"
                )
                return False
            
            # Construct GitHub API URL for file upload
            base_path = cls.github_captions_path.rstrip('/') if cls.github_captions_path else ""
            if base_path:
                github_file_path = f"{base_path}/{file_name}"
            else:
                github_file_path = file_name
            api_url = f"{cls.GITHUB_API_BASE}/repos/{cls.github_repo_owner}/{cls.github_repo_name}/contents/{github_file_path}"
            
            # Encode file content as base64
            encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
            
            # Prepare the request payload
            payload = {
                "message": f"Add/update captions: {file_name}",
                "content": encoded_content,
                "branch": "main",
            }
            
            # Check if file already exists to get its SHA (needed for updates)
            try:
                def get_existing_file():
                    return requests.get(
                        api_url,
                        headers=cls._get_github_headers(),
                        timeout=30
                    )
                
                existing_response = await asyncio.to_thread(get_existing_file)
                
                if existing_response.status_code == 200:
                    # File exists, add SHA for update
                    payload["sha"] = existing_response.json().get("sha")
                    operation = "Updated"
                elif existing_response.status_code != 404:
                    # Unexpected error checking for existing file
                    LogManager.log_upload_captions(
                        f"Error checking if file exists on GitHub for {file_name}: {existing_response.status_code} - {existing_response.text}"
                    )
                    return False
                else:
                    operation = "Created"
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Error checking existing file on GitHub for {file_name}: {e}"
                )
                return False
            
            # Upload/update the file
            try:
                def upload_file():
                    return requests.put(
                        api_url,
                        json=payload,
                        headers=cls._get_github_headers(),
                        timeout=30
                    )
                
                response = await asyncio.to_thread(upload_file)
                
                if response.status_code not in [200, 201]:
                    LogManager.log_upload_captions(
                        f"Failed to upload {file_name} to GitHub: {response.status_code} - {response.text}"
                    )
                    return False
                
                LogManager.log_upload_captions(
                    f"{operation} caption file on GitHub: {github_file_path}"
                )
                return True
                
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Error uploading {file_name} to GitHub: {e}\n{traceback.format_exc()}"
                )
                return False
                
        except Exception as e:
            LogManager.log_upload_captions(
                f"Unhandled exception uploading caption file: {e}\n{traceback.format_exc()}"
            )
            return False

    @classmethod
    async def process_upload_queue(cls):
        """
        Process all caption files in the upload queue directory.
        Successfully uploaded files are moved to the completed uploads directory.
        """
        async with cls._upload_execution_lock:
            try:
                # Ensure directories exist
                os.makedirs(cls.upload_queue_dir, exist_ok=True)
                os.makedirs(cls.completed_uploads_dir, exist_ok=True)
                
                # Get list of files in upload queue
                try:
                    def list_files():
                        if not os.path.exists(cls.upload_queue_dir):
                            return []
                        return [f for f in os.listdir(cls.upload_queue_dir) 
                                if f.endswith('.srt') and os.path.isfile(os.path.join(cls.upload_queue_dir, f))]
                    
                    files_to_upload = await asyncio.to_thread(list_files)
                except Exception as e:
                    LogManager.log_upload_captions(
                        f"Error listing files in upload queue: {e}"
                    )
                    return
                
                if not files_to_upload:
                    return
                
                LogManager.log_upload_captions(
                    f"Processing {len(files_to_upload)} caption file(s) from upload queue"
                )
                
                # Process each file
                for file_name in files_to_upload:
                    file_path = os.path.join(cls.upload_queue_dir, file_name)
                    
                    try:
                        LogManager.log_upload_captions(
                            f"Uploading caption file: {file_name}"
                        )
                        
                        # Upload the file
                        success = await cls.upload_caption_file(file_path)
                        
                        if success:
                            # Move to completed directory
                            completed_path = os.path.join(cls.completed_uploads_dir, file_name)
                            try:
                                def move_file():
                                    FileManager.move_file(
                                        file_path,
                                        completed_path,
                                        LogManager.UPLOAD_CAPTIONS_LOG_FILE
                                    )
                                
                                await asyncio.to_thread(move_file)
                                LogManager.log_upload_captions(
                                    f"Successfully moved caption to completed uploads: {file_name}"
                                )
                            except Exception as e:
                                LogManager.log_upload_captions(
                                    f"Failed to move completed caption file {file_name}: {e}"
                                )
                        else:
                            LogManager.log_upload_captions(
                                f"Failed to upload caption file {file_name} - keeping in queue for retry"
                            )
                            
                    except Exception as e:
                        LogManager.log_upload_captions(
                            f"Error processing caption file {file_name}: {e}\n{traceback.format_exc()}"
                        )
            
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Unhandled exception in process_upload_queue: {e}\n{traceback.format_exc()}"
                )

    @classmethod
    async def upload_captions(cls):
        """
        Main coroutine for continuously monitoring and uploading captions.
        Runs indefinitely, polling the upload queue at regular intervals.
        """
        LogManager.log_upload_captions(
            f"Starting caption uploader - monitoring {cls.upload_queue_dir}"
        )
        
        while True:
            try:
                await cls.process_upload_queue()
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Unhandled exception in upload_captions loop: {e}\n{traceback.format_exc()}"
                )
            
            try:
                await asyncio.sleep(cls._poll_interval)
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Sleep interrupted in upload_captions loop: {e}\n{traceback.format_exc()}"
                )
