import os
import traceback
import asyncio
import json
from datetime import datetime, timezone
from dlp.helpers import DLPHelpers
from utils.file_utils import FileManager
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class PlaylistManager:
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    _channel_source = Account_Config.get_youtube_source()
    channel_playlist = DVR_Config.get_channel_playlist(_channel_source)
    channel = Account_Config.build_youtube_url(_channel_source)
    videos_url = channel.rstrip("/") + "/videos"
    shorts_url = channel.rstrip("/") + "/shorts"
    channel_playlist_log_file = DVR_Config.get_channel_playlist_log_file()
    _update_playlist_lock = asyncio.Lock()

    @classmethod
    async def _ensure_playlist_file_exists(cls):
        """Ensure the persistent playlist file exists as an empty JSON array."""
        if not os.path.exists(cls.channel_playlist):
            try:
                await asyncio.to_thread(
                    lambda: open(cls.channel_playlist, "w", encoding="utf-8").write(
                        "[]"
                    )
                )
            except Exception as ex:
                LogManager.log_message(f"Failed to create playlist file: {ex}",cls.channel_playlist_log_file)

    @classmethod
    def _normalize_entries(cls, info):
        """Normalize the info response to a list of entries."""
        if isinstance(info, list):
            return info
        try:
            return info.get("entries") or []
        except Exception:
            return []

    @classmethod
    async def _load_playlist_data(cls):
        """Load the current playlist data from the persistent file."""
        try:
            return await asyncio.to_thread(
                lambda: json.load(open(cls.channel_playlist, "r", encoding="utf-8"))
            )
        except Exception:
            return []

    @classmethod
    async def _save_playlist_data(cls, playlist_data):
        """Save the playlist data to the persistent file."""
        try:
            await asyncio.to_thread(
                lambda: json.dump(
                    playlist_data,
                    open(cls.channel_playlist, "w", encoding="utf-8"),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception as ex:
            LogManager.log_message(f"Failed to save playlist data: {ex}",cls.channel_playlist_log_file)


    @classmethod
    async def _populate_has_captions(cls):
        """Populate the 'Has_Captions' field for all playlist items."""
        playlist_data = await cls._load_playlist_data()
        updated = False

        for item in playlist_data:
            if "Has_Captions" not in item:
                if url := item.get("URL"):
                    result = await cls._check_video_captions(url)
                    item["Has_Captions"] = result
                    if result is not None:
                        updated = True

        if updated:
            await cls._save_playlist_data(playlist_data)

    @classmethod
    async def _check_video_captions(cls, vidurl):
        """Check if video has English automatic captions."""
        try:
            ydl_opts = {
                "skip_download": True,
                "ignore_no_formats_error": True,
                "extract_flat": False,
            }
            info = await DLPHelpers.getinfo_with_retry(
                ydl_opts, vidurl, None, cls.channel_playlist_log_file
            )
            if info and "automatic_captions" in info:
                captions = info["automatic_captions"]
                return any(
                    lang.startswith("en") for lang in captions.keys()
                )
            else:
                return False
        except Exception as e:
            LogManager.log_message(
                f"Failed to check captions for {vidurl}: {e}",cls.channel_playlist_log_file
            )
            return None

    @classmethod
    async def _add_video_to_playlist(
        cls, vid_id, title, vidurl, is_short, was_live, live_status
    ):
        """Add a new video item to the playlist if it doesn't already exist."""
        playlist_data = await cls._load_playlist_data()
        exists = any(item.get("UniqueID") == vid_id for item in playlist_data)
        if not exists:
            new_item = {
                "Title": title,
                "UniqueID": vid_id,
                "DateTime": datetime.now(timezone.utc).isoformat(),
                "URL": vidurl,
                "IsShort": is_short,
                "Live_Status": live_status,
                "Was_Live": was_live,
                "Has_Captions": None,
                "Downloaded_Video": False,
                "Downloaded_Caption": False,
                "Video_Download_Attempts": 0,
                "Caption_Download_Attempts": 0,
            }
            
            # Populate Has_Captions asynchronously
            new_item["Has_Captions"] = await cls._check_video_captions(vidurl)
            
            playlist_data.append(new_item)
            await cls._save_playlist_data(playlist_data)

    @classmethod
    async def _process_video_entry(cls, e):
        """Process a single video entry from the channel."""
        if not e:
            LogManager.log_message("No video entries found",cls.channel_playlist_log_file)
            return

        vid_id = e.get("id")
        title = (
            e.get("title").replace("\n", " ").replace("\r", " ")
            if e.get("title")
            else ""
        )
        vidurl = e.get("webpage_url")
        duration = e.get("duration")
        live_status = e.get("live_status", "unknown")

        if vidurl is None:
            LogManager.log_message("Video entry with no vidurl found, ",cls.channel_playlist_log_file)

        elif live_status == "unknown":
            LogManager.log_message(
                f"{vidurl} has unknown live_status. logging full metadata for debugging.",cls.channel_playlist_log_file
            )
            try:
                pretty = json.dumps(e, indent=2, ensure_ascii=False)
                LogManager.log_message(f"Full metadata for {vidurl}:\n{pretty}",cls.channel_playlist_log_file)
            except Exception as ex:
                LogManager.log_message(
                    f"Failed to serialize metadata for {vidurl}: {ex}",cls.channel_playlist_log_file
                )
        elif live_status != "not_live":
            LogManager.log_message(
                f"Skipping video : {vidurl} with live_status: {live_status}",cls.channel_playlist_log_file
            )
        else:
            LogManager.log_message(
                f"Adding video : {vidurl} with live_status: {live_status}",cls.channel_playlist_log_file
            )
            # Determine if this entry is a short
            try:
                is_short = (
                    bool(e.get("is_short"))
                    or (vidurl is not None and "/shorts/" in vidurl)
                    or (isinstance(duration, (int, float)) and duration <= 60)
                )
            except Exception:
                is_short = False

            # Determine if this video was previously live
            try:
                was_live = bool(e.get("was_live")) or (
                    e.get("live_status") == "was_live"
                )
            except Exception:
                was_live = False

            await cls._add_video_to_playlist(
                vid_id, title, vidurl, is_short, was_live, live_status
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
    async def _process_new_entries(cls, new_entries):
        """Fetch full metadata for new entries and add them to the playlist."""
        ydl_opts_full = {
            "skip_download": True,
            "ignore_no_formats_error": True,
            "extract_flat": False,
        }
        
        for e in new_entries:
            vidurl = e.get("webpage_url")
            if not vidurl:
                continue
            
            try:
                # Fetch full metadata for this specific video
                info = await DLPHelpers.getinfo_with_retry(
                    ydl_opts_full, vidurl, None, cls.channel_playlist_log_file
                )
                
                if info:
                    await cls._process_video_entry(info)
            except Exception as ex:
                LogManager.log_message(f"Failed to fetch full metadata for {vidurl}: {ex}",cls.channel_playlist_log_file)

    @classmethod
    async def update_channel_playlist(cls):
        async with cls._update_playlist_lock:
            # Step 1: Quick extraction to see what's on the channel (flat extraction for speed)
            ydl_opts_flat = {
                "skip_download": True,
                "ignore_no_formats_error": True,
                "extract_flat": True,
            }

            # Fetch videos and shorts quickly (flat extraction)
            videos_info = await DLPHelpers.getinfo_with_retry(
                ydl_opts_flat,
                cls.videos_url,
                cls.channel_playlist_log_file,
            )

            shorts_info = await DLPHelpers.getinfo_with_retry(
                ydl_opts_flat,
                cls.shorts_url,
                cls.channel_playlist_log_file,
            )

            if videos_info is None and shorts_info is None:
                LogManager.log_message("Failed to retrieve channel video entries",cls.channel_playlist_log_file)
                return

            await cls._ensure_playlist_file_exists()

            # Step 2: Normalize and merge flat entries from both sources
            videos_entries = cls._normalize_entries(videos_info)
            shorts_entries = cls._normalize_entries(shorts_info)
            flat_entries = videos_entries + shorts_entries

            # Step 3: Load persistent playlist and compare
            channel_playlist = await cls._load_playlist_data()
            existing_ids = {item.get("UniqueID") for item in channel_playlist}

            if new_entries := [
                e
                for e in flat_entries
                if e.get("id") and e.get("id") not in existing_ids
            ]:
                new_videos = sum(not cls._is_short_entry(e) for e in new_entries)
                new_shorts = len(new_entries) - new_videos
                LogManager.log_message(
                    f"Found {new_videos} new videos and {new_shorts} new shorts since the last scan",cls.channel_playlist_log_file
                )

                # Step 5: Fetch full metadata and process new entries
                await cls._process_new_entries(new_entries)
            else:
                LogManager.log_message("No new videos or shorts have been added since the last scan",cls.channel_playlist_log_file)

    @classmethod
    async def mark_as_downloaded(cls, url):
        try:
            try:
                playlist_data = await asyncio.to_thread(
                    lambda: json.load(
                        open(cls.channel_playlist, "r", encoding="utf-8")
                    )
                )
            except Exception:
                playlist_data = []

            updated = False
            for item in playlist_data:
                if item.get("URL") == url and not item.get("Downloaded_Video", False):
                    item["Downloaded_Video"] = True
                    try:
                        item["DownloadedDateTime"] = datetime.now(
                            timezone.utc
                        ).isoformat()
                    except Exception:
                        item["DownloadedDateTime"] = None
                    updated = True

            if updated:
                try:
                    await asyncio.to_thread(
                        lambda: json.dump(
                            playlist_data,
                            open(cls.channel_playlist, "w", encoding="utf-8"),
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                except Exception as ex:
                    LogManager.log_message(
                        f"Failed to save playlist after update: {ex}",cls.channel_playlist_log_file
                    )
        except Exception as e:
            LogManager.log_message(
                f"Failed to mark as downloaded: {e}\n{traceback.format_exc()}",cls.channel_playlist_log_file
            )