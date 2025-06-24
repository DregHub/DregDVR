import datetime
import os
import shutil
import traceback
import json
import re
from config import Config


class LogManager:
    Log_Dir = os.path.join(Config.ProjRoot_Dir, Config.get_value("Directories", "Log_Dir"))
    CORE_LOG_FILE = os.path.join(Log_Dir, "_Core_ContentGrabber.log")
    DOWNLOAD_COMMENTS_LOG_FILE = os.path.join(Log_Dir, "Download_YouTube_Comments.log")
    DOWNLOAD_LIVE_LOG_FILE = os.path.join(Log_Dir, "Download_YouTube_Live.log")
    DOWNLOAD_POSTED_LOG_FILE = os.path.join(Log_Dir, "Download_YouTube_Posted.log")
    UPLOAD_POSTED_LOG_FILE = os.path.join(Log_Dir, "Upload_Manager_Posted.log")
    UPLOAD_LIVE_LOG_FILE = os.path.join(Log_Dir, "Upload_Manager_Live.log")
    UPLOAD_IA_LOG_FILE = os.path.join(Log_Dir, "Upload_Platform_InternetArchive.log")
    UPLOAD_YT_LOG_FILE = os.path.join(Log_Dir, "Upload_Platform_YouTube.log")
    ArchivedLogs_Dir = os.path.join(Log_Dir, "_ArchivedLogs")

    @staticmethod
    def parse_string_list(str_list):
        """Convert a string representation of a Python list to an actual list."""
        try:
            return json.loads(str_list)
        except Exception as e:
            LogManager.log_core(f"Failed to parse string list:  {e}\n{traceback.format_exc()}")
            return []

    CORE_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "CORE_LOG_FILTER"))
    DOWNLOAD_LIVE_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "DOWNLOAD_LIVE_LOG_FILTER"))
    DOWNLOAD_POSTED_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "DOWNLOAD_POSTED_LOG_FILTER"))
    UPLOAD_POSTED_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "UPLOAD_POSTED_LOG_FILTER"))
    UPLOAD_LIVE_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "UPLOAD_LIVE_LOG_FILTER"))
    UPLOAD_IA_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "UPLOAD_IA_LOG_FILTER"))
    UPLOAD_YT_LOG_FILTER = parse_string_list(Config.get_value("Log_Filters", "UPLOAD_YT_LOG_FILTER"))

    LOG_FILTERS = [CORE_LOG_FILTER, DOWNLOAD_LIVE_LOG_FILTER, DOWNLOAD_POSTED_LOG_FILTER,
                   UPLOAD_LIVE_LOG_FILTER, UPLOAD_IA_LOG_FILTER, UPLOAD_YT_LOG_FILTER]
    LOG_FILES = [CORE_LOG_FILE, DOWNLOAD_LIVE_LOG_FILE, DOWNLOAD_POSTED_LOG_FILE,
                 UPLOAD_LIVE_LOG_FILE, UPLOAD_IA_LOG_FILE, UPLOAD_YT_LOG_FILE]

    @classmethod
    def log_message(cls, message, log_file_name):
        """Log a message with a timestamp to the specified log file, aggregating consecutive duplicates, and filter messages."""
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

                if agg_match and agg_match.group(3) == message:
                    # Update the aggregated line
                    first_ts = agg_match.group(1)
                    repeat_count = int(agg_match.group(4)) + 1
                    new_line = f"[{first_ts} > {timestamp}] {message} [Repeat X {repeat_count}]"
                    lines[-1] = new_line + "\n"
                    with open(log_file_name, "w", encoding="utf-8") as log_file:
                        log_file.writelines(lines)
                    print(f"{log_file_name}   :   {new_line}")
                    return
                elif normal_match and normal_match.group(2) == message:
                    # Convert to aggregated line
                    first_ts = normal_match.group(1)
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
    def log_download_comments(cls, message):
        """Log a message to the Download YouTube Comments log."""
        cls.log_message(message, cls.DOWNLOAD_COMMENTS_LOG_FILE)

    @classmethod
    def log_download_posted(cls, message):
        """Log a message to the Download YouTube Posted log."""
        cls.log_message(message, cls.DOWNLOAD_POSTED_LOG_FILE)

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
    def archive_logs_for_stream(cls, filename, parent_folder, log_files):
        """Archive all log files to a folder named after the uploaded file inside the specified parent_folder."""
        try:
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
