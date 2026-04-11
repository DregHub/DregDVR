import contextlib
import json
import os
import asyncio
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple
from datetime import datetime, timezone
from utils.json_utils import JSONUtils
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from yt_dlp import YoutubeDL
from dlp.helpers import DLPHelpers
from dlp.events import DLPEvents
from yt_dlp_plugins.postprocessor import srt_fix as srt_fix_module
from utils.playlist_manager import PlaylistManager


class CaptionsPlaylistManager(PlaylistManager):
    """Caption-specific version of PlaylistManager with independent channel configuration."""
    
    # Initialize with caption source instead of youtube source
    _caption_source = Account_Config.get_caption_source()
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    channel_playlist = DVR_Config.get_channel_playlist(_caption_source)
    channel = Account_Config.build_youtube_url(_caption_source)
    videos_url = channel.rstrip("/") + "/videos"
    shorts_url = channel.rstrip("/") + "/shorts"
    channel_playlist_log_file = DVR_Config.get_channel_playlist_log_file(_caption_source)
    
    _update_playlist_lock = asyncio.Lock()


class CaptionsDownloader:
    maximum_threads = int(DVR_Config.get_value("General", "maximum_threads"))
    # When True, process caption downloads sequentially (no worker pool).
    use_sequential_downloads = True
    dlp_subtitle_use_srtfix = DVR_Config.get_dlp_subtitle_use_srtfix()
    caption_dir = DVR_Config.get_live_captions_dir()
    temp_caption_dir = DVR_Config.get_temp_captions_dir()
    get_captions_upload_queue_dir = DVR_Config.get_captions_upload_queue_dir()
    get_captions_completed_uploads_dir = DVR_Config.get_captions_completed_uploads_dir()

    
    # Use the independent CaptionsPlaylistManager
    caption_channel_playlist = CaptionsPlaylistManager.channel_playlist

    _download_execution_lock = asyncio.Lock()
    
    @classmethod
    def _get_thread_log_file(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        log_filename = f"Download_YouTube_Captions_Thread{thread_number}.log"
        return os.path.join(log_dir, log_filename)
    
    @classmethod
    async def _increment_caption_download_attempts_thread_safe(cls, video_id: str):
        """Thread-safe method to increment caption download attempts."""
        try:
            # Construct the URL from video_id
            url = f"https://www.youtube.com/watch?v={video_id}"
            await CaptionsPlaylistManager.increment_caption_download_attempts(url)
        except Exception as e:
            LogManager.log_download_captions(
                f"Error incrementing caption download attempts for {video_id}: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    async def _mark_caption_downloaded_thread_safe(cls, video_id: str):
        """Thread-safe method to mark captions as downloaded."""
        try:
            # Construct the URL from video_id
            url = f"https://www.youtube.com/watch?v={video_id}"
            await CaptionsPlaylistManager.mark_caption_downloaded(url)
        except Exception as e:
            LogManager.log_download_captions(
                f"Error marking captions as downloaded for {video_id}: {e}\n{traceback.format_exc()}"
            )
    
    @classmethod
    def _process_caption_entry_threaded(cls, entry: dict, thread_number: int):
        """Process a single caption entry within a thread with thread-specific logging."""
        thread_log_file = cls._get_thread_log_file(thread_number)
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cls._process_caption_entry_threaded_async(entry, thread_log_file))
            loop.close()
        except Exception as e:
            LogManager.log_message(
                f"Thread {thread_number} error processing caption: {e}\n{traceback.format_exc()}",
                thread_log_file
            )

    @classmethod
    async def _process_caption_entry_threaded_async(cls, entry: dict, thread_log_file: str):
        """Async method to process a caption entry with thread-specific logging."""
        try:
            video_id = entry.get("UniqueID", "unknown")
            title = entry.get("Title", "unknown_title")
            has_subtitles = bool(entry.get("Has_Captions"))
            downloaded_caption = bool(entry.get("Downloaded_Caption"))
            caption_download_attempts = int(entry.get("Caption_Download_Attempts") or 0)

            if has_subtitles and not downloaded_caption and caption_download_attempts < 10:
                LogManager.log_message(
                    f"Attempting to download captions for {video_id}",
                    thread_log_file
                )

                success = await cls.download_caption_for_video(video_id, title, thread_log_file)

                LogManager.log_message(
                    f"Finished attempting to download captions for {video_id}",
                    thread_log_file
                )
                
                if success:
                    LogManager.log_message(
                        f"Caption download successful for video ID {video_id}",
                        thread_log_file
                    )
                    # Use thread-safe method to mark captions as downloaded
                    await cls._mark_caption_downloaded_thread_safe(video_id)
                else:
                    LogManager.log_message(
                        f"Caption download failed for video ID {video_id}",
                        thread_log_file
                    )
                
                # Always increment attempts counter (on success or failure)
                await cls._increment_caption_download_attempts_thread_safe(video_id)

        except Exception as e:
            video_id = entry.get("UniqueID", "unknown")
            LogManager.log_message(
                f"Unhandled exception processing caption entry {video_id}: {e}\n{traceback.format_exc()}",
                thread_log_file
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
                f"srtfix failed for {input_path} -> {output_path}: {e}\n{traceback.format_exc()}"
            )
            raise


    @classmethod
    async def download_captions(cls):
        LogManager.log_download_captions(
                f"Starting caption download for {Account_Config.extract_channel_handle(Account_Config.get_caption_source())}"
        )
        os.makedirs(cls.caption_dir, exist_ok=True)
        os.makedirs(cls.get_captions_completed_uploads_dir, exist_ok=True)
        os.makedirs(cls.get_captions_upload_queue_dir, exist_ok=True)
        os.makedirs(cls.temp_caption_dir, exist_ok=True)

        # Build full URL from channel source
        caption_source = Account_Config.get_caption_source()
        channel_url = Account_Config.build_youtube_url(caption_source)
        cls.dlp_events = DLPEvents(
                channel_url,
                LogManager.log_download_captions,
        )

        while True:
            async with cls._download_execution_lock:
                try: 
                    LogManager.log_download_captions(
                        "Starting caption download cycle..."
                    )
                    playlist_data = await JSONUtils.read_json(cls.caption_channel_playlist)

                    items = playlist_data if isinstance(playlist_data, list) else []
                    item_count = len(items)
                    
                    if not items:
                        LogManager.log_download_captions(
                            "No caption entries found in playlist."
                        )
                    else:
                        # Check if threading should be used
                        if item_count > cls.maximum_threads:
                            LogManager.log_download_captions(
                                f"Found {item_count} captions to download. Using {cls.maximum_threads} threads to process concurrently."
                            )
                            
                            # Use ThreadPoolExecutor for concurrent caption downloads
                            with ThreadPoolExecutor(max_workers=cls.maximum_threads) as executor:
                                futures = []
                                
                                # Submit all caption items to thread pool
                                for index, entry in enumerate(items):
                                    thread_number = (index % cls.maximum_threads) + 1
                                    future = executor.submit(
                                        cls._process_caption_entry_threaded,
                                        entry,
                                        thread_number
                                    )
                                    futures.append(future)
                                
                                # Wait for all threads to complete
                                for future in futures:
                                    try:
                                        future.result(timeout=1800)  # 30 minute timeout per caption
                                    except Exception as e:
                                        LogManager.log_download_captions(
                                            f"Thread execution error: {e}\n{traceback.format_exc()}"
                                        )
                        else:
                            # Use sequential processing for small batches
                            LogManager.log_download_captions(
                                f"Found {item_count} captions to download. Processing sequentially."
                            )
                            
                            for entry in items:
                                try:
                                    await cls.process_video_entry(
                                        entry,
                                        semaphore=None
                                    )
                                except Exception as e:
                                    video_id = entry.get("UniqueID", "unknown")
                                    LogManager.log_download_captions(
                                        f"Error processing video entry {video_id}: {e}\n{traceback.format_exc()}"
                                    )

                except Exception as e:
                    LogManager.log_download_captions(
                        f"Unhandled exception in download_captions: {e}\n{traceback.format_exc()}"
                    )

            try:
                await asyncio.sleep(300)
            except Exception as e:
                LogManager.log_download_captions(
                    f"Sleep interrupted in download_captions loop: {e}\n{traceback.format_exc()}"
                )

    @classmethod
    async def process_video_entry(cls, entry, semaphore=None):
        async def _run():
            video_id = entry.get("UniqueID", "unknown")
            title = entry.get("Title", "unknown_title")
            has_subtitles = bool(entry.get("Has_Captions"))
            downloaded_caption = bool(entry.get("Downloaded_Caption"))
            caption_download_attempts = int(entry.get("Caption_Download_Attempts") or 0)

            if has_subtitles and not downloaded_caption and caption_download_attempts < 10:
                LogManager.log_download_captions(f"Attempting to download captions for {video_id}")

                success = await cls.download_caption_for_video(video_id, title, LogManager.DOWNLOAD_CAPTIONS_LOG_FILE)

                LogManager.log_download_captions(
                    f"Finished attempting to download captions for {video_id}"
                )
                if success:
                    LogManager.log_download_captions(
                        f"Caption download successful for video ID {video_id}"
                    )
                    # Use thread-safe method to mark captions as downloaded
                    await cls._mark_caption_downloaded_thread_safe(video_id)
                else:
                    LogManager.log_download_captions(
                        f"Caption download failed for video ID {video_id}"
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
            video_id = entry.get("UniqueID", "unknown")
            LogManager.log_download_captions(
                f"Unhandled exception processing video entry {video_id}: {e}\n{traceback.format_exc()}"
            )
    @classmethod
    async def download_caption_for_video(cls, video_id: str, title: str, log_file: str = None) -> bool:
        """Download caption for a video with optional custom log file for threaded operations."""
        if log_file is None:
            log_file = LogManager.DOWNLOAD_CAPTIONS_LOG_FILE
            
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

            LogManager.log_message(
                f"Downloading captions for video {video_id} (title: {title}) with safename: {safename}",
                log_file
            )
            
            # Call download_with_retry to download subtitles
            await DLPHelpers.download_with_retry(
                ydl_opts=ydl_subtitle_opts,
                url_or_list=suburl,
                timeout_enabled=True,
                log_file_name=log_file,
                log_warnings_and_above_only=False,
            )
            
            # For caption downloads with skip_download=True, construct the expected file path
            # yt-dlp appends the language code to the output template
            temp_sub_path = os.path.join(cls.temp_caption_dir, f"{safename}.en.srt")
            
            # Verify the file actually exists
            if not os.path.exists(temp_sub_path):
                LogManager.log_message(
                    f"Downloaded subtitle file not found at expected path: {temp_sub_path}",
                    log_file
                )
                return False
            
            LogManager.log_message(
                f"Caption file located at: {temp_sub_path} (size: {os.path.getsize(temp_sub_path)} bytes)",
                log_file
            )
            
            processed_path = temp_sub_path

            try:
                if cls.dlp_subtitle_use_srtfix:
                    # Create a fixed path in temp directory for srtfix processing
                    fixed_path = os.path.join(cls.temp_caption_dir, f"{safename}.srt")
                    LogManager.log_message(
                        f"Running srtfix: {temp_sub_path} -> {fixed_path}",
                        log_file
                    )
                    await cls.fix_srt_async(temp_sub_path, fixed_path)
                    
                    if not os.path.exists(fixed_path):
                        LogManager.log_message(
                            f"srtfix failed to create output file: {fixed_path}",
                            log_file
                        )
                        return False
                    
                    FileManager.delete_file(
                        temp_sub_path, log_file
                    )
                    processed_path = fixed_path
                    LogManager.log_message(
                        f"srtfix completed successfully: {processed_path} (size: {os.path.getsize(processed_path)} bytes)",
                        log_file
                    )
                else:
                    LogManager.log_message(
                        f"srtfix disabled - using downloaded subtitle: {processed_path}",
                        log_file
                    )
                
                # Move to upload queue directory regardless of srtfix setting
                upload_queue_path = os.path.join(cls.get_captions_upload_queue_dir, os.path.basename(processed_path))
                LogManager.log_message(
                    f"Moving caption from {processed_path} to upload queue: {upload_queue_path}",
                    log_file
                )
                FileManager.move_file(
                    processed_path, upload_queue_path, log_file
                )
                
                if not os.path.exists(upload_queue_path):
                    LogManager.log_message(
                        f"File move verification failed - file not found at destination: {upload_queue_path}",
                        log_file
                    )
                    return False
                
                LogManager.log_message(
                    f"Successfully moved caption to upload queue: {upload_queue_path} (size: {os.path.getsize(upload_queue_path)} bytes)",
                    log_file
                )
            except Exception as e:
                LogManager.log_message(
                    f"Caption processing failed during file operations: {e}\n{traceback.format_exc()}",
                    log_file
                )
                return False

            LogManager.log_message(
                f"Successfully downloaded and processed captions for video {video_id}",
                log_file
            )
            return True
        except asyncio.TimeoutError:
            LogManager.log_message(
                f"Timeout while downloading captions for video {video_id}",
                log_file
            )
            return False
        except Exception as e:
            LogManager.log_message(
                f"Error downloading captions for video {video_id}: {e}\n{traceback.format_exc()}",
                log_file
            )
            return False