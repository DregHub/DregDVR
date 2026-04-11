import re
import traceback
import logging
from .config import BaseConfig

# Configure logger for this module
logger = logging.getLogger(__name__)


class Account_Config(BaseConfig):
    account_parser = None
    parser_attr_name = "account_parser"
    config_filename = "dvr_accounts.cfg"

    # Strings
    @classmethod
    def get_youtube_source(cls):
        try:
            cls._init_parser()
            return cls.get_value("YT_Sources", "source").strip('"')
        except Exception as e:
            logger.error(f"Error in get_youtube_source: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def build_youtube_url(cls, channel_name: str, add_live: bool = False) -> str:
        """
        Build a full YouTube URL from a channel name.
        Handles both @handle format and full URLs.
        
        Args:
            channel_name: Channel name like "@handle" or "https://www.youtube.com/@handle"
            add_live: Whether to append "/live" to the URL
        
        Returns:
            Full YouTube URL
        """
        try:
            channel_name = channel_name.strip('"').strip()
            
            # If already a full URL, return as-is (with optional /live)
            if channel_name.startswith("http://") or channel_name.startswith("https://"):
                url = channel_name.rstrip("/")
                return f"{url}/live" if add_live and not url.lower().endswith("/live") else url
            
            # Otherwise build URL from channel name
            handle = channel_name.lstrip("@").strip()
            url = f"https://www.youtube.com/@{handle}"
            return f"{url}/live" if add_live else url
        except Exception as e:
            logger.error(f"Error in build_youtube_url: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def extract_channel_handle(cls, channel_name: str) -> str:
        """
        Extract the @handle (with @) from a channel name or URL.
        
        Args:
            channel_name: Channel name like "@handle" or URL
        
        Returns:
            Channel handle like "@handle"
        """
        try:
            channel_name = channel_name.strip('"').strip()

            # If it's already a handle with @, return as-is
            if channel_name.startswith("@"):
                return channel_name

            # Extract from URL if needed
            if match := re.search(r"/@([^/]+)", channel_name):
                return f"@{match[1]}"

            return channel_name
        except Exception as e:
            logger.error(f"Error in extract_channel_handle: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_caption_source(cls):
        try:
            cls._init_parser()
            return cls.get_value("YT_Sources", "caption_source").strip('"')
        except Exception as e:
            logger.error(f"Error in get_caption_source: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_live_downloadprefix(cls):
        try:
            cls._init_parser()
            return cls.get_value("File_Naming", "live_downloadprefix").strip('"')
        except Exception as e:
            logger.error(f"Error in get_live_downloadprefix: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_downloadprefix(cls):
        try:
            cls._init_parser()
            return cls.get_value("File_Naming", "posted_downloadprefix").strip('"')
        except Exception as e:
            logger.error(f"Error in get_posted_downloadprefix: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_ia_itemid(cls):
        try:
            cls._init_parser()
            return cls.get_value("IA_Settings", "itemid").strip('"')
        except Exception as e:
            logger.error(f"Error in get_ia_itemid: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_ia_user_agent(cls):
        try:
            cls._init_parser()
            return cls.get_value("IA_Settings", "user_agent").strip('"')
        except Exception as e:
            logger.error(f"Error in get_ia_user_agent: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_ia_email(cls):
        try:
            cls._init_parser()
            return cls.get_value("IA_Credentials", "email").strip('"')
        except Exception as e:
            logger.error(f"Error in get_ia_email: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_ia_password(cls):
        try:
            cls._init_parser()
            return cls.get_value("IA_Credentials", "password").strip('"')
        except Exception as e:
            logger.error(f"Error in get_ia_password: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_github_token(cls):
        """Retrieve GitHub authentication token for caption uploads."""
        try:
            cls._init_parser()
            return cls.get_value("GitHub_Credentials", "token").strip('"')
        except Exception as e:
            logger.error(f"Error in get_github_token: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_github_repo_owner(cls):
        """Retrieve GitHub repository owner for caption uploads."""
        try:
            cls._init_parser()
            return cls.get_value("GitHub_Repo", "owner").strip('"')
        except Exception as e:
            logger.error(f"Error in get_github_repo_owner: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_github_repo_name(cls):
        """Retrieve GitHub repository name for caption uploads."""
        try:
            cls._init_parser()
            return cls.get_value("GitHub_Repo", "repo_name").strip('"')
        except Exception as e:
            logger.error(f"Error in get_github_repo_name: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_github_captions_path(cls):
        """Retrieve the GitHub repository path where captions should be uploaded."""
        try:
            cls._init_parser()
            return cls.get_value("GitHub_Repo", "captions_path").strip('"')
        except Exception as e:
            logger.error(f"Error in get_github_captions_path: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_rumble_email(cls):
        """Retrieve Rumble email for video uploads."""
        try:
            cls._init_parser()
            return cls.get_value("Rumble_Credentials", "email").strip('"')
        except Exception as e:
            logger.error(f"Error in get_rumble_email: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_rumble_password(cls):
        """Retrieve Rumble password for video uploads."""
        try:
            cls._init_parser()
            return cls.get_value("Rumble_Credentials", "password").strip('"')
        except Exception as e:
            logger.error(f"Error in get_rumble_password: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_rumble_primary_category(cls):
        """Retrieve Rumble primary category from config."""
        try:
            cls._init_parser()
            return cls.get_value("Rumble_Settings", "primary_category").strip('"')
        except Exception as e:
            logger.error(f"Error in get_rumble_primary_category: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_rumble_secondary_category(cls):
        """Retrieve Rumble secondary category from config."""
        try:
            cls._init_parser()
            return cls.get_value("Rumble_Settings", "secondary_category").strip('"')
        except Exception as e:
            logger.error(f"Error in get_rumble_secondary_category: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_bitchute_email(cls):
        """Retrieve BitChute email for video uploads."""
        try:
            cls._init_parser()
            return cls.get_value("BitChute_Credentials", "email").strip('"')
        except Exception as e:
            logger.error(f"Error in get_bitchute_email: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_bitchute_password(cls):
        """Retrieve BitChute password for video uploads."""
        try:
            cls._init_parser()
            return cls.get_value("BitChute_Credentials", "password").strip('"')
        except Exception as e:
            logger.error(f"Error in get_bitchute_password: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_odysee_email(cls):
        """Retrieve Odysee email for video uploads."""
        try:
            cls._init_parser()
            return cls.get_value("Odysee_Credentials", "email").strip('"')
        except Exception as e:
            logger.error(f"Error in get_odysee_email: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_odysee_password(cls):
        """Retrieve Odysee password for video uploads."""
        try:
            cls._init_parser()
            return cls.get_value("Odysee_Credentials", "password").strip('"')
        except Exception as e:
            logger.error(f"Error in get_odysee_password: {e}\n{traceback.format_exc()}")
            raise
