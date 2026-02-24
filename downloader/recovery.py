import asyncio
import traceback
import os
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess_realtime
from utils.dlp_utils import DLPEvents
from yt_dlp import YoutubeDL
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class RecoveryDownloader:
    _recovery_lock = asyncio.Lock()
    youtube_source = Account_Config.get_youtube_source()
    Live_DownloadRecovery_dir = DVR_Config.get_live_downloadrecovery_dir()
    DownloadFilePrefix = Account_Config.get_live_downloadprefix()
    DownloadTimeStampFormat = DVR_Config.get_download_timestamp_format()
    dlp_verbose = DVR_Config.get_verbose_dlp_mode()
    dlp_keep_fragments = DVR_Config.get_keep_fragments_dlp_downloads()
    dlp_no_progress = DVR_Config.no_progress_dlp_downloads()
    dlp_max_fragment_retry = DVR_Config.get_max_dlp_fragment_retries()
    dlp_max_dlp_download_retries = DVR_Config.get_max_dlp_download_retries()
    dlp_max_title_chars = DVR_Config.get_max_title_filename_chars()
    YT_Cookies_File = DVR_Config.get_yt_cookies_file()

    # Recovery queue: list of dicts with url, filename, download_complete, and recovery_attempts
    recoveryqueue = []

    @classmethod
    def download_started(cls):
        LogManager.log_download_live_recovery(
            f"RECOVERY DOWNLOAD START EVENT {cls.youtube_source}"
        )

    @classmethod
    def download_processing(cls):
        LogManager.log_download_live_recovery(
            f"RECOVERY DOWNLOAD PROCESSING EVENT {cls.youtube_source}"
        )

    @classmethod
    def download_complete(cls):
        LogManager.log_download_live_recovery(
            f"RECOVERY DOWNLOAD COMPLETE EVENT {cls.youtube_source}"
        )

    @classmethod
    async def add_to_recoveryqueue(cls, url, filename):
        cls.recoveryqueue.append(
            {
                "url": url,
                "filename": filename,
                "download_complete": False,
                "recovery_attempts": 0,
            }
        )

    @classmethod
    async def monitor_recoveryqueue(cls):
        while True:
            for item in cls.recoveryqueue:
                if not item["download_complete"] and item["recovery_attempts"] < 10:
                    try:
                        await cls.download_recovery_livestream(item)
                    except Exception as e:
                        LogManager.log_download_live_recovery(
                            f"Error downloading {item['url']}: {e} (attempt {item['recovery_attempts']})"
                        )
                        traceback.print_exc()
            await asyncio.sleep(60)

    @classmethod
    async def download_recovery_livestream(cls, item):
        async with cls._recovery_lock:
            LogManager.log_download_live_recovery(
                f"Starting Recovery Download For {item['url']}"
            )
            currenturl = f'{item["url"]}'

            # Progress hook callbacks for recovery downloads
            cls.dlp_events = DLPEvents(
                item["url"],
                LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILE,
                cls.download_started if hasattr(cls, "download_started") else None,
                cls.download_complete if hasattr(cls, "download_complete") else None,
                (
                    cls.download_processing
                    if hasattr(cls, "download_processing")
                    else None
                ),
            )

            # Build yt-dlp options similar to downloader/videos.py
            ydl_opts = {
                "paths": {"temp": cls.Live_DownloadRecovery_dir},
                "outtmpl": item["filename"],
                "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                "restrictfilenames": True,
                "fragment_retries": int(cls.dlp_max_fragment_retry),
                "retries": int(cls.dlp_max_dlp_download_retries),
                "progress_hooks": [cls.dlp_events.on_progress],
            }

            # Use cookies file if configured and present
            if cls.YT_Cookies_File and os.path.exists(cls.YT_Cookies_File):
                ydl_opts["cookiefile"] = cls.YT_Cookies_File

            if cls.dlp_keep_fragments == "true":
                ydl_opts["keep_fragments"] = True

            if cls.dlp_verbose == "true":
                ydl_opts["verbose"] = True

            if cls.dlp_no_progress == "true":
                for filt in DVR_Config.get_no_progress_dlp_filters():
                    if filt not in LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILTER:
                        LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILTER.append(filt)

            log_lines = []
            exit_code = None

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    # Run blocking download in thread to avoid blocking event loop
                    await asyncio.to_thread(ydl.download, [currenturl])
                exit_code = 0
                LogManager.log_download_live_recovery(
                    f"Detected the exit of yt-dlp process for: {item['url']} with exit code {exit_code}"
                )
                LogManager.log_download_live_recovery(
                    f"Recovery download for {item['url']} completed successfully."
                )
                item["download_complete"] = True

            except Exception as e:
                exit_code = 1
                LogManager.log_download_live_recovery(
                    f"Detected the exit of yt-dlp process for: {item['url']} with exit code {exit_code}"
                )
                LogManager.log_download_live_recovery(
                    f"Recovery download for {item['url']} did not complete successfully: {e}"
                )
                item["download_complete"] = False
                item["recovery_attempts"] += 1
