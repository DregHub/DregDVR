import os
import re
import json
from config import BaseConfig


class DVR_Config(BaseConfig):
    parser = None
    parser_attr_name = "parser"
    config_filename = "dvr_settings.cfg"
    Data_Root_Dir = None

    @classmethod
    def _init_parser(cls):
        """Initialize the configuration parser and set Data_Root_Dir."""
        # Only initialize parent parser, do NOT call other DVR_Config methods here
        super()._init_parser()
        
        # Set Data_Root_Dir only if parser is ready and not already set
        if cls.Data_Root_Dir is None and cls.parser is not None:
            try:
                data_dir_name = json.loads(cls.get_value("Directories", "data_dir"))
                cls.Data_Root_Dir = os.path.join(cls.Root_Dir, data_dir_name)
            except Exception:
                # If initialization fails, just skip - will retry on next call
                pass

    # Directory References

    # Live Directories
    @classmethod
    def get_live_downloadqueue_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "live_downloadqueue_dir").strip('"'))

    @classmethod
    def get_live_downloadrecovery_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "live_downloadrecovery_dir").strip('"'))

    @classmethod
    def get_live_completeduploads_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "live_completeduploads_dir").strip('"'))

    @classmethod
    def get_live_uploadqueue_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "live_uploadqueue_dir").strip('"'))
    
    @classmethod
    def get_live_comments_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "live_comments_dir").strip('"'))

    @classmethod
    def get_live_captions_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "captions_dir").strip('"'))

    # Posted Directories
    @classmethod
    def get_posted_downloadqueue_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "posted_downloadqueue_dir").strip('"'))

    @classmethod
    def get_posted_completeduploads_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "posted_completeduploads_dir").strip('"'))

    @classmethod
    def get_posted_playlists_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "posted_playlists_dir").strip('"'))

    @classmethod
    def get_posted_uploadqueue_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "posted_uploadqueue_dir").strip('"'))

    @classmethod
    def get_posted_notices_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Data_Root_Dir, cls.get_value("Directories", "posted_notices_dir").strip('"'))

    # Misc Directories
    @classmethod
    def get_auth_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Runtime_Profile_Dir, cls.get_value("Directories", "auth_dir").strip('"'))

    @classmethod
    def get_log_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Runtime_Profile_Dir, cls.get_value("Directories", "log_dir").strip('"'))

    @classmethod
    def get_archived_logs_dir(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "_ArchivedLogs")
    
    @classmethod
    def get_download_root(cls):
        cls._init_parser()
        root_dir_name = cls.get_value("Directories", "root_dir")
        return os.path.join(cls.Data_Root_Dir, root_dir_name)
    
    @classmethod
    def get_meta_data_dir(cls):
        cls._init_parser()
        return os.path.join(cls.Runtime_Profile_Dir, cls.get_value("Directories", "metadata_dir").strip('"'))
    

    # File References

    # Posted Files
    @classmethod
    def get_posted_delta_playlist(cls):
        cls._init_parser()
        playlist_dir = cls.get_posted_playlists_dir()
        return os.path.join(playlist_dir, "_Delta_Playlist.csv")

    @classmethod
    def get_posted_persistent_playlist(cls):
        cls._init_parser()
        playlist_dir = cls.get_posted_playlists_dir()
        return os.path.join(playlist_dir, "_Persistent_Playlist.csv")

    @classmethod
    def get_posted_download_list(cls):
        cls._init_parser()
        playlist_dir = cls.get_posted_playlists_dir()
        return os.path.join(playlist_dir, "_Download_Playlist.txt")

    # Upload Files
    @classmethod
    def get_yt_client_secret_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_auth_dir(), "YT-client_secret.json")

    @classmethod
    def get_yt_credentials_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_auth_dir(), "YT-oauth2.json")

    # Log File References
    @classmethod
    def get_core_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "_Core_Package_Updater.log")

    @classmethod
    def get_captions_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Captions.log")

    @classmethod
    def get_download_comments_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Comments.log")

    @classmethod
    def get_download_live_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Download_YouTube_LiveStreams.log")

    @classmethod
    def get_download_live_recovery_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Recovery.log")

    @classmethod
    def get_download_posted_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Posted_videos.log")

    @classmethod
    def get_download_posted_notices_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Download_YouTube_Posted_Notices.log")

    @classmethod
    def get_upload_posted_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Upload_Manager_Posted_Videos.log")

    @classmethod
    def get_upload_live_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Upload_Manager_LiveStreams.log")

    @classmethod
    def get_upload_ia_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Upload_Platform_InternetArchive.log")

    @classmethod
    def get_upload_yt_log_file(cls):
        cls._init_parser()
        return os.path.join(cls.get_log_dir(), "Upload_Platform_YouTube.log")

    # Log Filters
    @classmethod
    def core_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "core_log_filter"))

    @classmethod
    def captions_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "captions_log_filter"))

    @classmethod
    def download_live_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "download_live_log_filter"))

    @classmethod
    def download_live_recovery_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "download_live_recovery_log_filter"))

    @classmethod
    def download_posted_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "download_posted_log_filter"))

    @classmethod
    def download_posted_notices_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "download_posted_notices_log_filter"))

    @classmethod
    def upload_posted_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "upload_posted_log_filter"))

    @classmethod
    def upload_live_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "upload_live_log_filter"))

    @classmethod
    def upload_ia_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "upload_ia_log_filter"))

    @classmethod
    def upload_yt_log_filter(cls):
        return cls.parse_string_list(cls.get_value("Log_Filters", "upload_yt_log_filter"))

    # Strings

    @classmethod
    def get_log_archiving(cls):
        return cls.get_value("Logging", "log_archiving").lower()

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
    def get_yt_upload_visibility(cls):
        return cls.get_value("YT_UploadSettings", "upload_visibility").strip('"')

    @classmethod
    def get_yt_upload_catagory(cls):
        return cls.get_value("YT_UploadSettings", "upload_category").strip('"')

    @classmethod
    def get_required_py_dependencies(cls):
        dependencies = json.loads(cls.get_value("General", "required_pip_dependencies"))
        return tuple(dependencies)

    @classmethod
    def get_required_apk_dependencies(cls):
        dependencies = json.loads(cls.get_value("General", "required_apk_dependencies"))
        return tuple(dependencies)

    @classmethod
    def get_maximum_threads(cls):
        return cls.get_value("General", "maximum_threads")