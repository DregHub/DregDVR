import asyncio
import re
import traceback
from utils.index_utils import IndexManager
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess, run_subprocess_realtime
from downloader.recovery import RecoveryDownloader
from config import Config


class LivestreamDownloader:
    _download_execution_lock = asyncio.Lock()
    _monitor_execution_lock = asyncio.Lock()
    youtube_source = Config.get_youtube_source()
    Live_DownloadQueue_Dir = Config.get_live_downloadqueue_dir()
    Live_UploadQueue_Dir = Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = Config.get_live_completeduploads_dir()
    DownloadFilePrefix = Config.get_live_downloadprefix()
    DownloadTimeStampFormat = Config.get_download_timestamp_format()
    dlp_verbose = Config.get_verbose_dlp_mode()
    dlp_keep_fragments = Config.get_keep_fragments_dlp_downloads()
    dlp_no_progress = Config.no_progress_dlp_downloads()
    disable_comment_download = Config.get_disable_comment_download()

    @classmethod
    def extract_username(cls, url):
        parts = url.split("/")
        for part in parts:
            if part.startswith("@"):
                return part  # Return @handle if found
        return url  # If no match, return original URL

    # Recovery queue: list of dicts with url, index, download_complete, and download_attempts
    download_queue = []

    @classmethod
    async def check_livestream(cls):
        async with cls._monitor_execution_lock:
            try:
                current_videoid = None
                command = [
                    "yt-dlp",
                    "--simulate",
                    cls.youtube_source
                ]

                if (cls.dlp_verbose == "true"):
                    command.append("--verbose")

                MiniLog, exit_code = await run_subprocess(
                    command,
                    None,
                    "yt-dlp video/shorts playlist extraction failed",
                    "Exception in download_videos",
                    None  # Dont spam logs with errors for offline channels
                )
                current_videoid = None
                ScheduledStream = False
                InactiveStream = False

                if not MiniLog:
                    LogManager.log_download_live(
                        "No output from yt-dlp, possibly no new videos or shorts available.")
                else:
                    for line in MiniLog:
                        matched_download_start = re.search(
                            r"\[info\] ([^\s:]+): Downloading (\d+) format\(s\)", line)
                        if "does not pass filter" in line:
                            ScheduledStream = True
                        elif "The channel is not currently live" in line:
                            InactiveStream = True
                        elif matched_download_start:
                            current_videoid = matched_download_start.group(1)

                if (exit_code == 0 and ScheduledStream == False and InactiveStream == False and current_videoid is not None):
                    url = f'https://www.youtube.com/watch?v={current_videoid}'
                    if not any(item["url"] == url for item in cls.download_queue):
                        LogManager.log_download_live(
                            f"Adding new active livestream {current_videoid} to download queue")
                        CurrentIndex = IndexManager.find_new_live_index(LogManager.DOWNLOAD_LIVE_LOG_FILE)
                        await cls.add_to_downloadqueue(url, CurrentIndex)

            except Exception as e:
                LogManager.log_download_live(f"Exception in download_livestreams:  {e}\n{traceback.format_exc()}")
                await asyncio.sleep(30)

    @classmethod
    async def download_livestream(cls, item):
        async with cls._download_execution_lock:
            LogManager.log_download_live(f"Downloading active livestream {item['url']}")
            current_videoid = None  # Initialize to None
            CurrentDownloadFile = None  # Initialize to None
            CurrentIndex = item['index']
            try:
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
                    "--retries 15",
                    "--skip-unavailable-fragments",
                    "--no-abort-on-error",
                    f'"{item['url']}"',

                ]

                if (cls.dlp_verbose == "true"):
                    command.append("--verbose")

                if (cls.dlp_keep_fragments == "true"):
                    command.append("--keep-fragments")

                if cls.dlp_no_progress == "true":
                    for filt in Config.get_no_progress_dlp_filters():
                        if filt not in LogManager.DOWNLOAD_LIVE_LOG_FILTER:
                            LogManager.DOWNLOAD_LIVE_LOG_FILTER.append(filt)

                merger_line_found = False
                movefiles_line_found = False
                merged_filename = None

                log_lines = []

                exit_code = None
                async for line in run_subprocess_realtime(
                    command,
                    LogManager.DOWNLOAD_LIVE_LOG_FILE,
                    "yt-dlp command failed",
                    "Exception in run_yt_dlp",
                    cls.Live_UploadQueue_Dir
                ):
                    # Check for exit code sentinel
                    if isinstance(line, dict) and "__exit_code__" in line:
                        exit_code = line["__exit_code__"]
                        break

                    log_lines.append(line)

                    matched_download_start = None
                    if isinstance(line, str):
                        matched_download_start = re.search(
                            r"\[info\] ([^\s:]+): Downloading (\d+) format\(s\)", line)

                    if isinstance(line, str) and "does not pass filter" in line:
                        LogManager.log_download_live(
                            f"{YT_Handle} is scheduled to go live but it has not started yet, skipping download.")
                    elif isinstance(line, str) and "The channel is not currently live" in line:
                        LogManager.log_download_live(f"{YT_Handle} is not currently live, Sleeping for 30 seconds.")
                    elif matched_download_start:
                        current_videoid = matched_download_start.group(1)
                        LogManager.log_download_live(
                            f"Detected the start of a live stream https://www.youtube.com/watch?v={current_videoid}, Now we start the comments downloader.")

                        if cls.disable_comment_download != "true":
                            from downloader.comments import LiveCommentsDownloader
                            asyncio.create_task(LiveCommentsDownloader.download_comments(current_videoid))

                    merger_match = None
                    if isinstance(line, str):
                        merger_match = re.search(r'\[Merger\] Merging formats into "(.*?)"', line)
                    if merger_match:
                        merger_line_found = True
                        merged_filename = merger_match.group(1)
                    movefiles_match = None
                    if isinstance(line, str):
                        movefiles_match = re.search(r'\[MoveFiles\] Moving file "(.*?)" to "(.*?)"', line)
                    if movefiles_match and merged_filename and movefiles_match.group(1) == merged_filename:
                        movefiles_line_found = True

                LogManager.log_download_live("Detected the end of a yt-dlp process. exit code: " + str(
                    exit_code) + " merger_line_found: " + str(merger_line_found) + " movefiles_line_found: " + str(movefiles_line_found))
                # Patch exit code to 0 if we successfully merged and moved the file
                if exit_code == 1 and merger_line_found and movefiles_line_found:
                    LogManager.log_download_live(
                        "Masking yt-dlp exit code 1 to 0 due to successful move after merge.")
                    exit_code = 0

                if exit_code == 0:
                    LogManager.log_download_live(
                        f"yt-dlp exited with code {exit_code}, indicating a clean exit. Setting download_complete to True.")
                    item['download_complete'] = True
            finally:
                item['download_attempts'] += 1
                LogManager.log_download_live(
                    "Detected the end of a live stream, Adding to the recovery download queue.")
                if CurrentIndex is not None and current_videoid is not None:
                    await RecoveryDownloader.add_to_recoveryqueue(current_videoid, CurrentIndex)

    @classmethod
    async def add_to_downloadqueue(cls, url, index):
        cls.download_queue.append({
            "url": url,
            "index": index,
            "download_complete": False,
            "download_attempts": 0
        })

    @classmethod
    async def monitor_downloadqueue(cls):
        while True:
            for item in cls.download_queue:
                if not item["download_complete"] and not item["download_attempts"] > 10:
                    try:
                        LogManager.log_download_live(
                            f"Detected a new live stream in the download queue, starting download task. {item['url']}")
                        await cls.download_livestream(item)
                    except Exception as e:
                        LogManager.log_download_live(
                            f"Error downloading {item['url']}: {e} (attempt {item['download_attempts']})")
                        traceback.print_exc()
            await asyncio.sleep(30)

    @classmethod
    async def monitor_livestreams(cls):
        while True:
            await cls.check_livestream()
            await asyncio.sleep(30)

    @classmethod
    async def download_livestreams(cls):
        LogManager.log_download_live(f"Starting Livestream Downloader for {cls.youtube_source}")
        tasks = [
            cls.monitor_downloadqueue(),
            cls.monitor_livestreams()
        ]
        await asyncio.gather(*tasks)
