import datetime
import os
import shutil
import traceback
import json
import re
from config import Config


class LogManager:
    Log_Dir = Config.get_log_dir()
    CORE_LOG_FILE = Config.get_core_log_file()
    DOWNLOAD_COMMENTS_LOG_FILE = Config.get_download_comments_log_file()
    DOWNLOAD_LIVE_LOG_FILE = Config.get_download_live_log_file()
    DOWNLOAD_LIVE_RECOVERY_LOG_FILE = Config.get_download_live_recovery_log_file()
    DOWNLOAD_POSTED_LOG_FILE = Config.get_download_posted_log_file()
    DOWNLOAD_POSTED_NOTICES_LOG_FILE = Config.get_download_posted_notices_log_file()
    UPLOAD_POSTED_LOG_FILE = Config.get_upload_posted_log_file()
    UPLOAD_LIVE_LOG_FILE = Config.get_upload_live_log_file()
    UPLOAD_IA_LOG_FILE = Config.get_upload_ia_log_file()
    UPLOAD_YT_LOG_FILE = Config.get_upload_yt_log_file()
    ArchivedLogs_Dir = Config.get_archived_logs_dir()
    CORE_LOG_FILTER = Config.core_log_filter()
    DOWNLOAD_LIVE_LOG_FILTER = Config.download_live_log_filter()
    DOWNLOAD_LIVE_RECOVERY_LOG_FILTER = Config.download_live_recovery_log_filter()
    DOWNLOAD_POSTED_LOG_FILTER = Config.download_posted_log_filter()
    DOWNLOAD_POSTED_NOTICES_LOG_FILTER = Config.download_posted_notices_log_filter()
    UPLOAD_POSTED_LOG_FILTER = Config.upload_posted_log_filter()
    UPLOAD_LIVE_LOG_FILTER = Config.upload_live_log_filter()
    UPLOAD_IA_LOG_FILTER = Config.upload_ia_log_filter()
    UPLOAD_YT_LOG_FILTER = Config.upload_yt_log_filter()
    disable_log_archiving = Config.get_disable_log_archiving().lower() 


    LOG_FILTERS = [CORE_LOG_FILTER, DOWNLOAD_LIVE_LOG_FILTER,DOWNLOAD_LIVE_RECOVERY_LOG_FILTER, DOWNLOAD_POSTED_LOG_FILTER,DOWNLOAD_POSTED_NOTICES_LOG_FILTER,UPLOAD_LIVE_LOG_FILTER, UPLOAD_IA_LOG_FILTER, UPLOAD_YT_LOG_FILTER]
    LOG_FILES = [CORE_LOG_FILE, DOWNLOAD_LIVE_LOG_FILE,DOWNLOAD_LIVE_RECOVERY_LOG_FILE, DOWNLOAD_POSTED_LOG_FILE,DOWNLOAD_POSTED_NOTICES_LOG_FILE,UPLOAD_LIVE_LOG_FILE, UPLOAD_IA_LOG_FILE, UPLOAD_YT_LOG_FILE]

    @classmethod
    def log_message(cls, message, log_file_name):
        """Log a message with a timestamp to the specified log file, aggregating consecutive duplicates, and filter messages."""
        if not log_file_name:
            return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # Find the index of the log file and get the corresponding filter
            try:
                log_index = cls.LOG_FILES.index(log_file_name)
                log_filter = cls.LOG_FILTERS[log_index]
            except ValueError:
                log_filter = []

            # Filter the message if it matches any filter string
            if any(f in message for f in log_filter):
                return

            # Ensure the log file exists
            if not os.path.exists(log_file_name):
                open(log_file_name, "w").close()

            # Read the last line to check for repeat
            last_line = ""
            with open(log_file_name, "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
                if lines:
                    last_line = lines[-1].rstrip("\n")

            # Pattern to match the aggregated log format
            agg_pattern = re.compile(
                r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) > (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+) \[Repeat X (\d+)\]"
            )
            # Pattern to match the normal log format
            normal_pattern = re.compile(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.+)"
            )

            if last_line:
                agg_match = agg_pattern.fullmatch(last_line)
                normal_match = normal_pattern.fullmatch(last_line)

                if agg_match and agg_match[3] == message:
                    # Update the aggregated line
                    first_ts = agg_match[1]
                    repeat_count = int(agg_match[4]) + 1
                    new_line = f"[{first_ts} > {timestamp}] {message} [Repeat X {repeat_count}]"
                    lines[-1] = new_line + "\n"
                    with open(log_file_name, "w", encoding="utf-8") as log_file:
                        log_file.writelines(lines)
                    print(f"{log_file_name}   :   {new_line}")
                    return
                elif normal_match and normal_match[2] == message:
                    # Convert to aggregated line
                    first_ts = normal_match[1]
                    new_line = f"[{first_ts} > {timestamp}] {message} [Repeat X 2]"
                    lines[-1] = new_line + "\n"
                    with open(log_file_name, "w", encoding="utf-8") as log_file:
                        log_file.writelines(lines)
                    print(f"{log_file_name}   :   {new_line}")
                    return

            # Otherwise, just append as normal
            with open(log_file_name, "a", encoding="utf-8") as log_file:
                log_file.write(f"{timestamp} - {message}\n")
            print(f"{log_file_name}   :   {message}")

        except Exception as e:
            print(f"Failed to log message: {e}\n{traceback.format_exc()}")

    @classmethod
    def log_core(cls, message):
        """Log a message to the core dreggs dvr log."""
        cls.log_message(message, cls.CORE_LOG_FILE)

    @classmethod
    def log_download_live(cls, message):
        """Log a message to the Download YouTube Live log."""
        cls.log_message(message, cls.DOWNLOAD_LIVE_LOG_FILE)

    @classmethod
    def log_download_live_recovery(cls, message):
        """Log a message to the Download YouTube Live Recovery log."""
        cls.log_message(message, cls.DOWNLOAD_LIVE_RECOVERY_LOG_FILE)

    @classmethod
    def log_download_comments(cls, message):
        """Log a message to the Download YouTube Comments log."""
        cls.log_message(message, cls.DOWNLOAD_COMMENTS_LOG_FILE)

    @classmethod
    def log_download_posted(cls, message):
        """Log a message to the Download YouTube Posted log."""
        cls.log_message(message, cls.DOWNLOAD_POSTED_LOG_FILE)

    @classmethod
    def log_download_posted_notices(cls, message):
        """Log a message to the Download YouTube Posted Notices log."""
        cls.log_message(message, cls.DOWNLOAD_POSTED_NOTICES_LOG_FILE)

    @classmethod
    def log_upload_posted(cls, message):
        """Log a message to the Upload YouTube Posted log."""
        cls.log_message(message, cls.UPLOAD_POSTED_LOG_FILE)

    @classmethod
    def log_upload_live(cls, message):
        """Log a message to the Upload YouTube live log."""
        cls.log_message(message, cls.UPLOAD_LIVE_LOG_FILE)

    @classmethod
    def log_upload_ia(cls, message):
        """Log a message to the Upload Internet Archive log."""
        cls.log_message(message, cls.UPLOAD_IA_LOG_FILE)

    @classmethod
    def log_upload_yt(cls, message):
        """Log a message to the Upload YouTube log."""
        cls.log_message(message, cls.UPLOAD_YT_LOG_FILE)

    @classmethod
    def archive_logs(cls, filename, parent_folder, log_files):
        """Archive all log files to a folder named after the uploaded file inside the specified parent_folder."""
        try:
            if cls.disable_log_archiving != "true":
                log_archive_path = os.path.join(cls.Log_Dir, parent_folder)
                # Ensure log_archive_path exists
                if not os.path.exists(log_archive_path):
                    os.makedirs(log_archive_path)
                archive_folder = os.path.join(log_archive_path, filename)
                if not os.path.exists(archive_folder):
                    os.makedirs(archive_folder)
                for log_file in log_files:
                    if os.path.exists(log_file):
                        shutil.move(log_file, os.path.join(archive_folder, os.path.basename(log_file)))
        except Exception as e:
            cls.log_core(f"Failed to archive logs for {filename}: {e}\n{traceback.format_exc()}")
