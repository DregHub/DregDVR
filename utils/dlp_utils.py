import traceback
from utils.logging_utils import LogManager
import logging

class DLPEvents:
    """
    Event handler class for yt-dlp progress hooks.
    Instantiate with an optional `log_file_name` and two optional
    callbacks: `download_started(filename)` and `download_complete(filename)`.
    """

    def __init__(self, log_file_name=None, download_started=None, download_complete=None):
        self.log_file_name = log_file_name
        self.download_started = download_started if download_started is not None else (lambda filename: None)
        self.download_complete = download_complete if download_complete is not None else (lambda filename: None)
        self._active_downloads = set()

    def on_progress(self, d):
        """Event handler for yt-dlp progress hooks. Logs progress and calls callbacks."""
        try:
            status = d.get('status')
            filename = d.get('filename', 'Unknown')
            logging.error(f"DLP EVENT: status={status}, filename={filename}")
            if status == 'downloading':
                # If we haven't seen this filename before, call the started callback once.
                if filename not in self._active_downloads:
                    try:
                        self.download_started(filename)
                    except Exception:
                        pass
                    self._active_downloads.add(filename)
                else:
                    self.log_message(f"ddl: {filename}")

            elif status == 'finished':
                # finished -> call complete callback and remove from active set
                try:
                    self.download_complete(filename)
                except Exception:
                    pass
                self._active_downloads.discard(filename)
                self.log_message(f"Download finished: {filename}")

            elif status == 'error':
                self.log_message(f"Download error occurred: {d.get('_exception', 'Unknown error')}")

        except Exception as e:
            self.log_message(f"Error in dlp_events handler: {e}\n{traceback.format_exc()}")

    @staticmethod
    def format_bytes(bytes_value):
        """Convert bytes to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f}{unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f}TB"

    @classmethod
    def format_bytes_per_sec(cls, bytes_per_sec):
        """Convert bytes per second to human-readable format."""
        return f"{cls.format_bytes(bytes_per_sec)}/s"

    @staticmethod
    def format_time(seconds):
        """Convert seconds to human-readable time format."""
        if seconds is None or seconds < 0:
            return "Unknown"
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def log_message(self, message):
        """
        Forward a log message to LogManager. If `log_file_name` is provided,
        pass it as the second positional argument, otherwise pass None.
        """
        try:
            LogManager.log_message(message, self.log_file_name)
        except Exception as e:
            print(f"Failed to forward log message: {e}")
