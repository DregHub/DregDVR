import contextlib
import json
import os
import asyncio
import traceback
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
from downloader.playlist import PlaylistManager


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
                    await CaptionsPlaylistManager.update_channel_playlist()
                    playlist_data = await JSONUtils.read_json(cls.caption_channel_playlist)

                    items = playlist_data if isinstance(playlist_data, list) else []
                    if not items:
                        LogManager.log_download_captions(
                            "No caption entries found in playlist."
                        )
                    else:
                        workers = []
                        rate_limit_event = asyncio.Event()

                        if cls.use_sequential_downloads:
                            LogManager.log_download_captions(
                                "Sequential download mode enabled - processing items one at a time."
                            )
                            for entry in items:
                                try:
                                    await cls.process_video_entry(
                                        entry,
                                        semaphore=None,
                                        playlist_data=playlist_data,
                                    )
                                except Exception as e:
                                    video_id = entry.get("UniqueID", "unknown")
                                    LogManager.log_download_captions(
                                        f"Error processing video entry {video_id}: {e}\n{traceback.format_exc()}"
                                    )

                            await JSONUtils.save_json(
                                playlist_data, cls.caption_channel_playlist
                            )

                        else:
                            queue = asyncio.Queue()
                            for it in items:
                                await queue.put(it)

                            num_workers = min(max(1, cls.maximum_threads), len(items))

                            for _ in range(num_workers):
                                await queue.put(None)

                            async def worker():
                                while True:
                                    item = await queue.get()
                                    try:
                                        if item is None:
                                            break
                                        await cls.process_video_entry(
                                            item,
                                            semaphore=None,
                                            playlist_data=playlist_data,
                                        )
                                    except Exception as e:
                                        video_id = item.get("UniqueID", "unknown") if item else "unknown"
                                        LogManager.log_download_captions(
                                            f"Error in worker processing item {video_id}: {e}\n{traceback.format_exc()}"
                                        )
                                    finally:
                                        queue.task_done()

                            workers = [
                                asyncio.create_task(worker())
                                for _ in range(num_workers)
                            ]

                            join_task = asyncio.create_task(queue.join())
                            waiter = asyncio.create_task(rate_limit_event.wait())
                            done, pending = await asyncio.wait(
                                {join_task, waiter}, return_when=asyncio.FIRST_COMPLETED
                            )

                            if rate_limit_event.is_set():
                                with contextlib.suppress(asyncio.QueueEmpty):
                                    while True:
                                        item = queue.get_nowait()
                                        queue.task_done()
                            for t in pending:
                                t.cancel()

                            for w in workers:
                                w.cancel()
                            await asyncio.gather(*workers, return_exceptions=True)

                            await JSONUtils.save_json(
                                playlist_data, cls.caption_channel_playlist
                            )

                            if rate_limit_event.is_set():
                                LogManager.log_download_captions(
                                    "Rate limit detected during parallel processing - sleeping for 2 hours."
                                )
                                await asyncio.sleep(2 * 3600)
                                continue
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

            try:
                await JSONUtils.save_json(playlist_data, cls.caption_channel_playlist)
            except Exception as e:
                LogManager.log_download_captions(
                    f"Error saving playlist data in download_captions: {e}\n{traceback.format_exc()}"
                )

            await asyncio.sleep(300)

    @classmethod
    async def process_video_entry(
        cls, entry, semaphore=None, playlist_data=None
    ):
        async def _run():
            video_id = entry.get("UniqueID", "unknown")
            title = entry.get("Title", "unknown_title")
            has_subtitles = bool(entry.get("Has_Captions"))
            downloaded_caption = bool(entry.get("Downloaded_Caption"))
            caption_download_attempts = int(entry.get("Caption_Download_Attempts") or 0)

            if has_subtitles and not downloaded_caption and caption_download_attempts < 10:
                LogManager.log_download_captions(f"Attempting to download captions for {video_id}")

                success = await cls.download_caption_for_video(video_id, title)

                LogManager.log_download_captions(
                    f"Finished attempting to download captions for {video_id}"
                )
                if success:
                    LogManager.log_download_captions(
                        f"Caption download successful for video ID {video_id}"
                    )
                else:
                    LogManager.log_download_captions(
                        f"Caption download failed for video ID {video_id}"
                    )

                entry["Downloaded_Caption"] = success
                entry["Caption_Download_Attempts"] = caption_download_attempts + 1

                # if caller passed the in-memory playlist, save it
                if playlist_data is not None:
                    await JSONUtils.save_json(playlist_data, cls.caption_channel_playlist)

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
    async def download_caption_for_video(cls, video_id: str, title: str) -> bool:
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
                f"Downloading captions for video {video_id} (title: {title}) with safename: {safename}"
            )
            
            # Call download_with_retry to download subtitles
            await DLPHelpers.download_with_retry(ydl_subtitle_opts, suburl, LogManager.DOWNLOAD_CAPTIONS_LOG_FILE)
            
            # For caption downloads with skip_download=True, construct the expected file path
            # yt-dlp appends the language code to the output template
            temp_sub_path = os.path.join(cls.temp_caption_dir, f"{safename}.en.srt")
            
            # Verify the file actually exists
            if not os.path.exists(temp_sub_path):
                LogManager.log_download_captions(
                    f"Downloaded subtitle file not found at expected path: {temp_sub_path}"
                )
                return False
            
            LogManager.log_download_captions(
                f"Caption file located at: {temp_sub_path} (size: {os.path.getsize(temp_sub_path)} bytes)"
            )
            
            processed_path = temp_sub_path

            try:
                if cls.dlp_subtitle_use_srtfix:
                    # Create a fixed path in temp directory for srtfix processing
                    fixed_path = os.path.join(cls.temp_caption_dir, f"{safename}.srt")
                    LogManager.log_download_captions(
                        f"Running srtfix: {temp_sub_path} -> {fixed_path}"
                    )
                    await cls.fix_srt_async(temp_sub_path, fixed_path)
                    
                    if not os.path.exists(fixed_path):
                        LogManager.log_download_captions(
                            f"srtfix failed to create output file: {fixed_path}"
                        )
                        return False
                    
                    FileManager.delete_file(
                        temp_sub_path, LogManager.DOWNLOAD_CAPTIONS_LOG_FILE
                    )
                    processed_path = fixed_path
                    LogManager.log_download_captions(
                        f"srtfix completed successfully: {processed_path} (size: {os.path.getsize(processed_path)} bytes)"
                    )
                else:
                    LogManager.log_download_captions(
                        f"srtfix disabled - using downloaded subtitle: {processed_path}"
                    )
                
                # Move to upload queue directory regardless of srtfix setting
                upload_queue_path = os.path.join(cls.get_captions_upload_queue_dir, os.path.basename(processed_path))
                LogManager.log_download_captions(
                    f"Moving caption from {processed_path} to upload queue: {upload_queue_path}"
                )
                FileManager.move_file(
                    processed_path, upload_queue_path, LogManager.DOWNLOAD_CAPTIONS_LOG_FILE
                )
                
                if not os.path.exists(upload_queue_path):
                    LogManager.log_download_captions(
                        f"File move verification failed - file not found at destination: {upload_queue_path}"
                    )
                    return False
                
                LogManager.log_download_captions(
                    f"Successfully moved caption to upload queue: {upload_queue_path} (size: {os.path.getsize(upload_queue_path)} bytes)"
                )
            except Exception as e:
                LogManager.log_download_captions(
                    f"Caption processing failed during file operations: {e}\n{traceback.format_exc()}"
                )
                return False

            LogManager.log_download_captions(
                f"Successfully downloaded and processed captions for video {video_id}"
            )
            return True
        except asyncio.TimeoutError:
            LogManager.log_download_captions(
                f"Timeout while downloading captions for video {video_id}"
            )
            return False
        except Exception as e:
            LogManager.log_download_captions(
                f"Error downloading captions for video {video_id}: {e}\n{traceback.format_exc()}"
            )
            return False