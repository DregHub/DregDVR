import asyncio
import traceback
from utils.logging_utils import LogManager, LogLevels
from utils.playlist_manager import PlaylistManager
from utils.index_utils import IndexManager
from config.config_settings import DVR_Config
from dlp.events import DLPEvents
from dlp.helpers import DLPHelpers


class LivestreamDownloader:
    _download_execution_lock = asyncio.Lock()
    Live_DownloadQueue_Dir = None
    Live_UploadQueue_Dir = None
    DownloadFilePrefix = None
    DownloadTimeStampFormat = None
    dlp_max_dlp_download_retries = None
    playlist = PlaylistManager()
    current_videourl = None

    @classmethod
    async def _ensure_initialized(cls):
        """Ensure class variables are initialized with proper instance context."""
        try:
            cls.Live_DownloadQueue_Dir = DVR_Config.get_live_downloadqueue_dir()
            cls.Live_UploadQueue_Dir = DVR_Config.get_live_videos_dir()
            cls.DownloadFilePrefix = await DVR_Config.get_live_downloadprefix()
            cls.DownloadTimeStampFormat = (
                await DVR_Config.get_download_timestamp_format()
            )

            cls.dlp_max_dlp_download_retries = (
                await DVR_Config.get_dlp_max_download_retries()
            )

        except Exception as e:
            LogManager.log_download_live(
                f"Failed to initialize livestream downloader: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def download_started(cls):
        """Update playlist to mark livestream download as started."""
        await cls._update_live_download_stage("Started")

    @classmethod
    async def download_processing(cls):
        """Update playlist to mark livestream download as processing."""
        await cls._update_live_download_stage("Processing")

    @classmethod
    async def download_complete(cls):
        """Update playlist to mark livestream download as complete."""
        await cls._update_live_download_stage("Complete")

    @classmethod
    async def _update_live_download_stage(cls, stage: str):
        """Update the Live_Download_Stage field for the current livestream in the playlist.

        Args:
            stage: The stage value to set (e.g., "Started", "Processing", "Complete")
        """
        try:
            playlist_data = await cls.playlist._load_playlist_data()
            videos = playlist_data.get("Videos", [])
            updated = False

            for item in videos:
                if item.get("URL") == cls.current_videourl:
                    item["Live_Download_Stage"] = stage
                    updated = True
                    break

            if updated:
                await cls.playlist._save_playlist_data(playlist_data)
                LogManager.log_download_live(
                    f"Updated Live_Download_Stage to '{stage}' for {cls.current_videourl}",
                    LogLevels.Info,
                )
            else:
                LogManager.log_download_live(
                    f"Could not find {cls.current_videourl} in playlist to update Live_Download_Stage",
                    LogLevels.Warning,
                )
        except Exception as e:
            LogManager.log_download_live(
                f"Failed to update Live_Download_Stage: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )

    @classmethod
    async def _load_livestreams(cls):
        """Load livestreams from the database that are currently live and not downloaded."""
        await cls._ensure_initialized()

        try:
            instance_name = await cls.playlist._get_instance_name()
            channel_source = await cls.playlist._get_channel_source()

            if not instance_name or not channel_source:
                LogManager.log_download_live(
                    "Cannot load livestreams: instance_name or channel_source is not set",
                    LogLevels.Error,
                )
                return []

            db = await cls.playlist._get_db()
            download_table_name = db.get_playlist_download_table_name(channel_source)

            # Get current download playlist
            current_download_playlist = await db.get_current_download_playlist(
                instance_name
            )

            if not current_download_playlist:
                LogManager.log_download_live(
                    "Cannot load livestreams: current_download_playlist is not set",
                    LogLevels.Error,
                )
                return []

            LogManager.log_download_live(
                f"Looking for livestreams in table {download_table_name} for current playlist: {current_download_playlist} obtained from {channel_source} ",
                LogLevels.Info,
            )

            livestream_entries = await db.get_channel_playlist_entries_where(
                instance_name,
                channel_source,
                live_status="is_live",
                live_download_stage="new",
            )

            livestreams = [
                {
                    "url": entry.get("webpage_url") or entry.get("url"),
                    "unique_id": entry.get("unique_id"),
                    "title": entry.get("title"),
                }
                for entry in livestream_entries
                if entry.get("url")
            ]

            if len(livestreams) > 1:
                LogManager.log_download_live(
                    f"Found {len(livestreams)} active livestreams to download.",
                    LogLevels.Info,
                )
            elif len(livestreams) == 1:
                LogManager.log_download_live(
                    "Found an active livestream to download.", LogLevels.Info
                )

            return livestreams

        except Exception as e:
            LogManager.log_download_live(
                f"Error loading livestreams from database: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            return []

    @classmethod
    async def download_livestream(cls, livestream_url: str):
        """Download a single livestream from the given URL."""
        async with cls._download_execution_lock:
            try:
                # Set the current video URL for tracking
                cls.current_videourl = livestream_url

                # Get index from database instead of playlist file
                instance_name = await cls.playlist._get_instance_name()

                current_index = await IndexManager.get_current_live_index(instance_name)
                await IndexManager.increment_current_live_index(instance_name)
                current_name_template = f"{current_index} {cls.DownloadFilePrefix} {cls.DownloadTimeStampFormat}.%(ext)s"
                dlp_download_opts = {
                    "paths": {
                        "temp": cls.Live_DownloadQueue_Dir,
                        "home": cls.Live_UploadQueue_Dir,
                    },
                    "outtmpl": current_name_template,
                    "live_from_start": True,
                    "downloader_args": {"ffmpeg_i": "-loglevel quiet"},
                    "ignore_no_formats_error": True,  # ← prevents livestream errors from crashing
                    "retries": int(cls.dlp_max_dlp_download_retries),
                    "skip_unavailable_fragments": True,
                    "no_abort_on_error": True,
                    "restrictfilenames": True,
                    "noprogress": False,
                }

                # Get the actual livestream URL and verify it's still live
                try:
                    info = await DLPHelpers.getinfo_with_retry(
                        ydl_opts=dlp_download_opts,
                        url_or_list=livestream_url,
                        log_table_name=LogManager.table_download_live,
                        log_warnings_and_above_only=False,
                        desired_dicts=["live_status", "is_live", "webpage_url"],
                        thread_number=1,
                    )

                    if info.get("live_status") in ("is_live",):
                        # Attach the progress hooks and download the livestream
                        cls.dlp_events = DLPEvents(
                            cls.current_videourl,
                            LogManager.table_download_live,
                            cls.download_started,
                            cls.download_complete,
                            cls.download_processing,
                        )
                        dlp_download_opts["progress_hooks"] = [
                            cls.dlp_events.on_progress
                        ]

                        # Download livestream with timeout disabled (livestreams can be long)
                        await DLPHelpers.download_with_retry(
                            ydl_opts=dlp_download_opts,
                            url_or_list=cls.current_videourl,
                            timeout_enabled=False,
                            log_table_name=LogManager.table_download_live,
                            log_warnings_and_above_only=False,
                            thread_number=1,
                        )

                        LogManager.log_download_live(
                            f"Download completed for {cls.current_videourl}",
                            LogLevels.Info,
                        )
                        # Mark as downloaded in the playlist
                        await cls.playlist.mark_as_downloaded(cls.current_videourl)
                    else:
                        skipped_video = info.get("webpage_url") or livestream_url
                        skipped_status = info.get("live_status")
                        LogManager.log_download_live(
                            f"Skipping {skipped_video} as it has an unsupported live status {skipped_status}",
                            LogLevels.Info,
                        )
                except Exception as e:
                    LogManager.log_download_live(
                        f"Exception while downloading livestream {livestream_url}: {e}\n{traceback.format_exc()}",
                        LogLevels.Error,
                    )
                    raise

            except Exception as e:
                LogManager.log_download_live(
                    f"Exception while downloading livestream {livestream_url}: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )

    @classmethod
    async def download_livestreams(cls):
        """Main loop: load livestreams from playlist and process them."""
        await cls._ensure_initialized()
        LogManager.log_download_live(f"Starting Livestream Downloader", LogLevels.Info)
        while True:
            try:
                livestreams = await cls._load_livestreams()
                livestream_count = len(livestreams)

                LogManager.log_download_live(f"starting live", LogLevels.Info)

                if livestream_count > 0:
                    LogManager.log_download_live(
                        f"Processing {livestream_count} active livestream(s).",
                        LogLevels.Info,
                    )

                    for livestream in livestreams:
                        try:
                            url = livestream.get("url")
                            LogManager.log_download_live(
                                f"Starting download for livestream: {url}",
                                LogLevels.Info,
                            )
                            await cls.download_livestream(url)
                        except Exception as e:
                            LogManager.log_download_live(
                                f"Error downloading livestream {livestream.get('url')}: {e}\n{traceback.format_exc()}",
                                LogLevels.Error,
                            )
                            # Continue to next livestream on error
                            continue
                else:
                    LogManager.log_download_live(
                        "No active livestreams to download at this time.",
                        LogLevels.Info,
                    )

                LogManager.log_download_live(
                    f"Download cycle complete. Waiting 1 minute before checking for new livestreams.",
                    LogLevels.Info,
                )
                await asyncio.sleep(60)

            except Exception as e:
                LogManager.log_download_live(
                    f"Exception in download_livestreams: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )
                try:
                    await asyncio.sleep(30)
                except Exception:
                    LogManager.log_download_live(
                        "Sleep interrupted in download_livestreams loop",
                        LogLevels.Error,
                    )
                # Continue to next iteration after exception
