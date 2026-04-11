import os
import asyncio
import traceback
import base64
import threading
from concurrent.futures import ThreadPoolExecutor
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
    
    # Threading configuration
    maximum_threads = int(DVR_Config.get_maximum_threads())
    _upload_execution_lock = asyncio.Lock()
    _poll_interval = 300  # Poll every 5 minutes
    
    # Thread-safe lock for file operations
    _upload_file_lock = threading.Lock()

    @classmethod
    def _get_github_headers(cls) -> dict:
        """Get standard headers for GitHub API requests."""
        return {
            "Authorization": f"token {cls.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

    @classmethod
    def _get_thread_log_file(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Captions_Thread{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    async def _upload_caption_file_threaded(cls, file_path: str, thread_log_file: str) -> bool:
        """
        Upload a single caption file to GitHub with thread-specific logging.
        
        Args:
            file_path: Path to the caption file to upload
            thread_log_file: Path to the thread-specific log file
            
        Returns:
            True if upload was successful, False otherwise
        """
        try:
            file_name = os.path.basename(file_path)
            LogManager.log_message(
                f"Starting upload of caption file: {file_name}",
                thread_log_file
            )
            
            # Read the file content
            try:
                def read_file():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return f.read()
                
                file_content = await asyncio.to_thread(read_file)
            except Exception as e:
                LogManager.log_message(
                    f"Failed to read caption file {file_name}: {e}",
                    thread_log_file
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
                    LogManager.log_message(
                        f"Error checking if file exists on GitHub for {file_name}: {existing_response.status_code} - {existing_response.text}",
                        thread_log_file
                    )
                    return False
                else:
                    operation = "Created"
            except Exception as e:
                LogManager.log_message(
                    f"Error checking existing file on GitHub for {file_name}: {e}",
                    thread_log_file
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
                    LogManager.log_message(
                        f"Failed to upload {file_name} to GitHub: {response.status_code} - {response.text}",
                        thread_log_file
                    )
                    return False
                
                LogManager.log_message(
                    f"{operation} caption file on GitHub: {github_file_path}",
                    thread_log_file
                )
                return True
                
            except Exception as e:
                LogManager.log_message(
                    f"Error uploading {file_name} to GitHub: {e}\n{traceback.format_exc()}",
                    thread_log_file
                )
                return False
                
        except Exception as e:
            LogManager.log_message(
                f"Unhandled exception uploading caption file: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False

    @classmethod
    def _upload_caption_file_threaded_wrapper(cls, file_path: str, thread_number: int) -> bool:
        """Wrapper to handle async context within thread."""
        thread_log_file = cls._get_thread_log_file(thread_number)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                cls._upload_caption_file_threaded(file_path, thread_log_file)
            )
            loop.close()
            return result
        except Exception as e:
            LogManager.log_message(
                f"Wrapper error in thread {thread_number}: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False

    @classmethod
    async def upload_caption_file(cls, file_path: str) -> bool:
        """
        Upload a single caption file to GitHub.
        
        Args:
            file_path: Path to the caption file to upload
            
        Returns:
            True if upload was successful, False otherwise
        """
        return await cls._upload_caption_file_threaded(file_path, LogManager.UPLOAD_CAPTIONS_LOG_FILE)

    @classmethod
    def _move_completed_caption_file(cls, file_path: str) -> bool:
        """Move a successfully uploaded caption file to the completed directory."""
        try:
            file_name = os.path.basename(file_path)
            with cls._upload_file_lock:
                completed_path = os.path.join(cls.completed_uploads_dir, file_name)
                os.makedirs(cls.completed_uploads_dir, exist_ok=True)
                FileManager.move_file(
                    file_path,
                    completed_path,
                    LogManager.UPLOAD_CAPTIONS_LOG_FILE
                )
            return True
        except Exception as e:
            LogManager.log_upload_captions(
                f"Failed to move completed caption file {os.path.basename(file_path)}: {e}"
            )
            return False

    @classmethod
    async def process_upload_queue(cls):
        """
        Process all caption files in the upload queue directory.
        Successfully uploaded files are moved to the completed uploads directory.
        Uses multithreading for concurrent uploads when multiple files are present.
        """
        async with cls._upload_execution_lock:
            try:
                # Ensure directories exist
                os.makedirs(cls.upload_queue_dir, exist_ok=True)
                os.makedirs(cls.completed_uploads_dir, exist_ok=True)
                
                # Get list of files in upload queue
                try:
                    def list_files():
                        with cls._upload_file_lock:
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
                
                file_count = len(files_to_upload)
                file_paths = [os.path.join(cls.upload_queue_dir, f) for f in files_to_upload]
                
                # Check if threading should be used
                if file_count > cls.maximum_threads:
                    LogManager.log_upload_captions(
                        f"Found {file_count} caption files. Using {cls.maximum_threads} threads to process concurrently."
                    )
                    
                    # Use ThreadPoolExecutor for concurrent uploads
                    with ThreadPoolExecutor(max_workers=cls.maximum_threads) as executor:
                        futures = []
                        
                        # Submit all files to thread pool
                        for index, file_path in enumerate(file_paths):
                            thread_number = (index % cls.maximum_threads) + 1
                            future = executor.submit(
                                cls._upload_caption_file_threaded_wrapper,
                                file_path,
                                thread_number
                            )
                            futures.append((future, file_path))
                        
                        # Process results as they complete
                        for future, file_path in futures:
                            try:
                                success = future.result(timeout=300)  # 5 minute timeout per file
                                
                                if success:
                                    # Move to completed directory
                                    cls._move_completed_caption_file(file_path)
                                    LogManager.log_upload_captions(
                                        f"Successfully moved caption to completed uploads: {os.path.basename(file_path)}"
                                    )
                                else:
                                    LogManager.log_upload_captions(
                                        f"Failed to upload caption file {os.path.basename(file_path)} - keeping in queue for retry"
                                    )
                            except Exception as e:
                                LogManager.log_upload_captions(
                                    f"Thread execution error for {os.path.basename(file_path)}: {e}\n{traceback.format_exc()}"
                                )
                else:
                    # Use sequential processing for small batches
                    LogManager.log_upload_captions(
                        f"Found {file_count} caption file(s). Processing sequentially."
                    )
                    
                    for file_path in file_paths:
                        try:
                            # Upload the file
                            success = await cls.upload_caption_file(file_path)
                            
                            if success:
                                # Move to completed directory
                                cls._move_completed_caption_file(file_path)
                                LogManager.log_upload_captions(
                                    f"Successfully moved caption to completed uploads: {os.path.basename(file_path)}"
                                )
                            else:
                                LogManager.log_upload_captions(
                                    f"Failed to upload caption file {os.path.basename(file_path)} - keeping in queue for retry"
                                )
                                
                        except Exception as e:
                            LogManager.log_upload_captions(
                                f"Error processing caption file {os.path.basename(file_path)}: {e}\n{traceback.format_exc()}"
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
