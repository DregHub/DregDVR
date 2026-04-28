"""
Database-backed Settings Configuration
Replaces the INI file-based config_settings.py functionality
Now provides async methods for non-blocking database access.
"""

import os
import hashlib


class DVR_Config:
    """DVR settings configuration using SQLite database with async access."""

    Project_Root_Dir = None
    Data_Root_Dir = None
    _current_instance = None
    _db = None
    _instance_data_root_dirs = {}

    @classmethod
    def set_instance(cls, instance_name: str):
        """Set the current instance by name."""
        from utils.file_utils import FileManager

        # Convert instance name to safe format
        safe_name = FileManager.gen_safe_filename(instance_name)
        cls._current_instance = safe_name

    @classmethod
    def get_current_instance(cls):
        """Get the current instance name."""
        return cls._current_instance

    @classmethod
    def _init_parser(cls):
        """Initialize parser for the current instance (database-backed, no action needed)."""
        pass

    @classmethod
    async def _get_db(cls):
        """Get database instance (async version)."""
        if cls._db is None:
            from db.dvr_db import DVRDB

            cls._db = await DVRDB.get_global()
        return cls._db

    @classmethod
    async def _get_instance_name(cls):
        """Get current instance name from database (async version)."""
        if not cls._current_instance:
            return None

        db = await cls._get_db()
        instances = await db.get_all_instances()
        for inst in instances:
            from utils.file_utils import FileManager

            if (
                FileManager.gen_safe_filename(inst["instance_name"])
                == cls._current_instance
            ):
                return inst["instance_name"]
        return None

    # Directory getters - these return the standard directory names
    @classmethod
    def get_data_root_dir(cls):
        """Get data root directory."""
        return "_DVR_Data"

    @classmethod
    def get_live_videos_dir(cls):
        """Get live videos directory name."""
        return "_Live_Videos"

    @classmethod
    def get_live_downloadqueue_dir(cls):
        """Get live download queue directory name."""
        return "_Live_DownloadQueue"

    @classmethod
    def get_live_downloadrecovery_dir(cls):
        """Get live download recovery directory name."""
        return "_Live_DownloadRecovery"

    @classmethod
    def get_live_comments_dir(cls):
        """Get live comments directory name."""
        return "_Live_Comments"

    @classmethod
    def get_posted_videos_dir(cls):
        """Get posted videos directory name."""
        return "_Posted_Videos"

    @classmethod
    def get_posted_downloadqueue_dir(cls):
        """Get posted download queue directory name."""
        return "_Posted_DownloadQueue"

    @classmethod
    def get_posted_notices_dir(cls):
        """Get posted notices directory name."""
        return "_Posted_CommunityMessages"

    @classmethod
    def get_metadata_dir(cls):
        """Get metadata directory name."""
        return "_Meta"

    @classmethod
    def get_captions_dir(cls):
        """Get captions directory name."""
        return "_Captions"

    @classmethod
    def get_captions_upload_queue_dir(cls):
        """Get captions upload queue directory name."""
        return "_Captions_UploadQueue"

    @classmethod
    def get_captions_completed_uploads_dir(cls):
        """Get captions completed uploads directory name."""
        return "_Captions_CompletedUploads"

    @classmethod
    def get_temp_captions_dir(cls):
        """Get temp captions directory name."""
        return "_Temp"

    @classmethod
    def get_log_dir(cls):
        """Get log directory name."""
        return "_Logs"

    @classmethod
    def get_auth_dir(cls):
        """Get auth directory name."""
        return "_Auth"

    @classmethod
    def get_playwright_dir(cls):
        """Get playwright directory name."""
        return "_PlayWright"

    @classmethod
    def get_templates_dir(cls):
        """Get templates directory name."""
        return "_Templates"

    @classmethod
    def _ensure_auth_file_mirrored(
        cls, content: str, filename: str, use_global: bool = False
    ) -> str:
        """Ensure auth file is mirrored to temp directory and return file path.

        Args:
            content: File content to write
            filename: Name of the file
            use_global: If True, use global auth directory; if False, use instance-specific directory
        """
        if not content:
            return ""

        if use_global:
            auth_dir = os.path.join("/_DVR_Runtime", "Auth", "Global")
        else:
            instance_name = cls._get_instance_name()
            if not instance_name:
                return ""
            auth_dir = os.path.join("/_DVR_Runtime", "Auth", instance_name)

        os.makedirs(auth_dir, exist_ok=True)
        file_path = os.path.join(auth_dir, filename)

        # Check if file needs updating
        needs_update = True
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()
                if (
                    hashlib.md5(content.encode("utf-8")).hexdigest()
                    == hashlib.md5(existing_content.encode("utf-8")).hexdigest()
                ):
                    needs_update = False
            except Exception:
                pass  # If read fails, update anyway

        if needs_update:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"Failed to write auth file {file_path}: {e}")
                return ""

        return file_path

    @classmethod
    def save_download_cookies(cls, content: str) -> str:
        """Save YouTube download cookies to Auth/Download/cookies1.txt and database.

        Args:
            content: Cookie file content

        Returns:
            Path to saved cookies file
        """
        if not content:
            return ""

        auth_dir = os.path.join("/_DVR_Runtime", "Auth", "Download")
        os.makedirs(auth_dir, exist_ok=True)
        file_path = os.path.join(auth_dir, "cookies1.txt")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Saved download cookies to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save download cookies to {file_path}: {e}")
            return ""

    @classmethod
    def get_yt_cookies_file(cls):
        """Get YouTube cookies file path from Auth/Download/cookies1.txt.

        Returns:
            Path to first available cookies file, or empty string if none exist.
        """
        file_path = os.path.join("/_DVR_Runtime", "Auth", "Download", "cookies1.txt")
        if os.path.exists(file_path):
            return file_path
        return ""

    @classmethod
    def add_cookies_to_ydl_opts(cls, ydl_opts: dict) -> dict:
        """Safely add cookies to yt-dlp options if they exist.

        Only adds the 'cookiefile' parameter if a cookies file is actually present.
        Otherwise leaves ydl_opts unchanged.

        Args:
            ydl_opts: YoutubeDL options dictionary

        Returns:
            Modified ydl_opts with cookiefile parameter (if cookies exist), otherwise unchanged
        """
        if ydl_opts is None:
            ydl_opts = {}

        cookies_file = cls.get_yt_cookies_file()
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        return ydl_opts

    @classmethod
    async def get_yt_client_secret_file(cls):
        """Get YouTube client secret file path, ensuring it's mirrored from database."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        content = await db.get_yt_client_secret_content(instance_name)
        return (
            cls._ensure_auth_file_mirrored(content, "client_secret.json")
            if content
            else ""
        )

    @classmethod
    async def get_yt_credentials_file(cls):
        """Get YouTube credentials file path, ensuring it's mirrored from database."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        content = await db.get_yt_oauth2_content(instance_name)
        return cls._ensure_auth_file_mirrored(content, "oauth2.json") if content else ""

    # Download settings
    @classmethod
    async def get_download_timestamp_format(cls):
        """Get download timestamp format (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return (
            settings.get("download_timestamp_format")
            or "%(timestamp>%d-%m-%Y %I-%M%p)s"
            if settings
            else "%(timestamp>%d-%m-%Y %I-%M%p)s"
        )

    @classmethod
    async def get_dlp_verbose_downloads(cls):
        """Get DLP verbose downloads flag (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return bool(settings.get("dlp_verbose_downloads", True) if settings else True)

    @classmethod
    async def get_dlp_keep_fragments_downloads(cls):
        """Get DLP keep fragments flag (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return bool(
            settings.get("dlp_keep_fragments_downloads", False) if settings else False
        )

    @classmethod
    async def get_dlp_max_download_retries(cls):
        """Get DLP max download retries (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("dlp_max_download_retries", 10) if settings else 10

    @classmethod
    async def get_dlp_max_fragment_retries(cls):
        """Get DLP max fragment retries (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("dlp_max_fragment_retries", 10) if settings else 10

    @classmethod
    async def get_dlp_js_runtime(cls):
        """Get DLP JavaScript runtime (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("dlp_js_runtime", "deno") if settings else "deno"

    @classmethod
    async def get_dlp_truncate_title_after_x_chars(cls):
        """Get DLP title truncate length (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("dlp_truncate_title_after_x_chars", 60) if settings else 60

    @classmethod
    async def get_dlp_subtitle_use_srtfix(cls):
        """Get DLP use srtfix flag (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return bool(settings.get("dlp_subtitle_use_srtfix", True) if settings else True)

    @classmethod
    async def get_dlp_getinfo_timeout_seconds(cls):
        """Get DLP getinfo timeout (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("dlp_getinfo_timeout_seconds", 800) if settings else 800

    @classmethod
    async def get_dlp_stall_timeout_seconds(cls):
        """Get DLP stall timeout (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("dlp_stall_timeout_seconds", 800) if settings else 800

    @classmethod
    async def get_dlp_buffer_first_attempt_errors(cls):
        """Get DLP buffer first attempt errors flag (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return bool(
            settings.get("dlp_buffer_first_attempt_errors", True) if settings else True
        )

    @classmethod
    def get_verbose_dlp_mode(cls):
        """Get DLP verbose mode flag - always returns True now that we have filtered logs."""
        return True

    # Upload settings (instance-scoped)
    @classmethod
    async def get_upload_visibility(cls):
        """Get default upload visibility (instance setting)."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return "Public"
        db = await cls._get_db()
        settings = await db.get_instance_settings(instance_name)
        return settings.get("upload_visibility", "Public") if settings else "Public"

    @classmethod
    async def get_upload_category(cls):
        """Get default upload category (instance setting)."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return "22"
        db = await cls._get_db()
        settings = await db.get_instance_settings(instance_name)
        return settings.get("upload_category", "22") if settings else "22"

    # Threading settings (global)
    @classmethod
    async def get_video_download_max_threads(cls):
        """Get max video download threads (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("video_download_max_threads", 6) if settings else 6

    @classmethod
    async def get_caption_download_max_threads(cls):
        """Get max caption download threads (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("caption_download_max_threads", 6) if settings else 6

    @classmethod
    async def get_caption_upload_max_threads(cls):
        """Get max caption upload threads (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("caption_upload_max_threads", 6) if settings else 6

    @classmethod
    async def get_video_upload_max_threads(cls):
        """Get max video upload threads (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("video_upload_max_threads", 6) if settings else 6

    @classmethod
    async def get_playlist_processing_max_threads(cls):
        """Get max playlist processing threads (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return settings.get("playlist_processing_max_threads", 6) if settings else 6

    # Session settings (global)
    @classmethod
    async def get_playwright_session_video_recording(cls):
        """Get session video recording flag (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return bool(
            settings.get("session_video_recording", False) if settings else False
        )

    @classmethod
    async def get_playwright_session_error_html_dump(cls):
        """Get session error HTML dump flag (global setting)."""
        db = await cls._get_db()
        settings = await db.get_global_settings()
        return bool(
            settings.get("session_error_html_dump", False) if settings else False
        )

    # Logging configuration methods (all now use database for storage)
    # These methods return log type identifiers for the logging database

    @classmethod
    def get_core_log_table(cls):
        """Get core log type identifier."""
        return "core"

    @classmethod
    def get_captions_log_table(cls):
        """Get captions log type identifier."""
        return "download_captions"

    @classmethod
    def get_download_comments_log_table(cls):
        """Get download comments log type identifier."""
        return "download_comments"

    @classmethod
    def get_download_live_log_table(cls):
        """Get download live log type identifier."""
        return "download_live"

    @classmethod
    def get_download_live_recovery_log_table(cls):
        """Get download live recovery log type identifier."""
        return "download_live_recovery"

    @classmethod
    def get_download_posted_log_table(cls):
        """Get download posted log type identifier."""
        return "download_posted"

    @classmethod
    def get_playlist_update_log_table(cls):
        """Get channel playlist log type identifier."""
        return "channel_playlist"

    @classmethod
    def get_download_posted_notices_log_table(cls):
        """Get download posted notices log type identifier."""
        return "download_posted_notices"

    @classmethod
    def get_upload_posted_log_table(cls):
        """Get upload posted log type identifier."""
        return "upload_posted"

    @classmethod
    def get_upload_live_log_table(cls):
        """Get upload live log type identifier."""
        return "upload_live"

    @classmethod
    def get_upload_ia_log_table(cls):
        """Get upload Internet Archive log type identifier."""
        return "upload_ia"

    @classmethod
    def get_upload_yt_log_table(cls):
        """Get upload YouTube log type identifier."""
        return "upload_yt"

    @classmethod
    def get_upload_rumble_log_table(cls):
        """Get upload Rumble log type identifier."""
        return "upload_rumble"

    @classmethod
    def get_upload_bitchute_log_table(cls):
        """Get upload BitChute log type identifier."""
        return "upload_bitchute"

    @classmethod
    def get_upload_odysee_log_table(cls):
        """Get upload Odysee log type identifier."""
        return "upload_odysee"

    @classmethod
    def get_upload_captions_log_table(cls):
        """Get upload captions log type identifier."""
        return "upload_captions"

    @classmethod
    async def get_console_thread_logging(cls):
        """Get console thread logging flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return bool(
            settings.get("console_thread_logging", False) if settings else False
        )

    @classmethod
    def build_youtube_url(cls, channel_name: str, add_live: bool = False) -> str:
        """Build a full YouTube URL from a channel name."""
        if not channel_name:
            return ""

        # If it's already a URL, return it
        if channel_name.startswith("http"):
            url = channel_name
        else:
            # Handle @handle format
            if not channel_name.startswith("@"):
                channel_name = "@" + channel_name
            url = f"https://www.youtube.com/{channel_name}"

        if add_live:
            url += "/live"

        return url

    @classmethod
    def extract_channel_handle(cls, channel_name: str) -> str:
        """Extract the @handle from a channel name or URL."""
        if not channel_name:
            return ""

        # If it's already a handle
        if channel_name.startswith("@"):
            return channel_name

        # If it's a URL, extract the handle
        if "youtube.com/" in channel_name:
            parts = channel_name.split("youtube.com/")
            if len(parts) > 1:
                return parts[1].strip("/")

        return channel_name

    # File naming
    @classmethod
    async def get_live_downloadprefix(cls):
        """Get live download prefix."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("live_downloadprefix") or "" if account else ""

    @classmethod
    async def get_posted_downloadprefix(cls):
        """Get posted videos download prefix."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("posted_downloadprefix") or "" if account else ""

    # Internet Archive
    @classmethod
    async def get_ia_itemid(cls):
        """Get Internet Archive item ID."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("ia_itemid") or "" if account else ""

    @classmethod
    async def get_ia_user_agent(cls):
        """Get Internet Archive user agent."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("ia_user_agent") or "" if account else ""

    @classmethod
    async def get_ia_email(cls):
        """Get Internet Archive email."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("ia_email") or "" if account else ""

    @classmethod
    async def get_ia_password(cls):
        """Get Internet Archive password."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("ia_password") or "" if account else ""

    # GitHub
    @classmethod
    async def get_github_token(cls):
        """Get GitHub personal access token."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("github_token") or "" if account else ""

    @classmethod
    async def get_github_repo_owner(cls):
        """Get GitHub repository owner."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("github_repo_owner") or "" if account else ""

    @classmethod
    async def get_github_repo_name(cls):
        """Get GitHub repository name."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("github_repo_name") or "" if account else ""

    @classmethod
    async def get_github_captions_path(cls):
        """Get GitHub captions path."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("github_captions_path") or "" if account else ""

    # Rumble
    @classmethod
    async def get_rumble_email(cls):
        """Get Rumble email."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("rumble_email") or "" if account else ""

    @classmethod
    async def get_rumble_password(cls):
        """Get Rumble password."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("rumble_password") or "" if account else ""

    @classmethod
    async def get_rumble_primary_category(cls):
        """Get Rumble primary category."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("rumble_primary_category") or "" if account else ""

    @classmethod
    async def get_rumble_secondary_category(cls):
        """Get Rumble secondary category."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("rumble_secondary_category") or "" if account else ""

    # BitChute
    @classmethod
    async def get_bitchute_email(cls):
        """Get BitChute email."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("bitchute_email") or "" if account else ""

    @classmethod
    async def get_bitchute_password(cls):
        """Get BitChute password."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("bitchute_password") or "" if account else ""

    # Odysee
    @classmethod
    async def get_odysee_email(cls):
        """Get Odysee email."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("odysee_email") or "" if account else ""

    @classmethod
    async def get_odysee_password(cls):
        """Get Odysee password."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return ""
        db = await cls._get_db()
        account = await db.get_account(instance_name)
        return account.get("odysee_password") or "" if account else ""

    # Upload enable flags
    @classmethod
    async def upload_to_ia_enabled(cls):
        """Check if upload to Internet Archive is enabled."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return bool(settings.get("upload_to_ia_enabled", False) if settings else False)

    @classmethod
    async def upload_to_youtube_enabled(cls):
        """Check if upload to YouTube is enabled."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return bool(
            settings.get("upload_to_youtube_enabled", False) if settings else False
        )

    @classmethod
    async def upload_to_rumble_enabled(cls):
        """Check if upload to Rumble is enabled."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return bool(
            settings.get("upload_to_rumble_enabled", False) if settings else False
        )

    @classmethod
    async def upload_to_bitchute_enabled(cls):
        """Check if upload to BitChute is enabled."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return bool(
            settings.get("upload_to_bitchute_enabled", False) if settings else False
        )

    @classmethod
    async def upload_to_odysee_enabled(cls):
        """Check if upload to Odysee is enabled."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return bool(
            settings.get("upload_to_odysee_enabled", False) if settings else False
        )

    @classmethod
    async def get_maximum_threads(cls):
        """Get maximum threads setting."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return 1
        db = await cls._get_db()
        settings = await db.get_settings(instance_name)
        return settings.get("maximum_threads", 1) if settings else 1
