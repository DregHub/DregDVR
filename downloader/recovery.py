import asyncio
import re
import traceback
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess, run_subprocess_realtime
from config import Config


class RecoveryDownloader:
    _recovery_lock = asyncio.Lock()
    youtube_source = Config.get_youtube_source()
    Live_DownloadRecovery_dir = Config.get_live_downloadrecovery_dir()
    DownloadFilePrefix = Config.get_live_downloadprefix()
    DownloadTimeStampFormat = Config.get_download_timestamp_format()
    dlp_verbose = Config.get_verbose_dlp_mode()
    dlp_keep_fragments = Config.get_keep_fragments_dlp_downloads()
    dlp_no_progress = Config.no_progress_dlp_downloads()

    # Recovery queue: list of dicts with url, index, download_complete, and recovery_attempts
    recoveryqueue = []

    @classmethod
    async def add_to_recoveryqueue(cls, url, index):
        cls.recoveryqueue.append({
            "url": url,
            "index": index,
            "download_complete": False,
            "recovery_attempts": 0
        })

    @classmethod
    async def monitor_recoveryqueue(cls):
        while True:
            for item in cls.recoveryqueue:
                if not item["download_complete"] and item["recovery_attempts"] < 10:
                    try:
                        await cls.download_recovery_livestream(item)
                    except Exception as e:
                        LogManager.log_download_live_recovery(
                            f"Error downloading {item['url']}: {e} (attempt {item['recovery_attempts']})")
                        traceback.print_exc()
            await asyncio.sleep(60)

    @classmethod
    async def download_recovery_livestream(cls, item):
        async with cls._recovery_lock:
            LogManager.log_download_live_recovery(f"Starting Recovery Download For {item['url']}")
            
            CurrentRecoveryFile = f"{item['index']} {cls.DownloadFilePrefix} %(title)s {cls.DownloadTimeStampFormat}.%(ext)s"
            currenturl = f'https://www.youtube.com/watch?v={item["url"]}'
            recovery_command = [
                "yt-dlp",
                "--paths", f"temp:{cls.Live_DownloadRecovery_dir}",
                "--output", f'"{CurrentRecoveryFile}"',
                "--downloader-args", f'"ffmpeg_i:-loglevel quiet"',
                f'"{currenturl}"',
            ]

            if (cls.dlp_verbose == "true"):
                recovery_command.append("--verbose")

            if cls.dlp_no_progress == "true":
                for filt in Config.get_no_progress_dlp_filters():
                    if filt not in LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILTER:
                        LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILTER.append(filt)

            log_lines = []
            exit_code = None
            async for line in run_subprocess_realtime(
                recovery_command,
                LogManager.DOWNLOAD_LIVE_RECOVERY_LOG_FILE,
                "yt-dlp command failed",
                "Exception in run_yt_dlp",
                cls.Live_DownloadRecovery_dir
            ):
                # Check for exit code sentinel
                if isinstance(line, dict) and "__exit_code__" in line:
                    exit_code = line["__exit_code__"]
                    break
                log_lines.append(line)

            LogManager.log_download_live_recovery(
                f"Detected the exit of yt-dlp process for: {item['url']} with exit code {exit_code}")
            if exit_code == 0:
                LogManager.log_download_live_recovery(f"Recovery download for {item['url']} completed successfully.")
                item["download_complete"] = True
            else:
                LogManager.log_download_live_recovery(
                    f"Recovery download for {item['url']} did not complete successfully.")
                item["download_complete"] = False
                item["recovery_attempts"] += 1
