import os
import re
import traceback
from utils.logging_utils import LogManager
from config import Config

class IndexManager:
    Live_DownloadQueue_Dir = Config.get_live_downloadqueue_dir()
    Live_UploadQueue_Dir = Config.get_live_uploadqueue_dir()
    Live_CompletedUploads_Dir = Config.get_live_completeduploads_dir()

    Posted_DownloadQueue_Dir = Config.get_posted_downloadqueue_dir()
    Posted_UploadQueue_Dir = Config.get_posted_uploadqueue_dir()
    Posted_CompletedUploads_Dir = Config.get_posted_completeduploads_dir()

    @staticmethod
    def find_current_live_index(log_file):
        """
        Calculate the index by searching for video files in the specified directories.
        The filename format is 'INDEXNUM FILENAME', and the index is set as the highest INDEXNUM found.
        Returns "1" if no video files are found.
        """
        try:
            dirs = [
                IndexManager.Live_DownloadQueue_Dir,
                IndexManager.Live_UploadQueue_Dir,
                IndexManager.Live_CompletedUploads_Dir,
            ]
            max_index = 0
            pattern = re.compile(r"^(\d+)\s")
            previous_videos = False

            for dir_path in dirs:
                if not os.path.isdir(dir_path):
                    continue
                for fname in os.listdir(dir_path):
                    if fname.lower().endswith(Config.get_video_file_extensions()):
                        previous_videos = True
                        if match := pattern.match(fname):
                            idx = int(match[1])
                            if idx > max_index:
                                max_index = idx

            if not previous_videos:
                LogManager.log_message("No previous videos found, Index will be returned as 0", log_file)
                return "0"

            return str(max_index)
        except Exception as e:
            LogManager.log_message(f"Failed to get index: {e}\n{traceback.format_exc()}", log_file)
            return None

    @staticmethod
    def find_new_live_index(log_file):
        """Calculate the next available free index"""
        try:
            current_index = IndexManager.find_current_live_index(log_file)
            if current_index is None:
                LogManager.log_message("Current index is None, cannot increment.", log_file)
                return None
            current_index_num = int(current_index) + 1
            return str(current_index_num)
        except Exception as e:
            LogManager.log_message(f"Failed to get next free index: {e}\n{traceback.format_exc()}", log_file)
            return None

    @staticmethod
    def find_current_posted_index(log_file):
        """
        Calculate the index by searching for video files in the specified directories.
        The filename format is 'INDEXNUM FILENAME', and the index is set as the highest INDEXNUM found.
        Returns "1" if no video files are found.
        """
        try:
            dirs = [
                IndexManager.Posted_DownloadQueue_Dir,
                IndexManager.Posted_UploadQueue_Dir,
                IndexManager.Posted_CompletedUploads_Dir,
            ]
            max_index = 0
            pattern = re.compile(r"^(\d+)\s")
            previous_videos = False

            for dir_path in dirs:
                if not os.path.isdir(dir_path):
                    continue
                for fname in os.listdir(dir_path):
                    if fname.lower().endswith(Config.get_video_file_extensions()):
                        previous_videos = True
                        cleaned_name = fname.replace(Config.get_posted_downloadprefix(), "")
                        if match := pattern.match(cleaned_name):
                            idx = int(match[1])
                            if idx > max_index:
                                max_index = idx

            if not previous_videos:
                LogManager.log_message("No previous videos found, Index will be returned as 0", log_file)
                return "0"

            return str(max_index)
        except Exception as e:
            LogManager.log_message(f"Failed to get index: {e}\n{traceback.format_exc()}", log_file)
            return None

    @staticmethod
    def find_new_posted_index(log_file):
        """Calculate the next available free index"""
        try:
            current_index = IndexManager.find_current_posted_index(log_file)
            if current_index is None:
                LogManager.log_message("Current index is None, cannot increment.", log_file)
                return None
            current_index_num = int(current_index) + 1
            
            LogManager.log_message(f"Next Free Index: {current_index_num}", log_file)
            return str(current_index_num)
        except Exception as e:
            LogManager.log_message(f"Failed to get next free index: {e}\n{traceback.format_exc()}", log_file)
            return None
