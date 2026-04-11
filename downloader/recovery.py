import asyncio
import traceback
from utils.logging_utils import LogManager
from dlp.helpers import DLPHelpers
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class RecoveryDownloader:
    _recovery_lock = asyncio.Lock()
    youtube_source = Account_Config.get_youtube_source()
    Live_DownloadRecovery_dir = DVR_Config.get_live_downloadrecovery_dir()
    DownloadFilePrefix = Account_Config.get_live_downloadprefix()
    DownloadTimeStampFormat = DVR_Config.get_download_timestamp_format()
    dlp_max_fragment_retry = DVR_Config.get_max_dlp_fragment_retries()
    dlp_max_dlp_download_retries = DVR_Config.get_max_dlp_download_retries()
    dlp_max_title_chars = DVR_Config.get_max_title_filename_chars()

    # Recovery queue: list of dicts with url, filename, download_complete, and recovery_attempts
    recoveryqueue = []

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
    def _get_items_to_process(cls):
        """Get items from queue that should be processed (not complete, under retry limit)."""
        return [
            item
            for item in cls.recoveryqueue
            if not item["download_complete"] and item["recovery_attempts"] < 10
        ]

    @classmethod
    def _cleanup_queue(cls):
        """Remove completed or exhausted items from queue to prevent memory bloat."""
        cls.recoveryqueue = [
            item
            for item in cls.recoveryqueue
            if not item["download_complete"] and item["recovery_attempts"] < 10
        ]

    @classmethod
    async def _process_recovery_item(cls, item):
        """Process a single recovery queue item with error handling."""
        try:
            async with cls._recovery_lock:
                # Check if stream is still live
                is_still_live = await cls.check_recovery_livestream(item)

                if not is_still_live:
                    # Stream is ready, proceed with download
                    await cls.download_recovery_livestream_content(item)
        except Exception as e:
            LogManager.log_download_live_recovery(
                f"Error downloading {item['url']}: {e} (attempt {item['recovery_attempts']})"
            )
            traceback.print_exc()

    @classmethod
    async def monitor_recoveryqueue(cls):
        """Monitor recovery queue and process items in a continuous loop."""
        LogManager.log_download_live_recovery(
            f"Starting Live Recovery Downloader for {cls.youtube_source}"
        )
        while True:
            items_to_process = cls._get_items_to_process()

            for item in items_to_process:
                await cls._process_recovery_item(item)

            cls._cleanup_queue()
            await asyncio.sleep(60)

    @classmethod
    async def check_recovery_livestream(cls, item):
        """Check if stream is live. Returns True if live status prohibits download, False if ready to download."""
        try:
            currenturl = f'{item["url"]}'

            # Get info to check live status
            info_ydl_opts = {
                "quiet": False,
                "no_warnings": False,
            }

            info = await DLPHelpers.getinfo_with_retry(
                ydl_opts=info_ydl_opts,
                url_or_list=currenturl,
                log_file_name=LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILE,
                log_warnings_and_above_only=False,
                desired_dicts=["live_status","is_live", "webpage_url"],
            )

            if info is None:
                LogManager.log_download_live_recovery(
                    f"Failed to get info for {currenturl}, will retry later"
                )
                item["recovery_attempts"] += 1
                return True  # Treat as still live, will retry

            live_status = info.get("live_status")

            if live_status == "is_live":
                LogManager.log_download_live_recovery(
                    f"Skipping recovery download for {currenturl}: stream is still live (will retry later)"
                )
                item["recovery_attempts"] += 1
                return True  # Stream is live

            return False  # Stream is ready for download

        except Exception as e:
            LogManager.log_download_live_recovery(
                f"Exception in check_recovery_livestream for {item.get('url')}: {e}\n{traceback.format_exc()}"
            )
            item["recovery_attempts"] += 1
            return True  # Treat as error, will retry

    @classmethod
    async def download_recovery_livestream_content(cls, item):
        """Download the recovery livestream content."""
        try:
            currenturl = f'{item["url"]}'

            LogManager.log_download_live_recovery(
                f"Starting Recovery Download For {currenturl}"
            )

            # Build yt-dlp options similar to downloader/videos.py
            download_ydl_opts = {
                "paths": {"home": cls.Live_DownloadRecovery_dir},
                "outtmpl": item["filename"],
                "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                "restrictfilenames": True,
                "fragment_retries": int(cls.dlp_max_fragment_retry),
                "retries": int(cls.dlp_max_dlp_download_retries),
                "progress_hooks": [cls.dlp_events.on_progress],
            }

            await DLPHelpers.download_with_retry(
                ydl_opts=download_ydl_opts,
                url_or_list=[currenturl],
                timeout_enabled=True,
                log_file_name=LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILE,
                log_warnings_and_above_only=False,
            )

            item["download_complete"] = True
            LogManager.log_download_live_recovery(
                f"Recovery download completed for {currenturl}"
            )

        except Exception as e:
            LogManager.log_download_live_recovery(
                f"Exception in download_recovery_livestream_content for {item.get('url')}: {e}\n{traceback.format_exc()}"
            )
            item["recovery_attempts"] += 1
