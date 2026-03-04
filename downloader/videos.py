import asyncio
import os
import traceback
from yt_dlp import YoutubeDL
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from downloader.playlist import PlaylistManager
from utils.index_utils import IndexManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from utils.dlp_utils import download_with_retry, getinfo_with_retry


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

    youtube_channel = Account_Config.get_youtube_handle()

    @classmethod
    async def download_videos(cls):
        LogManager.log_download_posted(
            f"Starting Video & Shorts Downloader for {cls.youtube_channel}"
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
                await cls.playlist.generate_download_List()

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

                            # Build yt-dlp options
                            ydl_opts = {
                                "paths": {
                                    "temp": cls.Posted_DownloadQueue_Dir,
                                    "home": cls.Posted_UploadQueue_Dir,
                                },
                                "outtmpl": CurrentDownloadFile,
                                "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                                "restrictfilenames": True,
                                "fragment_retries": int(cls.dlp_max_fragment_retries),
                                "retries": int(cls.dlp_max_dlp_download_retries),
                                "ignore_no_formats_error": True,  # ← prevents livestream errors from crashing
                            }

                            try:
                                if cls.dlp_keep_fragments == "true":
                                    ydl_opts["keep_fragments"] = True

                                if cls.dlp_verbose == "true":
                                    ydl_opts["verbose"] = True

                                info = await getinfo_with_retry(
                                    ydl_opts, url, LogManager.DOWNLOAD_POSTED_LOG_FILE
                                )
                                live_status = info.get("live_status")

                                if live_status in ["is_live", "is_upcoming"]:
                                    LogManager.log_download_posted(
                                        f"{url} is a live or upcoming stream live_status = {live_status} , skipping download."
                                    )
                                elif live_status in ["post_live", "was_live"]:
                                    LogManager.log_download_posted(
                                        f"{url} is a past livestream live_status = {live_status} , skipping download because this is handled by the livestream downloader."
                                    )
                                elif live_status == "not_live":
                                    try:
                                        LogManager.log_download_posted(
                                            f"{url} is a published video live_status = {live_status} , Proceding to download."
                                        )
                                        await download_with_retry(
                                            ydl_opts,
                                            [url],
                                            LogManager.DOWNLOAD_POSTED_LOG_FILE,
                                        )
                                    except Exception:
                                        # Let outer exception handler log details
                                        raise
                                    LogManager.log_download_posted(
                                        f"Posted Video {url} Downloaded Successfully"
                                    )
                                    await cls.playlist.mark_as_downloaded(url)
                                else:
                                    LogManager.log_download_posted(
                                        f"{url} Has an unknown live status type live_status = {live_status} skipping download"
                                    )

                            except Exception as e:
                                LogManager.log_download_posted(
                                    f"yt-dlp python API failed for {url}: {e}\n{traceback.format_exc()}"
                                )

                        if len(urls) > 1:
                            LogManager.log_download_posted(
                                f"Finished processing all {len(urls)} new videos/shorts from channel {cls.youtube_channel}"
                            )
                        elif len(urls) == 1:
                            LogManager.log_download_posted(
                                f"Finished processing the new video/short from channel {cls.youtube_channel}"
                            )

                        LogManager.log_download_posted(
                            f"Download cycle complete. Waiting 1 minute before checking {cls.youtube_channel} for new videos/shorts."
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
