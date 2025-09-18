import os
import shutil
import traceback
import mmap
import asyncio
from utils.logging_utils import LogManager


class FileManager:
    """Utility class for file operations."""
    @classmethod
    def move_file(cls, src, dst, logfile):
        """Move a file from src to dst."""
        try:
            shutil.move(src, dst)
        except Exception as e:
            LogManager.log_message(f"Failed to move file from {src} to {dst}:  {e}\n{traceback.format_exc()}", logfile)

    @classmethod
    def delete_file(cls, filepath, logfile):
        """Delete a file at the specified filepath."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            LogManager.log_message(f"Failed to delete file {filepath}:  {e}\n{traceback.format_exc()}", logfile)

    @classmethod
    def create_directory(cls, directory, logfile):
        """Create a directory if it does not exist."""
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
        except Exception as e:
            LogManager.log_message(f"Failed to create directory {directory}:  {e}\n{traceback.format_exc()}", logfile)

    @classmethod
    async def file_contains_string_mmap_async(cls, file_path: str, search_string: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, cls._file_contains_string_mmap, file_path, search_string)

    @classmethod
    def _file_contains_string_mmap(cls, file_path: str, search_string: str) -> bool:
        try:
            with open(file_path, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    return mm.find(search_string.encode()) != -1
        except Exception as e:
            LogManager.log_download_posted_notices(f"Error reading file {file_path}: {e}\n{traceback.format_exc()}")
            return False
