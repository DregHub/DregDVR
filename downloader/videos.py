import asyncio
import os
import csv
import traceback
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess
from config import Config
from utils.file_utils import delete_file
from downloader.playlist import PlaylistManager
from utils.index_utils import IndexManager


class VideoDownloader:
    playlist = PlaylistManager()
    DownloadTimeStampFormat = Config.get_value("YT_DownloadSettings", "DownloadTimeStampFormat")
    playlist_dir = os.path.join(Config.ProjRoot_Dir, Config.get_value("Directories", "posted_playlists_dir"))
    Posted_DownloadQueue_Dir = os.path.join(
        Config.ProjRoot_Dir, Config.get_value("Directories", "posted_downloadqueue_dir"))
    Posted_UploadQueue_Dir = os.path.join(
        Config.ProjRoot_Dir, Config.get_value("Directories", "posted_uploadqueue_dir"))
    posted_download_list = os.path.join(playlist_dir, "_Download_Playlist.txt")
    delta_playlist = os.path.join(playlist_dir, "_Delta_Playlist.csv")
    persistent_playlist = os.path.join(playlist_dir, "_Persistent_Playlist.csv")

    @classmethod
    async def generate_download_List(cls):
        try:
            open(cls.posted_download_list, "w").close()
            rows = []
            urls_to_download = []
            # Create persistent_playlist if it does not exist
            if not os.path.exists(cls.persistent_playlist):
                with open(cls.persistent_playlist, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["UniqueID", "Title", "URL", "Downloaded"])

            with open(cls.persistent_playlist, "r", encoding="utf-8") as infile:
                reader = csv.reader(infile)
                headers = next(reader, None)
                for row in reader:
                    if len(row) < 4:
                        row += [""] * (4 - len(row))
                    if row[3] == "0":
                        urls_to_download.append(row[2])
                        row[3] = "1"
                    rows.append(row)

            if urls_to_download:
                with open(cls.posted_download_list, "w", encoding="utf-8") as outfile:
                    for url in urls_to_download:
                        outfile.write(url + "\n")
            else:
                if os.path.exists(cls.posted_download_list):
                    delete_file(cls.posted_download_list, LogManager.DOWNLOAD_POSTED_LOG_FILE)

            with open(cls.persistent_playlist, "w", newline="", encoding="utf-8") as outfile:
                writer = csv.writer(outfile)
                if headers:
                    writer.writerow(headers)
                writer.writerows(rows)

            LogManager.log_download_posted(
                f"Exported {len(urls_to_download)} URLs to Download.txt and updated Uploaded status.")
        except Exception as e:
            LogManager.log_download_posted(f"Failed in generate_download_List:  {e}\n{traceback.format_exc()}")

    @classmethod
    async def download_videos(cls):
        while True:
            try:
                await cls.playlist.download_channel_playlist()
                await cls.playlist.merge_delta_playlist()
                await cls.generate_download_List()

                if os.path.exists(cls.posted_download_list):
                    with open(cls.posted_download_list, "r", encoding="utf-8") as infile:
                        urls = [line.strip() for line in infile if line.strip()]
                        for url in urls:
                            CurrentIndex = IndexManager.get_index("posted_index", LogManager.DOWNLOAD_POSTED_LOG_FILE)
                            CurrentDownloadFile = f"999999{CurrentIndex} %(title)s {cls.DownloadTimeStampFormat}.%(ext)s"
                            command = [
                                "yt-dlp",
                                f"--paths temp:{cls.Posted_DownloadQueue_Dir}",
                                "--match-filter live_status=not_live",
                                "--output",
                                f'"{CurrentDownloadFile}"',
                                str(url)
                                # ,"-v"
                            ]

                            MiniLog = await run_subprocess(
                                command,
                                LogManager.DOWNLOAD_POSTED_LOG_FILE,
                                "yt-dlp video/shorts playlist extraction failed",
                                "Exception in download_videos",
                                cls.Posted_UploadQueue_Dir
                            )

                            if not MiniLog:
                                LogManager.log_download_posted(
                                    "No output from yt-dlp, possibly no new videos or shorts available.")
                            else:
                                LogManager.log_download_posted(f"Published video {url} Downloaded Successfully.")
                                IndexManager.increment_index("posted_index", LogManager.DOWNLOAD_POSTED_LOG_FILE)

                if os.path.exists(cls.posted_download_list):
                    delete_file(cls.posted_download_list, LogManager.DOWNLOAD_POSTED_LOG_FILE)

                await asyncio.sleep(60)

            except Exception as e:
                LogManager.log_download_posted(f"Exception in download_videos:  {e}\n{traceback.format_exc()}")
                await asyncio.sleep(30)
