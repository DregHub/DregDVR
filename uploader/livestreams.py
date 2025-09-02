import asyncio
import os
import shutil
import traceback
from utils.logging_utils import LogManager
from config import Config
from uploader.platform_internet_archive import upload_to_ia
from uploader.platform_youtube import upload_to_youtube


class LiveStreamUploader:
    Live_DownloadQueue_Dir = Config.get_live_downloadqueue_dir()
    Live_UploadQueue_Dir = Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = Config.get_live_completeduploads_dir()
    upload_live_videos_lock = asyncio.Lock()

    @classmethod
    async def upload_live_videos(cls):
        if cls.upload_live_videos_lock.locked():
            LogManager.log_upload_live("upload_live_videos is already running. Skipping this invocation.")
            return

        async with cls.upload_live_videos_lock:
            while True:
                LogManager.log_upload_live(f"Monitoring {cls.Live_UploadQueue_Dir} For Published Videos")
                try:
                    files = [
                        file for file in os.listdir(cls.Live_UploadQueue_Dir)
                        if file.lower().endswith(Config.get_video_file_extensions())
                    ]
                    for file in files:
                        filepath = os.path.join(cls.Live_UploadQueue_Dir, file)
                        filename = os.path.splitext(file)[0]  # Extract file name without extension
                        if filename.lower().endswith("am") or filename.lower().endswith("pm"):
                            # Run uploads concurrently for this file
                            await asyncio.gather(
                                upload_to_ia(filepath, filename),
                                upload_to_youtube(filepath, filename)
                            )

                            LogManager.log_upload_live(f"Completed upload of file: {file} to video hosts")
                            shutil.move(filepath, os.path.join(cls.Live_CompletedUploads_Dir, file))

                            # Archive logs after upload
                            archive_log_files = [
                                LogManager.DOWNLOAD_LIVE_LOG_FILE,
                                LogManager.DOWNLOAD_COMMENTS_LOG_FILE,
                                LogManager.UPLOAD_LIVE_LOG_FILE,
                                LogManager.UPLOAD_IA_LOG_FILE,
                                LogManager.UPLOAD_YT_LOG_FILE
                            ]
                            LogManager.archive_logs_for_stream(
                                filename, "_Archived_LiveStream_Logs", archive_log_files)
                        else:
                            LogManager.log_upload_live(
                                f"Skipping file {file} as it is an elementary stream not a complete video file.")
                    # Log files with wrong extension
                    other_files = [
                        file for file in os.listdir(cls.Live_UploadQueue_Dir)
                        if not file.lower().endswith(Config.get_video_file_extensions())
                    ]
                    for file in other_files:
                        LogManager.log_upload_live(f"file: {file} has the wrong file extension")

                except Exception as e:
                    LogManager.log_upload_live(f"Exception in upload_live_videos: {e}\n{traceback.format_exc()}")
                finally:
                    await asyncio.sleep(30)
