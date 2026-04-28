import asyncio
import os
import traceback
import json
from concurrent.futures import ThreadPoolExecutor
from utils.logging_utils import LogManager, LogLevels
from utils.thread_context import ThreadContext
from utils.playlist_manager import PlaylistManager
from utils.index_utils import IndexManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from dlp.helpers import DLPHelpers


class VideoDownloader:
    playlist = PlaylistManager()
    DownloadTimeStampFormat = None  # Lazy loaded
    posted_downloadprefix = None  # Lazy loaded
    Posted_DownloadQueue_Dir = None  # Lazy loaded
    Posted_UploadQueue_Dir = None  # Lazy loaded
    dlp_max_dlp_download_retries = None  # Lazy loaded
    dlp_max_title_chars = None  # Lazy loaded
    maximum_threads = None  # Lazy loaded

    @classmethod
    async def _ensure_initialized(cls):
        """Ensure class variables are initialized with proper instance context."""
        if cls.DownloadTimeStampFormat is not None:
            return  # Already initialized

        # Get instance context
        instance_name = await cls.playlist._get_instance_name()

        if not instance_name:
            raise ValueError(
                "Cannot initialize: instance_name is not set"
            )

        cls.DownloadTimeStampFormat = await DVR_Config.get_download_timestamp_format()
        cls.posted_downloadprefix = await DVR_Config.get_posted_downloadprefix()
        cls.Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
        cls.Posted_UploadQueue_Dir = DVR_Config.get_posted_videos_dir()
        cls.dlp_max_dlp_download_retries = (
            await DVR_Config.get_dlp_max_download_retries()
        )
        cls.dlp_max_title_chars = (
            await DVR_Config.get_dlp_truncate_title_after_x_chars()
        )
        cls.maximum_threads = int(await DVR_Config.get_video_download_max_threads())

    @classmethod
    async def _mark_downloaded_thread_safe(cls, url: str):
        """Thread-safe method to mark a video as downloaded."""
        # Note: Lock is not needed here as this is already called from within an async context
        # and mark_as_downloaded handles its own thread-safe file operations
        try:
            await cls.playlist.mark_as_downloaded(url)
        except Exception as e:
            LogManager.log_download_posted(
                f"Error marking {url} as downloaded: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    async def _increment_video_download_attempts_thread_safe(cls, url: str):
        """Thread-safe method to increment video download attempts."""
        try:
            await cls.playlist.increment_video_download_attempts(url)
        except Exception as e:
            LogManager.log_download_posted(
                f"Error incrementing video download attempts for {url}: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    async def _process_url_threaded(
        cls, url: str, thread_number: int, live_status: str = None
    ):
        """Process a single URL within a thread with thread-specific logging."""
        try:
            # Get index from database instead of playlist file
            instance_name = await cls.playlist._get_instance_name()
            db = await cls.playlist._get_db()
            current_download_playlist = await db.get_current_download_playlist(
                instance_name
            )

            if not current_download_playlist:
                LogManager.log_download_posted(
                    "Cannot process URL: current_download_playlist is not set",
                    LogLevels.Error,
                    thread_number=thread_number,
                )
                return

            # Get count of downloaded videos from database
            downloaded_entries = await db.get_channel_playlist_entries_where(
                instance_name,
                current_download_playlist,
                downloaded_video=1,
            )
            CurrentIndex = await IndexManager.get_current_posted_index(instance_name)
            await IndexManager.increment_current_posted_index(instance_name)
            CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"
            ydl_opts = cls._build_ydl_opts(CurrentDownloadFile)

            try:
                # Use forwarded live_status if available, otherwise retrieve it
                if live_status is None:
                    LogManager.log_download_posted(
                        f"Launching getinfo_with_retry for URL: {url} to determine live status before downloading.",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                    info = await DLPHelpers.getinfo_with_retry(
                        ydl_opts=ydl_opts,
                        url_or_list=url,
                        log_table_name=LogManager.table_download_posted,
                        desired_dicts=["live_status", "is_live", "webpage_url"],
                        thread_number=thread_number,
                    )

                    # Handle case where info is None
                    if info is None:
                        LogManager.log_download_posted(
                            f"{url} - Failed to retrieve video info, skipping download",
                            LogLevels.Warning,
                            thread_number=thread_number,
                        )
                        return

                    live_status = (
                        info.get("live_status") if isinstance(info, dict) else None
                    )
                else:
                    LogManager.log_download_posted(
                        f"Using forwarded live_status: {live_status} for URL: {url}",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )

                if live_status in ["is_live", "is_upcoming"]:
                    LogManager.log_download_posted(
                        f"{url} is a live or upcoming stream live_status = {live_status} , skipping download.",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                elif live_status in ["post_live", "was_live"]:
                    LogManager.log_download_posted(
                        f"{url} is a past livestream live_status = {live_status} , skipping download because this is handled by the livestream downloader.",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                elif live_status == "not_live":
                    LogManager.log_download_posted(
                        f"{url} is a published video live_status = {live_status} , Proceding to download.",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                    LogManager.log_download_posted(
                        f"Launching download_with_retry for URL: {url} with ydl_opts: {ydl_opts}",
                        LogLevels.Info,
                        thread_number=thread_number,
                    )
                    try:
                        downloaded_file_path = await DLPHelpers.download_with_retry(
                            ydl_opts=ydl_opts,
                            url_or_list=[url],
                            timeout_enabled=True,
                            log_table_name=LogManager.table_download_posted,
                            log_warnings_and_above_only=False,
                            thread_number=thread_number,
                        )
                        LogManager.log_download_posted(
                            f"Posted Video {url} Downloaded Successfully",
                            LogLevels.Info,
                            thread_number=thread_number,
                        )

                        # Populate file_path column if download was successful
                        if downloaded_file_path:
                            await db.update_channel_playlist_entry_field(
                                instance_name,
                                current_download_playlist,
                                url,
                                "file_path",
                                downloaded_file_path
                            )
                            LogManager.log_download_posted(
                                f"Updated file_path for {url} to {downloaded_file_path}",
                                LogLevels.Info,
                                thread_number=thread_number,
                            )

                        # Increment attempt counter and mark as downloaded
                        await cls._increment_video_download_attempts_thread_safe(url)
                        await cls._mark_downloaded_thread_safe(url)
                    except Exception as download_error:
                        LogManager.log_download_posted(
                            f"Failed to download {url}: {download_error}",
                            LogLevels.Error,
                            thread_number=thread_number,
                        )
                        # Increment attempt counter on failure
                        await cls._increment_video_download_attempts_thread_safe(url)
                        raise  # Re-raise to be caught by outer exception handler
                else:
                    LogManager.log_download_posted(
                        f"{url} Has an unknown live status type live_status = {live_status} skipping download",
                        LogLevels.Warning,
                        thread_number=thread_number,
                    )

            except Exception as e:
                LogManager.log_download_posted(
                    f"yt-dlp python API failed for {url}: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                    thread_number=thread_number,
                )

            # Finishing per-url housekeeping
            LogManager.log_download_posted(
                f"Finished processing the new video/short",
                LogLevels.Info,
                thread_number=thread_number,
            )

        except Exception as e:
            LogManager.log_download_posted(
                f"Thread {thread_number} error processing {url}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number=thread_number,
            )

    @classmethod
    def _process_url_threaded_wrapper(
        cls, url: str, thread_number: int, live_status: str = None
    ):
        """Wrapper to handle async context within thread."""
        ThreadContext.set_thread_context(thread_number)
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Register with lifecycle manager if possible
            try:
                from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

                AsyncioLifecycleManager.register_loop(
                    loop, loop_name=f"videos_thread_{thread_number}"
                )
            except Exception as e:
                LogManager.log_download_posted(
                    f"Thread {thread_number} warning: could not register loop: {e}",
                    LogLevels.Warning,
                    thread_number=thread_number,
                )

            loop.run_until_complete(
                cls._process_url_threaded(url, thread_number, live_status)
            )

            # IMPORTANT: Do NOT call loop.close() here - it causes "Event loop is closed" errors
            # when aiosqlite worker threads try to report results on a closed loop.
            # Let the loop be garbage collected instead.

        except asyncio.CancelledError:
            LogManager.log_download_posted(
                f"Thread {thread_number} cancelled during video processing",
                LogLevels.Warning,
                thread_number=thread_number,
            )
        except Exception as e:
            LogManager.log_download_posted(
                f"Wrapper error in thread {thread_number}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number=thread_number,
            )
        finally:
            # Clean up: set event loop to None and let garbage collector handle it
            if loop is not None:
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass  # Ignore errors during cleanup

    @classmethod
    async def _load_urls(cls):
        try:
            # Get instance context
            instance_name = await cls.playlist._get_instance_name()

            if not instance_name:
                LogManager.log_download_posted(
                    "Cannot load URLs: instance_name is not set",
                    LogLevels.Error,
                )
                return []

            # Get database and current download playlist
            db = await cls.playlist._get_db()
            current_download_playlist = await db.get_current_download_playlist(
                instance_name
            )

            if not current_download_playlist:
                LogManager.log_download_posted(
                    "Cannot load URLs: current_download_playlist is not set",
                    LogLevels.Error,
                )
                return []

            LogManager.log_download_posted(
                f"Querying download table for current playlist: {current_download_playlist}",
                LogLevels.Info,
            )

            # Query for pending downloads with specific criteria:
            # live_status = 'not_live', downloaded_video = 0, video_download_attempts < 10
            all_entries = await db.get_channel_playlist_entries_where(
                instance_name,
                current_download_playlist,
                live_status='not_live',
                downloaded_video=0,
            )

            # Filter by video_download_attempts < 10
            filtered_entries = [
                entry for entry in all_entries
                if entry.get('video_download_attempts', 0) < 10
            ]

            # Convert to expected format
            filtered_urls = [
                {
                    "url": entry.get("webpage_url") or entry.get("url", ""),
                    "live_status": entry.get("live_status") or "",
                }
                for entry in filtered_entries
                if entry.get("url") or entry.get("webpage_url")
            ]
        except Exception:
            filtered_urls = []

        if len(filtered_urls) > 1:
            LogManager.log_download_posted(
                f"Found {len(filtered_urls)} new videos/shorts to download.",
                LogLevels.Info,
            )
        elif len(filtered_urls) == 1:
            LogManager.log_download_posted(
                "Found a new video/short to download.",
                LogLevels.Info,
            )

        return filtered_urls

    @classmethod
    def _build_ydl_opts(cls, out_template: str):
        return {
            "paths": {
                "temp": cls.Posted_DownloadQueue_Dir,
                "home": cls.Posted_UploadQueue_Dir,
            },
            "outtmpl": out_template,
            "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
            "restrictfilenames": True,
            "retries": int(cls.dlp_max_dlp_download_retries),
            "ignore_no_formats_error": True,
        }

    @classmethod
    async def _process_url(cls, url: str, live_status: str = None):
        # Get index from database instead of playlist file
        instance_name = await cls.playlist._get_instance_name()
        db = await cls.playlist._get_db()
        current_download_playlist = await db.get_current_download_playlist(
            instance_name
        )

        if not current_download_playlist:
            LogManager.log_download_posted(
                "Cannot process URL: current_download_playlist is not set",
                LogLevels.Error,
            )
            return

        # Get current index from database
        CurrentIndex = await IndexManager.get_current_posted_index(instance_name)
        await IndexManager.increment_current_posted_index(instance_name)

        CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"
        ydl_opts = cls._build_ydl_opts(CurrentDownloadFile)

        try:
            # Use forwarded live_status if available, otherwise retrieve it
            if live_status is None:
                LogManager.log_download_posted(
                    f"Launching getinfo_with_retry for URL: {url} to determine live status before downloading.",
                    LogLevels.Info,
                )
                info = await DLPHelpers.getinfo_with_retry(
                    ydl_opts=ydl_opts,
                    url_or_list=url,
                    log_table_name=LogManager.table_download_posted,
                    log_warnings_and_above_only=False,
                    desired_dicts=["live_status", "is_live", "webpage_url"],
                    thread_number=1,
                )

                # Handle case where info is None
                if info is None:
                    LogManager.log_download_posted(
                        f"{url} - Failed to retrieve video info, skipping download",
                        LogLevels.Warning,
                    )
                    return

                live_status = (
                    info.get("live_status") if isinstance(info, dict) else None
                )
            else:
                LogManager.log_download_posted(
                    f"Using forwarded live_status: {live_status} for URL: {url}",
                    LogLevels.Info,
                )

            if live_status in ["is_live", "is_upcoming"]:
                LogManager.log_download_posted(
                    f"{url} is a live or upcoming stream live_status = {live_status} , skipping download.",
                    LogLevels.Info,
                )
            elif live_status in ["post_live", "was_live"]:
                LogManager.log_download_posted(
                    f"{url} is a past livestream live_status = {live_status} , skipping download because this is handled by the livestream downloader.",
                    LogLevels.Info,
                )
            elif live_status == "not_live":
                LogManager.log_download_posted(
                    f"{url} is a published video live_status = {live_status} , Proceding to download.",
                    LogLevels.Info,
                )
                LogManager.log_download_posted(
                    f"Launching download_with_retry for URL: {url} with ydl_opts: {ydl_opts}",
                    LogLevels.Info,
                )
                try:
                    downloaded_file_path = await DLPHelpers.download_with_retry(
                        ydl_opts=ydl_opts,
                        url_or_list=[url],
                        timeout_enabled=True,
                        log_table_name=LogManager.table_download_posted,
                        log_warnings_and_above_only=False,
                        thread_number=1,
                    )
                    LogManager.log_download_posted(
                        f"Posted Video {url} Downloaded Successfully",
                        LogLevels.Info,
                    )

                    # Populate file_path column if download was successful
                    if downloaded_file_path:
                        await db.update_channel_playlist_entry_field(
                            instance_name,
                            current_download_playlist,
                            url,
                            "file_path",
                            downloaded_file_path
                        )
                        LogManager.log_download_posted(
                            f"Updated file_path for {url} to {downloaded_file_path}",
                            LogLevels.Info,
                        )

                    # Increment attempt counter and mark as downloaded
                    await cls.playlist.increment_video_download_attempts(url)
                    await cls.playlist.mark_as_downloaded(url)
                except Exception as download_error:
                    LogManager.log_download_posted(
                        f"Failed to download {url}: {download_error}",
                        LogLevels.Error,
                    )
                    # Increment attempt counter on failure
                    await cls.playlist.increment_video_download_attempts(url)
                    raise  # Re-raise to be caught by outer exception handler
            else:
                LogManager.log_download_posted(
                    f"{url} Has an unknown live status type live_status = {live_status} skipping download",
                    LogLevels.Warning,
                )

        except Exception as e:
            LogManager.log_download_posted(
                f"yt-dlp python API failed for {url}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

        # Finishing per-url housekeeping
        LogManager.log_download_posted(
            f"Finished processing the new video/short",
            LogLevels.Info,
        )

    @classmethod
    async def download_videos(cls):
        await cls._ensure_initialized()
        LogManager.log_download_posted(
            f"Starting Video & Shorts Downloader",
            LogLevels.Info,
        )
        while True:
            try:

                urls = await cls._load_urls()
                url_count = len(urls)

                # Check if threading should be used
                if url_count > cls.maximum_threads:
                    LogManager.log_download_posted(
                        f"Found {url_count} videos to download. Using {cls.maximum_threads} threads to process concurrently.",
                        LogLevels.Info,
                    )

                    # Use ThreadPoolExecutor for concurrent downloads
                    with ThreadPoolExecutor(
                        max_workers=cls.maximum_threads
                    ) as executor:
                        futures = []

                        # Submit all URLs to thread pool
                        for index, url_info in enumerate(urls):
                            thread_number = (index % cls.maximum_threads) + 1
                            future = executor.submit(
                                cls._process_url_threaded_wrapper,
                                url_info["url"],
                                thread_number,
                                url_info["live_status"],
                            )
                            futures.append(future)

                        # Wait for all threads to complete
                        for future in futures:
                            try:
                                future.result(timeout=1800)  # 30 minute timeout per URL
                            except Exception as e:
                                LogManager.log_download_posted(
                                    f"Thread execution error: {e}\n{traceback.format_exc()}",
                                    LogLevels.Error,
                                )
                else:
                    # Use sequential processing for small batches
                    LogManager.log_download_posted(
                        f"Found {url_count} videos to download. Processing sequentially.",
                        LogLevels.Info,
                    )

                    for url_info in urls:
                        try:
                            # Wrap each URL processing with a timeout to prevent indefinite hangs
                            # Use 30 minutes per URL as safety limit to catch stalled downloads
                            await asyncio.wait_for(
                                cls._process_url(
                                    url_info["url"], url_info["live_status"]
                                ),
                                timeout=1800,
                            )
                        except asyncio.TimeoutError:
                            LogManager.log_download_posted(
                                f"Timeout processing {url_info['url']}: exceeded 1800s limit. Moving to next URL.",
                                LogLevels.Warning,
                            )
                        except Exception as e:
                            LogManager.log_download_posted(
                                f"Error processing {url_info['url']}: {e}\n{traceback.format_exc()}",
                                LogLevels.Error,
                            )

                LogManager.log_download_posted(
                    f"Download cycle complete. Waiting 1 minute before checking for new videos/shorts.",
                    LogLevels.Info,
                )
                await asyncio.sleep(60)

            except Exception as e:
                LogManager.log_download_posted(
                    f"Exception in download_videos:  {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )
                try:
                    await asyncio.sleep(30)
                except Exception:
                    LogManager.log_download_posted(
                        "Sleep interrupted in download_videos loop",
                        LogLevels.Warning,
                    )
