import os
import csv
import traceback
import asyncio
import json
from yt_dlp import YoutubeDL
from utils.file_utils import FileManager
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config


class PlaylistManager:
    playlist_dir = DVR_Config.get_posted_playlists_dir()
    Posted_DownloadQueue_Dir = DVR_Config.get_posted_downloadqueue_dir()
    delta_playlist = DVR_Config.get_posted_delta_playlist()
    persistent_playlist = DVR_Config.get_posted_persistent_playlist()
    posted_download_list = DVR_Config.get_posted_download_list()

    @classmethod
    async def download_channel_playlist(cls):
        open(cls.delta_playlist, "w").close()
        channel = Account_Config.get_youtube_handle()

        def extract_playlist():
            ydl_opts = {
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }
            lines = []
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel, download=False)
                entries = info.get("entries") or [info]
                for e in entries:
                    if not e:
                        continue

                    vidurl = e.get("url")
                    if vidurl is not None:
                        LogManager.log_download_posted(
                            f"Checking: {vidurl} for video download eligibility"
                        )
                        # treat missing live_status as not_live
                        live_status = e.get("live_status", "unknown")

                        if live_status == "unknown":
                            LogManager.log_download_posted(
                                f"{vidurl} has unknown live_status. logging full metadata for debugging."
                            )
                            # log all properties for debugging
                            try:
                                pretty = json.dumps(e, indent=2, ensure_ascii=False)
                                LogManager.log_download_posted(
                                    f"Full metadata for {vidurl}:\n{pretty}"
                                )
                            except Exception as ex:
                                LogManager.log_download_posted(
                                    f"Failed to serialize metadata for {vidurl}: {ex}"
                                )

                        elif live_status != "not_live":
                            LogManager.log_download_posted(
                                f"Skipping video : {vidurl} with live_status: {live_status}"
                            )
                        else:
                            live_status = e.get("live_status", "unknown")
                            vid_id = e.get("id") or e.get("url")
                            title = (
                                e.get("title", "").replace("\n", " ").replace("\r", " ")
                            )
                            url = (
                                e.get("url")
                                or e.get("webpage_url")
                                or f"https://www.youtube.com/watch?v={vid_id}"
                            )
                            LogManager.log_download_posted(
                                f"Adding video : {vidurl} with live_status: {live_status}"
                            )
                            lines.append(f"{vid_id},{title},{url},0")
                    else:
                        # log all properties for debugging
                        try:
                            pretty = json.dumps(e, indent=2, ensure_ascii=False)
                            LogManager.log_download_posted(
                                f"Entry with no vidurl found full metadata to follow:\n{pretty}"
                            )
                        except Exception as ex:
                            LogManager.log_download_posted(
                                f"Failed to serialize metadata for {vidurl}: {ex}"
                            )
            return lines

        try:
            lines = await asyncio.to_thread(extract_playlist)
            with open(cls.delta_playlist, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")
        except Exception as e:
            LogManager.log_download_posted(
                f"yt-dlp API playlist extraction failed: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    async def merge_delta_playlist(cls):
        headers = ["UniqueID", "Title", "URL", "Downloaded"]

        # Skip if delta_playlist is missing or empty
        if not os.path.exists(cls.delta_playlist):
            # LogManager.log_download_posted(f"Delta playlist file {cls.delta_playlist} does not exist. Skipping merge.")
            return

        try:
            with open(cls.delta_playlist, "r", encoding="utf-8") as source_file:
                delta_lines = [line.strip() for line in source_file if line.strip()]

            if not delta_lines:
                return

            existing_ids = set()
            # Create persistent_playlist with headers if it does not exist
            if not os.path.exists(cls.persistent_playlist):
                with open(
                    cls.persistent_playlist, "w", newline="", encoding="utf-8"
                ) as outfile:
                    writer = csv.writer(outfile)
                    writer.writerow(headers)
            else:
                with open(
                    cls.persistent_playlist, "r", encoding="utf-8"
                ) as persistent_file:
                    reader = csv.reader(persistent_file)
                    next(reader, None)
                    for row in reader:
                        if row and row[0]:
                            existing_ids.add(row[0])

            # Open persistent_playlist in append mode to write new rows
            with open(
                cls.persistent_playlist, "a", newline="", encoding="utf-8"
            ) as outfile:
                writer = csv.writer(outfile)
                for line in delta_lines:
                    row = line.split(",", 3)
                    while len(row) < 4:
                        row.append("")
                    unique_id = row[0]

                    if not existing_ids or (
                        unique_id and unique_id not in existing_ids
                    ):
                        writer.writerow(row)
                        existing_ids.add(unique_id)
            # LogManager.log_download_posted(f"Merged delta playlist written to {cls.persistent_playlist}")
        except Exception as e:
            LogManager.log_download_posted(
                f"Failed to merge delta playlist:  {e}\n{traceback.format_exc()}"
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
