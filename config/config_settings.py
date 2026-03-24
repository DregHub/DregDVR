import contextlib
import os
import json
import traceback
import logging
from .config import BaseConfig
# Configure logger for this module

logger = logging.getLogger(__name__)
class DVR_Config(BaseConfig):
    parser = None
    parser_attr_name = "parser"
    config_filename = "dvr_settings.cfg"
    Project_Root_Dir = None
    Data_Root_Dir = None

    @classmethod
    def _init_parser(cls):
        """Initialize the configuration parser and set Data_Root_Dir."""
        try:
            # Call parent's _init_parser to initialize the parser attribute
            super()._init_parser()

            # Set Data_Root_Dir only if parser is ready and not already set
            if cls.Data_Root_Dir is None and cls.parser is not None:
                with contextlib.suppress(Exception):
                    data_dir_name = json.loads(cls.get_value("Directories", "data_dir"))
                    cls.Data_Root_Dir = os.path.join(cls.Root_Dir, data_dir_name)
        except Exception as e:
            logger.error(f"Error in DVR_Config._init_parser: {e}\n{traceback.format_exc()}")
            raise
    # Live Directories

    @classmethod
    def get_live_downloadqueue_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "live_downloadqueue_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_live_downloadqueue_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_live_downloadrecovery_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "live_downloadrecovery_dir").strip('"'),
            )

        except Exception as e:
            logger.error(
                f"Error in get_live_downloadrecovery_dir: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_live_completeduploads_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "live_completeduploads_dir").strip('"'),
            )

        except Exception as e:
            logger.error(
                f"Error in get_live_completeduploads_dir: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_live_uploadqueue_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "live_uploadqueue_dir").strip('"'),
            )

        except Exception as e:
            logger.error(f"Error in get_live_uploadqueue_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_live_comments_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "live_comments_dir").strip('"'),
            )

        except Exception as e:
            logger.error(f"Error in get_live_comments_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_live_captions_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "captions_dir").strip('"'),
            )

        except Exception as e:
            logger.error(f"Error in get_live_captions_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_temp_captions_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.get_live_captions_dir(),
                cls.get_value("Directories", "temp_captions_dir").strip('"'),
            )

        except Exception as e:
            logger.error(f"Error in get_temp_captions_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_captions_upload_queue_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.get_live_captions_dir(),
                cls.get_value("Directories", "captions_upload_queue_dir").strip('"'),
            )

        except Exception as e:

            logger.error(f"Error in get_captions_upload_queue_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_captions_completed_uploads_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.get_live_captions_dir(),
                cls.get_value("Directories", "captions_completed_uploads_dir").strip('"'),
            )

        except Exception as e:

            logger.error(f"Error in get_captions_completed_uploads_dir: {e}\n{traceback.format_exc()}")
            raise


    # Posted Directories

    @classmethod
    def get_posted_downloadqueue_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "posted_downloadqueue_dir").strip('"'),
            )
        except Exception as e:
            logger.error(
                f"Error in get_posted_downloadqueue_dir: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_posted_completeduploads_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "posted_completeduploads_dir").strip('"'),
            )
        except Exception as e:
            logger.error(
                f"Error in get_posted_completeduploads_dir: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_channel_playlists_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Runtime_Profile_Dir,
                cls.get_value("Directories", "channel_playlists_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_channel_playlists_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_uploadqueue_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "posted_uploadqueue_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_posted_uploadqueue_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_notices_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Data_Root_Dir,
                cls.get_value("Directories", "posted_notices_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_posted_notices_dir: {e}\n{traceback.format_exc()}")
            raise

    # Misc Directories

    @classmethod
    def get_auth_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Runtime_Profile_Dir,
                cls.get_value("Directories", "auth_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_auth_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_log_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Runtime_Profile_Dir,
                cls.get_value("Directories", "log_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_log_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_templates_dir(cls):
        try:
            cls._init_parser()
            # Remove user customise option as its now part of the project
            return os.path.join(cls.Project_Root_Dir, "templates")
        except Exception as e:
            logger.error(f"Error in get_templates_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_archived_logs_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "_ArchivedLogs")
        except Exception as e:
            logger.error(f"Error in get_archived_logs_dir: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_download_root(cls):
        try:
            cls._init_parser()
            root_dir_name = cls.get_value("Directories", "root_dir")
            return os.path.join(cls.Data_Root_Dir, root_dir_name)
        except Exception as e:
            logger.error(f"Error in get_download_root: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_meta_data_dir(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.Runtime_Profile_Dir,
                cls.get_value("Directories", "metadata_dir").strip('"'),
            )
        except Exception as e:
            logger.error(f"Error in get_meta_data_dir: {e}\n{traceback.format_exc()}")
            raise

    # File References
    # Posted Files

    @classmethod
    def get_channel_playlist(cls, channel_name=None):
        try:
            cls._init_parser()
            playlist_dir = cls.get_channel_playlists_dir()
            if channel_name:
                # Strip the @ prefix from the channel name if present
                clean_channel_name = channel_name.lstrip("@").strip('"').strip()
                filename = f"{clean_channel_name}_Playlist.json"
            else:
                filename = "Playlist.json"
            return os.path.join(playlist_dir, filename)
        except Exception as e:
            logger.error(
                f"Error in get_channel_playlist: {e}\n{traceback.format_exc()}"
            )
            raise

    # Upload Files
    @classmethod
    def get_yt_client_secret_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_auth_dir(), "YT-client_secret.json")
        except Exception as e:
            logger.error(f"Error in get_yt_client_secret_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_yt_credentials_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_auth_dir(), "YT-oauth2.json")
        except Exception as e:
            logger.error(f"Error in get_yt_credentials_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_yt_cookies_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_auth_dir(), "cookies.txt")
        except Exception as e:
            logger.error(f"Error in get_yt_cookies_file: {e}\n{traceback.format_exc()}")
            raise

    # Log File References

    @classmethod
    def get_core_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Core_Package_Updater.log")
        except Exception as e:
            logger.error(f"Error in get_core_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_captions_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Download_YouTube_Captions.log")
        except Exception as e:
            logger.error(f"Error in get_captions_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_download_comments_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Download_YouTube_Comments.log")
        except Exception as e:
            logger.error(
                f"Error in get_download_comments_log_file: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_download_live_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Download_YouTube_Live.log")
        except Exception as e:
            logger.error(f"Error in get_download_live_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_download_live_recovery_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Download_YouTube_Live_Recovery.log")
        except Exception as e:
            logger.error(
                f"Error in get_download_live_recovery_log_file: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_download_posted_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Download_YouTube_Posted_Videos.log")
        except Exception as e:
            logger.error(
                f"Error in get_download_posted_log_file: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_channel_playlist_log_file(cls, channel_name=None):
        try:
            cls._init_parser()
            if channel_name:
                # Strip the @ prefix from the channel name if present
                clean_channel_name = channel_name.lstrip("@").strip('"').strip()
                filename = f"Download_YouTube_Channel_Playlist_{clean_channel_name}.log"
            else:
                filename = "Download_YouTube_Channel_Playlist.log"
            return os.path.join(cls.get_log_dir(), filename)
        except Exception as e:
            logger.error(
                f"Error in get_channel_playlist_log_file: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_download_posted_notices_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.get_log_dir(), "Download_YouTube_Posted_Notices.log"
            )
        except Exception as e:
            logger.error(
                f"Error in get_download_posted_notices_log_file: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_upload_posted_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Upload_Manager_Posted_Videos.log")
        except Exception as e:
            logger.error(f"Error in get_upload_posted_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_upload_live_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Upload_Manager_LiveStreams.log")
        except Exception as e:
            logger.error(f"Error in get_upload_live_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_upload_ia_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(
                cls.get_log_dir(), "Upload_Platform_InternetArchive.log"
            )
        except Exception as e:
            logger.error(f"Error in get_upload_ia_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_upload_yt_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Upload_Platform_YouTube.log")
        except Exception as e:
            logger.error(f"Error in get_upload_yt_log_file: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_upload_captions_log_file(cls):
        try:
            cls._init_parser()
            return os.path.join(cls.get_log_dir(), "Upload_Manager_Captions.log")
        except Exception as e:
            logger.error(f"Error in get_upload_captions_log_file: {e}\n{traceback.format_exc()}")
            raise

    # Log Filters

    @classmethod
    def core_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "core_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in core_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def captions_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "captions_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in captions_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def download_live_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "download_live_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in download_live_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def download_live_recovery_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "download_live_recovery_log_filter")
            )
        except Exception as e:
            logger.error(
                f"Error in download_live_recovery_log_filter: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def download_posted_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "download_posted_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in download_posted_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def channel_playlist_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "channel_playlist_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in channel_playlist_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def download_posted_notices_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "download_posted_notices_log_filter")
            )
        except Exception as e:
            logger.error(
                f"Error in download_posted_notices_log_filter: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def upload_posted_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "upload_posted_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in upload_posted_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def upload_live_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "upload_live_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in upload_live_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def upload_ia_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "upload_ia_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in upload_ia_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def upload_yt_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "upload_yt_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in upload_yt_log_filter: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def upload_captions_log_filter(cls):
        try:
            return cls.parse_string_list(
                cls.get_value("Log_Filters", "upload_captions_log_filter")
            )
        except Exception as e:
            logger.error(f"Error in upload_captions_log_filter: {e}\n{traceback.format_exc()}")
            raise

    # Strings

    @classmethod
    def get_log_archiving(cls):
        try:
            return cls.get_value_as_bool("Logging", "log_archiving")
        except Exception as e:
            logger.error(f"Error in get_log_archiving: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_download_timestamp_format(cls):
        try:
            return cls.get_value("YT_DownloadSettings", "download_timestamp_format")
        except Exception as e:
            logger.error(
                f"Error in get_download_timestamp_format: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_max_title_filename_chars(cls):
        try:
            return cls.get_value(
                "YT_DownloadSettings", "dlp_truncate_title_after_x_chars"
            )
        except Exception as e:
            logger.error(
                f"Error in get_max_title_filename_chars: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_max_dlp_download_retries(cls):
        try:
            return cls.get_value("YT_DownloadSettings", "dlp_max_download_retries")
        except Exception as e:
            logger.error(
                f"Error in get_max_dlp_download_retries: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_max_dlp_fragment_retries(cls):
        try:
            return cls.get_value("YT_DownloadSettings", "dlp_max_fragment_retries")
        except Exception as e:
            logger.error(
                f"Error in get_max_dlp_fragment_retries: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_verbose_dlp_mode(cls):
        try:
            return cls.get_value_as_bool("YT_DownloadSettings", "dlp_verbose_downloads")
        except Exception as e:
            logger.error(f"Error in get_verbose_dlp_mode: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def no_progress_dlp_downloads(cls):
        try:
            return cls.get_value_as_bool(
                "YT_DownloadSettings", "dlp_no_progress_downloads"
            )
        except Exception as e:
            logger.error(f"Error in no_progress_dlp_downloads: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_keep_fragments_dlp_downloads(cls):
        try:
            return cls.get_value_as_bool(
                "YT_DownloadSettings", "dlp_keep_fragments_downloads"
            )
        except Exception as e:
            logger.error(
                f"Error in get_keep_fragments_dlp_downloads: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_video_file_extensions(cls):
        try:
            file_extensions = json.loads(
                cls.get_value("YT_UploadSettings", "upload_file_extensions")
            )
            return tuple(file_extensions)
        except Exception as e:
            logger.error(f"Error in get_video_file_extensions: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_yt_upload_visibility(cls):
        try:
            return cls.get_value("YT_UploadSettings", "upload_visibility").strip('"')
        except Exception as e:
            logger.error(f"Error in get_yt_upload_visibility: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_yt_upload_catagory(cls):
        try:
            return cls.get_value("YT_UploadSettings", "upload_category").strip('"')
        except Exception as e:
            logger.error(f"Error in get_yt_upload_catagory: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_required_py_dependencies(cls):
        try:
            dependencies = json.loads(
                cls.get_value("General", "required_pip_dependencies")
            )
            return tuple(dependencies)
        except Exception as e:
            logger.error(
                f"Error in get_required_py_dependencies: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_required_apk_dependencies(cls):
        try:
            dependencies = json.loads(
                cls.get_value("General", "required_apk_dependencies")
            )
            return tuple(dependencies)
        except Exception as e:
            logger.error(
                f"Error in get_required_apk_dependencies: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_maximum_threads(cls):
        try:
            return cls.get_value("General", "maximum_threads")
        except Exception as e:
            logger.error(f"Error in get_maximum_threads: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_dlp_subtitle_use_srtfix(cls):
        try:
            return cls.get_value_as_bool(
                "YT_DownloadSettings", "dlp_subtitle_use_srtfix"
            )
        except Exception as e:
            logger.error(
                f"Error in get_dlp_subtitle_use_srtfix: {e}\n{traceback.format_exc()}"
            )
            raise
