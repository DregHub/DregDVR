import contextlib
import json
import os
import asyncio
import traceback
from typing import Tuple
from utils.json_utils import JSONUtils
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError
from utils.dlp_utils import DLPEvents
from yt_dlp_plugins.postprocessor import srt_fix as srt_fix_module


class RateLimitError(Exception):
    """Raised when yt-dlp indicates the account is rate-limited by YouTube."""


class CaptionsDownloader:
    maximum_threads = int(DVR_Config.get_value("General", "maximum_threads"))
    # When True, process caption downloads sequentially (no worker pool).
    use_sequential_downloads = True
    dlp_subtitle_use_srtfix = DVR_Config.get_dlp_subtitle_use_srtfix()
    caption_dir = DVR_Config.get_live_captions_dir()
    temp_caption_dir = DVR_Config.get_temp_captions_dir()
    publish_caption_dir = DVR_Config.get_published_captions_dir()
    index_dir = DVR_Config.get_caption_index_dir()

    video_json = os.path.join(index_dir, "_Channel_Videos.json")
    shorts_json = os.path.join(index_dir, "_Channel_Shorts.json")
    caption_index_file = os.path.join(index_dir, "_Caption_Index.json")

    _download_execution_lock = asyncio.Lock()
    _monitor_execution_lock = asyncio.Lock()

    video_playlist = f"{Account_Config.get_caption_handle()}/videos"
    shorts_playlist = f"{Account_Config.get_caption_handle()}/shorts"

    @classmethod
    async def monitor_channel(cls):
        try:
            LogManager.log_download_captions(
                f"Starting Channel Monitor for {Account_Config.get_caption_handle()}"
            )

            LogManager.log_download_captions(
                f"Using caption directory: {cls.caption_dir}\n"
                f"Using temp caption directory: {cls.temp_caption_dir}\n"
                f"Using index directory: {cls.index_dir}"
            )

            os.makedirs(cls.caption_dir, exist_ok=True)
            os.makedirs(cls.publish_caption_dir, exist_ok=True)
            os.makedirs(cls.temp_caption_dir, exist_ok=True)
            os.makedirs(cls.index_dir, exist_ok=True)

            # Use configured handle; if it's not a full URL, prefix with YouTube base
            handle = Account_Config.get_caption_handle()
            if handle.startswith("http://") or handle.startswith("https://"):
                channel_url = handle
            else:
                # ensure leading slash is correct
                channel_url = f"https://www.youtube.com/{handle.lstrip('/')}"
            cls.dlp_events = DLPEvents(
                channel_url,
                LogManager.log_download_captions,
                cls.download_started,
                cls.download_complete,
                cls.download_processing,
            )
            LogManager.log_download_captions(f"Monitoring channel {channel_url}")
            # tasks = [cls.manage_caption_index_file()]
            tasks = [cls.download_captions()]
            # tasks.append(cls.download_captions())

        except Exception as e:
            LogManager.log_download_captions(
                f"Failed to schedule caption tasks:{e} \n{traceback.format_exc()}"
            )
        await asyncio.gather(*tasks, return_exceptions=True)

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
    async def manage_caption_index_file(cls):
        while True:
            async with cls._monitor_execution_lock:
                try:
                    if cls._download_execution_lock.locked():
                        await asyncio.sleep(300)
                    else:
                        LogManager.log_download_captions(
                            f"Started Update Captions Index Proccess for {cls.caption_index_file}"
                        )
                        await cls.get_flat_playlist_async(
                            cls.video_playlist, cls.video_json
                        )
                        await cls.get_flat_playlist_async(
                            cls.shorts_playlist, cls.shorts_json
                        )

                        # Update caption index with new entries from shorts and videos playlists
                        video_contents = await JSONUtils.read_json(cls.video_json)
                        await cls.populate_captions_index(
                            video_contents, cls.caption_index_file
                        )
                        shorts_contents = await JSONUtils.read_json(cls.shorts_json)
                        await cls.populate_captions_index(
                            shorts_contents, cls.caption_index_file
                        )

                        LogManager.log_download_captions(
                            "The Captions Index File has been updated with new videos & shorts"
                        )

                        await cls.populate_hascaptions_field()
                        LogManager.log_download_captions(
                            f'Finished Updating "has_captions" field in {cls.caption_index_file}'
                        )
                except Exception as e:
                    LogManager.log_download_captions(
                        f"Unhandled exception in manage_caption_index_file: {e}\n{traceback.format_exc()}"
                    )

            # --- Waiting section ---
            LogManager.log_download_captions(
                "Caption Index Proccess completed. Sleeping for 1 hour."
            )
            await asyncio.sleep(3600)

    @classmethod
    async def download_captions(cls):
        # Wait for 1 min on device startup to allow the index file to populate first
        # await asyncio.sleep(60)
        while True:
            async with cls._download_execution_lock:
                try:
                    if cls._monitor_execution_lock.locked():
                        await asyncio.sleep(300)
                        continue

                    if not os.path.exists(cls.caption_index_file):
                        # If the caption index file doesn't exist yet, wait and retry
                        await asyncio.sleep(300)
                        continue

                    LogManager.log_download_captions("Starting caption download cycle...")
                    index_data = await JSONUtils.read_json(cls.caption_index_file)

                # Build list of items to process
                items = list(index_data.items())
                if not items:
                    LogManager.log_download_captions(
                        "No caption entries found in index."
                    )
                else:
                    workers = []
                    rate_limit_event = asyncio.Event()

                    # If sequential mode is enabled, process items one-by-one asynchronously.
                    if cls.use_sequential_downloads:
                        LogManager.log_download_captions(
                            "Sequential download mode enabled - processing items one at a time."
                        )
                        rate_limited = False
                        for video_id, entry in items:
                            try:
                                await cls.process_video_entry(
                                    video_id,
                                    entry,
                                    semaphore=None,
                                    index_data=index_data,
                                )
                            except RateLimitError:
                                LogManager.log_download_captions(
                                    "Detected YouTube rate limit - aborting current cycle and sleeping for 2 hours."
                                )
                                rate_limited = True
                                break

                        # Save any updates to the index file after processing
                        await JSONUtils.save_json(index_data, cls.caption_index_file)

                        if rate_limited:
                            await asyncio.sleep(2 * 3600)
                            # continue outer loop after sleeping
                            continue
                    else:
                        # Use a queue + worker tasks limited by maximum_threads to control concurrency
                        queue = asyncio.Queue()
                        for it in items:
                            await queue.put(it)

                        num_workers = min(max(1, cls.maximum_threads), len(items))

                        # add sentinel values to stop workers
                        for _ in range(num_workers):
                            await queue.put(None)

                        async def worker():
                            while True:
                                item = await queue.get()
                                try:
                                    if item is None:
                                        break
                                    video_id, entry = item
                                    try:
                                        await cls.process_video_entry(
                                            video_id,
                                            entry,
                                            semaphore=None,
                                            index_data=index_data,
                                        )
                                    except RateLimitError:
                                        # signal the rate limit and stop processing
                                        rate_limit_event.set()
                                        break
                                finally:
                                    queue.task_done()

                        workers = [
                            asyncio.create_task(worker()) for _ in range(num_workers)
                        ]

                        # wait for either queue.join() or rate limit event
                        join_task = asyncio.create_task(queue.join())
                        waiter = asyncio.create_task(rate_limit_event.wait())
                        done, pending = await asyncio.wait(
                            {join_task, waiter}, return_when=asyncio.FIRST_COMPLETED
                        )

                        if rate_limit_event.is_set():
                            # Drain remaining items so queue.join() won't hang
                            with contextlib.suppress(asyncio.QueueEmpty):
                                while True:
                                    item = queue.get_nowait()
                                    queue.task_done()
                        # cancel any pending tasks
                        for t in pending:
                            t.cancel()

                        for w in workers:
                            w.cancel()
                        await asyncio.gather(*workers, return_exceptions=True)

                        # Save any updates to the index file after processing
                        await JSONUtils.save_json(index_data, cls.caption_index_file)

                        if rate_limit_event.is_set():
                            LogManager.log_download_captions(
                                "Rate limit detected during parallel processing - sleeping for 2 hours."
                            )
                            await asyncio.sleep(2 * 3600)
                            continue

            # --- Waiting section ---
            try:
                await asyncio.sleep(300)
            except Exception:
                # Sleep interrupted; log and continue
                LogManager.log_download_captions(
                    "Sleep interrupted in download_captions loop"
                )
            # Save any updates to the index file after processing (defensive save)
            await JSONUtils.save_json(index_data, cls.caption_index_file)

            # --- Waiting section ---
            await asyncio.sleep(300)

    @classmethod
    async def process_video_entry(
        cls, video_id, entry, semaphore=None, index_data=None
    ):
        async def _run():
            title = entry.get("title", "unknown_title")
            has_subtitles = bool(entry.get("has_captions"))
            downloaded = bool(entry.get("downloaded"))
            download_attempts = int(entry.get("download_attempts") or 0)

            if has_subtitles and not downloaded and download_attempts < 10:
                LogManager.log_download_captions(f"Attempting to download {video_id}")
                try:
                    success = await cls.download_caption_for_video(video_id, title)
                except RateLimitError:
                    # propagate to caller to allow higher-level handling (break cycle / sleep)
                    raise
                LogManager.log_download_captions(
                    f"Finished attempting to download {video_id}"
                )
                if success:
                    LogManager.log_download_captions(
                        f"Caption download successful for video ID {video_id}"
                    )
                else:
                    LogManager.log_download_captions(
                        f"Caption download failed for video ID {video_id}"
                    )

                entry["downloaded"] = success
                entry["download_attempts"] = download_attempts + 1

                # if caller passed the in-memory index, save it
                if index_data is not None:
                    await JSONUtils.save_json(index_data, cls.caption_index_file)
            else:
                LogManager.log_download_captions(
                    f"Skipping video ID {video_id} - has_captions: {has_subtitles}, downloaded: {downloaded}, attempts: {download_attempts}"
                )

        try:
            if semaphore:
                async with semaphore:
                    await _run()
            else:
                await _run()
        except Exception as e:
            LogManager.log_download_captions(
                f"Unhandled exception processing video entry {video_id}: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    def download_started(cls):
        LogManager.log_download_captions("Download operation has started processing")

    @classmethod
    def download_processing(cls):
        LogManager.log_download_captions("Download operation is in progress.")

    @classmethod
    def download_complete(cls):
        LogManager.log_download_captions("Download operation has finished processing")

    @classmethod
    async def get_flat_playlist_async(cls, playlist_url: str, output_path: str):
        def run_ytdlp():
            try:
                ydl_opts = {
                    "extract_flat": True,  # --flat-playlist
                    "skip_download": True,
                    "quiet": False,
                    "progress_hooks": [cls.dlp_events.on_progress],
                }

                LogManager.log_download_captions(
                    f"Saving JSON from {playlist_url} to {output_path}"
                )
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(playlist_url, download=False)

                # Save JSON to file
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(info, f, indent=2, ensure_ascii=False)
            except Exception as e:
                LogManager.log_download_captions(
                    f"Failed to extract flat playlist {playlist_url}: {e}\n{traceback.format_exc()}"
                )
                raise

        return await asyncio.to_thread(run_ytdlp)

    @classmethod
    async def populate_captions_index(cls, index_data: dict, captions_index_path: str):
        # Load the existing captions index from file
        captions_index = await JSONUtils.read_json(captions_index_path)

        # Iterate through entries in index_data
        for entry in index_data.get("entries", []):
            entry_id = entry.get("id")
            entry_title = entry.get("title")
            filename = (
                entry_title.split(" (")[0] if " (" in entry_title else entry_title
            )
            if entry_id and entry_id not in captions_index:
                captions_index[entry_id] = {
                    "id": entry_id,
                    "title": filename,
                    "has_captions": None,
                    "download_attempts": 0,
                    "downloaded": False,
                }

        # Save updated captions index back to file
        await JSONUtils.save_json(captions_index, captions_index_path)

    @classmethod
    async def populate_hascaptions_field(cls):
        caption_index = await JSONUtils.read_json(cls.caption_index_file)

        # Filter video IDs based on the specified conditions
        video_ids = [
            vid
            for vid, data in caption_index.items()
            if data.get("has_captions") not in [True, False]
            and data.get("downloaded") is False
            and data.get("download_attempts", 0) < 10
        ]
        if video_ids:
            LogManager.log_download_captions(
                f"Checking {len(video_ids)} videos for captions.."
            )
            LogManager.log_download_captions(
                "This make quite some time for large channels.."
            )

            semaphore = asyncio.Semaphore(cls.maximum_threads)

            async def limited_check(video_id):
                async with semaphore:
                    return await cls.check_captions(video_id)

            tasks = [limited_check(vid) for vid in video_ids]
            results = await asyncio.gather(*tasks)

            for vid, has_captions in results:
                caption_index[vid]["has_captions"] = has_captions

            await JSONUtils.save_json(caption_index, cls.caption_index_file)
            LogManager.log_download_captions(
                "Filtered parallel update of 'has_captions' completed."
            )

    @classmethod
    async def check_captions(cls, video_id: str) -> Tuple[str, bool]:
        try:
            ydl_opts = {
                "quiet": False,
                "skip_download": True,
                "progress_hooks": [cls.dlp_events.on_progress],
            }
            if cls.YT_Cookies_File and os.path.exists(cls.YT_Cookies_File):
                ydl_opts["cookiefile"] = cls.YT_Cookies_File
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )

            has_captions = bool(info.get("automatic_captions") or info.get("subtitles"))
            LogManager.log_download_captions(
                f"Video id: {video_id} caption status = {has_captions}"
            )
            return video_id, has_captions
        except Exception as e:
            LogManager.log_download_captions(
                f"Failed to retrieve metadata for video {video_id}: {e}"
            )
            return video_id, False

    @classmethod
    async def download_caption_for_video(cls, video_id: str, title: str) -> bool:
        def run_ytdlp():
            suburl = f"https://www.youtube.com/watch?v={video_id}"
            safename = FileManager.gen_safe_filename(title)
            ydl_subtitle_opts = {
                "paths": {
                    "home": cls.temp_caption_dir,
                },
                "verbose": True,
                "quiet": False,
                "subtitlesformat": "srt",
                "writeautomaticsub": True,
                "subtitleslangs": ["en"],
                "skip_download": True,
                "outtmpl": f"{safename}",
            }
            if cls.YT_Cookies_File and os.path.exists(cls.YT_Cookies_File):
                ydl_subtitle_opts["cookiefile"] = cls.YT_Cookies_File

            with YoutubeDL(ydl_subtitle_opts) as ydl:
                try:
                    info = ydl.extract_info(suburl, download=True)
                except ExtractorError as ex:
                    msg = str(ex).lower()
                    if (
                        "rate-limited" in msg
                        or "rate limited" in msg
                        or "rate-limited by youtube" in msg
                        or "your account has been rate-limited" in msg
                    ):
                        # signal rate limit to caller
                        raise RateLimitError(str(ex)) from ex
                    # re-raise other ExtractorError to be handled by outer logic
                    raise
            LogManager.log_download_captions(
                "Successfully downloaded captions for video"
            )

            try:
                lang = "en"
                sub_path = info["requested_subtitles"][lang]["filepath"]
            except Exception as e:
                LogManager.log_download_captions(f"Subtitle path not found: {e}")
                return None
            fixed_path = os.path.join(cls.publish_caption_dir, f"{safename}.srt")

            # Return paths for async processing of srt_fix
            return sub_path, fixed_path

        try:
            result = await asyncio.wait_for(asyncio.to_thread(run_ytdlp), timeout=60)
            if not result:
                return False
            temp_sub_path, fixed_path = result

            try:
                if cls.dlp_subtitle_use_srtfix == "true":
                    await cls.fix_srt_async(temp_sub_path, fixed_path)
                    FileManager.delete_file(
                        temp_sub_path, LogManager.DOWNLOAD_CAPTIONS_LOG_FILE
                    )
                    LogManager.log_download_captions(
                        f"srtfix completed: Published SRT to: {fixed_path}"
                    )
                else:
                    # If srtfix is disabled, just move the file to the publish directory
                    FileManager.move_file(
                        temp_sub_path, fixed_path, LogManager.DOWNLOAD_CAPTIONS_LOG_FILE
                    )
                    LogManager.log_download_captions(
                        f"srtfix disabled - moved subtitle to publish directory: {fixed_path}"
                    )
            except Exception as e:
                LogManager.log_download_captions(f"srtfix failed: {e}")
                return False

            LogManager.log_download_captions(
                "Successfully downloaded and fixed captions"
            )
            return True
        except asyncio.TimeoutError:
            LogManager.log_download_captions(
                "Timeout while downloading captions for video"
            )
            return False
        except RateLimitError:
            # propagate rate-limit to allow caller to abort processing and sleep
            raise
        except Exception as e:
            LogManager.log_download_captions(
                f"Error downloading captions for video: {e}\n{traceback.format_exc()}"
            )
            return False
