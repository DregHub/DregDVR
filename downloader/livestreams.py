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
from yt_dlp.utils import UserNotLive, match_filter_func
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
    YT_Cookies_File = DVR_Config.get_yt_cookies_file()

    current_videourl = None
    current_videofile = None

    # Recovery queue: list of dicts with url, index, download_complete, and download_attempts
    download_queue = []

    @classmethod
    def download_started(cls):
        LogManager.log_download_live(
            f"DOWNLOAD STARTED CALLBACK FOR  {cls.current_videourl}"
        )
        if cls.comment_download == "true":
            try:
                scheduled = AsyncScheduler.schedule_nonblocking(
                    LiveCommentsDownloader.download_comments(
                        cls.current_videourl, cls.current_videofile
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
            f"Detected end of livestream {cls.current_videourl}, Adding this to the download recovery queue while we continue proccessing the file."
        )
        RecoveryDownloader.add_to_recoveryqueue(
            cls.current_videourl, cls.current_videofile
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
                    "match_filter": match_filter_func("live_status=is_live"),
                }

                # Add cookiefile if present
                if cls.YT_Cookies_File and os.path.exists(cls.YT_Cookies_File):
                    mon_ydl_opts["cookiefile"] = cls.YT_Cookies_File

                with yt_dlp.YoutubeDL(mon_ydl_opts) as ydl:
                    try:
                        try:
                            info = ydl.extract_info(cls.youtube_source, download=False)
                        except UserNotLive:
                            # Channel not live — silently ignore and don't treat as failure
                            # Dont waste further resources we will recheck next cycle
                            return
                        # ignore errors, if the stream is not live or scheduled, it will raise a DownloadError
                        is_live = info.get("live_status")
                        livestream_url = info.get("webpage_url")
                        if is_live:
                            if all(
                                item["url"] != livestream_url
                                for item in cls.download_queue
                            ):
                                LogManager.log_download_live(
                                    f"Adding new active livestream {livestream_url} to download queue"
                                )
                                CurrentIndex = IndexManager.find_new_live_index(
                                    LogManager.DOWNLOAD_LIVE_LOG_FILE
                                )
                                await cls.add_to_downloadqueue(
                                    livestream_url, CurrentIndex
                                )
                            return
                    except yt_dlp.utils.DownloadError as e:
                        # Ignore the error is due to the stream not being live or scheduled
                        return

            except Exception as e:
                LogManager.log_download_live(
                    f"Exception in download_livestreams:  {e}\n{traceback.format_exc()}"
                )
                await asyncio.sleep(30)

    @classmethod
    async def download_livestream(cls, item):
        async with cls._download_execution_lock:
            CurrentIndex = item["index"]
            try:
                current_nametemplate = f"{CurrentIndex} {cls.DownloadFilePrefix} {cls.DownloadTimeStampFormat}.%(ext)s"
                dlp_download_opts = {
                    "paths": {
                        "temp": cls.Live_DownloadQueue_Dir,
                        "home": cls.Live_UploadQueue_Dir,
                    },
                    "outtmpl": current_nametemplate,
                    "live_from_start": True,
                    "match_filter": match_filter_func("live_status=is_live"),
                    "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                    "ignore_no_formats_error": True,  # ← prevents livestream errors from crashing
                    "fragment_retries": int(cls.dlp_max_fragment_retries),
                    "retries": int(cls.dlp_max_dlp_download_retries),
                    "skip_unavailable_fragments": True,
                    "no_abort_on_error": True,
                    "restrictfilenames": True,
                    "noprogress": True,
                }

                # Add cookiefile if present
                if cls.YT_Cookies_File and os.path.exists(cls.YT_Cookies_File):
                    dlp_download_opts["cookiefile"] = cls.YT_Cookies_File
                # Convert the /@channel/live into an actual video url and get the publish file name
                # Use a temporary YoutubeDL to extract info only (do not call download here)
                with yt_dlp.YoutubeDL(dlp_download_opts) as ydl:
                    info = ydl.extract_info(cls.youtube_source, download=False)

                    if info.get("live_status") in ("is_upcoming"):
                        LogManager.log_download_posted(
                            "Current Video is an upcoming stream, skipping download for now."
                        )
                        return
                    current_videofilepath = ydl.prepare_filename(info)
                    cls.current_videofile = os.path.splitext(
                        os.path.basename(current_videofilepath)
                    )[0].rstrip()
                    cls.current_videourl = info.get("webpage_url")
                    LogManager.log_download_live(
                        f"Resolved video url to: {cls.current_videourl}"
                    )
                    LogManager.log_download_live(
                        f"Publish video file name will be: {cls.current_videofile}"
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

                # Create a fresh YoutubeDL with progress hooks and run download in a thread
                try:
                    with yt_dlp.YoutubeDL(dlp_download_opts) as ydl_with_hooks:
                        await asyncio.to_thread(
                            ydl_with_hooks.download, cls.current_videourl
                        )
                except Exception as e:
                    msg = str(e)
                    if (
                        ("429" in msg)
                        or ("rate limit" in msg.lower())
                        or ("too many requests" in msg.lower())
                    ) and "cookiefile" in dlp_download_opts:
                        LogManager.log_download_live(
                            "Rate limit detected, retrying livestream download without cookiefile"
                        )
                        dlp_opts_no_cookie = dict(dlp_download_opts)
                        dlp_opts_no_cookie.pop("cookiefile", None)
                        with yt_dlp.YoutubeDL(dlp_opts_no_cookie) as ydl_no_cookie:
                            await asyncio.to_thread(
                                ydl_no_cookie.download, cls.current_videourl
                            )
                    else:
                        raise

            except Exception as e:
                msg = str(e)
                # Only log if the error is not related to the channel not being live, since that can be expected if the stream ends while we are trying to download it
                if "The channel is not currently live" not in msg:
                    LogManager.log_download_live(
                        f"yt-dlp python API failed for {cls.current_videourl}: {e}\n{traceback.format_exc()}"
                    )

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
            await cls.check_livestream()
            await asyncio.sleep(30)

    @classmethod
    async def download_livestreams(cls):
        LogManager.log_download_live(
            f"Starting Livestream Downloader for {cls.youtube_source}"
        )
        tasks = [cls.monitor_downloadqueue(), cls.monitor_livestreams()]
        await asyncio.gather(*tasks)
