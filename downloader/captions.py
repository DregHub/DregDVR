import os
import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from utils.logging_utils import LogManager, LogLevels
from utils.thread_context import ThreadContext
from utils.file_utils import FileManager
from config.config_settings import DVR_Config
from config.config_settings import DVR_Config
from dlp.helpers import DLPHelpers
from dlp.events import DLPEvents
from yt_dlp_plugins.postprocessor import srt_fix as srt_fix_module
from utils.playlist_manager import PlaylistManager


class CaptionsDownloader:
    maximum_threads = None
    # When True, process caption downloads sequentially (no worker pool).
    use_sequential_downloads = True
    dlp_subtitle_use_srtfix = None
    caption_dir = None
    temp_caption_dir = None
    caption_channel_playlist = PlaylistManager.PLAYLIST_UPDATE_LOG_TABLE
    _download_execution_lock = asyncio.Lock()

    @classmethod
    async def _ensure_initialized(cls):
        """Initialize class variables from config on first use."""
        if cls.maximum_threads is not None:
            return  # Already initialized
        cls.maximum_threads = int(await DVR_Config.get_caption_download_max_threads())
        cls.dlp_subtitle_use_srtfix = await DVR_Config.get_dlp_subtitle_use_srtfix()
        cls.caption_dir = DVR_Config.get_captions_dir()
        cls.temp_caption_dir = DVR_Config.get_captions_upload_queue_dir()

    @classmethod
    def _get_thread_log_table(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_tablename = f"Download_YouTube_Captions_Thread{thread_number}.log"
        return os.path.join(log_dir, log_tablename)

    @classmethod
    async def _increment_caption_download_attempts_thread_safe(cls, video_id: str):
        """Thread-safe method to increment caption download attempts."""
        try:
            # Construct the URL from video_id
            url = f"https://www.youtube.com/watch?v={video_id}"

            # Get instance context
            instance_name = await PlaylistManager._get_instance_name()
            channel_source = await PlaylistManager._get_channel_source()

            if not instance_name or not channel_source:
                LogManager.log_download_captions(
                    f"Cannot increment caption download attempts: instance_name or channel_source is not set",
                    LogLevels.Error,
                )
                return

            # Get database and increment the attempts counter
            db = await PlaylistManager._get_db()

            # Get current entry to read current attempts
            entry = await db.get_channel_playlist_entry_by_url(
                instance_name, channel_source, url
            )

            if entry:
                current_attempts = entry.get("caption_download_attempts", 0)
                await db.update_channel_playlist_entry_field(
                    instance_name,
                    channel_source,
                    url,
                    "caption_download_attempts",
                    current_attempts + 1,
                )
        except Exception as e:
            LogManager.log_download_captions(
                f"Error incrementing caption download attempts for {video_id}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

    @classmethod
    async def _mark_Captions_Download_Started(cls, video_id: str):
        """Mark that captions processing has started for this video."""
        try:
            # Construct the URL from video_id
            url = f"https://www.youtube.com/watch?v={video_id}"

            # Get instance context
            instance_name = await PlaylistManager._get_instance_name()
            channel_source = await PlaylistManager._get_channel_source()

            if not instance_name or not channel_source:
                LogManager.log_download_captions(
                    f"Cannot mark captions as started: instance_name or channel_source is not set",
                    LogLevels.Error,
                )
                return

            # Get database and update the field
            db = await PlaylistManager._get_db()
            await db.update_channel_playlist_entry_field(
                instance_name, channel_source, url, "captions_download_started", 1
            )
        except Exception as e:
            LogManager.log_download_captions(
                f"Error marking captions as started for {video_id}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

    @classmethod
    async def _mark_caption_downloaded_thread_safe(cls, video_id: str):
        """Thread-safe method to mark captions as downloaded."""
        try:
            # Construct the URL from video_id
            url = f"https://www.youtube.com/watch?v={video_id}"
            await PlaylistManager.mark_caption_downloaded(url)
        except Exception as e:
            LogManager.log_download_captions(
                f"Error marking caption as downloaded for {video_id}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

    @classmethod
    def _process_caption_entry_threaded(cls, entry: dict, thread_number: int):
        """Process a single caption entry within a thread with thread-specific logging."""
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
                    loop, loop_name=f"captions_thread_{thread_number}"
                )
            except Exception as e:
                LogManager.log_download_captions(
                    f"Thread {thread_number} warning: could not register loop: {e}",
                    LogLevels.Warning,
                )

            loop.run_until_complete(
                cls._process_caption_entry_threaded_async(
                    entry, thread_log_table, thread_number
                )
            )

            # IMPORTANT: Do NOT call loop.close() here - it causes "Event loop is closed" errors
            # when aiosqlite worker threads try to report results on a closed loop.
            # Let the loop be garbage collected instead.

        except asyncio.CancelledError:
            LogManager.log_download_captions(
                f"Thread {thread_number} cancelled during caption processing",
                LogLevels.Warning,
            )
        except Exception as e:
            LogManager.log_download_captions(
                f"Thread {thread_number} error processing caption: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
        finally:
            # Clean up: set event loop to None and let garbage collector handle it
            if loop is not None:
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass  # Ignore errors during cleanup

    @classmethod
    async def _process_caption_entry_threaded_async(
        cls, entry: dict, thread_log_table: str, thread_number: int = None
    ):
        """Async method to process a caption entry with thread-specific logging."""
        try:
            video_id = entry.get("unique_id", "unknown")
            title = entry.get("title", "unknown_title")
            has_subtitles = bool(entry.get("has_captions"))
            downloaded_caption = bool(entry.get("downloaded_caption"))
            caption_download_attempts = int(entry.get("caption_download_attempts") or 0)

            if (
                has_subtitles
                and not downloaded_caption
                and caption_download_attempts < 10
            ):
                # Mark that captions processing has started for this entry
                await cls._mark_Captions_Download_Started(video_id)

                LogManager.log_download_captions(
                    f"Attempting to download captions for {video_id}",
                    LogLevels.Info,
                    thread_number=thread_number,
                )

                success = await cls.download_caption_for_video(
                    video_id, title, LogLevels.Info, thread_number=thread_number
                )

                LogManager.log_download_captions(
                    f"Finished attempting to download captions for {video_id}",
                    LogLevels.Info,
                )

                if success:
                    LogManager.log_download_captions(
                        f"Caption download successful for video ID {video_id}",
                        LogLevels.Info,
                    )
                    # Use thread-safe method to mark captions as downloaded
                    await cls._mark_caption_downloaded_thread_safe(video_id)
                else:
                    LogManager.log_download_captions(
                        f"Caption download failed for video ID {video_id}",
                        LogLevels.Warning,
                    )

                # Always increment attempts counter (on success or failure)
                await cls._increment_caption_download_attempts_thread_safe(video_id)

        except Exception as e:
            video_id = entry.get("unique_id", "unknown")
            LogManager.log_download_captions(
                f"Unhandled exception processing caption entry {video_id}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

    @classmethod
    async def fix_srt_async(cls, input_path, output_path=None):
        if output_path is None:
            raise ValueError(
                "output_path is required because process_srt expects two arguments"
            )

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, srt_fix_module.process_srt, input_path, output_path
            )
        except Exception as e:
            LogManager.log_download_captions(
                f"srtfix failed for {input_path} -> {output_path}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def download_captions(cls):
        await cls._ensure_initialized()
        LogManager.log_download_captions(f"Starting caption download", LogLevels.Info)
        os.makedirs(cls.caption_dir, exist_ok=True)
        os.makedirs(cls.temp_caption_dir, exist_ok=True)

        channel_url = DVR_Config.build_youtube_url(channel_source)
        cls.dlp_events = DLPEvents(
            channel_url,
            LogManager.log_download_captions,
        )

        while True:
            async with cls._download_execution_lock:
                try:
                    LogManager.log_download_captions(
                        "Starting caption download cycle...", LogLevels.Info
                    )

                    # Get instance context
                    from utils.playlist_manager import PlaylistManager

                    instance_name = await PlaylistManager._get_instance_name()
                    channel_source = await PlaylistManager._get_channel_source()

                    if not instance_name or not channel_source:
                        LogManager.log_download_captions(
                            "Cannot get instance context: instance_name or channel_source is not set",
                            LogLevels.Warning,
                        )
                        await asyncio.sleep(60)
                        continue

                    # Get download table name for current instance
                    db = await PlaylistManager._get_db()
                    download_table_name = db.get_playlist_download_table_name(
                        channel_source
                    )

                    # Get current download playlist
                    current_download_playlist = await db.get_current_download_playlist(
                        instance_name
                    )

                    if not current_download_playlist:
                        LogManager.log_download_captions(
                            "Cannot get current download playlist: current_download_playlist is not set",
                            LogLevels.Warning,
                        )
                        await asyncio.sleep(60)
                        continue

                    LogManager.log_download_captions(
                        f"Scanning download table: {download_table_name} for current playlist: {current_download_playlist} for caption entries",
                        LogLevels.Info,
                    )

                    # Query for entries that need caption processing
                    caption_entries = await db.get_channel_playlist_entries_where(
                        instance_name,
                        channel_source,
                        live_download_stage="Started",
                    )

                    # Filter results for caption processing
                    filtered_caption_entries = [
                        entry
                        for entry in caption_entries
                        if entry.get("has_captions", False)
                        and not entry.get("downloaded_caption", False)
                        and entry.get("captions_download_started") is None
                        and (entry.get("caption_download_attempts") or 0) < 10
                    ]

                    item_count = len(filtered_caption_entries)

                    if not filtered_caption_entries:
                        LogManager.log_download_captions(
                            "No livestream entries ready for caption download.",
                            LogLevels.Info,
                        )
                    else:
                        # Check if threading should be used
                        if item_count > cls.maximum_threads:
                            LogManager.log_download_captions(
                                f"Found {item_count} livestream captions to download. Using {cls.maximum_threads} threads to process concurrently.",
                                LogLevels.Info,
                            )

                            # Use ThreadPoolExecutor for concurrent caption downloads
                            with ThreadPoolExecutor(
                                max_workers=cls.maximum_threads
                            ) as executor:
                                futures = []

                                # Submit all caption items to thread pool
                                for index, entry in enumerate(filtered_caption_entries):
                                    thread_number = (index % cls.maximum_threads) + 1
                                    future = executor.submit(
                                        cls._process_caption_entry_threaded,
                                        entry,
                                        thread_number,
                                    )
                                    futures.append(future)

                                # Wait for all threads to complete
                                for future in futures:
                                    try:
                                        future.result(
                                            timeout=1800
                                        )  # 30 minute timeout per caption
                                    except Exception as e:
                                        LogManager.log_download_captions(
                                            f"Thread execution error: {e}\n{traceback.format_exc()}",
                                            LogLevels.Error,
                                        )
                        else:
                            # Use sequential processing for small batches
                            LogManager.log_download_captions(
                                f"Found {item_count} livestream captions to download. Processing sequentially.",
                                LogLevels.Info,
                            )

                            for entry in filtered_caption_entries:
                                try:
                                    await cls.process_video_entry(entry, semaphore=None)
                                except Exception as e:
                                    video_id = entry.get("unique_id", "unknown")
                                    LogManager.log_download_captions(
                                        f"Error processing video entry {video_id}: {e}\n{traceback.format_exc()}",
                                        LogLevels.Error,
                                    )

                except Exception as e:
                    LogManager.log_download_captions(
                        f"Unhandled exception in download_captions: {e}\n{traceback.format_exc()}",
                        LogLevels.Error,
                    )

            try:
                await asyncio.sleep(300)
            except Exception as e:
                LogManager.log_download_captions(
                    f"Sleep interrupted in download_captions loop: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )

    @classmethod
    async def process_video_entry(cls, entry, semaphore=None):
        async def _run():
            video_id = entry.get("unique_id", "unknown")
            title = entry.get("title", "unknown_title")
            has_subtitles = bool(entry.get("has_captions"))
            downloaded_caption = bool(entry.get("downloaded_caption"))
            caption_download_attempts = int(entry.get("caption_download_attempts") or 0)

            if (
                has_subtitles
                and not downloaded_caption
                and caption_download_attempts < 10
            ):
                # Mark that captions processing has started for this entry
                await cls._mark_Captions_Download_Started(video_id)

                LogManager.log_download_captions(
                    f"Attempting to download captions for {video_id}", LogLevels.Info
                )

                success = await cls.download_caption_for_video(
                    video_id, title, LogManager.table_download_captions
                )

                LogManager.log_download_captions(
                    f"Finished attempting to download captions for {video_id}",
                    LogLevels.Info,
                )
                if success:
                    LogManager.log_download_captions(
                        f"Caption download successful for video ID {video_id}",
                        LogLevels.Info,
                    )
                    # Use thread-safe method to mark captions as downloaded
                    await cls._mark_caption_downloaded_thread_safe(video_id)
                else:
                    LogManager.log_download_captions(
                        f"Caption download failed for video ID {video_id}",
                        LogLevels.Warning,
                    )

                # Always increment attempts counter (on success or failure)
                await cls._increment_caption_download_attempts_thread_safe(video_id)

        try:
            if semaphore:
                async with semaphore:
                    await _run()
            else:
                await _run()
        except Exception as e:
            video_id = entry.get("unique_id", "unknown")
            LogManager.log_download_captions(
                f"Unhandled exception processing video entry {video_id}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

    @classmethod
    async def download_caption_for_video(
        cls, video_id: str, title: str, log_table: str = None, thread_number: int = None
    ) -> bool:
        """Download caption for a video with optional custom log file for threaded operations."""
        if log_table is None:
            log_table = LogManager.table_download_captions

        try:
            suburl = f"https://www.youtube.com/watch?v={video_id}"
            safename = FileManager.gen_safe_filename(title)
            ydl_subtitle_opts = {
                "paths": {
                    "home": cls.temp_caption_dir,
                },
                "quiet": False,
                "subtitlesformat": "srt",
                "writeautomaticsub": True,
                "subtitleslangs": ["en"],
                "skip_download": True,
                "outtmpl": f"{safename}",
            }

            LogManager.log_download_captions(
                f"Downloading captions for video {video_id} (title: {title}) with safename: {safename}",
                LogLevels.Info,
                thread_number=thread_number,
            )

            # Call download_with_retry to download subtitles
            await DLPHelpers.download_with_retry(
                ydl_opts=ydl_subtitle_opts,
                url_or_list=suburl,
                timeout_enabled=True,
                log_table_name=log_table,
                log_warnings_and_above_only=False,
                thread_number=thread_number,
            )

            # For caption downloads with skip_download=True, construct the expected file path
            # yt-dlp appends the language code to the output template
            temp_sub_path = os.path.join(cls.temp_caption_dir, f"{safename}.en.srt")

            # Verify the file actually exists
            if not os.path.exists(temp_sub_path):
                LogManager.log_download_captions(
                    f"Downloaded subtitle file not found at expected path: {temp_sub_path}",
                    LogLevels.Error,
                    thread_number=thread_number,
                )
                return False

            LogManager.log_download_captions(
                f"Caption file located at: {temp_sub_path} (size: {os.path.getsize(temp_sub_path)} bytes)",
                LogLevels.Info,
                thread_number=thread_number,
            )

            processed_path = temp_sub_path

            try:
                if cls.dlp_subtitle_use_srtfix:
                    # Create a fixed path in temp directory for srtfix processing
                    fixed_path = os.path.join(cls.temp_caption_dir, f"{safename}.srt")
                    LogManager.log_download_captions(
                        f"Running srtfix: {temp_sub_path} -> {fixed_path}",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                    await cls.fix_srt_async(temp_sub_path, fixed_path)

                    if not os.path.exists(fixed_path):
                        LogManager.log_download_captions(
                            f"srtfix failed to create output file: {fixed_path}",
                            LogLevels.Error,
                            thread_number=thread_number,
                        )
                        return False

                    FileManager.delete_file(temp_sub_path, log_table)
                    processed_path = fixed_path
                    LogManager.log_download_captions(
                        f"srtfix completed successfully: {processed_path} (size: {os.path.getsize(processed_path)} bytes)",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                else:
                    LogManager.log_download_captions(
                        f"srtfix disabled - using downloaded subtitle: {processed_path}",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )

                # Move to caption directory
                final_caption_path = os.path.join(
                    cls.caption_dir, os.path.basename(processed_path)
                )
                LogManager.log_download_captions(
                    f"Moving caption from {processed_path} to captions directory: {final_caption_path}",
                    LogLevels.Info,
                    thread_number=thread_number,
                )
                FileManager.move_file(processed_path, final_caption_path, log_table)

                if not os.path.exists(final_caption_path):
                    LogManager.log_download_captions(
                        f"File move verification failed - file not found at destination: {final_caption_path}",
                        LogLevels.Error,
                        thread_number=thread_number,
                    )
                    return False

                LogManager.log_download_captions(
                    f"Successfully moved caption to captions directory: {final_caption_path} (size: {os.path.getsize(final_caption_path)} bytes)",
                    LogLevels.Info,
                    thread_number=thread_number,
                )
            except Exception as e:
                LogManager.log_download_captions(
                    f"Caption processing failed during file operations: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                    thread_number=thread_number,
                )
                return False

            LogManager.log_download_captions(
                f"Successfully downloaded and processed captions for video {video_id}",
                LogLevels.Info,
                thread_number=thread_number,
            )
            return True
        except asyncio.TimeoutError:
            LogManager.log_download_captions(
                f"Timeout while downloading captions for video {video_id}",
                LogLevels.Error,
                thread_number=thread_number,
            )
            return False
        except Exception as e:
            LogManager.log_download_captions(
                f"Error downloading captions for video {video_id}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number=thread_number,
            )
            return False
