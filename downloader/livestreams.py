import asyncio
import os
import traceback
import yt_dlp
from utils.async_scheduler import AsyncScheduler
from utils.index_utils import IndexManager
from utils.logging_utils import LogManager
from downloader.recovery import RecoveryDownloader
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from config.config_tasks import DVR_Tasks
from utils.dlp_utils import DLPEvents
from utils.dlp_utils import download_with_retry, getinfo_with_retry
from downloader.comments import LiveCommentsDownloader


class LivestreamDownloader:
    _download_execution_lock = asyncio.Lock()
    _monitor_execution_lock = asyncio.Lock()
    youtube_source = Account_Config.get_youtube_source()
    Live_DownloadQueue_Dir = DVR_Config.get_live_downloadqueue_dir()
    Live_UploadQueue_Dir = DVR_Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = DVR_Config.get_live_completeduploads_dir()
    DownloadFilePrefix = Account_Config.get_live_downloadprefix()
    DownloadTimeStampFormat = DVR_Config.get_download_timestamp_format()
    dlp_verbose = DVR_Config.get_verbose_dlp_mode()
    dlp_keep_fragments = DVR_Config.get_keep_fragments_dlp_downloads()
    dlp_no_progress = DVR_Config.no_progress_dlp_downloads()
    dlp_max_fragment_retries = DVR_Config.get_max_dlp_fragment_retries()
    dlp_max_dlp_download_retries = DVR_Config.get_max_dlp_download_retries()
    dlp_max_title_chars = DVR_Config.get_max_title_filename_chars()
    comment_download = DVR_Tasks.get_comments_download()

    subtitle_name_template = None
    subtitle_name_prefix = None
    current_name_template = None
    current_videourl = None

    # Recovery queue: list of dicts with url, index, download_complete, and download_attempts
    download_queue = []

    @classmethod
    def download_started(cls):
        if cls.comment_download == "true":
            try:
                LogManager.log_download_live(
                    f"Scheduling Live Comments Downloader for livestream {cls.current_videourl}"
                )
                scheduled = AsyncScheduler.schedule_nonblocking(
                    LiveCommentsDownloader.download_comments(
                        cls.current_videourl,
                        cls.subtitle_name_template,
                        cls.subtitle_name_prefix,
                    ),
                    getattr(cls, "_main_loop", None),
                )
                if not scheduled:
                    LogManager.log_download_live(
                        "Failed to schedule LiveCommentsDownloader (no event loop available)"
                    )
            except Exception as e:
                LogManager.log_download_live(
                    f"Exception while scheduling comment download: {e}\n{traceback.format_exc()}"
                )
        else:
            LogManager.log_download_live(
                "Livestream comment download is disabled in INI Tasks. Skipping comment download..."
            )

    @classmethod
    def download_processing(cls):
        LogManager.log_download_live(
            f"Detected end of livestream {cls.current_videourl}, Adding this to the download recovery queue while we continue proccessing the file for publishing."
        )
        RecoveryDownloader.add_to_recoveryqueue(
            cls.current_videourl, cls.current_name_template
        )

    @classmethod
    def download_complete(cls):
        LogManager.log_download_live(f"{cls.youtube_source} Has finished proccessing")

    @classmethod
    async def check_livestream(cls):
        async with cls._monitor_execution_lock:
            try:
                mon_ydl_opts = {
                    "quiet": True,
                    "skip_download": True,
                    "forcejson": True,
                    "extract_flat": False,
                    "ignore-errors": True,
                }

                try:
                    info = await getinfo_with_retry(
                        mon_ydl_opts,
                        cls.youtube_source,
                        LogManager.DOWNLOAD_LIVE_LOG_FILE,
                    )
                    LiveStatus = info.get("live_status")
                    if LiveStatus == "is_live":
                        livestream_url = info.get("webpage_url")
                        if all(
                            item["url"] != livestream_url for item in cls.download_queue
                        ):
                            LogManager.log_download_live(
                                f"Adding new active livestream {livestream_url} to download queue"
                            )
                            CurrentIndex = IndexManager.find_new_live_index(
                                LogManager.DOWNLOAD_LIVE_LOG_FILE
                            )
                            await cls.add_to_downloadqueue(livestream_url, CurrentIndex)
                        return
                    else:
                        LogManager.log_download_live(
                            f"Channel is not live (live_status={LiveStatus}), Skipping download."
                        )
                except Exception as e:
                    # let the helper have already logged; escalate so caller can handle if desired
                    LogManager.log_download_live(
                        f"Exception in download_livestreams:  {e}\n{traceback.format_exc()}"
                    )
                    raise

            except Exception as e:
                LogManager.log_download_live(
                    f"Exception in download_livestreams:  {e}\n{traceback.format_exc()}"
                )
                await asyncio.sleep(30)

    @classmethod
    async def download_livestream(cls, item):
        async with cls._download_execution_lock:
            CurrentIndex = item["index"]
            # Increment attempt count for bookkeeping
            item["download_attempts"] = item.get("download_attempts", 0) + 1
            try:
                cls.current_name_template = f"{CurrentIndex} {cls.DownloadFilePrefix} {cls.DownloadTimeStampFormat}.%(ext)s"
                cls.subtitle_name_template = f"{CurrentIndex} {cls.DownloadFilePrefix} {cls.DownloadTimeStampFormat}"
                cls.subtitle_name_prefix = f"{CurrentIndex} {cls.DownloadFilePrefix}"
                dlp_download_opts = {
                    "paths": {
                        "temp": cls.Live_DownloadQueue_Dir,
                        "home": cls.Live_UploadQueue_Dir,
                    },
                    "outtmpl": cls.current_name_template,
                    "live_from_start": True,
                    "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                    "ignore_no_formats_error": True,  # ← prevents livestream errors from crashing
                    "fragment_retries": int(cls.dlp_max_fragment_retries),
                    "retries": int(cls.dlp_max_dlp_download_retries),
                    "skip_unavailable_fragments": True,
                    "no_abort_on_error": True,
                    "restrictfilenames": True,
                    "noprogress": True,
                }

                if cls.dlp_verbose == "true":
                    dlp_download_opts["verbose"] = True

                # Convert the /@channel/live into an actual video url and get the publish file name
                # Use helper to extract info with retry behavior
                info = await getinfo_with_retry(
                    dlp_download_opts,
                    cls.youtube_source,
                    LogManager.DOWNLOAD_LIVE_LOG_FILE,
                )

                if info.get("live_status") in ("is_live"):
                    cls.current_videourl = info.get("webpage_url")
                    LogManager.log_download_live(
                        f"Resolved video url to: {cls.current_videourl}"
                    )

                    # Now attach the progress hooks and download the actual livestream using a new YoutubeDL instance
                    cls.dlp_events = DLPEvents(
                        cls.current_videourl,
                        LogManager.DOWNLOAD_LIVE_LOG_FILE,
                        cls.download_started,
                        cls.download_complete,
                        cls.download_processing,
                    )
                    dlp_download_opts["progress_hooks"] = [cls.dlp_events.on_progress]
                    await download_with_retry(
                        dlp_download_opts,
                        cls.current_videourl,
                        LogManager.DOWNLOAD_LIVE_LOG_FILE,
                    )

                    # If we reach here, download succeeded; mark item complete
                    item["download_complete"] = True
                    LogManager.log_download_live(
                        f"Download completed for {cls.current_videourl}"
                    )
                else:
                    skipped_video = info.get("webpage_url")
                    skipped_status = info.get("live_status")
                    LogManager.log_download_live(
                        f"Skipping {skipped_video} as it has an unsupported live status {skipped_status}"
                    )

            except Exception as e:
                LogManager.log_download_live(
                    f"Exception while downloading livestream {item.get('url')}: {e}\n{traceback.format_exc()}"
                )
                # Do not re-raise; monitor loop will retry based on download_attempts.
                return

    @classmethod
    async def add_to_downloadqueue(cls, url, index):
        cls.download_queue.append(
            {
                "url": url,
                "index": index,
                "download_complete": False,
                "download_attempts": 0,
            }
        )

    @classmethod
    async def monitor_downloadqueue(cls):
        while True:
            for item in cls.download_queue:
                if not item["download_complete"] and item["download_attempts"] <= 10:
                    try:
                        LogManager.log_download_live(
                            f"Detected a new live stream in the download queue, starting download task. {item['url']}"
                        )
                        await cls.download_livestream(item)
                    except Exception as e:
                        LogManager.log_download_live(
                            f"Error downloading {item['url']}: {e} (attempt {item['download_attempts']})"
                        )
                        traceback.print_exc()
            await asyncio.sleep(30)

    @classmethod
    async def monitor_livestreams(cls):
        while True:
            try:
                await cls.check_livestream()
            except Exception as e:
                LogManager.log_download_live(
                    f"Unhandled exception in monitor_livestreams: {e}\n{traceback.format_exc()}"
                )
            try:
                await asyncio.sleep(30)
            except Exception:
                LogManager.log_download_live("Sleep interrupted in monitor_livestreams")

    @classmethod
    async def download_livestreams(cls):
        LogManager.log_download_live(
            f"Starting Livestream Downloader for {cls.youtube_source}"
        )
        tasks = [cls.monitor_downloadqueue(), cls.monitor_livestreams()]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            LogManager.log_download_live(
                f"Unhandled exception in download_livestreams gather: {e}\n{traceback.format_exc()}"
            )
