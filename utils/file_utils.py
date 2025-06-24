import os
import shutil
import traceback
from utils.logging_utils import LogManager


def move_file(src, dst, logfile):
    """Move a file from src to dst."""
    try:
        shutil.move(src, dst)
    except Exception as e:
        LogManager.log_message(f"Failed to move file from {src} to {dst}:  {e}\n{traceback.format_exc()}", logfile)


def delete_file(filepath, logfile):
    """Delete a file at the specified filepath."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        LogManager.log_message(f"Failed to delete file {filepath}:  {e}\n{traceback.format_exc()}", logfile)


def create_directory(directory, logfile):
    """Create a directory if it does not exist."""
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
    except Exception as e:
        LogManager.log_message(f"Failed to create directory {directory}:  {e}\n{traceback.format_exc()}", logfile)
