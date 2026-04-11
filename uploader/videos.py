import asyncio
import os
import re
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from weakref import WeakKeyDictionary
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from config.config_settings import DVR_Config
from utils.playlist_manager import PlaylistManager
from uploader.platform_internet_archive import upload_to_ia
from uploader.platform_youtube import upload_to_youtube
from uploader.platform_rumble import upload_to_rumble
from uploader.platform_bitchute import upload_to_bitchute
from uploader.platform_odysee import upload_to_odysee


class VideoUploader:
    Posted_UploadQueue_Dir = DVR_Config.get_posted_uploadqueue_dir()
    Posted_CompletedUploads_Dir = DVR_Config.get_posted_completeduploads_dir()
    Live_UploadQueue_Dir = DVR_Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = DVR_Config.get_live_completeduploads_dir()
    _upload_posted_lock = asyncio.Lock()
    _upload_live_lock = asyncio.Lock()
    
    # Threading configuration
    maximum_threads = int(DVR_Config.get_maximum_threads())
    _upload_file_lock = threading.Lock()
    _thread_number_map = {}
    _thread_number_map_lock = threading.Lock()
    _poll_interval = 300  # Poll every 5 minutes

    @classmethod
    def _get_worker_thread_number(cls) -> int:
        """Assign each worker thread a stable index from 1..maximum_threads."""
        thread_id = threading.get_ident()
        with cls._thread_number_map_lock:
            if thread_id in cls._thread_number_map:
                return cls._thread_number_map[thread_id]

            used = set(cls._thread_number_map.values())
            for num in range(1, cls.maximum_threads + 1):
                if num not in used:
                    cls._thread_number_map[thread_id] = num
                    return num

            # Fallback in case more threads are created than max (should not happen)
            fallback = (len(cls._thread_number_map) % cls.maximum_threads) + 1
            cls._thread_number_map[thread_id] = fallback
            return fallback

    @classmethod
    def _get_thread_log_file(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Videos_Thread_{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    def _get_thread_log_file_ia(cls, thread_number: int) -> str:
        """Generate Internet Archive platform thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Platform_IA_Thread_{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    def _get_thread_log_file_yt(cls, thread_number: int) -> str:
        """Generate YouTube platform thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Platform_YT_Thread_{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    def _get_thread_log_file_rumble(cls, thread_number: int) -> str:
        """Generate Rumble platform thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Platform_Rumble_Thread_{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    def _get_thread_log_file_bitchute(cls, thread_number: int) -> str:
        """Generate BitChute platform thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Platform_BitChute_Thread_{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    def _get_thread_log_file_odysee(cls, thread_number: int) -> str:
        """Generate Odysee platform thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Upload_Platform_Odysee_Thread_{thread_number}.log"
        return os.path.join(log_dir, log_filename)

    @classmethod
    def _get_slot_queue(cls):
        """Create or return a per-event-loop slot queue for maxthread slots."""
        if not hasattr(cls, "_slot_queues"):
            cls._slot_queues = WeakKeyDictionary()

        loop = asyncio.get_running_loop()
        if loop in cls._slot_queues:
            return cls._slot_queues[loop]

        slot_queue = asyncio.Queue(maxsize=cls.maximum_threads)
        for num in range(1, cls.maximum_threads + 1):
            slot_queue.put_nowait(num)

        cls._slot_queues[loop] = slot_queue
        return slot_queue

    @classmethod
    async def _process_playlist_entry_slot(cls, entry):
        """Run entry processing in a slot-bound context to preserve max thread-like concurrency."""
        slot_queue = cls._get_slot_queue()
        thread_number = await slot_queue.get()
        try:
            thread_log_file = cls._get_thread_log_file(thread_number)
            await cls._process_playlist_entry(entry, thread_log_file, thread_number)
        finally:
            await slot_queue.put(thread_number)

    @classmethod
    def _strip_timestamp_from_safe_filename(cls, safe_filename):
        if not safe_filename:
            return safe_filename

        # Matches ending timestamp pattern like:
        # ..._21-05-2025_03-08AM or ..._17-05-2025_08-23PM
        match = re.search(r"_(\d{2}-\d{2}-\d{4}_\d{2}-\d{2}(?:AM|PM))$", safe_filename)
        return safe_filename[: match.start()] if match else safe_filename

    @classmethod
    async def _move_completed_file(cls, filepath, live_status):
        if not filepath or not os.path.isfile(filepath):
            return False

        if live_status == "not_live":
            dest_dir = cls.Posted_CompletedUploads_Dir
        else:
            dest_dir = cls.Live_CompletedUploads_Dir

        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, os.path.basename(filepath))

        try:
            FileManager.move_file(filepath, dest_path, LogManager.UPLOAD_POSTED_LOG_FILE)
            return True
        except Exception as e:
            LogManager.log_upload_posted(f"Failed to move uploaded file {filepath} to completed uploads: {e}")
            return False

    @classmethod
    def _strip_leading_number_from_title(cls, title):
        if not title:
            return title
        # Remove leading digits and following space if present, e.g. "123 Title" -> "Title"
        return re.sub(r"^\s*\d+\s+", "", title)

    @classmethod
    async def _process_playlist_entry(cls, entry, log_file=None, thread_number=None):
        title = entry.get("Title", "")
        url = entry.get("URL")
        live_status = entry.get("Live_Status")
        filepath = entry.get("File_Path")
        uniqueid = entry.get("UniqueID")

        if not url:
            LogManager.log_message("Skipping playlist entry with missing URL", log_file)
            return
        if not filepath:
            LogManager.log_message(
                f"No file path found for URL {url}. Skipping upload for this entry.",
                log_file
            )
            return
        
        # Generate platform-specific log files if thread_number is provided
        ia_log_file = cls._get_thread_log_file_ia(thread_number) if thread_number else None
        yt_log_file = cls._get_thread_log_file_yt(thread_number) if thread_number else None
        rumble_log_file = cls._get_thread_log_file_rumble(thread_number) if thread_number else None
        bitchute_log_file = cls._get_thread_log_file_bitchute(thread_number) if thread_number else None
        odysee_log_file = cls._get_thread_log_file_odysee(thread_number) if thread_number else None
        
        # Determine and call each required upload platform only if not already marked uploaded
        upload_tasks = []
        if DVR_Config.upload_to_ia_enabled() and not entry.get("Uploaded_Video_IA", False):
            upload_tasks.append(("Uploaded_Video_IA", upload_to_ia, title, ia_log_file, uniqueid))
        if DVR_Config.upload_to_youtube_enabled() and not entry.get("Uploaded_Video_YT", False):
            upload_tasks.append(("Uploaded_Video_YT", upload_to_youtube, title, yt_log_file, uniqueid))
        if DVR_Config.upload_to_rumble_enabled() and not entry.get("Uploaded_Video_RM", False):
            upload_tasks.append(("Uploaded_Video_RM", upload_to_rumble, title, rumble_log_file, uniqueid))
        if DVR_Config.upload_to_bitchute_enabled() and not entry.get("Uploaded_Video_BC", False):
            upload_tasks.append(("Uploaded_Video_BC", upload_to_bitchute, title, bitchute_log_file, uniqueid))
        if DVR_Config.upload_to_odysee_enabled() and not entry.get("Uploaded_Video_OD", False):
            upload_tasks.append(("Uploaded_Video_OD", upload_to_odysee, title, odysee_log_file, uniqueid))

        for platform_field, upload_fn, upload_title, platform_log_file, uniqueid in upload_tasks:
            try:
                base_filename = os.path.splitext(os.path.basename(filepath))[0]
                LogManager.log_message(
                    f"Starting upload of {title} using {platform_field} helper function",
                    log_file
                )
                # Use platform-specific log file if available, otherwise use main log file
                upload_log_file = platform_log_file or log_file

                if platform_field == "Uploaded_Video_IA":
                    status, failure_reason = await upload_fn(filepath, base_filename, upload_title, upload_log_file, uniqueid=uniqueid)
                elif platform_field == "Uploaded_Video_YT":
                    status, failure_reason = await upload_fn(filepath, base_filename, upload_title, upload_log_file, uniqueid=uniqueid)
                elif platform_field == "Uploaded_Video_RM":
                    status = await asyncio.get_event_loop().run_in_executor(None, cls._upload_to_rumble_threaded, filepath, base_filename, upload_title, upload_log_file, uniqueid, thread_number)
                    failure_reason = None if status else "Threaded upload failed"
                elif platform_field == "Uploaded_Video_BC":
                    status = await asyncio.get_event_loop().run_in_executor(None, cls._upload_to_bitchute_threaded, filepath, base_filename, upload_title, upload_log_file, uniqueid, thread_number)
                    failure_reason = None if status else "Threaded upload failed"
                elif platform_field == "Uploaded_Video_OD":
                    status = await asyncio.get_event_loop().run_in_executor(None, cls._upload_to_odysee_threaded, filepath, base_filename, upload_title, upload_log_file, uniqueid, thread_number)
                    failure_reason = None if status else "Threaded upload failed"

                if status:
                    # Mirror the upload success in the in-memory entry so the workflow can act on it immediately.
                    entry[platform_field] = True
                else:
                    # Save the failure reason if provided
                    failure_field = f"Upload_Failure_Reason_{platform_field.split('_')[-1]}"
                    entry[failure_field] = failure_reason or "Unknown error"

                await PlaylistManager.mark_video_upload_status(url, platform_field, bool(status))
                LogManager.log_message(
                    f"{platform_field} Task Completed, Success: {bool(status)}",
                    log_file
                )
            except Exception as e:
                LogManager.log_message(
                    f"Exception uploading {url} to {platform_field}: {e}\n{traceback.format_exc()}",
                    log_file
                )
                await PlaylistManager.mark_video_upload_status(url, platform_field, False)

                # Save the exception as the failure reason
                failure_field = f"Upload_Failure_Reason_{platform_field.split('_')[-1]}"
                entry[failure_field] = str(e)

    @classmethod
    def _upload_to_ia_threaded(cls, filepath: str, filename: str, title: str, thread_log_file: str, uniqueid: str = None) -> bool:
        """Thread-safe wrapper for uploading to Internet Archive."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                upload_to_ia(filepath, filename, title, thread_log_file, uniqueid=uniqueid)
            )
        except Exception as e:
            LogManager.log_message(
                f"ERROR: Thread wrapper failed for IA upload: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False
        finally:
            loop.close()

    @classmethod
    def _upload_to_youtube_threaded(cls, filepath: str, filename: str, title: str, thread_log_file: str, uniqueid: str = None) -> bool:
        """Thread-safe wrapper for uploading to YouTube."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                upload_to_youtube(filepath, filename, title, thread_log_file, uniqueid=uniqueid)
            )
        except Exception as e:
            LogManager.log_message(
                f"ERROR: Thread wrapper failed for YouTube upload: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False
        finally:
            loop.close()

    @classmethod
    def _upload_to_rumble_threaded(cls, filepath: str, filename: str, title: str, thread_log_file: str, uniqueid: str = None, thread_number: int = None) -> bool:
        """Thread-safe wrapper for uploading to Rumble."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                upload_to_rumble(filepath, filename, title, thread_log_file, thread_number=thread_number, uniqueid=uniqueid)
            )
            # Extract boolean status from tuple (status, failure_reason)
            return result[0] if isinstance(result, tuple) else result
        except Exception as e:
            LogManager.log_message(
                f"ERROR: Thread wrapper failed for Rumble upload: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False
        finally:
            loop.close()

    @classmethod
    def _upload_to_bitchute_threaded(cls, filepath: str, filename: str, title: str, thread_log_file: str, uniqueid: str = None, thread_number: int = None) -> bool:
        """Thread-safe wrapper for uploading to BitChute."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                upload_to_bitchute(filepath, filename, title, thread_log_file, thread_number=thread_number, uniqueid=uniqueid)
            )
            # Extract boolean status from tuple (status, failure_reason)
            return result[0] if isinstance(result, tuple) else result
        except Exception as e:
            LogManager.log_message(
                f"ERROR: Thread wrapper failed for BitChute upload: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False
        finally:
            loop.close()

    @classmethod
    def _upload_to_odysee_threaded(cls, filepath: str, filename: str, title: str, thread_log_file: str, uniqueid: str = None, thread_number: int = None) -> bool:
        """Thread-safe wrapper for uploading to Odysee."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                upload_to_odysee(filepath, filename, title, thread_log_file, thread_number=thread_number, uniqueid=uniqueid)
            )
            # Extract boolean status from tuple (status, failure_reason)
            return result[0] if isinstance(result, tuple) else result
        except Exception as e:
            LogManager.log_message(
                f"ERROR: Thread wrapper failed for Odysee upload: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
            return False
        finally:
            loop.close()

    @classmethod
    def _process_playlist_entry_threaded(cls, entry: dict) -> None:
        """Thread-safe wrapper for processing a single playlist entry."""
        try:
            thread_number = cls._get_worker_thread_number()
            thread_log_file = cls._get_thread_log_file(thread_number)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cls._process_playlist_entry(entry, thread_log_file, thread_number))
        except Exception as e:
            LogManager.log_message(
                f"ERROR: Thread wrapper failed for playlist entry: {e}\n{traceback.format_exc()}",
                thread_log_file
            )
        finally:
            loop.close()

    @classmethod
    async def upload_posted_videos(cls):
        # Determine enabled upload hosts
        enabled_hosts = []
        if DVR_Config.upload_to_ia_enabled():
            enabled_hosts.append("Internet Archive")
        if DVR_Config.upload_to_youtube_enabled():
            enabled_hosts.append("YouTube")
        if DVR_Config.upload_to_rumble_enabled():
            enabled_hosts.append("Rumble")
        if DVR_Config.upload_to_bitchute_enabled():
            enabled_hosts.append("BitChute")
        if DVR_Config.upload_to_odysee_enabled():
            enabled_hosts.append("Odysee")
        
        hosts_str = ", ".join(enabled_hosts) if enabled_hosts else "None"
        LogManager.log_upload_posted(
            f"Monitoring playlist for posted uploads (Downloaded_Video=True, Uploaded_Video_All_Hosts=False). Enabled upload hosts: {hosts_str}"
        )

        while True:
            if cls._upload_posted_lock.locked():
                LogManager.log_upload_posted(
                    "upload_posted_videos is already running, skipping this call."
                )
                await asyncio.sleep(30)
                continue

            async with cls._upload_posted_lock:
                try:
                    entries = await PlaylistManager.get_pending_upload_entries(live_status_filter="not_live")
                    if not entries:
                        LogManager.log_upload_posted("No posted uploads pending in playlist.")
                    else:
                        LogManager.log_upload_posted(f"Found {len(entries)} posted upload(s) to process. Submitting batch to thread pool.")
                        # Use asyncio tasks with a slot queue to ensure a bounded number of parallel browser sessions
                        tasks = [
                            asyncio.create_task(cls._process_playlist_entry_slot(entry))
                            for entry in entries
                        ]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for result in results:
                            if isinstance(result, Exception):
                                LogManager.log_upload_posted(
                                    f"Exception in upload_posted_videos task: {result}\n{traceback.format_exc()}"
                                )

                except Exception as e:
                    LogManager.log_upload_posted(
                        f"Exception in upload_posted_videos: {e}\n{traceback.format_exc()}"
                    )

            await asyncio.sleep(cls._poll_interval)

    @classmethod
    async def upload_livestreams(cls):
        # Determine enabled upload hosts
        enabled_hosts = []
        if DVR_Config.upload_to_ia_enabled():
            enabled_hosts.append("Internet Archive")
        if DVR_Config.upload_to_youtube_enabled():
            enabled_hosts.append("YouTube")
        if DVR_Config.upload_to_rumble_enabled():
            enabled_hosts.append("Rumble")
        if DVR_Config.upload_to_bitchute_enabled():
            enabled_hosts.append("BitChute")
        if DVR_Config.upload_to_odysee_enabled():
            enabled_hosts.append("Odysee")
        
        hosts_str = ", ".join(enabled_hosts) if enabled_hosts else "None"
        LogManager.log_upload_posted(
            f"Monitoring playlist for livestream uploads (Downloaded_Video=True, Uploaded_Video_All_Hosts=False). Enabled upload hosts: {hosts_str}"
        )

        while True:
            if cls._upload_live_lock.locked():
                LogManager.log_upload_posted(
                    "upload_livestreams is already running, skipping this call."
                )
                await asyncio.sleep(30)
                continue

            async with cls._upload_live_lock:
                try:
                    entries = await PlaylistManager.get_pending_upload_entries(live_status_filter="live")
                    if not entries:
                        LogManager.log_upload_posted("No livestream uploads pending in playlist.")
                    else:
                        LogManager.log_upload_posted(f"Found {len(entries)} livestream upload(s) to process. Submitting batch to thread pool.")
                        # Use asyncio tasks with a slot queue to ensure a bounded number of parallel browser sessions
                        tasks = [
                            asyncio.create_task(cls._process_playlist_entry_slot(entry))
                            for entry in entries
                        ]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for result in results:
                            if isinstance(result, Exception):
                                LogManager.log_upload_posted(
                                    f"Exception in upload_livestreams task: {result}\n{traceback.format_exc()}"
                                )

                except Exception as e:
                    LogManager.log_upload_posted(
                        f"Exception in upload_livestreams: {e}\n{traceback.format_exc()}"
                    )

            await asyncio.sleep(cls._poll_interval)

