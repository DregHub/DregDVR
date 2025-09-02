
import os
import csv
import traceback
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess
from config import Config


class PlaylistManager:
    youtube_source = Config.get_youtube_source().strip('"')
    if youtube_source.lower().endswith("/live"):
        youtube_channel = youtube_source[: -len("/live")]
    else:
        youtube_channel = youtube_source

    LogManager.log_download_posted(f"Generated channel url from {youtube_channel}")
    playlist_dir = Config.get_posted_playlists_dir()
    Posted_DownloadQueue_Dir =  Config.get_posted_downloadqueue_dir()
    delta_playlist = Config.get_posted_delta_playlist()
    persistent_playlist = Config.get_posted_persistent_playlist()

    @classmethod
    async def download_channel_playlist(cls):
        open(cls.delta_playlist, "w").close()

        command = [
            "yt-dlp",
            "-i",
            "--flat-playlist",
            "--match-filter live_status=not_live",
            "--print-to-file",
            "'%(id)s,%(title)s,%(url)s,0'",
            cls.delta_playlist,
            cls.youtube_channel
        ]

        MiniLog = await run_subprocess(
            command,
            LogManager.DOWNLOAD_POSTED_LOG_FILE,
            "yt-dlp video/shorts playlist extraction failed",
            "Exception in download_videos_and_shorts",
            cls.Posted_DownloadQueue_Dir
        )

        if not MiniLog:
            LogManager.log_download_posted("No output from yt-dlp, possibly no new videos or shorts available.")

    @classmethod
    async def merge_delta_playlist(cls):
        headers = ["UniqueID", "Title", "URL", "Downloaded"]

        # Skip if delta_playlist is missing or empty
        if not os.path.exists(cls.delta_playlist):
            LogManager.log_download_posted(f"Delta playlist file {cls.delta_playlist} does not exist. Skipping merge.")
            return

        try:
            with open(cls.delta_playlist, "r", encoding="utf-8") as source_file:
                delta_lines = [line.strip() for line in source_file if line.strip()]

            if not delta_lines:
                LogManager.log_download_posted(f"Delta playlist file {cls.delta_playlist} is empty. Skipping merge.")
                return

            existing_ids = set()
            # Create persistent_playlist with headers if it does not exist
            if not os.path.exists(cls.persistent_playlist):
                with open(cls.persistent_playlist, "w", newline="", encoding="utf-8") as outfile:
                    writer = csv.writer(outfile)
                    writer.writerow(headers)
            else:
                with open(cls.persistent_playlist, "r", encoding="utf-8") as persistent_file:
                    reader = csv.reader(persistent_file)
                    next(reader, None)
                    for row in reader:
                        if row and row[0]:
                            existing_ids.add(row[0])

            # Read existing rows (after header) if file exists, else start with header
            with open(cls.persistent_playlist, "a", newline="", encoding="utf-8") as outfile:
                writer = csv.writer(outfile)
                for line in delta_lines:
                    row = line.split(",", 3)
                    while len(row) < 4:
                        row.append("")
                    unique_id = row[0]

                    if not existing_ids or (unique_id and unique_id not in existing_ids):
                        writer.writerow(row)
                        existing_ids.add(unique_id)
                    else:
                        LogManager.log_download_posted(f"Skipping existing primary key {unique_id}")
            LogManager.log_download_posted(f"Merged delta playlist written to {cls.persistent_playlist}")
        except Exception as e:
            LogManager.log_download_posted(f"Failed to merge delta playlist:  {e}\n{traceback.format_exc()}")
