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
    def get_youtube_handle(cls):
        try:
            cls._init_parser()
            # https://www.youtube.com/@ThoughtsOfPeterFaik
            youtube_source = cls.get_youtube_source().strip('"')
            return (
                youtube_source[:-5]
                if youtube_source.lower().endswith("/live")
                else youtube_source
            )
        except Exception as e:
            logger.error(f"Error in get_youtube_handle: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_youtube_handle_name(cls):
        try:
            cls._init_parser()
            # @ThoughtsOfPeterFaik
            youtube_source = cls.get_youtube_source().strip('"')
            if match := re.search(r"/@([^/]+)", youtube_source):
                handle = match[1].strip("/")
                return f"@{handle}"
            return "Unknown_Handle"
        except Exception as e:
            logger.error(f"Error in get_youtube_handle_name: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_caption_source(cls):
        try:
            cls._init_parser()
            return cls.get_value("YT_Sources", "caption_source")
        except Exception as e:
            logger.error(f"Error in get_caption_source: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_caption_handle(cls):
        try:
            cls._init_parser()
            # https://www.youtube.com/@ThoughtsOfPeterFaik
            youtube_source = cls.get_caption_source().strip('"')
            return (
                youtube_source[:-5]
                if youtube_source.lower().endswith("/live")
                else youtube_source
            )
        except Exception as e:
            logger.error(f"Error in get_caption_handle: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_caption_handle_name(cls):
        try:
            cls._init_parser()
            # @ThoughtsOfPeterFaik
            youtube_source = cls.get_caption_source().strip('"')
            if match := re.search(r"/@([^/]+)", youtube_source):
                handle = match[1].strip("/")
                return f"@{handle}"
            return "Unknown_Handle"
        except Exception as e:
            logger.error(f"Error in get_caption_handle_name: {e}\n{traceback.format_exc()}")
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
