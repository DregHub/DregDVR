import asyncio
import traceback
from utils.logging_utils import LogManager, LogLevels
from dlp.helpers import DLPHelpers
from config.config_settings import DVR_Config


class RecoveryDownloader:
    _recovery_lock = asyncio.Lock()
    # Lazy-loaded on first use in _ensure_initialized()
    Live_DownloadRecovery_dir = None
    DownloadFilePrefix = None
    DownloadTimeStampFormat = None
    dlp_max_fragment_retry = None
    dlp_max_dlp_download_retries = None
    dlp_max_title_chars = None

    # Recovery queue: list of dicts with url, filename, download_complete, and recovery_attempts
    recoveryqueue = []

    @classmethod
    async def _ensure_initialized(cls):
        """Lazy-load configuration values from database."""
        if cls.Live_DownloadRecovery_dir is not None:
            return  # Already initialized

        cls.Live_DownloadRecovery_dir = DVR_Config.get_live_downloadrecovery_dir()
        cls.DownloadFilePrefix = await DVR_Config.get_live_downloadprefix()
        cls.DownloadTimeStampFormat = await DVR_Config.get_download_timestamp_format()
        cls.dlp_max_fragment_retry = await DVR_Config.get_dlp_max_fragment_retries()
        cls.dlp_max_dlp_download_retries = (
            await DVR_Config.get_dlp_max_download_retries()
        )
        cls.dlp_max_title_chars = (
            await DVR_Config.get_dlp_truncate_title_after_x_chars()
        )

    @classmethod
    async def _mark_Recovery_Download_Started(cls, url):
        """Mark that recovery processing has started for this video."""
        try:
            # Import PlaylistManager here to avoid circular imports
            from utils.playlist_manager import PlaylistManager

            # Get instance context
            instance_name = await PlaylistManager._get_instance_name()
            channel_source = await PlaylistManager._get_channel_source()

            if not instance_name or not channel_source:
                LogManager.log_download_live_recovery(
                    "Cannot mark recovery as started: instance_name or channel_source is not set",
                    LogLevels.Warning,
                )
                return

            # Get database and update the field
            db = await PlaylistManager._get_db()
            await db.update_channel_playlist_entry_field(
                instance_name, channel_source, url, "recovery_download_started", 1
            )
        except Exception as e:
            LogManager.log_download_live_recovery(
                f"Error marking recovery as started for {url}: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    def _generate_recovery_filename(cls, item):
        """Generate recovery filename based on playlist item data."""
        try:
            # Use the same naming pattern as livestream downloader
            current_index = (
                item.get("Video_Download_Attempts", 0) + 1
            )  # Use attempt count as index
            return f"{current_index} {cls.DownloadFilePrefix} {cls.DownloadTimeStampFormat}.%(ext)s"
        except Exception:
            # Fallback filename
            return f"recovery_{item.get('unique_id', 'unknown')}_{cls.DownloadTimeStampFormat}.%(ext)s"

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
            LogManager.log_core(traceback.format_exc())

    @classmethod
    async def monitor_recoveryqueue(cls):
        """Monitor playlist for livestreams that have reached Processing or Complete stage and start recovery."""
        await cls._ensure_initialized()
        LogManager.log_download_live_recovery(f"Starting Live Recovery Downloader")

        # Import PlaylistManager here to avoid circular imports
        from utils.playlist_manager import PlaylistManager

        while True:
            try:
                async with cls._recovery_lock:
                    # Get instance context
                    instance_name = await PlaylistManager._get_instance_name()
                    channel_source = await PlaylistManager._get_channel_source()

                    if not instance_name or not channel_source:
                        LogManager.log_download_live_recovery(
                            "Cannot get instance context: instance_name or channel_source is not set",
                            LogLevels.Warning,
                        )
                        await asyncio.sleep(60)
                        continue

                    # Get download table name for current instance
                    db = await PlaylistManager._get_db()
                    download_table_name = db.get_playlist_download_table_name(
                        channel_source
                    )

                    # Get current download playlist
                    current_download_playlist = await db.get_current_download_playlist(
                        instance_name
                    )

                    if not current_download_playlist:
                        LogManager.log_download_live_recovery(
                            "Cannot get recovery entries: current_download_playlist is not set",
                            LogLevels.Warning,
                        )
                        await asyncio.sleep(60)
                        continue

                    LogManager.log_download_live_recovery(
                        f"Scanning download table: {download_table_name} for current playlist: {current_download_playlist} for instance: {instance_name}",
                        LogLevels.Info,
                    )

                    # Query for entries that need recovery processing
                    recovery_entries = await db.get_channel_playlist_entries_where(
                        instance_name,
                        channel_source,
                        live_download_stage="Processing",
                    )

                    # Also query for entries with Complete stage
                    complete_entries = await db.get_channel_playlist_entries_where(
                        instance_name,
                        channel_source,
                        live_download_stage="Complete",
                    )

                    # Combine and filter results
                    all_entries = recovery_entries + complete_entries
                    filtered_entries = [
                        entry
                        for entry in all_entries
                        if entry.get("was_live", False)
                        and entry.get("recovery_download_started") is None
                    ]

                    for item in filtered_entries:
                        try:
                            url = item.get("webpage_url") or item.get("url")
                            if url:
                                # Mark recovery as started
                                await cls._mark_Recovery_Download_Started(url)

                                # Create recovery item for processing
                                recovery_item = {
                                    "url": url,
                                    "filename": cls._generate_recovery_filename(item),
                                    "download_complete": False,
                                    "recovery_attempts": 0,
                                }

                                LogManager.log_download_live_recovery(
                                    f"Starting recovery processing for {url}"
                                )

                                # Check if stream is still live
                                is_still_live = await cls.check_recovery_livestream(
                                    recovery_item
                                )

                                if not is_still_live:
                                    # Stream is ready, proceed with download
                                    await cls.download_recovery_livestream_content(
                                        recovery_item
                                    )
                                else:
                                    LogManager.log_download_live_recovery(
                                        f"Skipping recovery for {url}: stream is still live"
                                    )

                        except Exception as e:
                            url = item.get("webpage_url") or item.get("url", "unknown")
                            LogManager.log_download_live_recovery(
                                f"Error processing recovery for {url}: {e}\n{traceback.format_exc()}"
                            )

            except Exception as e:
                LogManager.log_download_live_recovery(
                    f"Unhandled exception in monitor_recoveryqueue: {e}\n{traceback.format_exc()}"
                )

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
                log_table_name=LogManager.table_download_live_recovery,
                log_warnings_and_above_only=False,
                desired_dicts=["live_status", "is_live", "webpage_url"],
                thread_number=1,
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

            # Initialize dlp_events if not already done
            if not hasattr(cls, "dlp_events"):
                from dlp.events import DLPEvents

                cls.dlp_events = DLPEvents(
                    currenturl,
                    LogManager.table_download_live_recovery,
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
                log_table_name=LogManager.table_download_live_recovery,
                log_warnings_and_above_only=False,
                thread_number=1,
            )

            item["download_complete"] = True

            # Mark the video as downloaded in the playlist
            from utils.playlist_manager import PlaylistManager

            await PlaylistManager.mark_as_downloaded(currenturl)

            LogManager.log_download_live_recovery(
                f"Recovery download completed for {currenturl}"
            )

        except Exception as e:
            LogManager.log_download_live_recovery(
                f"Exception in download_recovery_livestream_content for {item.get('url')}: {e}\n{traceback.format_exc()}"
            )
            item["recovery_attempts"] += 1
