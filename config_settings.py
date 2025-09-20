import os
import re
import traceback
import json
from configparser import ConfigParser, NoSectionError, NoOptionError


class DVR_Config:
    ProjRoot_Dir = os.path.dirname(os.path.abspath(__file__))
    Config_Dir = os.path.join(ProjRoot_Dir, "_Config")

    settings_parser = None

    @classmethod
    def _init_settings_parser(cls):
        if cls.settings_parser is None:
            settings_config_path = os.path.join(cls.Config_Dir, "dvr_settings.cfg")
            # Disable interpolation to allow raw % in values
            cls.settings_parser = ConfigParser(interpolation=None)
            if not os.path.exists(settings_config_path):
                # Create an empty config file if it does not exist
                with open(settings_config_path, "w") as f:
                    f.write("")
            cls.settings_parser.read(settings_config_path)

    @classmethod
    def get_value(cls, section, key):
        cls._init_settings_parser()
        if cls.settings_parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        try:
            return cls.settings_parser.get(section, key)
        except (NoSectionError, NoOptionError) as e:
            # Use print instead of log_core to avoid circular import
            print(f"Config error: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def set_value(cls, section, key, value):
        """
        Set a value in the config file and save it.
        """
        cls._init_settings_parser()
        if cls.settings_parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        if not cls.settings_parser.has_section(section):
            cls.settings_parser.add_section(section)
        cls.settings_parser.set(section, key, value)
        config_path = os.path.join(cls.Config_Dir, "dvr_settings.cfg")
        with open(config_path, "w") as cfg:
            cls.settings_parser.write(cfg)

    @staticmethod
    def parse_string_list(str_list):
        """Convert a string representation of a Python list to an actual list."""
        try:
            return json.loads(str_list)
        except Exception as e:
            raise RuntimeError(f"Failed to parse string list:  {e}\n{traceback.format_exc()}")

    # Directory References

    # Live Directories
    @classmethod
    def get_live_downloadqueue_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "Live_DownloadQueue_Dir"))

    @classmethod
    def get_live_downloadrecovery_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "live_downloadrecovery_dir"))

    @classmethod
    def get_live_completeduploads_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "live_completeduploads_dir"))

    @classmethod
    def get_live_uploadqueue_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "Live_UploadQueue_Dir"))

    @classmethod
    def get_live_comments_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "Live_Comments_Dir"))

    @classmethod
    def get_live_captions_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "Captions_Dir"))

    # Posted Directories
    @classmethod
    def get_posted_downloadqueue_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "posted_downloadqueue_dir"))

    @classmethod
    def get_posted_completeduploads_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "posted_completeduploads_dir"))

    @classmethod
    def get_posted_playlists_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "posted_playlists_dir"))

    @classmethod
    def get_posted_uploadqueue_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "posted_uploadqueue_dir"))

    @classmethod
    def get_posted_notices_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "posted_notices_dir"))

    # Misc Directories
    @classmethod
    def get_auth_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "Auth_Dir"))

    @classmethod
    def get_log_dir(cls):
        return os.path.join(cls.ProjRoot_Dir, cls.get_value("Directories", "Log_Dir"))

    @classmethod
    def get_archived_logs_dir(cls):
        return os.path.join(cls.get_log_dir(), "_ArchivedLogs")

    @classmethod
    def get_bin_dir(cls):
        return cls.get_value("Directories", "bin_dir")

    @classmethod
    def get_meta_data_dir(cls):
        MetaData_Dir_Name = cls.get_value("Directories", "MetaData_Dir")
        return os.path.join(cls.ProjRoot_Dir, MetaData_Dir_Name)

    # File References

    # Posted Files
    @classmethod
    def get_posted_delta_playlist(cls):
        playlist_dir = cls.get_posted_playlists_dir()
        return os.path.join(playlist_dir, "_Delta_Playlist.csv")

    @classmethod
    def get_posted_persistent_playlist(cls):
        playlist_dir = cls.get_posted_playlists_dir()
        return os.path.join(playlist_dir, "_Persistent_Playlist.csv")

    @classmethod
    def get_posted_download_list(cls):
        playlist_dir = cls.get_posted_playlists_dir()
        return os.path.join(playlist_dir, "_Download_Playlist.txt")

    # Upload Files
    @classmethod
    def get_yt_client_secret_file(cls):
        auth_dir = cls.get_auth_dir()
        return os.path.join(cls.ProjRoot_Dir, auth_dir, "YT-client_secret.json")

    @classmethod
    def get_yt_credentials_file(cls):
        auth_dir = cls.get_auth_dir()
        return os.path.join(cls.ProjRoot_Dir, auth_dir, "YT-oauth2.json")

    # Log File References
    @classmethod
    def get_core_log_file(cls):
        return os.path.join(cls.get_log_dir(), "_Core_Package_Updater.log")

    @classmethod
    def get_captions_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Captions.log")

    @classmethod
    def get_download_comments_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Comments.log")

    @classmethod
    def get_download_live_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Download_YouTube_LiveStreams.log")

    @classmethod
    def get_download_live_recovery_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Recovery.log")

    @classmethod
    def get_download_posted_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Posted_videos.log")

    @classmethod
    def get_download_posted_notices_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Posted_Notices.log")

    @classmethod
    def get_upload_posted_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Upload_Manager_Posted_Videos.log")

    @classmethod
    def get_upload_live_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Upload_Manager_LiveStreams.log")

    @classmethod
    def get_upload_ia_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Upload_Platform_InternetArchive.log")

    @classmethod
    def get_upload_yt_log_file(cls):
        return os.path.join(cls.get_log_dir(), "Upload_Platform_YouTube.log")

    # Log Filters
    @classmethod
    def core_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "CORE_LOG_FILTER"))

    @classmethod
    def captions_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "CAPTIONS_LOG_FILTER"))

    @classmethod
    def download_live_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "DOWNLOAD_LIVE_LOG_FILTER"))

    @classmethod
    def download_live_recovery_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "download_live_recovery_log_filter"))

    @classmethod
    def download_posted_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "DOWNLOAD_POSTED_LOG_FILTER"))

    @classmethod
    def download_posted_notices_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "DOWNLOAD_POSTED_NOTICES_LOG_FILTER"))

    @classmethod
    def upload_posted_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "UPLOAD_POSTED_LOG_FILTER"))

    @classmethod
    def upload_live_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "UPLOAD_LIVE_LOG_FILTER"))

    @classmethod
    def upload_ia_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "UPLOAD_IA_LOG_FILTER"))

    @classmethod
    def upload_yt_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "UPLOAD_YT_LOG_FILTER"))

    # Strings

    @classmethod
    def get_disable_log_archiving(cls):
        return cls.get_value("Logging", "disable_log_archiving").lower()

    @classmethod
    def get_download_timestamp_format(cls):
        return cls.get_value("YT_DownloadSettings", "download_timestamp_format")

    @classmethod
    def get_max_title_filename_chars(cls):
        return cls.get_value("YT_DownloadSettings", "dlp_truncate_title_after_x_chars")

    @classmethod
    def get_max_dlp_download_retries(cls):
        return cls.get_value("YT_DownloadSettings", "dlp_max_download_retries")

    @classmethod
    def get_max_dlp_fragment_retries(cls):
        return cls.get_value("YT_DownloadSettings", "dlp_max_fragment_retries")

    @classmethod
    def get_verbose_dlp_mode(cls):
        return cls.get_value("YT_DownloadSettings", "dlp_verbose_downloads")

    @classmethod
    def no_progress_dlp_downloads(cls):
        return cls.get_value("YT_DownloadSettings", "dlp_no_progress_downloads")

    @classmethod
    def get_keep_fragments_dlp_downloads(cls):
        return cls.get_value("YT_DownloadSettings", "dlp_keep_fragments_downloads")

    @classmethod
    def get_no_progress_dlp_filters(cls):
        file_extensions = json.loads(cls.get_value("YT_DownloadSettings", "dlp_no_progress_filters"))
        return tuple(file_extensions)

    @classmethod
    def get_video_file_extensions(cls):
        file_extensions = json.loads(cls.get_value("YT_UploadSettings", "upload_file_extensions"))
        return tuple(file_extensions)

    @classmethod
    def get_required_dependencies(cls):
        dependencies = json.loads(cls.get_value("General", "required_dependencies"))
        return tuple(dependencies)

    @classmethod
    def get_maximum_threads(cls):
        return cls.get_value("General", "maximum_threads")