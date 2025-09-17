import asyncio
import os
import csv
import traceback
import shlex
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess
from utils.file_utils import delete_file
from downloader.playlist import PlaylistManager
from utils.index_utils import IndexManager
from config import Config


class VideoDownloader:
    playlist = PlaylistManager()
    DownloadTimeStampFormat = Config.get_download_timestamp_format()
    posted_downloadprefix = Config.get_posted_downloadprefix()
    playlist_dir = Config.get_posted_playlists_dir()
    Posted_DownloadQueue_Dir = Config.get_posted_downloadqueue_dir()
    Posted_UploadQueue_Dir = Config.get_posted_uploadqueue_dir()
    posted_download_list = Config.get_posted_download_list()
    delta_playlist = Config.get_posted_delta_playlist()
    persistent_playlist = Config.get_posted_persistent_playlist()
    dlp_verbose = Config.get_verbose_dlp_mode()
    dlp_no_progress = Config.no_progress_dlp_downloads()
    dlp_keep_fragments = Config.get_keep_fragments_dlp_downloads()
    dlp_max_fragment_retry = Config.get_max_dlp_fragment_retries()
    dlp_max_title_chars = Config.get_max_title_filename_chars()
    youtube_source = Config.get_youtube_source()
    youtube_handle = Config.get_youtube_handle()

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

            #LogManager.log_download_posted(f"Reading {cls.persistent_playlist}.")
            with open(cls.persistent_playlist, "r", encoding="utf-8") as in_file:
                reader = csv.reader(in_file)
                headers = next(reader, None)
                for row in reader:
                    if len(row) < 4:
                        #LogManager.log_download_posted(f"Row with missing columns found: {row}. Padding to 4 columns.")
                        row += [""] * (4 - len(row))
                    if row[3] == "0":
                        #LogManager.log_download_posted(f"Queued for download: {row[2]}")
                        urls_to_download.append(row[2])
                    rows.append(row)

            if urls_to_download:
                #LogManager.log_download_posted(f"Writing {len(urls_to_download)} URLs to {cls.posted_download_list}.")
                with open(cls.posted_download_list, "w", encoding="utf-8") as out_file:
                    for url in urls_to_download:
                        out_file.write(url + "\n")
            elif os.path.exists(cls.posted_download_list):
                #LogManager.log_download_posted(f"No URLs to download. Deleting {cls.posted_download_list}.")
                delete_file(cls.posted_download_list, LogManager.DOWNLOAD_POSTED_LOG_FILE)

            #LogManager.log_download_posted(f"Writing updated rows back to {cls.persistent_playlist}.")
            with open(cls.persistent_playlist, "w", newline="", encoding="utf-8") as out_file:
                writer = csv.writer(out_file)
                if headers:
                    writer.writerow(headers)
                writer.writerows(rows)

        except Exception as e:
            LogManager.log_download_posted(f"Failed in generate_download_List:  {e}\n{traceback.format_exc()}")

    @classmethod
    async def mark_as_downloaded(cls, url):
        try:
            rows = []
            updated = False
            with open(cls.persistent_playlist, "r", encoding="utf-8") as in_file:
                reader = csv.reader(in_file)
                headers = next(reader, None)
                for row in reader:
                    if len(row) < 4:
                        row += [""] * (4 - len(row))
                    if row[2] == url and row[3] == "0":
                        row[3] = "1"
                        updated = True
                    rows.append(row)
            if updated:
                with open(cls.persistent_playlist, "w", newline="", encoding="utf-8") as out_file:
                    writer = csv.writer(out_file)
                    if headers:
                        writer.writerow(headers)
                    writer.writerows(rows)
        except Exception as e:
            LogManager.log_download_posted(f"Failed to mark as downloaded: {e}\n{traceback.format_exc()}")

    @classmethod
    async def download_videos(cls):
        LogManager.log_download_posted(f"Starting Video & Shorts Downloader for {cls.youtube_source}")
        while True:
            try:
                # Clean up the download old file if it exists
                if os.path.exists(cls.posted_download_list):
                    delete_file(cls.posted_download_list, LogManager.DOWNLOAD_POSTED_LOG_FILE)

                await cls.playlist.download_channel_playlist()
                await cls.playlist.merge_delta_playlist()
                await cls.generate_download_List()
                
                if os.path.exists(cls.posted_download_list):
                    with open(cls.posted_download_list, "r", encoding="utf-8") as in_file:
                        urls = [line.strip() for line in in_file if line.strip()]

                        if len(urls) > 1:
                            LogManager.log_download_posted(f"Found {len(urls)} new videos/shorts to download.")
                        elif len(urls) == 1:
                            LogManager.log_download_posted(f"Found a new video/short to download.")

                        for url in urls:
                            LogManager.log_download_posted(f"Found new video/short to download: {url}")
                            CurrentIndex = IndexManager.find_new_posted_index(LogManager.DOWNLOAD_POSTED_LOG_FILE)
                            CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"

                            command = [
                                "yt-dlp",
                                f"--paths temp:{cls.Posted_DownloadQueue_Dir}",
                                "--match-filter live_status=not_live",
                                "--output",
                                f'"{CurrentDownloadFile}"',
                                "--downloader-args", f'"ffmpeg_i:-loglevel quiet"',
                                "--restrict-filenames",
                                f'"{url}"',
                            ]

                            if (cls.dlp_verbose == "true"):
                                command.append("--verbose")

                            if cls.dlp_no_progress == "true":
                                for filt in Config.get_no_progress_dlp_filters():
                                    if filt not in LogManager.DOWNLOAD_POSTED_LOG_FILTER:
                                        LogManager.DOWNLOAD_POSTED_LOG_FILTER.append(filt)

                            MiniLog, exit_code = await run_subprocess(
                                command,
                                LogManager.DOWNLOAD_POSTED_LOG_FILE,
                                "yt-dlp video/shorts playlist extraction failed",
                                "Exception in download_videos",
                                cls.Posted_UploadQueue_Dir
                            )

                            if exit_code == 0:
                                LogManager.log_download_posted(f"Posted Video {url} Downloaded Successfully.")
                                await cls.mark_as_downloaded(url)
                            else:
                                LogManager.log_download_posted(f"yt-dlp failed for {url} with exit code {exit_code}")

                        if len(urls) > 1:
                            LogManager.log_download_posted(f"Finished downloading all {len(urls)} new videos/shorts from channel {cls.youtube_handle}")
                        elif len(urls) == 1:
                            LogManager.log_download_posted(f"Finished downloading the new video/short from channel {cls.youtube_handle}")

                        LogManager.log_download_posted(f"Download cycle complete. Waiting 1 minute before checking {cls.youtube_handle} for new videos/shorts.")
                        await asyncio.sleep(60)
                else:
                    # No new videos to download
                    await asyncio.sleep(360)
            except Exception as e:
                LogManager.log_download_posted(f"Exception in download_videos:  {e}\n{traceback.format_exc()}")
                await asyncio.sleep(30)
