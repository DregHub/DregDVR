import asyncio
import os
import shutil
import traceback
from utils.index_utils import IndexManager
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess
from config import Config


class LivestreamDownloader:
    youtube_source = Config.get_youtube_source()
    Live_DownloadQueue_Dir = Config.get_live_downloadqueue_dir()
    Live_UploadQueue_Dir = Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = Config.get_live_completeduploads_dir()
    DownloadFilePrefix = Config.get_live_downloadprefix()
    DownloadTimeStampFormat = Config.get_download_timestamp_format()
    dlp_verbose = Config.get_verbose_dlp_mode()
    dlp_keep_fragments = Config.get_dlp_keep_fragments()


    @classmethod
    def extract_username(cls, url):
        parts = url.split("/")
        for part in parts:
            if part.startswith("@"):
                return part  # Return @handle if found
        return url  # If no match, return original URL

    @classmethod
    async def download_livestreams(cls):
        LogManager.log_download_live(f"Starting YT-DLP Monitor for {cls.youtube_source}")
        while True:
            try:
                CurrentIndex = IndexManager.find_new_live_index(LogManager.DOWNLOAD_LIVE_LOG_FILE)
                YT_Handle = cls.extract_username(cls.youtube_source)
                CurrentDownloadFile = f"{CurrentIndex} {cls.DownloadFilePrefix} {cls.DownloadTimeStampFormat}.%(ext)s"

                command = [
                    "yt-dlp",
                    f"--paths temp:{cls.Live_DownloadQueue_Dir}",
                    "--output",
                    f'"{CurrentDownloadFile}"',
                    "--live-from-start",
                    "--match-filter live_status=is_live",
                    "--ignore-no-formats-error",
                    "--retries 30",
                    cls.youtube_source,
                ]

                if (cls.dlp_verbose == "true"):
                    command.append("--verbose")

                if (cls.dlp_keep_fragments == "true"):
                    command.append("--keep-fragments")

                mini_log = await run_subprocess(
                    command,
                    LogManager.DOWNLOAD_LIVE_LOG_FILE,
                    "yt-dlp command failed",
                    "Exception in run_yt_dlp",
                    cls.Live_UploadQueue_Dir
                )

                ScheduledStream = False
                InactiveStream = False

                if not mini_log:
                    LogManager.log_download_live("No output from yt-dlp, possibly no new lives available.")
                else:
                    for line in mini_log:
                        if "does not pass filter" in line:
                            ScheduledStream = True
                            LogManager.log_download_live(
                                f"{YT_Handle} is scheduled to go live but it has not started yet, skipping download.")
                        elif "The channel is not currently live" in line:
                            InactiveStream = True
                            LogManager.log_download_live(f"{YT_Handle} is not currently live, Sleeping for 30 seconds.")

                if not ScheduledStream and not InactiveStream:
                    LogManager.log_download_live(
                        f"Successful Download of {YT_Handle} Livestream, moving to Live_UploadQueue_Dir")
                    # No need to increment index anymore calculated by previous file
                    #IndexManager.increment_index(, LogManager.DOWNLOAD_LIVE_LOG_FILE)
                else:
                    await asyncio.sleep(30)
            except Exception as e:
                LogManager.log_download_live(f"Exception in download_livestreams:  {e}\n{traceback.format_exc()}")
                await asyncio.sleep(30)
