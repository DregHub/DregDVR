import contextlib
import os
import traceback
import asyncio
import json
import threading
import zipfile
from datetime import datetime, timezone
from dlp.helpers import DLPHelpers
from utils.file_utils import FileManager
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor


class PlaylistManager:
    playlist_dir = DVR_Config.get_channel_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    _channel_source = Account_Config.get_youtube_source()
    channel_playlist = DVR_Config.get_channel_playlist(_channel_source)
    channel = Account_Config.build_youtube_url(_channel_source)
    videos_url = channel.rstrip("/") + "/videos"
    shorts_url = channel.rstrip("/") + "/shorts"
    channel_playlist_log_file = DVR_Config.get_channel_playlist_log_file()
    
    @classmethod
    def _get_thread_log_file(cls, thread_number: int) -> str:
        """Generate thread-specific log file path."""
        log_dir = DVR_Config.get_log_dir()
        channel_name = cls._channel_source.lstrip('@').replace(' ', '_') if cls._channel_source else 'Channel'
        log_filename = f"Download_YouTube_Channel_Playlist_{channel_name}_Thread{{thread_number}}.log".format(thread_number=thread_number)
        return os.path.join(log_dir, log_filename)
    _update_playlist_lock = asyncio.Lock()
    # Thread-safe lock for file I/O to prevent race conditions when writing playlist JSON
    _playlist_file_lock = threading.Lock()

    @classmethod
    async def _ensure_playlist_file_exists(cls):
        """Ensure the persistent playlist file exists as an empty JSON array."""
        if not os.path.exists(cls.channel_playlist):
            try:
                def create_file():
                    with open(cls.channel_playlist, "w", encoding="utf-8") as f:
                        f.write("[]")
                await asyncio.to_thread(create_file)
            except Exception as ex:
                LogManager.log_message(f"Failed to create playlist file: {ex}", cls.channel_playlist_log_file)

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
    def _convert_to_new_format(cls, playlist_data):
        """Convert legacy playlist structures into new format with Totals + Videos."""
        if isinstance(playlist_data, list):
            playlist_data = {"Videos": playlist_data}

        if not isinstance(playlist_data, dict):
            return {"Videos": []}

        # If old style dict with video objects at top-level, detect and convert.
        if "Videos" not in playlist_data:
            candidate_videos = [v for v in playlist_data.values() if isinstance(v, dict) and "Title" in v]
            if candidate_videos and len(candidate_videos) > 0:
                playlist_data = {"Videos": candidate_videos}

        if "Videos" not in playlist_data or not isinstance(playlist_data.get("Videos"), list):
            playlist_data["Videos"] = []

        # Ensure totals are populated for new format (nor always saved on load, but consistent in memory)
        playlist_data = cls._update_json_totals(playlist_data)
        return playlist_data

    @classmethod
    async def _load_playlist_data(cls):
        """Load the current playlist data from the persistent file."""
        try:
            def load_json():
                with cls._playlist_file_lock:
                    with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not isinstance(data, dict):
                            # If it's still a list (old format), convert to new format
                            data = {"Videos": data}
                        return data
            playlist_data = await asyncio.to_thread(load_json)
            return cls._convert_to_new_format(playlist_data)
        except Exception:
            return {"Videos": []}

    @classmethod
    def _update_json_totals(cls, playlist_data):
        """Update playlist data with sorted videos and computed totals."""
        videos = playlist_data.get("Videos", [])
        # Sort the playlist data by title before saving
        videos.sort(key=lambda x: x.get("Title", "").lower())
        
        # Compute totals
        total_entries = len(videos)
        total_livestreams = sum(1 for item in videos if item.get("Was_Live") or item.get("Live_Status") == "was_live")
        total_posted_videos = sum(1 for item in videos if item.get("Live_Status") == "not_live" and not item.get("IsShort"))
        total_captions = sum(1 for item in videos if item.get("Has_Captions"))
        
        # Update the data in Totals section (and keep top-level for compatibility)
        totals = {
            "Total_Entries": total_entries,
            "Total_Livestreams": total_livestreams,
            "Total_Posted_Videos": total_posted_videos,
            "Total_Captions": total_captions,
            "Total_Downloads": sum(1 for item in videos if item.get("Downloaded_Video", False)),
            "Total_All_Platform_Uploads": sum(1 for item in videos if item.get("Uploaded_Video_All_Hosts", False)),
            "Total_YouTube_Uploads": sum(1 for item in videos if item.get("Uploaded_Video_YT", False)),
            "Total_Internet_Archive_Uploads": sum(1 for item in videos if item.get("Uploaded_Video_IA", False)),
            "Total_Rumble_Uploads": sum(1 for item in videos if item.get("Uploaded_Video_RM", False)),
            "Total_BitChute_Uploads": sum(1 for item in videos if item.get("Uploaded_Video_BC", False)),
            "Total_Odyssey_Uploads": sum(1 for item in videos if item.get("Uploaded_Video_OD", False)),
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

        ordered_data["Videos"] = videos

        return ordered_data

    @classmethod
    async def _save_playlist_data(cls, playlist_data):
        """Save the playlist data to the persistent file."""
        try:
            def save_json():
                updated_data = cls._update_json_totals(playlist_data)
                with cls._playlist_file_lock:
                    with open(cls.channel_playlist, "w", encoding="utf-8") as f:
                        json.dump(
                            updated_data,
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
            await asyncio.to_thread(save_json)
        except Exception as ex:
            LogManager.log_message(f"Failed to save playlist data: {ex}", cls.channel_playlist_log_file)

    @classmethod
    async def _add_missing_playlist_fields(cls, playlist_data):
        """Ensure each playlist entry includes required fields with sane defaults."""
        videos = playlist_data.get("Videos", [])
        if not isinstance(videos, list):
            return False

        required_defaults = {
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
        }

        updated = False
        for item in videos:
            if not isinstance(item, dict):
                continue
            for key, default in required_defaults.items():
                if key not in item:
                    item[key] = default
                    updated = True

        if updated:
            await cls._save_playlist_data(playlist_data)

        return updated

    @classmethod
    async def get_pending_upload_entries(cls, live_status_filter=None):
        """Return playlist entries ready for upload (downloaded but not all hosts uploaded)."""
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        pending = []

        for item in videos:
            if not item.get("Downloaded_Video", False):
                continue
            if item.get("Uploaded_Video_All_Hosts", False):
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
        ]:
            return False

        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        updated = False

        for item in videos:
            if item.get("URL") == url:
                item[platform_key] = bool(status)

                if (
                    item.get("Uploaded_Video_IA", False)
                    and item.get("Uploaded_Video_YT", False)
                    and item.get("Uploaded_Video_RM", False)
                ):
                    item["Uploaded_Video_All_Hosts"] = True
                else:
                    item["Uploaded_Video_All_Hosts"] = False

                updated = True
                break

        if updated:
            await cls._save_playlist_data(playlist_data)

        return updated

    @classmethod
    async def is_entry_fully_uploaded(cls, url):
        """Return True if all individual platform upload markers are set for the URL."""
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        for item in videos:
            if item.get("URL") == url:
                return (
                    item.get("Uploaded_Video_IA", False)
                    and item.get("Uploaded_Video_YT", False)
                    and item.get("Uploaded_Video_RM", False)
                    and item.get("Uploaded_Video_All_Hosts", False)
                )
        return False

    @classmethod
    async def _check_video_captions(cls, metadata, vidurl, thread_log_file=None):
        """Check if video has English automatic captions."""
        try:
            if metadata and "automatic_captions" in metadata:
                captions = metadata["automatic_captions"]
                return any(
                    lang.startswith("en") for lang in captions.keys()
                )
            else:
                return False
        except Exception as e:
            LogManager.log_message(
                f"Failed to check captions for {vidurl}: {e}", thread_log_file or cls.channel_playlist_log_file
            )
            return None

    @classmethod
    async def _add_basic_video_info_to_playlist(
        cls, vid_id, title, vidurl, thread_log_file
    ):  
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        exists = any(item.get("UniqueID") == vid_id for item in videos)
        if not exists:
            new_item = {
                "Title": title,
                "UniqueID": vid_id,
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
            }
            videos.append(new_item)
            playlist_data["Videos"] = videos
            await cls._save_playlist_data(playlist_data)
        else:
            LogManager.log_message(
                f"Video {vidurl} already exists in playlist, skipping basic info addition." , thread_log_file or cls.channel_playlist_log_file
            )
        

    @classmethod
    async def _fetch_full_metadata(cls, vidurl, thread_log_file=None):
        """Fetch full metadata for a video from yt-dlp."""
        ydl_opts = {
            "skip_download": True,
            "quiet": False,
            "ignore_no_formats_error": True,
            "extract_flat": False,
        }
        return await DLPHelpers.getinfo_with_retry(
            ydl_opts, vidurl, thread_log_file
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
                was_live = bool(metadata.get("was_live")) or (
                    live_status == "was_live"
                )
        return is_short, was_live, live_status

    @classmethod
    async def _handle_unknown_live_status(cls, metadata, vidurl, thread_log_file=None):
        """Handle videos with unknown live_status by logging full metadata."""
        LogManager.log_message(
            f"{vidurl} has unknown live_status. logging full metadata for debugging.",
            thread_log_file or cls.channel_playlist_log_file,
        )
        try:
            pretty = json.dumps(metadata, indent=2, ensure_ascii=False)
            LogManager.log_message(
                f"Full metadata for {vidurl}:\n{pretty}",
                thread_log_file or cls.channel_playlist_log_file,
            )
        except Exception as ex:
            LogManager.log_message(
                f"Failed to serialize metadata for {vidurl}: {ex}",
                thread_log_file or cls.channel_playlist_log_file,
            )

    @classmethod
    async def _handle_unwanted_live_status(cls, vidurl, live_status, thread_log_file=None):
        """Handle videos that should be skipped (not 'not_live' or 'unknown')."""
        LogManager.log_message(
            f"Skipping video : {vidurl} with live_status: {live_status}",
            thread_log_file or cls.channel_playlist_log_file,
        )

    @classmethod
    async def _process_not_live_video(
        cls, existing_item, metadata, vid_id, title, vidurl, is_short, was_live, live_status, thread_log_file=None
    ):
        """Process a video with live_status 'not_live' and add it to the playlist."""
        
        # Populate extended metadata fields for videos that are not live (this includes regular videos and past livestreams)
        existing_item["Has_Captions"] = await cls._check_video_captions(metadata, vidurl, thread_log_file=thread_log_file)
        existing_item["IsShort"] = is_short
        existing_item["Was_Live"] = was_live
        existing_item["Live_Status"] = live_status


        LogManager.log_message(
            f"{vid_id} - Has_Captions: {existing_item['Has_Captions']}, IsShort: {existing_item['IsShort']}, Was_Live: {existing_item['Was_Live']}, Live_Status: {existing_item['Live_Status']}",
            thread_log_file or cls.channel_playlist_log_file,
        )
        #We dont need to return anything as the existing_item is a reference to the item in the playlist_data list

    @classmethod
    async def _add_full_video_info_to_playlist(
        cls, vid_id, title, vidurl, thread_log_file=None
    ):
        """Add a new video item to the playlist or update existing item with full metadata."""
        LogManager.log_message(
            f"Fetching full metadata for {vid_id}",
            cls.channel_playlist_log_file,
        )
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        existing_item = next(
            (item for item in videos if item.get("UniqueID") == vid_id),
            None,
        )

        if not existing_item:
            # Create a new item if it doesn't exist
            existing_item = {
                "Title": title,
                "UniqueID": vid_id,
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
            }
            videos.append(existing_item)

        # Fetch full metadata
        metadata = await cls._fetch_full_metadata(vidurl, thread_log_file=thread_log_file)

        if metadata:
            is_short, was_live, live_status = cls._extract_video_properties(
                metadata, vidurl
            )

            if live_status == "unknown":
                await cls._handle_unknown_live_status(metadata, vidurl, thread_log_file=thread_log_file)
            elif live_status != "not_live":
                await cls._handle_unwanted_live_status(vidurl, live_status, thread_log_file=thread_log_file)
            else:
                await cls._process_not_live_video(
                    existing_item, metadata, vid_id, title, vidurl, is_short, was_live, live_status, thread_log_file=thread_log_file
                )

        playlist_data["Videos"] = videos
        await cls._save_playlist_data(playlist_data)

    @classmethod
    def _process_entries_threaded_wrapper(cls, entry, thread_number):
        """Wrapper to handle async context within thread for processing entries."""
        try:
            thread_log_file = cls._get_thread_log_file(thread_number)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                cls._process_entry_async(entry, thread_log_file)
            )
            loop.close()
        except Exception as e:
            thread_log_file = cls._get_thread_log_file(thread_number)
            LogManager.log_message(
                f"Wrapper error in thread {thread_number}: {e}\n{traceback.format_exc()}",
                thread_log_file,
            )

    @classmethod
    async def _process_entry_async(cls, entry, thread_log_file):
        """Process a single entry asynchronously."""
        try:
            vid_id = entry.get("id")
            title = (
                entry.get("title").replace("\n", " ").replace("\r", " ")
                if entry.get("title")
                else ""
            )
            vidurl = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None
            
            await cls._add_basic_video_info_to_playlist(vid_id, title, vidurl, thread_log_file)
            await cls._add_full_video_info_to_playlist(vid_id, title, vidurl, thread_log_file)
        except Exception as e:
            LogManager.log_message(
                f"Error processing entry {entry.get('id')}: {e}\n{traceback.format_exc()}",
                thread_log_file,
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
    async def _fetch_channel_entries(cls):
        """Fetch videos and shorts from the channel using flat extraction."""
        ydl_opts_flat = {
            "skip_download": True,
            "ignore_no_formats_error": True,
            "extract_flat": True,
        }

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

        return videos_info, shorts_info

    @classmethod
    async def _filter_new_entries(cls, flat_entries):
        """Filter entries that are not already in the persistent playlist."""
        playlist_data = await cls._load_playlist_data()
        videos = playlist_data.get("Videos", [])
        existing_ids = {item.get("UniqueID") for item in videos}
        
        return [
            e
            for e in flat_entries
            if e.get("id") and e.get("id") not in existing_ids
        ]

    @classmethod
    async def _process_new_entries(cls, new_entries):
        """Process new entries by adding them to the playlist."""
        new_videos = sum(not cls._is_short_entry(e) for e in new_entries)
        new_shorts = len(new_entries) - new_videos

        LogManager.log_message(
            f"Found {new_videos} new videos and {new_shorts} new shorts since the last scan",
            cls.channel_playlist_log_file,
        )

        LogManager.log_message(
            f"Adding basic video info to playlist for {new_videos} new videos and {new_shorts} new shorts",
            cls.channel_playlist_log_file,
        )

        try:
            max_threads = int(DVR_Config.get_maximum_threads())
            LogManager.log_message(
                f"Loaded MaxThreads = {max_threads} from DVR Settings",cls.channel_playlist_log_file,
            )
        except Exception:
            LogManager.log_message(
                "Error loading MaxThreads from DVR Settings defaulting to 1",cls.channel_playlist_log_file,
            )
            max_threads = 1

        if len(new_entries) > max_threads:
            LogManager.log_message(
                f"Processing {len(new_entries)} entries concurrently using ThreadPoolExecutor(max_workers={max_threads})",
                cls.channel_playlist_log_file,
            )
            
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = []
                
                # Submit all entries to thread pool with assigned thread numbers
                for index, entry in enumerate(new_entries):
                    thread_number = (index % max_threads) + 1
                    future = executor.submit(
                        cls._process_entries_threaded_wrapper,
                        entry,
                        thread_number
                    )
                    futures.append(future)
                
                # Wait for all threads to complete
                for future in futures:
                    try:
                        future.result(timeout=1800)  # 30 minute timeout per entry
                    except Exception as e:
                        LogManager.log_message(
                            f"Thread execution error: {e}\n{traceback.format_exc()}",
                            cls.channel_playlist_log_file,
                        )
        else:
            LogManager.log_message(
                f"Processing {len(new_entries)} entries sequentially without concurrency",cls.channel_playlist_log_file,
            )
            for e in new_entries:
                vid_id = e.get("id")
                title = (
                    e.get("title").replace("\n", " ").replace("\r", " ")
                    if e.get("title")
                    else ""
                )
                vidurl = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None

                await cls._add_basic_video_info_to_playlist(vid_id, title, vidurl, cls.channel_playlist_log_file)
                await cls._add_full_video_info_to_playlist(vid_id, title, vidurl, cls.channel_playlist_log_file)

    @classmethod
    async def run_playlist_update_task(cls):
        """Run a continuous task that updates the channel playlist every 5 minutes."""
        while True:
            await cls.update_channel_playlist()
            await asyncio.sleep(300)  # Sleep for 5 minutes

    @classmethod
    async def update_channel_playlist(cls):
        """Update the channel playlist with new videos and shorts."""
        async with cls._update_playlist_lock:
            # Create automatic zip backup
            try:
                current_date = datetime.now().strftime('%Y-%m-%d')
                channel_name = cls._channel_source.lstrip('@').replace(' ', '_') if cls._channel_source else 'channel'
                backup_name = FileManager.gen_safe_filename(f"Playlist_Backup_{channel_name}_{current_date}.zip")
                backup_dir = os.path.join(cls.playlist_dir, "_Backups")
                backup_path = os.path.join(backup_dir, backup_name)
                
                def create_backup():
                    os.makedirs(backup_dir, exist_ok=True)
                    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.write(cls.channel_playlist, os.path.basename(cls.channel_playlist))
                
                await asyncio.to_thread(create_backup)
                LogManager.log_message(
                    f"Created playlist backup: {backup_path}",
                    cls.channel_playlist_log_file,
                )
            except Exception as ex:
                LogManager.log_message(
                    f"Failed to create playlist backup: {ex}",
                    cls.channel_playlist_log_file,
                )

            # Step 1: Fetch videos and shorts from the channel
            videos_info, shorts_info = await cls._fetch_channel_entries()

            if videos_info is None and shorts_info is None:
                LogManager.log_message(
                    "Failed to retrieve channel video entries",
                    cls.channel_playlist_log_file,
                )
                return

            await cls._ensure_playlist_file_exists()

            # Step 2: Upgrade existing playlist entries with missing fields (new defaults)
            playlist_data = await cls._load_playlist_data()
            await cls._add_missing_playlist_fields(playlist_data)

            # Step 3: Normalize and merge flat entries from both sources
            videos_entries = cls._normalize_entries(videos_info)
            shorts_entries = cls._normalize_entries(shorts_info)
            flat_entries = videos_entries + shorts_entries

            # Step 3: Filter new entries not already in playlist
            new_entries = await cls._filter_new_entries(flat_entries)

            if new_entries:
                # Step 4 & 5: Process new entries (add basic and full metadata)
                await cls._process_new_entries(new_entries)
            else:
                LogManager.log_message(
                    "No new videos or shorts have been added since the last scan",
                    cls.channel_playlist_log_file,
                )

            # Sort and update totals regardless of new entries
            playlist_data = await cls._load_playlist_data()
            await cls._save_playlist_data(playlist_data)



    @classmethod
    async def mark_as_downloaded(cls, url):
        """Mark a video as downloaded in the playlist with verification."""
        try:
            def load_playlist():
                try:
                    with cls._playlist_file_lock:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            return json.load(f)
                except Exception:
                    return []

            def save_and_verify_playlist(data):
                """Save playlist and verify write was successful."""
                with cls._playlist_file_lock:
                    # Save the playlist
                    with open(cls.channel_playlist, "w", encoding="utf-8") as f:
                        json.dump(
                            data,
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    
                    # Read back immediately to verify write was successful
                    try:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            verified_data = json.load(f)
                        
                        # Check if the URL exists and is marked as downloaded
                        verification_successful = False
                        for item in verified_data:
                            if item.get("URL") == url and item.get("Downloaded_Video") is True:
                                verification_successful = True
                                break
                        
                        if not verification_successful:
                            raise Exception(
                                f"Verification failed: URL {url} not found or not marked as Downloaded_Video=true after save"
                            )
                        
                        return True
                    except json.JSONDecodeError as ex:
                        raise Exception(f"Verification failed: Saved JSON is corrupted - {ex}")

            playlist_data = await asyncio.to_thread(load_playlist)
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
                    await asyncio.to_thread(lambda: save_and_verify_playlist(playlist_data))
                    LogManager.log_message(
                        f"Successfully marked {url} as downloaded and verified",
                        cls.channel_playlist_log_file
                    )
                except Exception as ex:
                    LogManager.log_message(
                        f"Failed to mark or verify {url} as downloaded: {ex}\n{traceback.format_exc()}",
                        cls.channel_playlist_log_file
                    )
                    raise
            else:
                LogManager.log_message(
                    f"Video {url} not found or already marked as downloaded",
                    cls.channel_playlist_log_file,
                )
        except Exception as e:
            LogManager.log_message(
                f"Failed to mark as downloaded: {e}\n{traceback.format_exc()}",cls.channel_playlist_log_file
            )
            raise

    async def increment_video_download_attempts(cls, url):
        """Increment video download attempts counter with verification."""
        try:
            def load_playlist():
                try:
                    with cls._playlist_file_lock:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            return json.load(f)
                except Exception:
                    return []

            def save_and_verify_playlist(data, expected_attempts):
                """Save playlist and verify increment was successful."""
                with cls._playlist_file_lock:
                    # Save the playlist
                    with open(cls.channel_playlist, "w", encoding="utf-8") as f:
                        json.dump(
                            data,
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    
                    # Read back immediately to verify write was successful
                    try:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            verified_data = json.load(f)
                        
                        # Check if the URL exists and has the correct attempt count
                        verification_successful = False
                        for item in verified_data:
                            if item.get("URL") == url and item.get("Video_Download_Attempts") == expected_attempts:
                                verification_successful = True
                                break
                        
                        if not verification_successful:
                            raise Exception(
                                f"Verification failed: URL {url} not found or Video_Download_Attempts != {expected_attempts} after save"
                            )
                        
                        return True
                    except json.JSONDecodeError as ex:
                        raise Exception(f"Verification failed: Saved JSON is corrupted - {ex}")

            playlist_data = await asyncio.to_thread(load_playlist)
            updated = False
            
            for item in playlist_data:
                if item.get("URL") == url:
                    current_attempts = item.get("Video_Download_Attempts", 0)
                    new_attempts = current_attempts + 1
                    item["Video_Download_Attempts"] = new_attempts
                    updated = True
                    break

            if updated:
                try:
                    await asyncio.to_thread(lambda: save_and_verify_playlist(playlist_data, new_attempts))
                    LogManager.log_message(
                        f"Successfully incremented Video_Download_Attempts for {url} to {new_attempts}",
                        cls.channel_playlist_log_file
                    )
                except Exception as ex:
                    LogManager.log_message(
                        f"Failed to increment or verify Video_Download_Attempts for {url}: {ex}\n{traceback.format_exc()}",
                        cls.channel_playlist_log_file
                    )
                    raise
            else:
                LogManager.log_message(
                    f"Video {url} not found in playlist",
                    cls.channel_playlist_log_file,
                )
        except Exception as e:
            LogManager.log_message(
                f"Failed to increment video download attempts: {e}\n{traceback.format_exc()}",cls.channel_playlist_log_file
            )
            raise

    async def increment_caption_download_attempts(cls, url):
        """Increment caption download attempts counter with verification."""
        try:
            def load_playlist():
                try:
                    with cls._playlist_file_lock:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            return json.load(f)
                except Exception:
                    return []

            def save_and_verify_playlist(data, expected_attempts):
                """Save playlist and verify increment was successful."""
                with cls._playlist_file_lock:
                    # Save the playlist
                    with open(cls.channel_playlist, "w", encoding="utf-8") as f:
                        json.dump(
                            data,
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    
                    # Read back immediately to verify write was successful
                    try:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            verified_data = json.load(f)
                        
                        # Check if the URL exists and has the correct attempt count
                        verification_successful = False
                        for item in verified_data:
                            if item.get("URL") == url and item.get("Caption_Download_Attempts") == expected_attempts:
                                verification_successful = True
                                break
                        
                        if not verification_successful:
                            raise Exception(
                                f"Verification failed: URL {url} not found or Caption_Download_Attempts != {expected_attempts} after save"
                            )
                        
                        return True
                    except json.JSONDecodeError as ex:
                        raise Exception(f"Verification failed: Saved JSON is corrupted - {ex}")

            playlist_data = await asyncio.to_thread(load_playlist)
            updated = False
            
            for item in playlist_data:
                if item.get("URL") == url:
                    current_attempts = item.get("Caption_Download_Attempts", 0)
                    new_attempts = current_attempts + 1
                    item["Caption_Download_Attempts"] = new_attempts
                    updated = True
                    break

            if updated:
                try:
                    await asyncio.to_thread(lambda: save_and_verify_playlist(playlist_data, new_attempts))
                    LogManager.log_message(
                        f"Successfully incremented Caption_Download_Attempts for {url} to {new_attempts}",
                        cls.channel_playlist_log_file
                    )
                except Exception as ex:
                    LogManager.log_message(
                        f"Failed to increment or verify Caption_Download_Attempts for {url}: {ex}\n{traceback.format_exc()}",
                        cls.channel_playlist_log_file
                    )
                    raise
            else:
                LogManager.log_message(
                    f"Video {url} not found in playlist",
                    cls.channel_playlist_log_file,
                )
        except Exception as e:
            LogManager.log_message(
                f"Failed to increment caption download attempts: {e}\n{traceback.format_exc()}",cls.channel_playlist_log_file
            )
            raise

    async def mark_caption_downloaded(cls, url):
        """Mark a video's captions as downloaded in the playlist with verification."""
        try:
            def load_playlist():
                try:
                    with cls._playlist_file_lock:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            return json.load(f)
                except Exception:
                    return []

            def save_and_verify_playlist(data):
                """Save playlist and verify write was successful."""
                with cls._playlist_file_lock:
                    # Save the playlist
                    with open(cls.channel_playlist, "w", encoding="utf-8") as f:
                        json.dump(
                            data,
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    
                    # Read back immediately to verify write was successful
                    try:
                        with open(cls.channel_playlist, "r", encoding="utf-8") as f:
                            verified_data = json.load(f)
                        
                        # Check if the URL exists and is marked as caption downloaded
                        verification_successful = False
                        for item in verified_data:
                            if item.get("URL") == url and item.get("Downloaded_Caption") is True:
                                verification_successful = True
                                break
                        
                        if not verification_successful:
                            raise Exception(
                                f"Verification failed: URL {url} not found or not marked as Downloaded_Caption=true after save"
                            )
                        
                        return True
                    except json.JSONDecodeError as ex:
                        raise Exception(f"Verification failed: Saved JSON is corrupted - {ex}")

            playlist_data = await asyncio.to_thread(load_playlist)
            updated = False
            
            for item in playlist_data:
                if item.get("URL") == url and not item.get("Downloaded_Caption", False):
                    item["Downloaded_Caption"] = True
                    try:
                        item["CaptionDownloadedDateTime"] = datetime.now(
                            timezone.utc
                        ).isoformat()
                    except Exception:
                        item["CaptionDownloadedDateTime"] = None
                    updated = True
                    break

            if updated:
                try:
                    await asyncio.to_thread(lambda: save_and_verify_playlist(playlist_data))
                    LogManager.log_message(
                        f"Successfully marked {url} captions as downloaded and verified",
                        cls.channel_playlist_log_file
                    )
                except Exception as ex:
                    LogManager.log_message(
                        f"Failed to mark or verify {url} captions as downloaded: {ex}\n{traceback.format_exc()}",
                        cls.channel_playlist_log_file
                    )
                    raise
            else:
                LogManager.log_message(
                    f"Video {url} not found or already marked as caption downloaded",
                    cls.channel_playlist_log_file,
                )
        except Exception as e:
            LogManager.log_message(
                f"Failed to mark captions as downloaded: {e}\n{traceback.format_exc()}",cls.channel_playlist_log_file
            )
            raise
