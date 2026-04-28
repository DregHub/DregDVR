import os
import asyncio
import traceback
import base64
import threading
from concurrent.futures import ThreadPoolExecutor
import requests
from utils.logging_utils import LogManager, LogLevels
from utils.thread_context import ThreadContext
from config.config_settings import DVR_Config
from config.config_settings import DVR_Config


class CaptionsUploader:
    """Upload caption files to GitHub repository."""

    caption_dir = DVR_Config.get_captions_dir()

    # GitHub configuration (lazy loaded)
    github_token = None
    github_repo_owner = None
    github_repo_name = None
    github_captions_path = None

    # GitHub API base URL
    GITHUB_API_BASE = "https://api.github.com"

    # Threading configuration (lazy loaded)
    maximum_threads = None
    _upload_execution_lock = asyncio.Lock()
    _poll_interval = 300  # Poll every 5 minutes

    # Thread-safe lock for file operations
    _upload_file_lock = threading.Lock()

    @classmethod
    async def _ensure_initialized(cls):
        """Ensure class variables are initialized with proper instance context."""
        if cls.maximum_threads is not None:
            return  # Already initialized

        cls.maximum_threads = int(await DVR_Config.get_caption_upload_max_threads())
        cls.github_token = await DVR_Config.get_github_token()
        cls.github_repo_owner = await DVR_Config.get_github_repo_owner()
        cls.github_repo_name = await DVR_Config.get_github_repo_name()
        cls.github_captions_path = await DVR_Config.get_github_captions_path()

    @classmethod
    def _get_github_headers(cls) -> dict:
        """Get standard headers for GitHub API requests."""
        return {
            "Authorization": f"token {cls.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

    @classmethod
    def _get_thread_log_table(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_tablename = f"Upload_Captions_Thread{thread_number}.log"
        return os.path.join(log_dir, log_tablename)

    @classmethod
    async def _upload_caption_file_threaded(
        cls, file_path: str, thread_log_table: str, thread_number: int = None
    ) -> bool:
        """
        Upload a single caption file to GitHub with thread-specific logging.

        Args:
            file_path: Path to the caption file to upload
            thread_log_table: Path to the thread-specific log file
            thread_number: Thread number for logging purposes

        Returns:
            True if upload was successful, False otherwise
        """
        await cls._ensure_initialized()
        try:
            file_name = os.path.basename(file_path)
            LogManager.log_upload_captions(
                f"Starting upload of caption file: {file_name}",
                LogLevels.Info,
                thread_number=thread_number,
            )

            # Read the file content
            try:

                def read_file():
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read()

                file_content = await asyncio.to_thread(read_file)
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Failed to read caption file {file_name}: {e}",
                    LogLevels.Error,
                    thread_number=thread_number,
                )
                return False

            # Construct GitHub API URL for file upload
            base_path = (
                cls.github_captions_path.rstrip("/") if cls.github_captions_path else ""
            )
            if base_path:
                github_file_path = f"{base_path}/{file_name}"
            else:
                github_file_path = file_name
            api_url = f"{cls.GITHUB_API_BASE}/repos/{cls.github_repo_owner}/{cls.github_repo_name}/contents/{github_file_path}"

            # Encode file content as base64
            encoded_content = base64.b64encode(file_content.encode("utf-8")).decode(
                "utf-8"
            )

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
                        api_url, headers=cls._get_github_headers(), timeout=30
                    )

                existing_response = await asyncio.to_thread(get_existing_file)

                if existing_response.status_code == 200:
                    # File exists, add SHA for update
                    payload["sha"] = existing_response.json().get("sha")
                    operation = "Updated"
                elif existing_response.status_code != 404:
                    # Unexpected error checking for existing file
                    LogManager.log_upload_captions(
                        f"Error checking if file exists on GitHub for {file_name}: {existing_response.status_code} - {existing_response.text}",
                        LogLevels.Error,
                        thread_number=thread_number,
                    )
                    return False
                else:
                    operation = "Created"
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Error checking existing file on GitHub for {file_name}: {e}",
                    LogLevels.Error,
                    thread_number=thread_number,
                )
                return False

            # Upload/update the file
            try:

                def upload_file():
                    return requests.put(
                        api_url,
                        json=payload,
                        headers=cls._get_github_headers(),
                        timeout=30,
                    )

                response = await asyncio.to_thread(upload_file)

                if response.status_code not in [200, 201]:
                    LogManager.log_upload_captions(
                        f"Failed to upload {file_name} to GitHub: {response.status_code} - {response.text}",
                        LogLevels.Error,
                        thread_number=thread_number,
                    )
                    return False

                LogManager.log_upload_captions(
                    f"{operation} caption file on GitHub: {github_file_path}",
                    LogLevels.Info,
                    thread_number=thread_number,
                )
                return True

            except Exception as e:
                LogManager.log_upload_captions(
                    f"Error uploading {file_name} to GitHub: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                    thread_number=thread_number,
                )
                return False

        except Exception as e:
            LogManager.log_upload_captions(
                f"Unhandled exception uploading caption file: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number=thread_number,
            )
            return False

    @classmethod
    def _upload_caption_file_threaded_wrapper(
        cls, file_path: str, thread_number: int
    ) -> bool:
        """Wrapper to handle async context within thread."""
        ThreadContext.set_thread_context(thread_number)
        thread_log_table = cls._get_thread_log_table(thread_number)
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Register with lifecycle manager if possible
            try:
                from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

                AsyncioLifecycleManager.register_loop(
                    loop, loop_name=f"upload_captions_thread_{thread_number}"
                )
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Thread {thread_number} warning: could not register loop: {e}",
                    LogLevels.Warning,
                    thread_number=thread_number,
                )

            result = loop.run_until_complete(
                cls._upload_caption_file_threaded(
                    file_path, thread_log_table, thread_number
                )
            )

            # IMPORTANT: Do NOT call loop.close() here - it causes "Event loop is closed" errors
            # when aiosqlite worker threads try to report results on a closed loop.
            # Let the loop be garbage collected instead.

            return result
        except asyncio.CancelledError:
            LogManager.log_upload_captions(
                f"Thread {thread_number} cancelled during caption upload",
                LogLevels.Warning,
                thread_number=thread_number,
            )
            return False
        except Exception as e:
            LogManager.log_upload_captions(
                f"Wrapper error in thread {thread_number}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number=thread_number,
            )
            return False
        finally:
            # Clean up: set event loop to None and let garbage collector handle it
            if loop is not None:
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass  # Ignore errors during cleanup

    @classmethod
    async def upload_caption_file(cls, file_path: str) -> bool:
        """
        Upload a single caption file to GitHub.

        Args:
            file_path: Path to the caption file to upload

        Returns:
            True if upload was successful, False otherwise
        """
        return await cls._upload_caption_file_threaded(
            file_path, LogManager.table_upload_platform_gh, thread_number=None
        )

    @classmethod
    def _move_completed_caption_file(cls, file_path: str) -> bool:
        """Mark caption as uploaded in the playlist."""
        try:
            file_name = os.path.basename(file_path)
            # Extract video_id from the caption file name if possible
            # For now, we'll just log the completion
            # TODO: Implement proper tracking in PlaylistManager for uploaded captions
            LogManager.log_upload_captions(
                f"Caption file uploaded: {file_name}",
                LogLevels.Info,
            )
            return True
        except Exception as e:
            LogManager.log_upload_captions(
                f"Failed to mark caption file as uploaded {os.path.basename(file_path)}: {e}",
                LogLevels.Error,
            )
            return False

    @classmethod
    async def process_upload_queue(cls):
        """
        Process all caption files in the captions directory.
        Uses multithreading for concurrent uploads when multiple files are present.
        """
        await cls._ensure_initialized()
        async with cls._upload_execution_lock:
            # Check if GitHub uploads are enabled
            if not await DVR_Config.upload_to_github_enabled():
                return

            try:
                # Ensure captions directory exists
                os.makedirs(cls.caption_dir, exist_ok=True)

                # Get list of files in captions directory
                try:

                    def list_files():
                        with cls._upload_file_lock:
                            if not os.path.exists(cls.caption_dir):
                                return []
                            return [
                                f
                                for f in os.listdir(cls.caption_dir)
                                if f.endswith(".srt")
                                and os.path.isfile(os.path.join(cls.caption_dir, f))
                            ]

                    files_to_upload = await asyncio.to_thread(list_files)
                except Exception as e:
                    LogManager.log_upload_captions(
                        f"Error listing files in captions directory: {e}",
                        LogLevels.Error,
                    )
                    return

                if not files_to_upload:
                    return

                file_count = len(files_to_upload)
                file_paths = [os.path.join(cls.caption_dir, f) for f in files_to_upload]

                # Check if threading should be used
                if file_count > cls.maximum_threads:
                    LogManager.log_upload_captions(
                        f"Found {file_count} caption files. Using {cls.maximum_threads} threads to process concurrently.",
                        LogLevels.Info,
                    )

                    # Use ThreadPoolExecutor for concurrent uploads
                    with ThreadPoolExecutor(
                        max_workers=cls.maximum_threads
                    ) as executor:
                        futures = []

                        # Submit all files to thread pool
                        for index, file_path in enumerate(file_paths):
                            thread_number = (index % cls.maximum_threads) + 1
                            future = executor.submit(
                                cls._upload_caption_file_threaded_wrapper,
                                file_path,
                                thread_number,
                            )
                            futures.append((future, file_path))

                        # Process results as they complete
                        for future, file_path in futures:
                            try:
                                success = future.result(
                                    timeout=300
                                )  # 5 minute timeout per file

                                if success:
                                    # Move to completed directory
                                    cls._move_completed_caption_file(file_path)
                                    LogManager.log_upload_captions(
                                        f"Successfully moved caption to completed uploads: {os.path.basename(file_path)}",
                                        LogLevels.Info,
                                    )
                                else:
                                    LogManager.log_upload_captions(
                                        f"Failed to upload caption file {os.path.basename(file_path)} - keeping in queue for retry",
                                        LogLevels.Warning,
                                    )
                            except Exception as e:
                                LogManager.log_upload_captions(
                                    f"Thread execution error for {os.path.basename(file_path)}: {e}\n{traceback.format_exc()}",
                                    LogLevels.Error,
                                )
                else:
                    # Use sequential processing for small batches
                    LogManager.log_upload_captions(
                        f"Found {file_count} caption file(s). Processing sequentially.",
                        LogLevels.Info,
                    )

                    for file_path in file_paths:
                        try:
                            # Upload the file
                            success = await cls.upload_caption_file(file_path)

                            if success:
                                # Move to completed directory
                                cls._move_completed_caption_file(file_path)
                                LogManager.log_upload_captions(
                                    f"Successfully moved caption to completed uploads: {os.path.basename(file_path)}",
                                    LogLevels.Info,
                                )
                            else:
                                LogManager.log_upload_captions(
                                    f"Failed to upload caption file {os.path.basename(file_path)} - keeping in queue for retry",
                                    LogLevels.Warning,
                                )

                        except Exception as e:
                            LogManager.log_upload_captions(
                                f"Error processing caption file {os.path.basename(file_path)}: {e}\n{traceback.format_exc()}",
                                LogLevels.Error,
                            )

            except Exception as e:
                LogManager.log_upload_captions(
                    f"Unhandled exception in process_upload_queue: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )

    @classmethod
    async def upload_captions(cls):
        """
        Main coroutine for continuously monitoring and uploading captions.
        Runs indefinitely, polling the upload queue at regular intervals.
        """
        await cls._ensure_initialized()
        LogManager.log_upload_captions(
            f"Starting caption uploader - monitoring {cls.caption_dir}",
            LogLevels.Info,
        )

        while True:
            try:
                await cls.process_upload_queue()
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Unhandled exception in upload_captions loop: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )

            try:
                await asyncio.sleep(cls._poll_interval)
            except Exception as e:
                LogManager.log_upload_captions(
                    f"Sleep interrupted in upload_captions loop: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )
