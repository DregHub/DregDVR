import asyncio
import os
import shutil
import traceback
from utils.logging_utils import LogManager
from config_settings import DVR_Config
from uploader.platform_internet_archive import upload_to_ia
from uploader.platform_youtube import upload_to_youtube


class LiveStreamUploader:
    Live_DownloadQueue_Dir = DVR_Config.get_live_downloadqueue_dir()
    Live_UploadQueue_Dir = DVR_Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = DVR_Config.get_live_completeduploads_dir()
    upload_live_videos_lock = asyncio.Lock()

    @classmethod
    async def upload_live_videos(cls):
        LogManager.log_upload_live(f"Monitoring {cls.Live_UploadQueue_Dir} For Published Live Streams")
        if cls.upload_live_videos_lock.locked():
            LogManager.log_upload_live("upload_live_videos is already running. Skipping this invocation.")
            return

        # Normalize configured extensions to a tuple of lowercase suffixes
        raw_exts = DVR_Config.get_video_file_extensions()
        if isinstance(raw_exts, str):
            exts = (raw_exts.lower(),)
        elif isinstance(raw_exts, (list, tuple, set)):
            exts = tuple(s.lower() for s in raw_exts)
        else:
            # Fallback: coerce to string
            exts = (str(raw_exts).lower(),)

        async with cls.upload_live_videos_lock:
            while True:
                try:
                    # Collect actual files (skip directories)
                    all_entries = os.listdir(cls.Live_UploadQueue_Dir)
                    all_files = [
                        f for f in all_entries
                        if os.path.isfile(os.path.join(cls.Live_UploadQueue_Dir, f))
                    ]

                    # Partition files into video files and others based on normalized extensions
                    video_files = [
                        f for f in all_files
                        if f.lower().endswith(exts)
                    ]
                    other_files = [
                        f for f in all_files
                        if not f.lower().endswith(exts)
                    ]

                    for file in video_files:
                        filepath = os.path.join(cls.Live_UploadQueue_Dir, file)
                        if not os.path.isfile(filepath):
                            continue  # Skip if it ceased to be a file

                        LogManager.log_upload_live(f"Discovered new file: {file} for upload processing.")
                            
                        filename = os.path.splitext(file)[0]  # Extract file name without extension
                        if filename.lower().endswith("am") or filename.lower().endswith("pm"):
                            # Run uploads concurrently for this file
                            LogManager.log_upload_live(f"Starting upload of file: {file} to video hosts")
                            try:
                                await asyncio.gather(
                                    upload_to_youtube(filepath, filename),
                                    upload_to_ia(filepath, filename)
                                )
                                LogManager.log_upload_live(f"Completed upload of file: {file} to video hosts")
                            except Exception as upload_exc:
                                LogManager.log_upload_live(f"Exception while uploading {file}: {upload_exc}\n{traceback.format_exc()}")
                                # Do not attempt to move or archive if upload failed
                                continue

                            # Move the file to completed uploads directory
                            try:
                                dest = os.path.join(cls.Live_CompletedUploads_Dir, file)
                                # Ensure destination directory exists
                                os.makedirs(cls.Live_CompletedUploads_Dir, exist_ok=True)
                                # If a file with same name exists at destination, overwrite by removing first
                                if os.path.exists(dest):
                                    os.remove(dest)
                                shutil.move(filepath, dest)
                                LogManager.log_upload_live(f"Moved {file} to completed uploads.")
                            except Exception as move_exc:
                                LogManager.log_upload_live(f"Failed to move {file} to completed uploads: {move_exc}\n{traceback.format_exc()}")

                            # Archive logs after upload
                            archive_log_files = [
                                LogManager.DOWNLOAD_LIVE_LOG_FILE,
                                LogManager.DOWNLOAD_COMMENTS_LOG_FILE,
                                LogManager.UPLOAD_LIVE_LOG_FILE,
                                LogManager.UPLOAD_IA_LOG_FILE,
                                LogManager.UPLOAD_YT_LOG_FILE
                            ]
                            try:
                                LogManager.archive_logs(
                                    filename, "_Archived_LiveStream_Logs", archive_log_files)
                            except Exception as archive_exc:
                                LogManager.log_upload_live(f"Failed to archive logs for {filename}: {archive_exc}\n{traceback.format_exc()}")

                        else:
                            LogManager.log_upload_live(
                                f"Skipping file {file} as it is an elementary stream not a complete video file.")

                    # Log files with wrong extension
                    for file in other_files:
                        LogManager.log_upload_live(f"file: {file} has the wrong file extension")

                except Exception as e:
                    LogManager.log_upload_live(f"Exception in upload_live_videos: {e}\n{traceback.format_exc()}")
                finally:
                    await asyncio.sleep(30)
