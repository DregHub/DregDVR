import asyncio
import os
import traceback
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from utils.playlist_manager import PlaylistManager
from utils.index_utils import IndexManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from dlp.helpers import DLPHelpers


class VideosPlaylistManager(PlaylistManager):
    """Videos-specific version of PlaylistManager with independent channel configuration."""
    
    # Initialize with youtube source instead of caption source
    _youtube_source = Account_Config.get_youtube_source()
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    channel_playlist = DVR_Config.get_channel_playlist(_youtube_source)
    channel = Account_Config.build_youtube_url(_youtube_source)
    videos_url = channel.rstrip("/") + "/videos"
    shorts_url = channel.rstrip("/") + "/shorts"
    channel_playlist_log_file = DVR_Config.get_channel_playlist_log_file(_youtube_source)
    
    _update_playlist_lock = asyncio.Lock()


class VideoDownloader:
    # Use the independent VideosPlaylistManager
    playlist = VideosPlaylistManager()
    DownloadTimeStampFormat = DVR_Config.get_download_timestamp_format()
    posted_downloadprefix = Account_Config.get_posted_downloadprefix()
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    Posted_UploadQueue_Dir = DVR_Config.get_posted_uploadqueue_dir()
    channel_playlist = VideosPlaylistManager.channel_playlist
    dlp_max_dlp_download_retries = DVR_Config.get_max_dlp_download_retries()
    dlp_max_title_chars = DVR_Config.get_max_title_filename_chars()
    maximum_threads = int(DVR_Config.get_maximum_threads())

    youtube_channel = VideosPlaylistManager.channel

    @classmethod
    def _get_thread_log_file(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Download_YouTube_Posted_Videos_Thread{thread_number}.log"
        return os.path.join(log_dir, log_filename)

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
    async def _process_url_threaded(cls, url: str, thread_number: int, live_status: str = None):
        """Process a single URL within a thread with thread-specific logging."""
        thread_log_file = cls._get_thread_log_file(thread_number)
        
        try:
            CurrentIndex = IndexManager.find_new_posted_index(thread_log_file)
            CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"
            ydl_opts = cls._build_ydl_opts(CurrentDownloadFile)

            try:
                # Use forwarded live_status if available, otherwise retrieve it
                if live_status is None:
                    LogManager.log_message(
                        f"Launching getinfo_with_retry for URL: {url} to determine live status before downloading.",
                        thread_log_file
                    )
                    info = await DLPHelpers.getinfo_with_retry(
                        ydl_opts, url, thread_log_file, desired_dicts=["live_status","is_live", "webpage_url"]
                    )
                    
                    # Handle case where info is None
                    if info is None:
                        LogManager.log_message(
                            f"{url} - Failed to retrieve video info, skipping download",
                            thread_log_file
                        )
                        return
                    
                    live_status = info.get("live_status") if isinstance(info, dict) else None
                else:
                    LogManager.log_message(
                        f"Using forwarded live_status: {live_status} for URL: {url}",
                        thread_log_file
                    )

                if live_status in ["is_live", "is_upcoming"]:
                    LogManager.log_message(
                        f"{url} is a live or upcoming stream live_status = {live_status} , skipping download.",
                        thread_log_file
                    )
                elif live_status in ["post_live", "was_live"]:
                    LogManager.log_message(
                        f"{url} is a past livestream live_status = {live_status} , skipping download because this is handled by the livestream downloader.",
                        thread_log_file
                    )
                elif live_status == "not_live":
                    LogManager.log_message(
                        f"{url} is a published video live_status = {live_status} , Proceding to download.",
                        thread_log_file
                    )
                    LogManager.log_message(
                        f"Launching download_with_retry for URL: {url} with ydl_opts: {ydl_opts}",
                        thread_log_file
                    )
                    try:
                        await DLPHelpers.download_with_retry(
                            ydl_opts, [url], thread_log_file
                        )
                        LogManager.log_message(
                            f"Posted Video {url} Downloaded Successfully",
                            thread_log_file
                        )
                        # Increment attempt counter and mark as downloaded
                        await cls._increment_video_download_attempts_thread_safe(url)
                        await cls._mark_downloaded_thread_safe(url)
                    except Exception as download_error:
                        LogManager.log_message(
                            f"Failed to download {url}: {download_error}",
                            thread_log_file
                        )
                        # Increment attempt counter on failure
                        await cls._increment_video_download_attempts_thread_safe(url)
                        raise  # Re-raise to be caught by outer exception handler
                else:
                    LogManager.log_message(
                        f"{url} Has an unknown live status type live_status = {live_status} skipping download",
                        thread_log_file
                    )

            except Exception as e:
                LogManager.log_message(
                    f"yt-dlp python API failed for {url}: {e}\n{traceback.format_exc()}",
                    thread_log_file
                )

            # Finishing per-url housekeeping
            LogManager.log_message(
                f"Finished processing the new video/short from channel {cls.youtube_channel}",
                thread_log_file
            )

        except Exception as e:
            LogManager.log_message(
                f"Thread {thread_number} error processing {url}: {e}\n{traceback.format_exc()}",
                thread_log_file
            )

    @classmethod
    def _process_url_threaded_wrapper(cls, url: str, thread_number: int, live_status: str = None):
        """Wrapper to handle async context within thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cls._process_url_threaded(url, thread_number, live_status))
            loop.close()
        except Exception as e:
            thread_log_file = cls._get_thread_log_file(thread_number)
            LogManager.log_message(
                f"Wrapper error in thread {thread_number}: {e}\n{traceback.format_exc()}",
                thread_log_file
            )

    @classmethod
    async def _load_urls(cls):
        # Otherwise load persistent JSON playlist and return not-yet-downloaded URLs with their status info
        try:
            playlist_data = await asyncio.to_thread(
                lambda: json.load(open(cls.channel_playlist, "r", encoding="utf-8"))
            )
        except Exception:
            playlist_data = []

        urls = [
            {
                "url": item.get("URL"),
                "live_status": item.get("Live_Status"),
                "was_live": item.get("Was_Live")
            }
            for item in playlist_data
            if item.get("URL") and not item.get("Downloaded_Video", False)
        ]

        if len(urls) > 1:
            LogManager.log_download_posted(
                f"Found {len(urls)} new videos/shorts to download."
            )
        elif len(urls) == 1:
            LogManager.log_download_posted("Found a new video/short to download.")

        return urls

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
        CurrentIndex = IndexManager.find_new_posted_index(
            LogManager.DOWNLOAD_POSTED_LOG_FILE
        )
        CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"
        ydl_opts = cls._build_ydl_opts(CurrentDownloadFile)

        try:
            # Use forwarded live_status if available, otherwise retrieve it
            if live_status is None:
                LogManager.log_download_posted(
                        f"Launching getinfo_with_retry for URL: {url} to determine live status before downloading."
                )
                info = await DLPHelpers.getinfo_with_retry(
                    ydl_opts, url, LogManager.DOWNLOAD_POSTED_LOG_FILE, desired_dicts=["live_status","is_live", "webpage_url"]
                )
                
                # Handle case where info is None
                if info is None:
                    LogManager.log_download_posted(
                        f"{url} - Failed to retrieve video info, skipping download"
                    )
                    return
                
                live_status = info.get("live_status") if isinstance(info, dict) else None
            else:
                LogManager.log_download_posted(
                    f"Using forwarded live_status: {live_status} for URL: {url}"
                )

            if live_status in ["is_live", "is_upcoming"]:
                LogManager.log_download_posted(
                    f"{url} is a live or upcoming stream live_status = {live_status} , skipping download."
                )
            elif live_status in ["post_live", "was_live"]:
                LogManager.log_download_posted(
                    f"{url} is a past livestream live_status = {live_status} , skipping download because this is handled by the livestream downloader."
                )
            elif live_status == "not_live":
                LogManager.log_download_posted(
                    f"{url} is a published video live_status = {live_status} , Proceding to download."
                )
                LogManager.log_download_posted(
                    f"Launching download_with_retry for URL: {url} with ydl_opts: {ydl_opts}"
                )
                try:
                    await DLPHelpers.download_with_retry(
                        ydl_opts, [url], LogManager.DOWNLOAD_POSTED_LOG_FILE
                    )
                    LogManager.log_download_posted(
                        f"Posted Video {url} Downloaded Successfully"
                    )
                    # Increment attempt counter and mark as downloaded
                    await cls.playlist.increment_video_download_attempts(url)
                    await cls.playlist.mark_as_downloaded(url)
                except Exception as download_error:
                    LogManager.log_download_posted(
                        f"Failed to download {url}: {download_error}"
                    )
                    # Increment attempt counter on failure
                    await cls.playlist.increment_video_download_attempts(url)
                    raise  # Re-raise to be caught by outer exception handler
            else:
                LogManager.log_download_posted(
                    f"{url} Has an unknown live status type live_status = {live_status} skipping download"
                )

        except Exception as e:
            LogManager.log_download_posted(
                f"yt-dlp python API failed for {url}: {e}\n{traceback.format_exc()}"
            )

        # Finishing per-url housekeeping
        LogManager.log_download_posted(
            f"Finished processing the new video/short from channel {cls.youtube_channel}"
        )

    @classmethod
    async def download_videos(cls):
        LogManager.log_download_posted(
            f"Starting Video & Shorts Downloader for {cls.youtube_channel}"
        )
        while True:
            try:

                urls = await cls._load_urls()
                url_count = len(urls)

                # Check if threading should be used
                if url_count > cls.maximum_threads:
                    LogManager.log_download_posted(
                        f"Found {url_count} videos to download. Using {cls.maximum_threads} threads to process concurrently."
                    )
                    
                    # Use ThreadPoolExecutor for concurrent downloads
                    with ThreadPoolExecutor(max_workers=cls.maximum_threads) as executor:
                        futures = []
                        
                        # Submit all URLs to thread pool
                        for index, url_info in enumerate(urls):
                            thread_number = (index % cls.maximum_threads) + 1
                            future = executor.submit(
                                cls._process_url_threaded_wrapper,
                                url_info["url"],
                                thread_number,
                                url_info["live_status"]
                            )
                            futures.append(future)
                        
                        # Wait for all threads to complete
                        for future in futures:
                            try:
                                future.result(timeout=1800)  # 30 minute timeout per URL
                            except Exception as e:
                                LogManager.log_download_posted(
                                    f"Thread execution error: {e}\n{traceback.format_exc()}"
                                )
                else:
                    # Use sequential processing for small batches
                    LogManager.log_download_posted(
                        f"Found {url_count} videos to download. Processing sequentially."
                    )
                    
                    for url_info in urls:
                        try:
                            # Wrap each URL processing with a timeout to prevent indefinite hangs
                            # Use 30 minutes per URL as safety limit to catch stalled downloads
                            await asyncio.wait_for(
                                cls._process_url(url_info["url"], url_info["live_status"]),
                                timeout=1800
                            )
                        except asyncio.TimeoutError:
                            LogManager.log_download_posted(
                                f"Timeout processing {url}: exceeded 1800s limit. Moving to next URL."
                            )
                        except Exception as e:
                            LogManager.log_download_posted(
                                f"Error processing {url}: {e}\n{traceback.format_exc()}"
                            )

                LogManager.log_download_posted(
                    f"Download cycle complete. Waiting 1 minute before checking {cls.youtube_channel} for new videos/shorts."
                )
                await asyncio.sleep(60)

            except Exception as e:
                LogManager.log_download_posted(
                    f"Exception in download_videos:  {e}\n{traceback.format_exc()}"
                )
                try:
                    await asyncio.sleep(30)
                except Exception:
                    LogManager.log_download_posted(
                        "Sleep interrupted in download_videos loop"
                    )


