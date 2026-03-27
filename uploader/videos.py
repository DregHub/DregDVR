import asyncio
import os
import re
import traceback
from utils.logging_utils import LogManager
from utils.file_utils import FileManager
from config.config_settings import DVR_Config
from utils.playlist_manager import PlaylistManager
from uploader.platform_internet_archive import upload_to_ia
from uploader.platform_youtube import upload_to_youtube
from uploader.platform_rumble import upload_to_rumble


class VideoUploader:
    Posted_UploadQueue_Dir = DVR_Config.get_posted_uploadqueue_dir()
    Posted_CompletedUploads_Dir = DVR_Config.get_posted_completeduploads_dir()
    Live_UploadQueue_Dir = DVR_Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = DVR_Config.get_live_completeduploads_dir()
    _upload_posted_lock = asyncio.Lock()
    _upload_live_lock = asyncio.Lock()

    @classmethod
    def _strip_timestamp_from_safe_filename(cls, safe_filename):
        if not safe_filename:
            return safe_filename

        # Matches ending timestamp pattern like:
        # ..._21-05-2025_03-08AM or ..._17-05-2025_08-23PM
        match = re.search(r"_(\d{2}-\d{2}-\d{4}_\d{2}-\d{2}(?:AM|PM))$", safe_filename)
        if match:
            return safe_filename[: match.start()]

        return safe_filename

    @classmethod
    async def _move_completed_file(cls, filepath, live_status):
        if not filepath or not os.path.isfile(filepath):
            return False

        if live_status == "not_live":
            dest_dir = cls.Posted_CompletedUploads_Dir
        else:
            dest_dir = cls.Live_CompletedUploads_Dir

        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, os.path.basename(filepath))

        try:
            FileManager.move_file(filepath, dest_path, LogManager.UPLOAD_POSTED_LOG_FILE)
            return True
        except Exception as e:
            LogManager.log_upload_posted(f"Failed to move uploaded file {filepath} to completed uploads: {e}")
            return False

    @classmethod
    def _strip_leading_number_from_title(cls, title):
        if not title:
            return title
        # Remove leading digits and following space if present, e.g. "123 Title" -> "Title"
        return re.sub(r"^\s*\d+\s+", "", title)

    @classmethod
    async def _process_playlist_entry(cls, entry):
        title = entry.get("Title", "")
        title_without_leading_number = cls._strip_leading_number_from_title(title)
        url = entry.get("URL")
        live_status = entry.get("Live_Status")

        filepath = entry.get("File_Path")
        if not url:
            LogManager.log_upload_posted("Skipping playlist entry with missing URL")
            return
        if not filepath:
            LogManager.log_upload_posted(
                f"No file path found for URL {url}. Skipping upload for this entry."
            )
            return
        #strip leading numbers from title for upload if present, as some platforms may not handle them well (e.g. "123 Title" -> "Title")
        title = title_without_leading_number if title_without_leading_number else title
        # Determine and call each required upload platform only if not already marked uploaded
        upload_tasks = []
        if DVR_Config.upload_to_ia_enabled() and not entry.get("Uploaded_Video_IA", False):
            upload_tasks.append(("Uploaded_Video_IA", upload_to_ia, title))
        if DVR_Config.upload_to_youtube_enabled() and not entry.get("Uploaded_Video_YT", False):
            upload_tasks.append(("Uploaded_Video_YT", upload_to_youtube, title))
        if DVR_Config.upload_to_rumble_enabled() and not entry.get("Uploaded_Video_RM", False):
            upload_tasks.append(("Uploaded_Video_RM", upload_to_rumble, title))

        if not upload_tasks:
            # No platforms to upload for this entry (possibly due to platform-specific upload flags already marked)
            pass
        else:
            for platform_field, upload_fn, upload_title in upload_tasks:
                try:
                    base_filename = os.path.splitext(os.path.basename(filepath))[0]
                    LogManager.log_upload_posted(
                        f"Starting upload of {title} using {platform_field}"
                    )
                    status = await upload_fn(filepath, base_filename, upload_title)

                    if status:
                        # Mirror the upload success in the in-memory entry so the workflow can act on it immediately.
                        entry[platform_field] = True

                    await PlaylistManager.mark_video_upload_status(url, platform_field, bool(status))
                    LogManager.log_upload_posted(
                        f"{platform_field} Task Completed, Success: {bool(status)}"
                    )
                except Exception as e:
                    LogManager.log_upload_posted(
                        f"Exception uploading {url} to {platform_field}: {e}\n{traceback.format_exc()}"
                    )
                    await PlaylistManager.mark_video_upload_status(url, platform_field, False)

        # After platform statuses are updated, check all-hosts and move file if done
        playlist_data = await PlaylistManager._load_playlist_data()
        pending_entry = next(
            (item for item in playlist_data if isinstance(item, dict) and item.get("URL") == url),
            None,
        )

        if pending_entry and pending_entry.get("Uploaded_Video_All_Hosts", False):
            moved = await cls._move_completed_file(filepath, live_status)
            if moved:
                LogManager.log_upload_posted(f"Moved fully uploaded file to completed directory: {filepath}")

    @classmethod
    async def upload_posted_videos(cls):
        LogManager.log_upload_posted(
            "Monitoring playlist for posted uploads (Downloaded_Video=True, Uploaded_Video_All_Hosts=False)"
        )

        while True:
            if cls._upload_posted_lock.locked():
                LogManager.log_upload_posted(
                    "upload_posted_videos is already running, skipping this call."
                )
                await asyncio.sleep(30)
                continue

            async with cls._upload_posted_lock:
                try:
                    entries = await PlaylistManager.get_pending_upload_entries(live_status_filter="not_live")
                    if not entries:
                        LogManager.log_upload_posted("No posted uploads pending in playlist.")
                    else:
                        for entry in entries:
                            await cls._process_playlist_entry(entry)

                except Exception as e:
                    LogManager.log_upload_posted(
                        f"Exception in upload_posted_videos: {e}\n{traceback.format_exc()}"
                    )

            await asyncio.sleep(30)

    @classmethod
    async def upload_livestreams(cls):
        LogManager.log_upload_posted(
            "Monitoring playlist for livestream uploads (Downloaded_Video=True, Uploaded_Video_All_Hosts=False)"
        )

        while True:
            if cls._upload_live_lock.locked():
                LogManager.log_upload_posted(
                    "upload_livestreams is already running, skipping this call."
                )
                await asyncio.sleep(30)
                continue

            async with cls._upload_live_lock:
                try:
                    entries = await PlaylistManager.get_pending_upload_entries(live_status_filter="live")
                    if not entries:
                        LogManager.log_upload_posted("No livestream uploads pending in playlist.")
                    else:
                        for entry in entries:
                            await cls._process_playlist_entry(entry)

                except Exception as e:
                    LogManager.log_upload_posted(
                        f"Exception in upload_livestreams: {e}\n{traceback.format_exc()}"
                    )

            await asyncio.sleep(30)

