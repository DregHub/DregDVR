import asyncio
import os
import csv
import traceback
from yt_dlp import YoutubeDL
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from downloader.playlist import PlaylistManager
from utils.index_utils import IndexManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from utils.dlp_utils import DLPEvents
from yt_dlp.utils import match_filter_func


class VideoDownloader:
    playlist = PlaylistManager()
    DownloadTimeStampFormat = DVR_Config.get_download_timestamp_format()
    posted_downloadprefix = Account_Config.get_posted_downloadprefix()
    playlist_dir = DVR_Config.get_posted_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    Posted_UploadQueue_Dir = DVR_Config.get_posted_uploadqueue_dir()
    posted_download_list = DVR_Config.get_posted_download_list()
    delta_playlist = DVR_Config.get_posted_delta_playlist()
    persistent_playlist = DVR_Config.get_posted_persistent_playlist()
    dlp_verbose = DVR_Config.get_verbose_dlp_mode()
    dlp_no_progress = DVR_Config.no_progress_dlp_downloads()
    dlp_keep_fragments = DVR_Config.get_keep_fragments_dlp_downloads()
    dlp_max_fragment_retries = DVR_Config.get_max_dlp_fragment_retries()
    dlp_max_dlp_download_retries = DVR_Config.get_max_dlp_download_retries()
    dlp_max_title_chars = DVR_Config.get_max_title_filename_chars()
    youtube_source = Account_Config.get_youtube_source()
    youtube_handle = Account_Config.get_youtube_handle()
    YT_Cookies_File = DVR_Config.get_yt_cookies_file()

    @classmethod
    def download_started(cls):
        LogManager.log_download_posted(
            f"VIDEO DOWNLOAD START EVENT {cls.youtube_source}"
        )

    @classmethod
    def download_processing(cls):
        LogManager.log_download_posted(
            f"VIDEO DOWNLOAD PROCESSING EVENT {cls.youtube_source}"
        )

    @classmethod
    def download_complete(cls):
        LogManager.log_download_posted(
            f"VIDEO DOWNLOAD COMPLETE EVENT {cls.youtube_source}"
        )

    @classmethod
    async def generate_download_List(cls):
        try:
            open(cls.posted_download_list, "w").close()
            rows = []
            urls_to_download = []
            # Create persistent_playlist if it does not exist
            if not os.path.exists(cls.persistent_playlist):
                with open(
                    cls.persistent_playlist, "w", encoding="utf-8", newline=""
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(["UniqueID", "Title", "URL", "Downloaded"])

            # LogManager.log_download_posted(f"Reading {cls.persistent_playlist}.")
            with open(cls.persistent_playlist, "r", encoding="utf-8") as in_file:
                reader = csv.reader(in_file)
                headers = next(reader, None)
                for row in reader:
                    if len(row) < 4:
                        LogManager.log_download_posted(
                            f"Row with missing columns found: {row}. Padding to 4 columns."
                        )
                        row += [""] * (4 - len(row))
                    if row[3] == "0":
                        urls_to_download.append(row[2])
                    rows.append(row)

            if urls_to_download:
                # LogManager.log_download_posted(f"Writing {len(urls_to_download)} URLs to {cls.posted_download_list}.")
                with open(cls.posted_download_list, "w", encoding="utf-8") as out_file:
                    for url in urls_to_download:
                        out_file.write(url + "\n")
            elif os.path.exists(cls.posted_download_list):
                # LogManager.log_download_posted(f"No URLs to download. Deleting {cls.posted_download_list}.")
                FileManager.delete_file(
                    cls.posted_download_list, LogManager.DOWNLOAD_POSTED_LOG_FILE
                )

            # LogManager.log_download_posted(f"Writing updated rows back to {cls.persistent_playlist}.")
            with open(
                cls.persistent_playlist, "w", newline="", encoding="utf-8"
            ) as out_file:
                writer = csv.writer(out_file)
                if headers:
                    writer.writerow(headers)
                writer.writerows(rows)

        except Exception as e:
            LogManager.log_download_posted(
                f"Failed in generate_download_List:  {e}\n{traceback.format_exc()}"
            )

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
                with open(
                    cls.persistent_playlist, "w", newline="", encoding="utf-8"
                ) as out_file:
                    writer = csv.writer(out_file)
                    if headers:
                        writer.writerow(headers)
                    writer.writerows(rows)
        except Exception as e:
            LogManager.log_download_posted(
                f"Failed to mark as downloaded: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    async def download_videos(cls):
        LogManager.log_download_posted(
            f"Starting Video & Shorts Downloader for {cls.youtube_source}"
        )

        while True:
            try:
                # Clean up the download old file if it exists
                if os.path.exists(cls.posted_download_list):
                    FileManager.delete_file(
                        cls.posted_download_list, LogManager.DOWNLOAD_POSTED_LOG_FILE
                    )

                await cls.playlist.download_channel_playlist()
                await cls.playlist.merge_delta_playlist()
                await cls.generate_download_List()

                if os.path.exists(cls.posted_download_list):
                    with open(
                        cls.posted_download_list, "r", encoding="utf-8"
                    ) as in_file:
                        urls = [line.strip() for line in in_file if line.strip()]
                        if len(urls) > 1:
                            LogManager.log_download_posted(
                                f"Found {len(urls)} new videos/shorts to download."
                            )
                        elif len(urls) == 1:
                            LogManager.log_download_posted(
                                "Found a new video/short to download."
                            )

                        for url in urls:
                            CurrentIndex = IndexManager.find_new_posted_index(
                                LogManager.DOWNLOAD_POSTED_LOG_FILE
                            )
                            CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"
                            cls.dlp_events = DLPEvents(
                                url,
                                LogManager.DOWNLOAD_POSTED_LOG_FILE,
                                cls.download_started,
                                cls.download_complete,
                                cls.download_processing,
                            )

                            # Build yt-dlp options
                            ydl_opts = {
                                "paths": {
                                    "temp": cls.Posted_DownloadQueue_Dir,
                                    "home": cls.Posted_UploadQueue_Dir,
                                },
                                # Add was_live to the exclusion filter to prevent downloading livestreams again
                                "match_filter": match_filter_func(
                                    "live_status!=is_live & live_status!=is_upcoming & live_status!=was_live"
                                ),
                                "outtmpl": CurrentDownloadFile,
                                "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                                "restrictfilenames": True,
                                "fragment_retries": int(cls.dlp_max_fragment_retries),
                                "retries": int(cls.dlp_max_dlp_download_retries),
                                "ignore_no_formats_error": True,  # ← prevents livestream errors from crashing
                                "progress_hooks": [cls.dlp_events.on_progress],
                            }

                            # Use cookies file if configured and present
                            if cls.YT_Cookies_File and os.path.exists(
                                cls.YT_Cookies_File
                            ):
                                ydl_opts["cookiefile"] = cls.YT_Cookies_File

                            try:
                                if cls.dlp_keep_fragments == "true":
                                    ydl_opts["keep_fragments"] = True

                                if cls.dlp_verbose == "true":
                                    ydl_opts["verbose"] = True

                                with YoutubeDL(
                                    {"quiet": True, "ignore_no_formats_error": True}
                                ) as ydl:
                                    info = ydl.extract_info(url, download=False)

                                if info.get("live_status") in (
                                    "is_live",
                                    "is_upcoming",
                                ):
                                    LogManager.log_download_posted(
                                        f"{url} is a live or upcoming stream, skipping download."
                                    )
                                elif info.get("live_status") == "was_live":
                                    LogManager.log_download_posted(
                                        f"{url} is a past livestream, skipping download because this is handled by the livestream downloader."
                                    )
                                else:
                                    try:
                                        LogManager.log_download_posted(
                                            f"{url} is a published video, Proceding to download."
                                        )
                                        with YoutubeDL(ydl_opts) as ydl:
                                            await asyncio.to_thread(ydl.download, [url])
                                    except Exception as e:
                                        msg = str(e)
                                        if (
                                            "429" not in msg
                                            and "rate limit" not in msg.lower()
                                            and "too many requests" not in msg.lower()
                                            or "cookiefile" not in ydl_opts
                                        ):
                                            raise

                                        LogManager.log_download_posted(
                                            "Rate limit detected, retrying download without cookiefile"
                                        )
                                        ydl_opts_no_cookie = dict(ydl_opts)
                                        ydl_opts_no_cookie.pop("cookiefile", None)
                                        with YoutubeDL(ydl_opts_no_cookie) as ydl2:
                                            await asyncio.to_thread(
                                                ydl2.download, [url]
                                            )
                                    LogManager.log_download_posted(
                                        f"Posted Video {url} Downloaded Successfully to {cls.Posted_DownloadQueue_Dir} as {CurrentDownloadFile}"
                                    )
                                    await cls.mark_as_downloaded(url)

                            except Exception as e:
                                LogManager.log_download_posted(
                                    f"yt-dlp python API failed for {url}: {e}\n{traceback.format_exc()}"
                                )

                        if len(urls) > 1:
                            LogManager.log_download_posted(
                                f"Finished processing all {len(urls)} new videos/shorts from channel {cls.youtube_handle}"
                            )
                        elif len(urls) == 1:
                            LogManager.log_download_posted(
                                f"Finished processing the new video/short from channel {cls.youtube_handle}"
                            )

                        LogManager.log_download_posted(
                            f"Download cycle complete. Waiting 1 minute before checking {cls.youtube_handle} for new videos/shorts."
                        )
                        await asyncio.sleep(60)
                else:
                    # No new videos to download
                    await asyncio.sleep(360)
            except Exception as e:
                LogManager.log_download_posted(
                    f"Exception in download_videos:  {e}\n{traceback.format_exc()}"
                )
                await asyncio.sleep(30)
