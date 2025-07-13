import asyncio
import os
import shutil
import traceback
from utils.logging_utils import LogManager
from config import Config
from uploader.platform_internet_archive import upload_to_ia
from uploader.platform_youtube import upload_to_youtube


class VideoUploader:
    Posted_UploadQueue_Dir = os.path.join(
        Config.ProjRoot_Dir, Config.get_value("Directories", "Posted_UploadQueue_Dir"))
    _upload_videos_lock = asyncio.Lock()

    @classmethod
    async def upload_videos(cls):
        # Try to acquire the lock without waiting
        if cls._upload_videos_lock.locked():
            LogManager.log_upload_posted("upload_videos is already running, skipping this call.")
            return

        async with cls._upload_videos_lock:
            while True:
                LogManager.log_upload_posted(f"Monitoring {cls.Posted_UploadQueue_Dir} For Published Videos")
                try:
                    for file in os.listdir(cls.Posted_UploadQueue_Dir):
                        filepath = os.path.join(cls.Posted_UploadQueue_Dir, file)
                        if not os.path.isfile(filepath):
                            continue  # Skip directories or non-files

                        if file.lower().endswith((".mp4", ".webm", ".mkv", ".flv", ".3gp")):
                            filename = os.path.splitext(file)[0]  # Extract file name without extension

                            if (filename.lower().endswith("am") or filename.lower().endswith("pm")):
                                # Run all uploads concurrently
                                await asyncio.gather(
                                    upload_to_ia(filepath, filename),
                                    upload_to_youtube(filepath, filename)
                                )

                                LogManager.log_upload_posted(f"Completed upload of file: {file} to video hosts")
                                Posted_CompletedUploads_Dir = os.path.join(
                                    Config.ProjRoot_Dir, Config.get_value("Directories", "Posted_CompletedUploads_Dir"))
                                uploaded_filepath = os.path.join(Posted_CompletedUploads_Dir, file)
                                shutil.move(filepath, uploaded_filepath)

                                # Archive logs after upload
                                archive_log_files = [
                                    LogManager.DOWNLOAD_POSTED_LOG_FILE,
                                    LogManager.UPLOAD_POSTED_LOG_FILE,
                                    LogManager.UPLOAD_IA_LOG_FILE,
                                    LogManager.UPLOAD_YT_LOG_FILE,
                                ]
                                LogManager.archive_logs_for_stream(
                                    filename, "_Archived_PostedVideo_Logs", archive_log_files)
                            else:
                                LogManager.log_upload_posted(
                                    f"Skipping file {file} as it is an elementary stream not a complete video file.")
                        else:
                            LogManager.log_upload_posted(f"file: {file} has the wrong file extension")
                except Exception as e:
                    LogManager.log_upload_posted(f"Exception in upload_videos: {e}\n{traceback.format_exc()}")
                finally:
                    await asyncio.sleep(30)
