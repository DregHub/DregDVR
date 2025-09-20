import os
import re
import traceback
import json
from configparser import ConfigParser, NoSectionError, NoOptionError


class Account_Config:
    ProjRoot_Dir = os.path.dirname(os.path.abspath(__file__))
    Config_Dir = os.path.join(ProjRoot_Dir, "_Config")

    account_parser = None

    @classmethod
    def _init_account_parser(cls):
        if cls.account_parser is None:
            account_config_path = os.path.join(cls.Config_Dir, "dvr_accounts.cfg")
            # Disable interpolation to allow raw % in values
            cls.account_parser = ConfigParser(interpolation=None)
            if not os.path.exists(account_config_path):
                # Create an empty config file if it does not exist
                with open(account_config_path, "w") as f:
                    f.write("")
            cls.account_parser.read(account_config_path)
    dvr_parser = None

    @classmethod
    def get_value(cls, section, key):
        cls._init_account_parser()
        if cls.account_parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        try:
            return cls.account_parser.get(section, key)
        except (NoSectionError, NoOptionError) as e:
            # Use print instead of log_core to avoid circular import
            print(f"Config error: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def set_value(cls, section, key, value):
        """
        Set a value in the config file and save it.
        """
        cls._init_account_parser()
        if cls.account_parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        if not cls.account_parser.has_section(section):
            cls.account_parser.add_section(section)
        cls.account_parser.set(section, key, value)
        config_path = os.path.join(cls.Config_Dir, "dvr_accounts.cfg")
        with open(config_path, "w") as cfg:
            cls.account_parser.write(cfg)

    @staticmethod
    def parse_string_list(str_list):
        """Convert a string representation of a Python list to an actual list."""
        try:
            return json.loads(str_list)
        except Exception as e:
            raise RuntimeError(f"Failed to parse string list:  {e}\n{traceback.format_exc()}")

    # Strings
    @classmethod
    def get_youtube_source(cls):
        return cls.get_value("YT_Sources", "source")

    @classmethod
    def get_youtube_handle(cls):
        # https://www.youtube.com/@ThoughtsOfPeterFaik
        youtube_source = cls.get_youtube_source().strip('"')
        youtube_channel = youtube_source[:-5] if youtube_source.lower().endswith("/live") else youtube_source
        return youtube_channel

    @classmethod
    def get_youtube_handle_name(cls):
        # @ThoughtsOfPeterFaik
        youtube_source = cls.get_youtube_source().strip('"')
        match = re.search(r"/@([^/]+)", youtube_source)
        if match:
            handle = match.group(1).strip("/")
            return f'@{handle}'
        return 'Unknown_Handle'

    @classmethod
    def get_caption_source(cls):
        return cls.get_value("YT_Sources", "caption_source")

    @classmethod
    def get_caption_handle(cls):
        # https://www.youtube.com/@ThoughtsOfPeterFaik
        youtube_source = cls.get_caption_source().strip('"')
        youtube_channel = youtube_source[:-5] if youtube_source.lower().endswith("/live") else youtube_source
        return youtube_channel

    @classmethod
    def get_caption_handle_name(cls):
        # @ThoughtsOfPeterFaik
        youtube_source = cls.get_caption_source().strip('"')
        match = re.search(r"/@([^/]+)", youtube_source)
        if match:
            handle = match.group(1).strip("/")
            return f'@{handle}'
        return 'Unknown_Handle'

    @classmethod
    def get_live_downloadprefix(cls):
        return cls.get_value("File_Naming", "live_downloadprefix")

    @classmethod
    def get_posted_downloadprefix(cls):
        return cls.get_value("File_Naming", "posted_downloadprefix")

    @classmethod
    def get_ia_itemid(cls):
        return cls.get_value("IA_Settings", "itemid")

    @classmethod
    def get_ia_email(cls):
        return cls.get_value("IA_Credentials", "email")

    @classmethod
    def get_ia_password(cls):
        return cls.get_value("IA_Credentials", "password")
