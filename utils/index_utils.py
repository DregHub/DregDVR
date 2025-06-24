import os
import re
import traceback
from utils.logging_utils import LogManager
from config import Config


class IndexManager:
    Live_DownloadQueue_Dir = os.path.join(
        Config.ProjRoot_Dir, Config.get_value("Directories", "Live_DownloadQueue_Dir"))
    Live_UploadQueue_Dir = os.path.join(Config.ProjRoot_Dir, Config.get_value("Directories", "Live_UploadQueue_Dir"))
    Live_CompletedUploads_Dir = os.path.join(
        Config.ProjRoot_Dir, Config.get_value("Directories", "live_completeduploads_dir"))

    @staticmethod
    def find_current_index(log_file):
        """
        Calculate the index by searching for .mp4 files in the specified directories.
        The filename format is 'INDEXNUM FILENAME', and the index is set as the highest INDEXNUM found.
        Returns "1" if no .mp4 files are found.
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
                    if fname.lower().endswith(".mp4"):
                        previous_videos = True
                        match = pattern.match(fname)
                        if match:
                            idx = int(match.group(1))
                            if idx > max_index:
                                max_index = idx

            if not previous_videos:
                LogManager.log_message("No previous videos found, returning first index", log_file)
                return "1"

            string_index = str(max_index)
            return string_index

        except Exception as e:
            LogManager.log_message(f"Failed to get index: {e}\n{traceback.format_exc()}", log_file)
            return None

    @staticmethod
    def find_new_index(log_file):
        """Calculate the next available free index"""
        try:
            current_index = IndexManager.find_current_index(log_file)
            if current_index is None:
                LogManager.log_message("Current index is None, cannot increment.", log_file)
                return None
            current_index_num = int(current_index) + 1
            current_index_str = str(current_index_num)
            #LogManager.log_message(f"Returning {current_index_str} as the next available free index for new downloads", log_file)
            return current_index_str

        except Exception as e:
            LogManager.log_message(f"Failed to get next free index: {e}\n{traceback.format_exc()}", log_file)
            return None

    @staticmethod
    def get_index(specified_index, log_file):
        """Read the current value of specified Index from the config."""
        try:
            index = int(Config.get_value("Upload_Index", specified_index))
            string_index = str(index)
            return string_index

        except Exception as e:
            LogManager.log_message(f"Failed to get {specified_index}: {e}\n{traceback.format_exc()}", log_file)
            return None

    @staticmethod
    def increment_index(specified_index, log_file):
        """Increment the value of specified DownloadFileIndex by one and save it to the config."""
        try:
            download_file_index = int(Config.get_value("Upload_Index", specified_index))
            download_file_index += 1
            new_index = str(download_file_index)
            Config.set_value("Upload_Index", specified_index, new_index)
            LogManager.log_message(f"Incremented {specified_index} to : {new_index}", log_file)
        except Exception as e:
            LogManager.log_message(f"Failed to increment {specified_index}: {e}\n{traceback.format_exc()}", log_file)
