import asyncio
import os
import traceback
import json
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from downloader.playlist import PlaylistManager
from utils.index_utils import IndexManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
from dlp.helpers import DLPHelpers


class VideosPlaylistManager(PlaylistManager):
    """Videos-specific version of PlaylistManager with independent channel configuration."""
    
    # Initialize with youtube source instead of caption source
    _youtube_source = Account_Config.get_youtube_source()
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    channel_playlist = DVR_Config.get_channel_playlist(_youtube_source)
    channel = Account_Config.build_youtube_url(_youtube_source)
    videos_url = channel.rstrip("/") + "/videos"
    shorts_url = channel.rstrip("/") + "/shorts"
    channel_playlist_log_file = DVR_Config.get_channel_playlist_log_file(_youtube_source)
    
    _update_playlist_lock = asyncio.Lock()


class VideoDownloader:
    # Use the independent VideosPlaylistManager
    playlist = VideosPlaylistManager()
    DownloadTimeStampFormat = DVR_Config.get_download_timestamp_format()
    posted_downloadprefix = Account_Config.get_posted_downloadprefix()
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    Posted_UploadQueue_Dir = DVR_Config.get_posted_uploadqueue_dir()
    channel_playlist = VideosPlaylistManager.channel_playlist
    dlp_max_dlp_download_retries = DVR_Config.get_max_dlp_download_retries()
    dlp_max_title_chars = DVR_Config.get_max_title_filename_chars()

    youtube_channel = VideosPlaylistManager.channel

    @classmethod
    async def _load_urls(cls):
        # Otherwise load persistent JSON playlist and return not-yet-downloaded URLs
        try:
            playlist_data = await asyncio.to_thread(
                lambda: json.load(open(cls.channel_playlist, "r", encoding="utf-8"))
            )
        except Exception:
            playlist_data = []

        urls = [
            item.get("URL")
            for item in playlist_data
            if item.get("URL") and not item.get("Downloaded_Video", False)
        ]

        if len(urls) > 1:
            LogManager.log_download_posted(
                f"Found {len(urls)} new videos/shorts to download."
            )
        elif len(urls) == 1:
            LogManager.log_download_posted("Found a new video/short to download.")

        return urls

    @classmethod
    def _build_ydl_opts(cls, out_template: str):
        return {
            "paths": {
                "temp": cls.Posted_DownloadQueue_Dir,
                "home": cls.Posted_UploadQueue_Dir,
            },
            "outtmpl": out_template,
            "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
            "restrictfilenames": True,
            "retries": int(cls.dlp_max_dlp_download_retries),
            "ignore_no_formats_error": True,
        }

    @classmethod
    async def _process_url(cls, url: str):
        CurrentIndex = IndexManager.find_new_posted_index(
            LogManager.DOWNLOAD_POSTED_LOG_FILE
        )
        CurrentDownloadFile = f"{cls.posted_downloadprefix}{CurrentIndex} %(title).{cls.dlp_max_title_chars}s {cls.DownloadTimeStampFormat}.%(ext)s"
        ydl_opts = cls._build_ydl_opts(CurrentDownloadFile)

        try:
            LogManager.log_download_posted(
                    f"Launching getinfo_with_retry for URL: {url} to determine live status before downloading."
            )
            info = await DLPHelpers.getinfo_with_retry(
                ydl_opts, url, LogManager.DOWNLOAD_POSTED_LOG_FILE
            )
            
            # Handle case where info is None
            if info is None:
                LogManager.log_download_posted(
                    f"{url} - Failed to retrieve video info, skipping download"
                )
                return
            
            live_status = info.get("live_status") if isinstance(info, dict) else None

            if live_status in ["is_live", "is_upcoming"]:
                LogManager.log_download_posted(
                    f"{url} is a live or upcoming stream live_status = {live_status} , skipping download."
                )
            elif live_status in ["post_live", "was_live"]:
                LogManager.log_download_posted(
                    f"{url} is a past livestream live_status = {live_status} , skipping download because this is handled by the livestream downloader."
                )
            elif live_status == "not_live":
                LogManager.log_download_posted(
                    f"{url} is a published video live_status = {live_status} , Proceding to download."
                )
                LogManager.log_download_posted(
                    f"Launching download_with_retry for URL: {url} with ydl_opts: {ydl_opts}"
                )
                await DLPHelpers.download_with_retry(
                    ydl_opts, [url], LogManager.DOWNLOAD_POSTED_LOG_FILE
                )
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

        # Finishing per-url housekeeping
        LogManager.log_download_posted(
            f"Finished processing the new video/short from channel {cls.youtube_channel}"
        )

    @classmethod
    async def download_videos(cls):
        LogManager.log_download_posted(
            f"Starting Video & Shorts Downloader for {cls.youtube_channel}"
        )
        while True:
            try:
                await cls.playlist.update_channel_playlist()

                urls = await cls._load_urls()

                for url in urls:
                    await cls._process_url(url)

                LogManager.log_download_posted(
                    f"Download cycle complete. Waiting 1 minute before checking {cls.youtube_channel} for new videos/shorts."
                )
                await asyncio.sleep(60)

            except Exception as e:
                LogManager.log_download_posted(
                    f"Exception in download_videos:  {e}\n{traceback.format_exc()}"
                )
                try:
                    await asyncio.sleep(30)
                except Exception:
                    LogManager.log_download_posted(
                        "Sleep interrupted in download_videos loop"
                    )


