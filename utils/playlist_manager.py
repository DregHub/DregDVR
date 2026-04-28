import contextlib
import traceback
import asyncio
import threading
import json  # To print out yt-dlp outputs only
from datetime import datetime, timezone
from dlp.helpers import DLPHelpers
from config.config_settings import DVR_Config
from concurrent.futures import ThreadPoolExecutor
from utils.logging_utils import LogManager, LogLevels
from utils.thread_context import ThreadContext


class PlaylistManager:
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    PLAYLIST_UPDATE_LOG_TABLE = LogManager.table_playlist_update

    # Thread-safe lock
    _playlist_file_lock = threading.Lock()

    # New split table format fields
    download_fields = {
        "instance_name",
        "unique_id",
        "url",
        "file_path",
        "title",
        "datetime",
        "is_short",
        "live_status",
        "was_live",
        "live_download_stage",
        "captions_download_started",
        "recovery_download_started",
        "has_captions",
        "downloaded_video",
        "downloaded_caption",
        "video_download_attempts",
        "caption_download_attempts",
    }

    upload_fields = {
        "instance_name",
        "unique_id",
        "url",
        "uploaded_video_all_hosts",
        "uploaded_video_ia",
        "uploaded_video_yt",
        "uploaded_video_rm",
        "uploaded_video_bc",
        "uploaded_video_od",
        "uploaded_caption",
        "upload_error_bc",
        "upload_error_ia",
        "upload_error_yt",
        "upload_error_rm",
        "upload_error_od",
    }

    _playlist_entry_keys = [
        "URL",
        "File_Path",
        "Title",
        "unique_id",
        "DateTime",
        "IsShort",
        "Live_Status",
        "Was_Live",
        "Has_Captions",
        "Downloaded_Video",
        "Downloaded_Caption",
        "Video_Download_Attempts",
        "Caption_Download_Attempts",
        "Uploaded_Video_All_Hosts",
        "Uploaded_Video_IA",
        "Uploaded_Video_YT",
        "Uploaded_Video_RM",
        "Uploaded_Video_BC",
        "Uploaded_Video_OD",
        "Uploaded_Caption",
        "Upload_Error_BC",
        "Upload_Error_IA",
        "Upload_Error_YT",
        "Upload_Error_RM",
        "Upload_Error_OD",
        "Live_Download_Stage",
        "Captions_Download_Started",
        "Recovery_Download_Started",
    ]

    _db = None
    _channel_url = None
    _videos_url = None
    _shorts_url = None
    _live_url = None

    @classmethod
    def _run_async(cls, coro):
        """Helper to run async code from sync context."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    @classmethod
    async def _get_db(cls):
        if cls._db is None:
            from db.dvr_db import DVRDB

            cls._db = await DVRDB.get_global()
        return cls._db

    @classmethod
    async def _get_instance_name(cls):
        try:
            return await DVR_Config._get_instance_name() or ""
        except Exception:
            return ""

    @classmethod
    async def _get_channel_source(cls):
        """Get the channel source (yt_source) from the accounts table."""
        try:
            instance_name = await cls._get_instance_name()
            if not instance_name:
                return ""
            db = await cls._get_db()
            account = await db.get_account(instance_name)
            return (account.get("yt_source") or "") if account else ""
        except Exception:
            return ""

    @classmethod
    async def _initialize_channel_urls(cls):
        """Initialize all channel URLs at class level from the instances table."""
        channel_source = await cls._get_channel_source()
        if not channel_source:
            cls._channel_url = ""
            cls._videos_url = ""
            cls._shorts_url = ""
            cls._live_url = ""
            return

        base_url = DVR_Config.build_youtube_url(channel_source).rstrip("/")
        cls._channel_url = base_url
        cls._videos_url = f"{base_url}/videos"
        cls._shorts_url = f"{base_url}/shorts"
        cls._live_url = f"{base_url}/live"

    @classmethod
    async def _get_channel(cls):
        await cls._initialize_channel_urls()
        return cls._channel_url

    @classmethod
    async def _get_videos_url(cls):
        await cls._initialize_channel_urls()
        return cls._videos_url

    @classmethod
    async def _get_shorts_url(cls):
        await cls._initialize_channel_urls()
        return cls._shorts_url

    @classmethod
    async def _get_live_url(cls):
        await cls._initialize_channel_urls()
        return cls._live_url

    @classmethod
    async def _get_playlist_table_name(cls):
        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source:
            raise RuntimeError(
                "Cannot resolve instance name or channel source for playlist table"
            )
        db = await cls._get_db()
        return db.get_playlist_table_name(instance_name, channel_source)

    @classmethod
    async def _ensure_playlist_table_exists(cls):
        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source:
            return
        db = await cls._get_db()
        await db.ensure_playlist_table_exists(instance_name, channel_source)

    @classmethod
    def _convert_db_row_to_entry(cls, row):
        """Convert a merged database row (from download and upload tables) to internal entry format."""
        if not row:
            return {}
        data = dict(row)
        return {
            "URL": data.get("url"),
            "File_Path": data.get("file_path"),
            "Title": data.get("title"),
            "unique_id": data.get("unique_id"),
            "DateTime": data.get("datetime"),
            "IsShort": bool(data.get("is_short")),
            "Live_Status": data.get("live_status"),
            "Was_Live": bool(data.get("was_live")),
            "Has_Captions": bool(data.get("has_captions")),
            "Downloaded_Video": bool(data.get("downloaded_video")),
            "Downloaded_Caption": bool(data.get("downloaded_caption")),
            "Video_Download_Attempts": data.get("video_download_attempts", 0),
            "Caption_Download_Attempts": data.get("caption_download_attempts", 0),
            "Uploaded_Video_All_Hosts": bool(data.get("uploaded_video_all_hosts")),
            "Uploaded_Video_IA": bool(data.get("uploaded_video_ia")),
            "Uploaded_Video_YT": bool(data.get("uploaded_video_yt")),
            "Uploaded_Video_RM": bool(data.get("uploaded_video_rm")),
            "Uploaded_Video_BC": bool(data.get("uploaded_video_bc")),
            "Uploaded_Video_OD": bool(data.get("uploaded_video_od")),
            "Uploaded_Caption": bool(data.get("uploaded_caption")),
            "Upload_Error_BC": data.get("upload_error_bc"),
            "Upload_Error_IA": data.get("upload_error_ia"),
            "Upload_Error_YT": data.get("upload_error_yt"),
            "Upload_Error_RM": data.get("upload_error_rm"),
            "Upload_Error_OD": data.get("upload_error_od"),
            "Live_Download_Stage": data.get("live_download_stage"),
            "Captions_Download_Started": bool(data.get("captions_download_started")),
            "Recovery_Download_Started": bool(data.get("recovery_download_started")),
        }

    @classmethod
    def _prepare_entry_for_db(cls, item):
        """Convert internal entry format to database format (with all fields for splitting)."""
        return {
            "url": item.get("URL"),
            "file_path": item.get("File_Path"),
            "title": item.get("Title"),
            "unique_id": item.get("unique_id") or item.get("URL"),
            "datetime": item.get("DateTime"),
            "is_short": int(bool(item.get("IsShort"))),
            "live_status": item.get("Live_Status"),
            "was_live": int(bool(item.get("Was_Live"))),
            "has_captions": int(bool(item.get("Has_Captions"))),
            "downloaded_video": int(bool(item.get("Downloaded_Video"))),
            "downloaded_caption": int(bool(item.get("Downloaded_Caption"))),
            "video_download_attempts": item.get("Video_Download_Attempts", 0),
            "caption_download_attempts": item.get("Caption_Download_Attempts", 0),
            "uploaded_video_all_hosts": int(bool(item.get("Uploaded_Video_All_Hosts"))),
            "uploaded_video_ia": int(bool(item.get("Uploaded_Video_IA"))),
            "uploaded_video_yt": int(bool(item.get("Uploaded_Video_YT"))),
            "uploaded_video_rm": int(bool(item.get("Uploaded_Video_RM"))),
            "uploaded_video_bc": int(bool(item.get("Uploaded_Video_BC"))),
            "uploaded_video_od": int(bool(item.get("Uploaded_Video_OD"))),
            "uploaded_caption": int(bool(item.get("Uploaded_Caption"))),
            "upload_error_bc": item.get("Upload_Error_BC"),
            "upload_error_ia": item.get("Upload_Error_IA"),
            "upload_error_yt": item.get("Upload_Error_YT"),
            "upload_error_rm": item.get("Upload_Error_RM"),
            "upload_error_od": item.get("Upload_Error_OD"),
            "live_download_stage": item.get("Live_Download_Stage"),
            "captions_download_started": int(
                bool(item.get("Captions_Download_Started"))
            ),
            "recovery_download_started": int(
                bool(item.get("Recovery_Download_Started"))
            ),
        }

    @classmethod
    async def get_pending_download_entries(cls):
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        return [
            {
                "url": item.get("URL"),
                "live_status": item.get("Live_Status"),
                "was_live": item.get("Was_Live"),
            }
            for item in videos
            if item.get("URL") and not bool(item.get("Downloaded_Video", False))
        ]

    @classmethod
    async def _ensure_playlist_file_exists(cls):
        """Ensure the persistent playlist storage exists for the playlist.

        For database-backed playlists this means ensuring the playlist table exists.
        """
        try:
            await cls._ensure_playlist_table_exists()
        except Exception as ex:
            LogManager.log_channel_playlist(
                f"Failed to ensure playlist storage exists: {ex}", LogLevels.Error
            )

    @classmethod
    def _normalize_entries(cls, info):
        """Normalize the info response to a list of entries.

        Handles three cases:
        1. Already a list of entries
        2. A dict with 'entries' key (playlist response)
        3. A single video dict (wrap in list to normalize)
        """
        if isinstance(info, list):
            return info
        try:
            # Check if this is a playlist with entries
            if isinstance(info, dict) and "entries" in info:
                return info.get("entries") or []
            # Check if this is a single video (has 'id' but no 'entries')
            if isinstance(info, dict) and "id" in info and "entries" not in info:
                return [info]
            # Otherwise return empty list
            return []
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Error normalizing entries: {e}, info type: {type(info)}",
                LogLevels.Error,
            )
            return []

    @classmethod
    async def _load_playlist_data(cls):
        """Load the current playlist data from the database-backed playlist table (merged from download and upload tables)."""
        try:
            await cls._ensure_playlist_table_exists()
            instance_name = await cls._get_instance_name()
            channel_source = await cls._get_channel_source()
            if not instance_name or not channel_source:
                return {"Videos": []}

            db = await cls._get_db()

            # Get download table entries
            download_table_name = db.get_playlist_download_table_name(channel_source)
            download_entries = await db.get_channel_playlist_entries(
                instance_name, channel_source
            )

            # Get upload table entries
            upload_table_name = db.get_playlist_upload_table_name(channel_source)
            upload_entries = []
            try:
                conn = await db._get_connection()
                cursor = await conn.execute(f"SELECT * FROM {upload_table_name}")
                upload_rows = await cursor.fetchall()
                await cursor.close()
                upload_entries = (
                    [dict(row) for row in upload_rows] if upload_rows else []
                )
            except Exception as e:
                # Upload table might not exist yet or be empty
                pass

            # Merge download and upload entries by unique_id
            upload_dict = {entry.get("unique_id"): entry for entry in upload_entries}
            merged_entries = []

            for download_row in download_entries:
                download_data = dict(download_row)
                unique_id = download_data.get("unique_id")

                # Merge with upload data if available
                if unique_id in upload_dict:
                    upload_data = upload_dict[unique_id]
                    download_data.update(
                        {
                            "uploaded_video_all_hosts": upload_data.get(
                                "uploaded_video_all_hosts"
                            ),
                            "uploaded_video_ia": upload_data.get("uploaded_video_ia"),
                            "uploaded_video_yt": upload_data.get("uploaded_video_yt"),
                            "uploaded_video_rm": upload_data.get("uploaded_video_rm"),
                            "uploaded_video_bc": upload_data.get("uploaded_video_bc"),
                            "uploaded_video_od": upload_data.get("uploaded_video_od"),
                            "uploaded_caption": upload_data.get("uploaded_caption"),
                            "upload_error_bc": upload_data.get("upload_error_bc"),
                            "upload_error_ia": upload_data.get("upload_error_ia"),
                            "upload_error_yt": upload_data.get("upload_error_yt"),
                            "upload_error_rm": upload_data.get("upload_error_rm"),
                            "upload_error_od": upload_data.get("upload_error_od"),
                        }
                    )

                merged_entries.append(download_data)

            videos = [cls._convert_db_row_to_entry(row) for row in merged_entries]
            return {"Videos": videos}
        except Exception:
            return {"Videos": []}

    @classmethod
    def _update_playlist_totals(cls, playlist_data):
        """Update playlist data with sorted videos and computed totals."""
        videos = playlist_data.get("Videos", [])
        # Sort the playlist data by title before saving
        videos.sort(key=lambda x: x.get("Title", "").lower())

        # Compute totals
        total_entries = len(videos)
        total_livestreams = sum(
            1
            for item in videos
            if item.get("Was_Live") or item.get("Live_Status") == "was_live"
        )
        total_posted_videos = sum(
            1
            for item in videos
            if item.get("Live_Status") == "not_live" and not item.get("IsShort")
        )
        total_captions = sum(1 for item in videos if item.get("Has_Captions"))

        # Update the data in Totals section (and keep top-level for compatibility)
        totals = {
            "Total_Entries": total_entries,
            "Total_Livestreams": total_livestreams,
            "Total_Posted_Videos": total_posted_videos,
            "Total_Captions": total_captions,
            "Total_Downloads": sum(
                1 for item in videos if bool(item.get("Downloaded_Video", False))
            ),
            "Total_All_Platform_Uploads": sum(
                1
                for item in videos
                if bool(item.get("Uploaded_Video_All_Hosts", False))
            ),
            "Total_YouTube_Uploads": sum(
                1 for item in videos if bool(item.get("Uploaded_Video_YT", False))
            ),
            "Total_Failed_YouTube_Uploads": sum(
                1 for item in videos if item.get("Upload_Error_YT")
            ),
            "Total_Internet_Archive_Uploads": sum(
                1 for item in videos if bool(item.get("Uploaded_Video_IA", False))
            ),
            "Total_Failed_Internet_Archive_Uploads": sum(
                1 for item in videos if item.get("Upload_Error_IA")
            ),
            "Total_Rumble_Uploads": sum(
                1 for item in videos if bool(item.get("Uploaded_Video_RM", False))
            ),
            "Total_Failed_Rumble_Uploads": sum(
                1 for item in videos if item.get("Upload_Error_RM")
            ),
            "Total_BitChute_Uploads": sum(
                1 for item in videos if bool(item.get("Uploaded_Video_BC", False))
            ),
            "Total_Failed_BitChute_Uploads": sum(
                1 for item in videos if item.get("Upload_Error_BC")
            ),
            "Total_Odyssey_Uploads": sum(
                1 for item in videos if bool(item.get("Uploaded_Video_OD", False))
            ),
            "Total_Failed_Odyssey_Uploads": sum(
                1 for item in videos if item.get("Upload_Error_OD")
            ),
        }

        # Reconstruct dict to put Totals before Videos while preserving other keys
        ordered_data = {
            "Playlist_Totals": totals,
        }

        # Preserve any additional metadata keys from original data except Totals/Videos
        for key, value in playlist_data.items():
            if key in ["Playlist_Totals", "Videos"]:
                continue
            ordered_data[key] = value

        ordered_data["Videos"] = [
            cls._order_playlist_entry_fields(item) for item in videos
        ]

        return ordered_data

    @classmethod
    async def _save_playlist_data(cls, playlist_data):
        """Save the playlist data to the database-backed playlist table (split into download and upload tables)."""
        try:
            updated_data = cls._update_playlist_totals(playlist_data)
            videos = updated_data.get("Videos", [])
            if not isinstance(videos, list):
                return

            instance_name = await cls._get_instance_name()
            channel_source = await cls._get_channel_source()
            if not instance_name or not channel_source:
                return

            db = await cls._get_db()

            for item in videos:
                if not isinstance(item, dict):
                    continue

                db_item = cls._prepare_entry_for_db(item)

                # Split into download and upload items using class-level field sets
                download_item = {
                    k: v for k, v in db_item.items() if k in cls.download_fields
                }
                upload_item = {
                    k: v for k, v in db_item.items() if k in cls.upload_fields
                }

                # Ensure instance_name is included in download item
                download_item["instance_name"] = instance_name

                # Save to download table
                if download_item:
                    await db.add_or_update_channel_playlist_entry(
                        instance_name, channel_source, download_item
                    )

                # Save to upload table
                if upload_item:
                    # Ensure instance_name and unique_id are included
                    upload_item["instance_name"] = instance_name
                    if "unique_id" not in upload_item:
                        upload_item["unique_id"] = upload_item.get("url")

                    upload_table_name = db.get_playlist_upload_table_name(
                        channel_source
                    )
                    try:
                        conn = await db._get_connection()

                        # Check if entry exists by unique_id
                        cursor = await conn.execute(
                            f"SELECT url FROM {upload_table_name} WHERE instance_name = ? AND unique_id = ?",
                            (instance_name, upload_item.get("unique_id")),
                        )
                        existing = await cursor.fetchone()
                        await cursor.close()

                        if existing:
                            # Update existing entry
                            set_clause = ", ".join(
                                [
                                    f"{k} = ?"
                                    for k in upload_item.keys()
                                    if k not in ["url", "instance_name", "unique_id"]
                                ]
                            )
                            values = [
                                v
                                for k, v in upload_item.items()
                                if k not in ["url", "instance_name", "unique_id"]
                            ] + [instance_name, upload_item.get("unique_id")]
                            await conn.execute(
                                f"UPDATE {upload_table_name} SET {set_clause} WHERE instance_name = ? AND unique_id = ?",
                                values,
                            )
                        else:
                            # Insert new entry
                            columns = list(upload_item.keys())
                            placeholders = ["?"] * len(columns)
                            await conn.execute(
                                f"INSERT INTO {upload_table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                                list(upload_item.values()),
                            )

                        await conn.commit()
                    except Exception as e:
                        # Upload table might not exist yet or other error
                        pass

        except Exception as ex:
            LogManager.log_channel_playlist(
                f"Failed to save playlist data: {ex}", LogLevels.Error
            )

    @classmethod
    async def _add_missing_playlist_fields(cls, playlist_data):
        """Ensure each playlist entry includes required fields with sane defaults."""
        if playlist_data is None:
            return False

        videos = playlist_data.get("Videos", [])
        if not isinstance(videos, list):
            return False

        required_defaults = {
            "unique_id": None,
            "URL": None,
            "File_Path": None,
            "Title": None,
            "DateTime": None,
            "IsShort": None,
            "Live_Status": None,
            "Was_Live": None,
            "Has_Captions": None,
            "Downloaded_Video": None,
            "Downloaded_Caption": None,
            "Video_Download_Attempts": 0,
            "Caption_Download_Attempts": 0,
            "Uploaded_Video_All_Hosts": False,
            "Uploaded_Video_IA": False,
            "Uploaded_Video_YT": False,
            "Uploaded_Video_RM": False,
            "Uploaded_Video_BC": False,
            "Uploaded_Video_OD": False,
            "Uploaded_Caption": False,
            "Upload_Error_BC": None,
            "Upload_Error_IA": None,
            "Upload_Error_YT": None,
            "Upload_Error_RM": None,
            "Upload_Error_OD": None,
            "Live_Download_Stage": "na",
            "Captions_Download_Started": False,
            "Recovery_Download_Started": False,
        }

        updated = False
        for item in videos:
            if not isinstance(item, dict):
                continue
            for key in cls._playlist_entry_keys:
                if key not in item:
                    item[key] = required_defaults.get(key)
                    updated = True

        if updated:
            await cls._save_playlist_data(playlist_data)

        return updated

    @classmethod
    def _order_playlist_entry_fields(cls, item):
        if not isinstance(item, dict):
            return item

        ordered_item = {}
        for key in cls._playlist_entry_keys:
            if key in item:
                ordered_item[key] = item[key]

        for key, value in item.items():
            if key not in cls._playlist_entry_keys:
                ordered_item[key] = value

        return ordered_item

    @classmethod
    async def get_pending_upload_entries(cls, live_status_filter=None):
        """Return playlist entries ready for upload (downloaded but not all enabled hosts uploaded)."""
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        pending = []

        # Determine which platforms are enabled
        enabled_platforms = []
        if await DVR_Config.upload_to_ia_enabled():
            enabled_platforms.append("Uploaded_Video_IA")
        if await DVR_Config.upload_to_youtube_enabled():
            enabled_platforms.append("Uploaded_Video_YT")
        if await DVR_Config.upload_to_rumble_enabled():
            enabled_platforms.append("Uploaded_Video_RM")
        if await DVR_Config.upload_to_bitchute_enabled():
            enabled_platforms.append("Uploaded_Video_BC")
        if await DVR_Config.upload_to_odysee_enabled():
            enabled_platforms.append("Uploaded_Video_OD")

        for item in videos:
            if not bool(item.get("Downloaded_Video", False)):
                continue

            # Skip if already uploaded to all enabled platforms
            if enabled_platforms and all(
                bool(item.get(platform, False)) for platform in enabled_platforms
            ):
                continue

            if live_status_filter == "not_live":
                if item.get("Live_Status") != "not_live":
                    continue
            elif live_status_filter == "live":
                if item.get("Live_Status") == "not_live":
                    continue

            pending.append(item)

        return pending

    @classmethod
    async def mark_video_upload_status(cls, url, platform_key, status: bool):
        """Mark a playlist item upload status for a specific platform and update All_Hosts."""
        if platform_key not in [
            "Uploaded_Video_IA",
            "Uploaded_Video_YT",
            "Uploaded_Video_RM",
            "Uploaded_Video_OD",
            "Uploaded_Video_BC",
        ]:
            return False

        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source:
            return False

        db = await cls._get_db()

        # Get the entry to find unique_id
        entry = await db.get_channel_playlist_entry_by_url(
            instance_name, channel_source, url
        )
        if not entry:
            return False

        unique_id = entry.get("unique_id")
        if not unique_id:
            return False

        # Map platform key to database field name
        platform_field_map = {
            "Uploaded_Video_IA": "uploaded_video_ia",
            "Uploaded_Video_YT": "uploaded_video_yt",
            "Uploaded_Video_RM": "uploaded_video_rm",
            "Uploaded_Video_OD": "uploaded_video_od",
            "Uploaded_Video_BC": "uploaded_video_bc",
        }

        db_field = platform_field_map[platform_key]

        # Update the upload table
        upload_table_name = db.get_playlist_upload_table_name(channel_source)
        try:
            conn = await db._get_connection()

            # Update the specific platform field
            await conn.execute(
                f"UPDATE {upload_table_name} SET {db_field} = ? WHERE instance_name = ? AND unique_id = ?",
                (int(status), instance_name, unique_id),
            )

            # Get all platform statuses to update uploaded_video_all_hosts
            cursor = await conn.execute(
                f"SELECT uploaded_video_ia, uploaded_video_yt, uploaded_video_rm, uploaded_video_od, uploaded_video_bc FROM {upload_table_name} WHERE instance_name = ? AND unique_id = ?",
                (instance_name, unique_id),
            )
            row = await cursor.fetchone()
            await cursor.close()

            if row:
                # Convert row to dict for easier access
                row_dict = dict(row) if hasattr(row, 'keys') else {
                    "uploaded_video_ia": row[0],
                    "uploaded_video_yt": row[1],
                    "uploaded_video_rm": row[2],
                    "uploaded_video_od": row[3],
                    "uploaded_video_bc": row[4],
                }
                all_hosts_uploaded = all(
                    bool(row_dict.get(f"uploaded_video_{platform}"))
                    for platform in ["ia", "yt", "rm", "od", "bc"]
                )

                await conn.execute(
                    f"UPDATE {upload_table_name} SET uploaded_video_all_hosts = ? WHERE instance_name = ? AND unique_id = ?",
                    (int(all_hosts_uploaded), instance_name, unique_id),
                )

            await conn.commit()
            return True
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to mark upload status: {e}", LogLevels.Error
            )
            return False

    @classmethod
    async def mark_video_upload_error(cls, unique_id, platform_suffix, error_code: str):
        """Mark a playlist item upload error for a specific platform.

        Args:
            unique_id: Unique ID of the video entry to mark
            platform_suffix: Without 'Upload_Error_' prefix (e.g., 'BC', 'YT', 'RM', 'OD', 'IA')
            error_code: Error code identifier (e.g., 'FileTooSmall_Min1MBForBitchute')
        """
        if platform_suffix not in ["IA", "YT", "RM", "OD", "BC"]:
            return False

        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source:
            return False

        db = await cls._get_db()

        # Map platform suffix to database field name
        error_field_map = {
            "IA": "upload_error_ia",
            "YT": "upload_error_yt",
            "RM": "upload_error_rm",
            "OD": "upload_error_od",
            "BC": "upload_error_bc",
        }

        db_field = error_field_map[platform_suffix]

        # Update the upload table
        upload_table_name = db.get_playlist_upload_table_name(channel_source)
        try:
            conn = await db._get_connection()

            # Update the error field
            await conn.execute(
                f"UPDATE {upload_table_name} SET {db_field} = ? WHERE instance_name = ? AND unique_id = ?",
                (error_code, instance_name, unique_id),
            )

            await conn.commit()
            return True
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to mark upload error: {e}", LogLevels.Error
            )
            return False

    @classmethod
    async def is_entry_fully_uploaded(cls, url):
        """Return True if all individual platform upload markers are set for the URL."""
        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source:
            return False

        db = await cls._get_db()

        # Get the entry to find unique_id
        entry = await db.get_channel_playlist_entry_by_url(
            instance_name, channel_source, url
        )
        if not entry:
            return False

        unique_id = entry.get("unique_id")
        if not unique_id:
            return False

        # Check the upload table for all platform statuses
        upload_table_name = db.get_playlist_upload_table_name(channel_source)
        try:
            conn = await db._get_connection()
            cursor = await conn.execute(
                f"SELECT uploaded_video_ia, uploaded_video_yt, uploaded_video_rm, uploaded_video_od, uploaded_video_bc, uploaded_video_all_hosts FROM {upload_table_name} WHERE instance_name = ? AND unique_id = ?",
                (instance_name, unique_id),
            )
            row = await cursor.fetchone()
            await cursor.close()

            if row:
                # Convert row to dict for easier access
                row_dict = dict(row) if hasattr(row, 'keys') else {
                    "uploaded_video_ia": row[0],
                    "uploaded_video_yt": row[1],
                    "uploaded_video_rm": row[2],
                    "uploaded_video_od": row[3],
                    "uploaded_video_bc": row[4],
                    "uploaded_video_all_hosts": row[5],
                }
                return (
                    bool(row_dict.get("uploaded_video_ia"))
                    and bool(row_dict.get("uploaded_video_yt"))
                    and bool(row_dict.get("uploaded_video_rm"))
                    and bool(row_dict.get("uploaded_video_od"))
                    and bool(row_dict.get("uploaded_video_bc"))
                    and bool(row_dict.get("uploaded_video_all_hosts"))
                )
            return False
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to check upload status: {e}", LogLevels.Error
            )
            return False

    @classmethod
    async def _check_video_captions(cls, metadata, vidurl, thread_number=None):
        """Check if video has English automatic captions."""
        try:
            if metadata and "automatic_captions" in metadata:
                captions = metadata["automatic_captions"]
                return any(lang.startswith("en") for lang in captions.keys())
            else:
                return False
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to check captions for {vidurl}: {e}",
                LogLevels.Error,
                thread_number,
            )
            return None

    @classmethod
    async def _add_basic_video_info_to_playlist(
        cls, vid_id, title, vidurl, thread_number: int = None
    ):
        if not vidurl:
            return

        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source:
            return

        db = await cls._get_db()

        async def add_entry():
            existing = await db.get_channel_playlist_entry_by_url(
                instance_name, channel_source, vidurl
            )
            if existing:
                return False

            new_item = {
                "Title": title,
                "unique_id": vid_id or vidurl,
                "DateTime": datetime.now(timezone.utc).isoformat(),
                "URL": vidurl,
                "IsShort": None,
                "Live_Status": None,
                "Was_Live": None,
                "Has_Captions": None,
                "Downloaded_Video": False,
                "Downloaded_Caption": False,
                "Uploaded_Video_All_Hosts": False,
                "Uploaded_Video_IA": False,
                "Uploaded_Video_YT": False,
                "Uploaded_Video_RM": False,
                "Uploaded_Video_BC": False,
                "Uploaded_Video_OD": False,
                "Uploaded_Caption": False,
                "Video_Download_Attempts": 0,
                "Caption_Download_Attempts": 0,
                "Live_Download_Stage": "na",
                "Captions_Download_Started": False,
                "Recovery_Download_Started": False,
            }
            db_item = cls._prepare_entry_for_db(new_item)

            # Split into download and upload items
            download_item = {
                k: v for k, v in db_item.items() if k in cls.download_fields
            }
            upload_item = {k: v for k, v in db_item.items() if k in cls.upload_fields}

            # Ensure instance_name is included
            download_item["instance_name"] = instance_name
            upload_item["instance_name"] = instance_name

            # Save to download table
            result = await db.add_or_update_channel_playlist_entry(
                instance_name, channel_source, download_item
            )

            # Save to upload table
            upload_table_name = db.get_playlist_upload_table_name(channel_source)
            try:
                conn = await db._get_connection()
                columns = list(upload_item.keys())
                placeholders = ["?"] * len(columns)
                await conn.execute(
                    f"INSERT INTO {upload_table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    list(upload_item.values()),
                )
                await conn.commit()
            except Exception as e:
                # Upload table might not exist yet or other error
                pass

            return result

        added = await add_entry()
        if not added:
            LogManager.log_channel_playlist(
                f"Video {vidurl} already exists in playlist, skipping basic info addition.",
                LogLevels.Info,
                thread_number,
            )

    @classmethod
    async def _fetch_full_metadata(cls, vidurl, thread_number=None):
        """Fetch full metadata for a video from yt-dlp."""
        ydl_opts = {
            "skip_download": True,
            "quiet": False,
            "ignore_no_formats_error": True,
            "extract_flat": False,
        }
        return await DLPHelpers.getinfo_with_retry(
            ydl_opts=ydl_opts,
            url_or_list=vidurl,
            log_table_name=cls.PLAYLIST_UPDATE_LOG_TABLE,
        )

    @classmethod
    def _extract_video_properties(cls, metadata, vidurl):
        """Extract video properties from metadata.

        Returns a tuple of (is_short, was_live, live_status).
        """
        is_short = False
        was_live = False
        live_status = None

        with contextlib.suppress(Exception):
            if metadata:
                live_status = metadata.get("live_status")
                duration = metadata.get("duration")

                is_short = (
                    bool(metadata.get("is_short"))
                    or (vidurl is not None and "/shorts/" in vidurl)
                    or (isinstance(duration, (int, float)) and duration <= 60)
                )
                was_live = (
                    bool(metadata.get("was_live"))
                    or (live_status == "was_live")
                    or (live_status == "is_live")
                )
        return is_short, was_live, live_status

    @classmethod
    async def _handle_unknown_live_status(cls, metadata, vidurl, thread_number=None):
        """Handle videos with unknown live_status by logging full metadata."""
        LogManager.log_channel_playlist(
            f"{vidurl} has unknown live_status. logging full metadata for debugging.",
            LogLevels.Warning,
            thread_number,
        )
        try:
            pretty = json.dumps(metadata, indent=2, ensure_ascii=False)
            LogManager.log_channel_playlist(
                f"Full metadata for {vidurl}:\n{pretty}",
                LogLevels.Debug,
                thread_number,
            )
        except Exception as ex:
            LogManager.log_channel_playlist(
                f"Failed to serialize metadata for {vidurl}: {ex}",
                LogLevels.Error,
                thread_number,
            )

    @classmethod
    async def _handle_unwanted_live_status(
        cls, vidurl, live_status, thread_number=None
    ):
        """Handle videos that should be skipped (not 'not_live' or 'unknown')."""
        LogManager.log_channel_playlist(
            f"Skipping video : {vidurl} with live_status: {live_status}",
            LogLevels.Info,
            thread_number,
        )

    @classmethod
    async def _process_not_live_video(
        cls,
        existing_item,
        metadata,
        vid_id,
        title,
        vidurl,
        is_short,
        was_live,
        live_status,
        thread_number=None,
    ):
        """Process a video with live_status 'not_live' and add it to the playlist."""

        # Populate extended metadata fields for videos that are not live (this includes regular videos and past livestreams)
        existing_item["Has_Captions"] = await cls._check_video_captions(
            metadata, vidurl, thread_number=thread_number
        )
        existing_item["IsShort"] = is_short
        existing_item["Was_Live"] = was_live
        existing_item["Live_Status"] = live_status
        existing_item["Live_Download_Stage"] = "na"

        LogManager.log_channel_playlist(
            f"{vid_id} - Has_Captions: {existing_item['Has_Captions']}, IsShort: {existing_item['IsShort']}, Was_Live: {existing_item['Was_Live']}, Live_Status: {existing_item['Live_Status']}, Live_Download_Stage: {existing_item['Live_Download_Stage']}",
            LogLevels.Debug,
            thread_number,
        )
        # We dont need to return anything as the existing_item is a reference to the item in the playlist_data list

    @classmethod
    async def _process_live_video(
        cls,
        existing_item,
        metadata,
        vid_id,
        title,
        vidurl,
        is_short,
        was_live,
        live_status,
        thread_number=None,
    ):
        """Process a video with live_status 'is_live' and add it to the playlist."""

        existing_item["IsShort"] = is_short
        existing_item["Was_Live"] = was_live
        existing_item["Live_Status"] = live_status
        existing_item["Live_Download_Stage"] = "new"

        # We dont need to return anything as the existing_item is a reference to the item in the playlist_data list

    @classmethod
    async def _add_full_video_info_to_playlist(
        cls, vid_id, title, vidurl, thread_number=None
    ):
        """Add a new video item to the playlist or update existing item with full metadata."""
        LogManager.log_channel_playlist(
            f"Fetching full metadata for {vid_id}",
            LogLevels.Debug,
            thread_number,
        )
        instance_name = await cls._get_instance_name()
        channel_source = await cls._get_channel_source()
        if not instance_name or not channel_source or not vidurl:
            return

        db = await cls._get_db()

        async def add_or_update_item():
            existing_entry = await db.get_channel_playlist_entry_by_url(
                instance_name, channel_source, vidurl
            )
            if existing_entry:
                entry = cls._convert_db_row_to_entry(existing_entry)
            else:
                entry = {
                    "Title": title,
                    "unique_id": vid_id or vidurl,
                    "DateTime": datetime.now(timezone.utc).isoformat(),
                    "URL": vidurl,
                    "IsShort": None,
                    "Live_Status": None,
                    "Was_Live": None,
                    "Has_Captions": None,
                    "Downloaded_Video": False,
                    "Downloaded_Caption": False,
                    "Uploaded_Video_All_Hosts": False,
                    "Uploaded_Video_IA": False,
                    "Uploaded_Video_YT": False,
                    "Uploaded_Video_RM": False,
                    "Uploaded_Video_BC": False,
                    "Uploaded_Video_OD": False,
                    "Uploaded_Caption": False,
                    "Video_Download_Attempts": 0,
                    "Caption_Download_Attempts": 0,
                    "Live_Download_Stage": "na",
                    "Captions_Download_Started": False,
                    "Recovery_Download_Started": False,
                }
            return entry

        playlist_entry = await add_or_update_item()

        metadata = await cls._fetch_full_metadata(vidurl, thread_number=thread_number)

        if metadata:
            is_short, was_live, live_status = cls._extract_video_properties(
                metadata, vidurl
            )

            if live_status == "unknown":
                await cls._handle_unknown_live_status(
                    metadata, vidurl, thread_number=thread_number
                )
            elif live_status == "is_live":
                await cls._process_live_video(
                    playlist_entry,
                    metadata,
                    vid_id,
                    title,
                    vidurl,
                    is_short,
                    was_live,
                    live_status,
                    thread_number=thread_number,
                )
            elif live_status != "not_live":
                await cls._handle_unwanted_live_status(
                    vidurl, live_status, thread_number=thread_number
                )
            else:
                await cls._process_not_live_video(
                    playlist_entry,
                    metadata,
                    vid_id,
                    title,
                    vidurl,
                    is_short,
                    was_live,
                    live_status,
                    thread_number=thread_number,
                )

        async def persist_entry():
            db_item = cls._prepare_entry_for_db(playlist_entry)

            # Split into download and upload items
            download_item = {
                k: v for k, v in db_item.items() if k in cls.download_fields
            }
            upload_item = {k: v for k, v in db_item.items() if k in cls.upload_fields}

            # Ensure instance_name is included
            download_item["instance_name"] = instance_name
            upload_item["instance_name"] = instance_name

            # Save to download table
            await db.add_or_update_channel_playlist_entry(
                instance_name, channel_source, download_item
            )

            # Save to upload table
            upload_table_name = db.get_playlist_upload_table_name(channel_source)
            try:
                conn = await db._get_connection()

                # Check if entry exists by unique_id
                cursor = await conn.execute(
                    f"SELECT url FROM {upload_table_name} WHERE instance_name = ? AND unique_id = ?",
                    (instance_name, upload_item.get("unique_id")),
                )
                existing = await cursor.fetchone()
                await cursor.close()

                if existing:
                    # Update existing entry
                    set_clause = ", ".join(
                        [
                            f"{k} = ?"
                            for k in upload_item.keys()
                            if k not in ["url", "instance_name", "unique_id"]
                        ]
                    )
                    values = [
                        v
                        for k, v in upload_item.items()
                        if k not in ["url", "instance_name", "unique_id"]
                    ] + [instance_name, upload_item.get("unique_id")]
                    await conn.execute(
                        f"UPDATE {upload_table_name} SET {set_clause} WHERE instance_name = ? AND unique_id = ?",
                        values,
                    )
                else:
                    # Insert new entry
                    columns = list(upload_item.keys())
                    placeholders = ["?"] * len(columns)
                    await conn.execute(
                        f"INSERT INTO {upload_table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                        list(upload_item.values()),
                    )

                await conn.commit()
            except Exception as e:
                # Upload table might not exist yet or other error
                pass

        await persist_entry()

    @classmethod
    def _process_entries_threaded_wrapper(cls, entry, thread_number):
        """Wrapper to handle async context within thread for processing entries."""
        ThreadContext.set_thread_context(thread_number)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cls._process_entry_async(entry, thread_number))
            loop.close()
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Wrapper error in thread {thread_number}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number,
            )

    @classmethod
    async def _process_entry_async(cls, entry, thread_number):
        """Process a single entry asynchronously."""
        try:
            vid_id = entry.get("id")
            title = (
                entry.get("title").replace("\n", " ").replace("\r", " ")
                if entry.get("title")
                else ""
            )
            vidurl = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None

            await cls._add_basic_video_info_to_playlist(
                vid_id, title, vidurl, thread_number
            )
            await cls._add_full_video_info_to_playlist(
                vid_id, title, vidurl, thread_number
            )
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Error processing entry {entry.get('id')}: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                thread_number,
            )

    @classmethod
    def _is_short_entry(cls, entry):
        """Determine if an entry is a short based on available info."""
        try:
            url = entry.get("webpage_url", "")
            duration = entry.get("duration")
            return (
                bool(entry.get("is_short"))
                or "/shorts/" in url
                or (isinstance(duration, (int, float)) and duration <= 60)
            )
        except Exception:
            return False

    @classmethod
    def _is_live_entry(cls, entry):
        """Determine if an entry is a livestream based on available info."""
        try:
            return bool(entry.get("is_live"))
        except Exception:
            return False

    @classmethod
    async def _fetch_channel_entries(cls):
        """Fetch videos, shorts, and live videos from the channel using flat extraction."""
        ydl_opts_flat = {
            "skip_download": True,
            "ignore_no_formats_error": True,
            "extract_flat": True,
        }

        ydl_opts_full = {
            "skip_download": True,
            "ignore_no_formats_error": True,
            "extract_flat": False,
        }

        videos_url = await cls._get_videos_url()
        shorts_url = await cls._get_shorts_url()
        live_url = await cls._get_live_url()

        LogManager.log_channel_playlist(
            f"Fetching videos from: {videos_url}",
            LogLevels.Debug,
        )
        videos_info = await DLPHelpers.getinfo_with_retry(
            ydl_opts=ydl_opts_flat,
            url_or_list=videos_url,
            log_table_name=cls.PLAYLIST_UPDATE_LOG_TABLE,
        )
        LogManager.log_channel_playlist(
            f"Videos info type: {type(videos_info)}, has entries: {bool(videos_info.get('entries')) if isinstance(videos_info, dict) else 'N/A'}",
            LogLevels.Debug,
        )

        LogManager.log_channel_playlist(
            f"Fetching shorts from: {shorts_url}",
            LogLevels.Debug,
        )
        shorts_info = await DLPHelpers.getinfo_with_retry(
            ydl_opts=ydl_opts_flat,
            url_or_list=shorts_url,
            log_table_name=cls.PLAYLIST_UPDATE_LOG_TABLE,
        )
        LogManager.log_channel_playlist(
            f"Shorts info type: {type(shorts_info)}, has entries: {bool(shorts_info.get('entries')) if isinstance(shorts_info, dict) else 'N/A'}",
            LogLevels.Debug,
        )

        LogManager.log_channel_playlist(
            f"Fetching live from: {live_url}",
            LogLevels.Debug,
        )
        LogManager.log_channel_playlist(
            f"Live URL ydl_opts: {ydl_opts_full}",
            LogLevels.Debug,
        )
        live_info = await DLPHelpers.getinfo_with_retry(
            ydl_opts=ydl_opts_full,
            url_or_list=live_url,
            log_table_name=cls.PLAYLIST_UPDATE_LOG_TABLE,
        )
        LogManager.log_channel_playlist(
            f"Live info type: {type(live_info)}, value: {live_info}",
            LogLevels.Debug,
        )
        if isinstance(live_info, dict):
            LogManager.log_channel_playlist(
                f"Live info keys: {list(live_info.keys())}",
                LogLevels.Debug,
            )
            LogManager.log_channel_playlist(
                f"Live info has entries: {bool(live_info.get('entries'))}",
                LogLevels.Debug,
            )
            LogManager.log_channel_playlist(
                f"Live info _type: {live_info.get('_type')}",
                LogLevels.Debug,
            )
            if live_info.get("entries"):
                LogManager.log_channel_playlist(
                    f"Live entries count: {len(live_info.get('entries'))}",
                    LogLevels.Debug,
                )
                for idx, entry in enumerate(live_info.get("entries", [])[:3]):
                    LogManager.log_channel_playlist(
                        f"Live entry {idx}: id={entry.get('id')}, title={entry.get('title')}, is_live={entry.get('is_live')}",
                        LogLevels.Debug,
                    )

        return videos_info, shorts_info, live_info

    @classmethod
    async def _filter_new_entries(cls, flat_entries):
        """Filter entries that are not already in the persistent playlist."""
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        existing_ids = {
            item.get("unique_id") for item in videos if item.get("unique_id")
        }

        return [
            e for e in flat_entries if e.get("id") and e.get("id") not in existing_ids
        ]

    @classmethod
    async def _process_new_entries(cls, new_entries):
        """Process new entries by adding them to the playlist, prioritizing livestreams."""
        new_videos = sum(not cls._is_short_entry(e) for e in new_entries)
        new_shorts = len(new_entries) - new_videos
        new_livestreams = sum(cls._is_live_entry(e) for e in new_entries)

        LogManager.log_channel_playlist(
            f"Found {new_videos} new videos, {new_shorts} new shorts, and {new_livestreams} new livestreams since the last scan",
            LogLevels.Info,
        )

        LogManager.log_channel_playlist(
            f"Adding basic video info to playlist for {new_videos} new videos, {new_shorts} new shorts, and {new_livestreams} new livestreams",
            LogLevels.Info,
        )

        try:
            max_threads = int(await DVR_Config.get_playlist_processing_max_threads())
            LogManager.log_channel_playlist(
                f"Loaded PlaylistProcessingMaxThreads = {max_threads} from global DVR Settings",
                LogLevels.Info,
            )
        except Exception:
            LogManager.log_channel_playlist(
                "Error loading PlaylistProcessingMaxThreads from DVR Settings defaulting to 6",
                LogLevels.Warning,
            )
            max_threads = 6

        # Separate livestreams from other entries to prioritize them
        livestream_entries = [e for e in new_entries if cls._is_live_entry(e)]
        other_entries = [e for e in new_entries if not cls._is_live_entry(e)]

        # Process livestreams first
        if livestream_entries:
            LogManager.log_channel_playlist(
                f"Prioritizing {len(livestream_entries)} livestream entries for processing",
                LogLevels.Info,
            )
            await cls._process_entries_batch(livestream_entries, max_threads)

        # Process remaining entries (videos and shorts)
        if other_entries:
            LogManager.log_channel_playlist(
                f"Processing {len(other_entries)} remaining entries (videos and shorts)",
                LogLevels.Info,
            )
            await cls._process_entries_batch(other_entries, max_threads)

    @classmethod
    async def _process_entries_batch(cls, entries, max_threads):
        """Process a batch of entries using thread pool or sequential processing."""
        if len(entries) > max_threads:
            LogManager.log_channel_playlist(
                f"Processing {len(entries)} entries concurrently using ThreadPoolExecutor(max_workers={max_threads})",
                LogLevels.Info,
            )

            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = []

                # Submit all entries to thread pool with assigned thread numbers
                for index, entry in enumerate(entries):
                    thread_number = (index % max_threads) + 1
                    future = executor.submit(
                        cls._process_entries_threaded_wrapper, entry, thread_number
                    )
                    futures.append(future)

                # Wait for all threads to complete
                for future in futures:
                    try:
                        future.result(timeout=1800)  # 30 minute timeout per entry
                    except Exception as e:
                        LogManager.log_channel_playlist(
                            f"Thread execution error: {e}\n{traceback.format_exc()}",
                            LogLevels.Error,
                        )
        else:
            LogManager.log_channel_playlist(
                f"Processing {len(entries)} entries sequentially without concurrency",
                LogLevels.Info,
            )
            for e in entries:
                vid_id = e.get("id")
                title = (
                    e.get("title").replace("\n", " ").replace("\r", " ")
                    if e.get("title")
                    else ""
                )
                vidurl = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None

                await cls._add_basic_video_info_to_playlist(
                    vid_id, title, vidurl, thread_number=None
                )
                await cls._add_full_video_info_to_playlist(
                    vid_id, title, vidurl, thread_number=None
                )

    @classmethod
    async def run_playlist_update_task(cls):
        """Run a continuous task that updates the channel playlist every 5 minutes."""
        try:
            LogManager.log_channel_playlist(
                f"Playlist update task started - Log table: {cls.PLAYLIST_UPDATE_LOG_TABLE}",
                LogLevels.Info,
                0,
            )

            while True:
                try:
                    LogManager.log_channel_playlist(
                        "Calling update_channel_playlist", LogLevels.Info, 0
                    )

                    await cls.update_channel_playlist()

                    LogManager.log_channel_playlist(
                        "update_channel_playlist completed", LogLevels.Info, 0
                    )
                except Exception as e:
                    import traceback

                    LogManager.log_channel_playlist(
                        f"Error in update_channel_playlist: {e}\n{traceback.format_exc()}",
                        LogLevels.Error,
                        0,
                    )
                LogManager.log_channel_playlist(
                    "Sleeping for 300 seconds", LogLevels.Info, 0
                )
                await asyncio.sleep(300)  # Sleep for 5 minutes
        except Exception as e:
            import traceback

            LogManager.log_channel_playlist(
                f"FATAL: Playlist update task crashed: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                0,
            )

    @classmethod
    async def update_channel_playlist(cls):
        """Update the channel playlist with new videos and shorts."""
        try:
            LogManager.log_channel_playlist(
                "update_channel_playlist called", LogLevels.Info, 0
            )

            # Initialize lock if needed
            if not hasattr(cls, "_update_playlist_lock"):
                cls._update_playlist_lock = asyncio.Lock()

            LogManager.log_channel_playlist(
                "Starting playlist update - acquiring lock", LogLevels.Info, 0
            )

            async with cls._update_playlist_lock:
                LogManager.log_channel_playlist(
                    "Lock acquired - beginning playlist fetch", LogLevels.Info, 0
                )

                # Step 1: Fetch videos, shorts, and live videos from the channel
                LogManager.log_channel_playlist(
                    "Fetching channel entries",
                    LogLevels.Info,
                )
                videos_info, shorts_info, live_info = await cls._fetch_channel_entries()

                if videos_info is None and shorts_info is None and live_info is None:
                    LogManager.log_channel_playlist(
                        "Failed to retrieve channel video entries",
                        LogLevels.Error,
                    )
                    return

                await cls._ensure_playlist_file_exists()

                # Step 2: Upgrade existing playlist entries with missing fields (new defaults)
                LogManager.log_channel_playlist(
                    "Loading playlist data",
                    LogLevels.Info,
                )
                playlist_data = await cls._load_playlist_data()
                if playlist_data is not None:
                    await cls._add_missing_playlist_fields(playlist_data)

                # Step 3: Normalize and merge flat entries from all sources
                LogManager.log_channel_playlist(
                    "Normalizing entries",
                    LogLevels.Info,
                )
                videos_entries = cls._normalize_entries(videos_info)
                shorts_entries = cls._normalize_entries(shorts_info)
                live_entries = cls._normalize_entries(live_info)

                LogManager.log_channel_playlist(
                    f"Fetched {len(videos_entries)} videos, {len(shorts_entries)} shorts, and {len(live_entries)} live entries",
                    LogLevels.Info,
                )

                LogManager.log_channel_playlist(
                    f"Videos info object: {type(videos_info)} - {videos_info if not isinstance(videos_info, dict) or len(str(videos_info)) < 500 else 'dict (truncated)'}",
                    LogLevels.Debug,
                )
                LogManager.log_channel_playlist(
                    f"Shorts info object: {type(shorts_info)} - {shorts_info if not isinstance(shorts_info, dict) or len(str(shorts_info)) < 500 else 'dict (truncated)'}",
                    LogLevels.Debug,
                )
                LogManager.log_channel_playlist(
                    f"Live info object: {type(live_info)} - {live_info if not isinstance(live_info, dict) or len(str(live_info)) < 500 else 'dict (truncated)'}",
                    LogLevels.Debug,
                )

                if live_entries:
                    LogManager.log_channel_playlist(
                        f"Live entries found: {live_entries}",
                        LogLevels.Debug,
                    )
                else:
                    LogManager.log_channel_playlist(
                        f"No live entries. live_info structure: {json.dumps(live_info, default=str, indent=2) if isinstance(live_info, dict) else type(live_info)}",
                        LogLevels.Debug,
                    )

                flat_entries = videos_entries + shorts_entries + live_entries

                # Step 4: Filter new entries not already in playlist
                LogManager.log_channel_playlist(
                    "Filtering new entries",
                    LogLevels.Info,
                )
                new_entries = await cls._filter_new_entries(flat_entries)

                if new_entries:
                    # Step 5 & 6: Process new entries (add basic and full metadata)
                    LogManager.log_channel_playlist(
                        f"Found {len(new_entries)} new entries to process",
                        LogLevels.Info,
                    )
                    await cls._process_new_entries(new_entries)
                    # Reload playlist data to capture all database changes from processing
                    LogManager.log_channel_playlist(
                        "Reloading playlist data after processing",
                        LogLevels.Info,
                    )
                    playlist_data = await cls._load_playlist_data()
                else:
                    LogManager.log_channel_playlist(
                        "No new videos or shorts have been added since the last scan",
                        LogLevels.Info,
                    )

                # Sort and update totals regardless of new entries
                LogManager.log_channel_playlist(
                    "Saving playlist data",
                    LogLevels.Info,
                )
                await cls._save_playlist_data(playlist_data)

                LogManager.log_channel_playlist(
                    "Playlist update completed successfully", LogLevels.Info, 0
                )
        except Exception as e:
            import traceback

            LogManager.log_channel_playlist(
                f"CRITICAL ERROR in update_channel_playlist: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
                0,
            )

    @classmethod
    async def mark_as_downloaded(cls, url):
        """Mark a video as downloaded in the playlist with verification."""
        try:
            instance_name = await cls._get_instance_name()
            channel_source = await cls._get_channel_source()
            if not instance_name or not channel_source:
                raise RuntimeError("Cannot resolve playlist storage context")

            db = await cls._get_db()

            async def update_entry():
                updated = await db.update_channel_playlist_entry_field(
                    instance_name,
                    channel_source,
                    url,
                    "downloaded_video",
                    1,
                )
                if not updated:
                    return False
                entry = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                return bool(entry and entry.get("downloaded_video"))

            verified = await update_entry()
            if verified:
                LogManager.log_channel_playlist(
                    f"Successfully marked {url} as downloaded and verified",
                    LogLevels.Info,
                )
            else:
                LogManager.log_channel_playlist(
                    f"Video {url} not found or already marked as downloaded",
                    LogLevels.Warning,
                )
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to mark as downloaded: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def increment_video_download_attempts(cls, url):
        """Increment video download attempts counter with verification."""
        try:
            instance_name = await cls._get_instance_name()
            channel_source = await cls._get_channel_source()
            if not instance_name or not channel_source:
                raise RuntimeError("Cannot resolve playlist storage context")

            db = await cls._get_db()

            async def increment_attempts():
                entry = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                if not entry:
                    return None
                current_attempts = entry.get("video_download_attempts", 0) or 0
                new_attempts = current_attempts + 1
                updated = await db.update_channel_playlist_entry_field(
                    instance_name,
                    channel_source,
                    url,
                    "video_download_attempts",
                    new_attempts,
                )
                if not updated:
                    return None
                refreshed = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                return refreshed.get("video_download_attempts") if refreshed else None

            result_attempts = await increment_attempts()
            if result_attempts is not None:
                LogManager.log_channel_playlist(
                    f"Successfully incremented Video_Download_Attempts for {url} to {result_attempts}",
                    LogLevels.Info,
                )
            else:
                LogManager.log_channel_playlist(
                    f"Video {url} not found in playlist",
                    LogLevels.Warning,
                )
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to increment video download attempts: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def increment_caption_download_attempts(cls, url):
        """Increment caption download attempts counter with verification."""
        try:
            instance_name = await cls._get_instance_name()
            channel_source = await cls._get_channel_source()
            if not instance_name or not channel_source:
                raise RuntimeError("Cannot resolve playlist storage context")

            db = await cls._get_db()

            async def increment_attempts():
                entry = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                if not entry:
                    return None
                current_attempts = entry.get("caption_download_attempts", 0) or 0
                new_attempts = current_attempts + 1
                updated = await db.update_channel_playlist_entry_field(
                    instance_name,
                    channel_source,
                    url,
                    "caption_download_attempts",
                    new_attempts,
                )
                if not updated:
                    return None
                refreshed = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                return refreshed.get("caption_download_attempts") if refreshed else None

            result_attempts = await increment_attempts()
            if result_attempts is not None:
                LogManager.log_channel_playlist(
                    f"Successfully incremented Caption_Download_Attempts for {url} to {result_attempts}",
                    LogLevels.Info,
                )
            else:
                LogManager.log_channel_playlist(
                    f"Video {url} not found in playlist",
                    LogLevels.Warning,
                )
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to increment caption download attempts: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def mark_caption_downloaded(cls, url):
        """Mark a video's captions as downloaded in the playlist with verification."""
        try:
            instance_name = await cls._get_instance_name()
            channel_source = await cls._get_channel_source()
            if not instance_name or not channel_source:
                raise RuntimeError("Cannot resolve playlist storage context")

            db = await cls._get_db()

            async def update_entry():
                entry = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                if not entry:
                    return False
                updated = await db.update_channel_playlist_entry_field(
                    instance_name,
                    channel_source,
                    url,
                    "downloaded_caption",
                    1,
                )
                if not updated:
                    return False
                verified = await db.get_channel_playlist_entry_by_url(
                    instance_name, channel_source, url
                )
                return bool(verified and verified.get("downloaded_caption"))

            verified = await update_entry()
            if verified:
                LogManager.log_channel_playlist(
                    f"Successfully marked {url} captions as downloaded and verified",
                    LogLevels.Info,
                )
            else:
                LogManager.log_channel_playlist(
                    f"Video {url} not found or already marked as caption downloaded",
                    LogLevels.Warning,
                )
        except Exception as e:
            LogManager.log_channel_playlist(
                f"Failed to mark captions as downloaded: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise
