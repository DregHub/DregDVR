import os
import json
import subprocess
import asyncio
import asyncio
from typing import Tuple
import subprocess
from utils.json_utils import JSONUtils
from utils.logging_utils import LogManager
from config_settings import DVR_Config
from config_accounts import Account_Config


class CaptionsDownloader:
    maximum_threads = int(DVR_Config.get_value("General", "maximum_threads"))
    caption_dir = DVR_Config.get_live_captions_dir()
    video_json = os.path.join(caption_dir, "_Channel_Videos.json")
    shorts_json = os.path.join(caption_dir, "_Channel_Shorts.json")
    caption_index_file = os.path.join(caption_dir, "_Caption_Index.json")
    _download_execution_lock = asyncio.Lock()
    _monitor_execution_lock = asyncio.Lock()

    video_playlist = f'{Account_Config.get_caption_handle()}/videos'
    shorts_playlist = f'{Account_Config.get_caption_handle()}/shorts'

    video_playlist_command = ["yt-dlp", "--flat-playlist", "-J", video_playlist]
    shorts_playlist_command = ["yt-dlp", "--flat-playlist", "-J", shorts_playlist]

    @classmethod
    async def monitor_channel(cls):
        tasks = []
        tasks.append(cls.manage_caption_index_file())
        tasks.append(cls.download_captions())
        await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    async def manage_caption_index_file(cls):
        while True:
            async with cls._monitor_execution_lock:
                if cls._download_execution_lock.locked():
                    await asyncio.sleep(300)
                else:
                    LogManager.log_download_captions(
                        f'Started Update Captions Index Proccess for {cls.caption_index_file}')
                    await cls.download_playlist_json(cls.video_playlist_command, cls.video_json)
                    await cls.download_playlist_json(cls.shorts_playlist_command, cls.shorts_json)

                    # Update caption index with new entries from shorts and videos playlists
                    video_contents = await JSONUtils.read_json(cls.video_json)
                    await cls.populate_captions_index(video_contents, cls.caption_index_file)
                    shorts_contents = await JSONUtils.read_json(cls.shorts_json)
                    await cls.populate_captions_index(shorts_contents, cls.caption_index_file)

                    LogManager.log_download_captions(
                        f'The Captions Index File has been updated with new videos & shorts')

                    await cls.populate_hascaptions_field()
                    LogManager.log_download_captions(
                        f'Finished Updating "has_captions" field in {cls.caption_index_file}')

            # --- Waiting section ---
            LogManager.log_download_captions(f'Caption Index Proccess completed. Sleeping for 1 hour.')
            await asyncio.sleep(3600)

    @classmethod
    async def download_captions(cls):
        # Wait for 1 mins on device startup to allow the index file to populate first
        await asyncio.sleep(60)
        semaphore = asyncio.Semaphore(cls.maximum_threads)
        while True:
            async with cls._download_execution_lock:
                if cls._monitor_execution_lock.locked():
                    await asyncio.sleep(300)
                    continue
                else:
                    LogManager.log_download_captions("Starting caption download cycle...")
                    index_data = await JSONUtils.read_json(cls.caption_index_file)
                    tasks = [
                        cls.process_video_entry(video_id, entry, semaphore, index_data)
                        for video_id, entry in index_data.items()
                    ]
                    await asyncio.gather(*tasks)
            # --- Waiting section ---
            await asyncio.sleep(300)

    @classmethod
    async def process_video_entry(cls, video_id, entry, semaphore, index_data):
        video_title = entry.get("title", "")
        filename = video_title.split(" (")[0] if " (" in video_title else video_title
        filepath = os.path.join(cls.caption_dir, f"{filename}")
        has_subtitles = bool(entry.get("has_captions"))
        downloaded = bool(entry.get("downloaded"))
        download_attempts = int(entry.get("download_attempts") or 0)

        if has_subtitles and not downloaded and download_attempts < 10:
            async with semaphore:
                success = await cls.download_caption_for_video(video_id, filepath)
            if success:
                LogManager.log_download_captions(f"Caption download successful for video ID {video_id}")
            else:
                LogManager.log_download_captions(f"Caption download failed for video ID {video_id}")

            entry["downloaded"] = success
            entry["download_attempts"] = download_attempts + 1

            await JSONUtils.save_json(index_data, cls.caption_index_file)

    @classmethod
    async def download_playlist_json(cls, playlist_command, outputfile):
        process = await asyncio.create_subprocess_exec(
            *playlist_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        # Write stdout to file
        with open(outputfile, "w", encoding="utf-8") as outfile:
            outfile.write(stdout.decode())

        if process.returncode == 0:
            LogManager.log_download_captions(f"Successfully Updated Playlist {outputfile}")
        else:
            LogManager.log_download_captions(f"Failed to update playlist. Error: {stderr.decode()}")

    @classmethod
    async def populate_captions_index(cls, index_data: dict, captions_index_path: str):
        # Load the existing captions index from file
        captions_index = await JSONUtils.read_json(captions_index_path)

        # Iterate through entries in index_data
        for entry in index_data.get("entries", []):
            entry_id = entry.get("id")
            entry_title = entry.get("title")
            filename = entry_title.split(" (")[0] if " (" in entry_title else entry_title
            if entry_id and entry_id not in captions_index:
                captions_index[entry_id] = {
                    "id": entry_id,
                    "title": filename,
                    "has_captions": None,
                    "download_attempts": 0,
                    "downloaded": False
                }

        # Save updated captions index back to file
        await JSONUtils.save_json(captions_index, captions_index_path)

    @classmethod
    async def populate_hascaptions_field(cls):
        caption_index = await JSONUtils.read_json(cls.caption_index_file)

        # Filter video IDs based on the specified conditions
        video_ids = [
            vid for vid, data in caption_index.items()
            if data.get("has_captions") not in [True, False]
            and data.get("downloaded") is False
            and data.get("download_attempts", 0) < 10
        ]
        if (len(video_ids) != 0):
            LogManager.log_download_captions(f"Checking {len(video_ids)} videos for captions..")
            LogManager.log_download_captions(f"This make quite some time for large channels..")

            semaphore = asyncio.Semaphore(cls.maximum_threads)

            async def limited_check(video_id):
                async with semaphore:
                    return await cls.check_captions(video_id)

            tasks = [limited_check(vid) for vid in video_ids]
            results = await asyncio.gather(*tasks)

            for vid, has_captions in results:
                caption_index[vid]["has_captions"] = has_captions

            await JSONUtils.save_json(caption_index, cls.caption_index_file)
            LogManager.log_download_captions("Filtered parallel update of 'has_captions' completed.")

    @classmethod
    async def check_captions(cls, video_id: str) -> Tuple[str, bool]:
        def run_subprocess():
            try:
                result = subprocess.run([
                    "yt-dlp", "-J", f"https://www.youtube.com/watch?v={video_id}"
                ], capture_output=True, text=True)
                metadata = json.loads(result.stdout)
                has_captions = bool(metadata.get("automatic_captions") or metadata.get("subtitles"))
                LogManager.log_download_captions(f"Video id: {video_id} caption status = {has_captions}")
                return video_id, has_captions
            except Exception as e:
                LogManager.log_download_captions(f"Failed to retrieve metadata for video {video_id}: {e}")
                return video_id, False

        return await asyncio.to_thread(run_subprocess)

    @classmethod
    async def download_caption_for_video(cls, video_id: str, filepath: str) -> bool:
        command = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--convert-subs", "srt",
            "--skip-download",
            "--restrict-filenames",
            "-o", filepath,
            f"https://www.youtube.com/watch?v={video_id}"
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            return True
        else:
            LogManager.log_download_captions(f"yt-dlp error for video {video_id}: {stderr.decode()}")
            return False
