import os
import traceback
import asyncio
import json
from datetime import datetime, timezone
from utils.dlp_utils import getinfo_with_retry, getentries_with_retry
from utils.file_utils import FileManager
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class PlaylistManager:
    playlist_dir = DVR_Config.get_posted_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    persistent_playlist = DVR_Config.get_posted_persistent_playlist()
    channel = Account_Config.get_youtube_handle()
    videos_url = channel.rstrip("/") + "/videos"
    shorts_url = channel.rstrip("/") + "/shorts"

    @classmethod
    async def update_channel_playlist(cls):
        ydl_opts = {
            "skip_download": True,
            "quiet": False,
            "ignore_no_formats_error": True,
            "extract_flat": False,
        }

        info = await getentries_with_retry(
            ydl_opts,
            cls.videos_url,
            cls.shorts_url,
            LogManager.POSTED_PLAYLIST_LOG_FILE,
        )
        if info is None:
            LogManager.log_posted_playlist("Failed to retrieve channel video entries")
            return

        # Ensure persistent playlist exists as JSON array
        if not os.path.exists(cls.persistent_playlist):
            try:
                await asyncio.to_thread(
                    lambda: open(cls.persistent_playlist, "w", encoding="utf-8").write(
                        "[]"
                    )
                )
            except Exception as ex:
                LogManager.log_posted_playlist(f"Failed to create playlist file: {ex}")

        # Normalize entries: get list whether info is a dict with 'entries' or a list directly
        if isinstance(info, list):
            entries = info
        else:
            try:
                entries = info.get("entries") or []
            except Exception:
                entries = []

        for e in entries:
            if not e:
                LogManager.log_posted_playlist("No video entries found")
                continue

            vid_id = e.get("id")
            title = (
                e.get("title").replace("\n", " ").replace("\r", " ")
                if e.get("title")
                else ""
            )
            vidurl = e.get("webpage_url")
            duration = e.get("duration")
            live_status = e.get("live_status", "unknown")

            if vidurl is not None:
                if live_status == "unknown":
                    LogManager.log_posted_playlist(
                        f"{vidurl} has unknown live_status. logging full metadata for debugging."
                    )
                    try:
                        pretty = json.dumps(e, indent=2, ensure_ascii=False)
                        LogManager.log_posted_playlist(
                            f"Full metadata for {vidurl}:\n{pretty}"
                        )
                    except Exception as ex:
                        LogManager.log_posted_playlist(
                            f"Failed to serialize metadata for {vidurl}: {ex}"
                        )

                elif live_status != "not_live":
                    LogManager.log_posted_playlist(
                        f"Skipping video : {vidurl} with live_status: {live_status}"
                    )
                else:
                    LogManager.log_posted_playlist(
                        f"Adding video : {vidurl} with live_status: {live_status} to playlist"
                    )
                    try:
                        # Load current JSON playlist in a thread to avoid blocking
                        try:
                            playlist_data = await asyncio.to_thread(
                                lambda: json.load(
                                    open(
                                        cls.persistent_playlist,
                                        "r",
                                        encoding="utf-8",
                                    )
                                )
                            )
                        except Exception:
                            playlist_data = []

                        # Check if video already present by UniqueID
                        exists = any(
                            (item.get("UniqueID") == vid_id) for item in playlist_data
                        )

                    except Exception:
                        exists = False

                    if not exists:
                        # Determine if this entry is a short
                        try:
                            is_short = (
                                bool(e.get("is_short"))
                                or (vidurl is not None and "/shorts/" in vidurl)
                                or (
                                    isinstance(duration, (int, float))
                                    and duration <= 60
                                )
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

                        new_item = {
                            "Title": title,
                            "UniqueID": vid_id,
                            "DateTime": datetime.now(timezone.utc).isoformat(),
                            "URL": vidurl,
                            "IsShort": is_short,
                            "Live_Status": live_status,
                            "Was_Live": was_live,
                            "Downloaded": False,
                        }
                        try:
                            playlist_data.append(new_item)
                            await asyncio.to_thread(
                                lambda: json.dump(
                                    playlist_data,
                                    open(
                                        cls.persistent_playlist,
                                        "w",
                                        encoding="utf-8",
                                    ),
                                    ensure_ascii=False,
                                    indent=2,
                                )
                            )
                        except Exception as ex:
                            LogManager.log_posted_playlist(
                                f"Failed to write to playlist: {ex}"
                            )

            else:
                LogManager.log_posted_playlist("Video entry with no vidurl found, ")

    @classmethod
    async def mark_as_downloaded(cls, url):
        try:
            try:
                playlist_data = await asyncio.to_thread(
                    lambda: json.load(
                        open(cls.persistent_playlist, "r", encoding="utf-8")
                    )
                )
            except Exception:
                playlist_data = []

            updated = False
            for item in playlist_data:
                if item.get("URL") == url and not item.get("Downloaded", False):
                    item["Downloaded"] = True
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
                            open(cls.persistent_playlist, "w", encoding="utf-8"),
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                except Exception as ex:
                    LogManager.log_posted_playlist(
                        f"Failed to save playlist after update: {ex}"
                    )
        except Exception as e:
            LogManager.log_posted_playlist(
                f"Failed to mark as downloaded: {e}\n{traceback.format_exc()}"
            )
