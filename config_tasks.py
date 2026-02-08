import os
import re
import traceback
import json
from configparser import ConfigParser, NoSectionError, NoOptionError


class DVR_Tasks:
    ProjRoot_Dir = os.path.dirname(os.path.abspath(__file__))
    Config_Dir = os.path.join(ProjRoot_Dir,"_Config")

    tasks_parser = None

    @classmethod
    def _init_settings_parser(cls):
        if cls.tasks_parser is None:
            settings_config_path = os.path.join(cls.Config_Dir, "dvr_tasks.cfg")
            # Disable interpolation to allow raw % in values
            cls.tasks_parser = ConfigParser(interpolation=None)
            if not os.path.exists(settings_config_path):
                # Create an empty config file if it does not exist
                with open(settings_config_path, "w") as f:
                    f.write("")
            cls.tasks_parser.read(settings_config_path)

    @classmethod
    def get_value(cls, section, key):
        cls._init_settings_parser()
        if cls.tasks_parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        try:
            return cls.tasks_parser.get(section, key)
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
        if cls.tasks_parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        if not cls.tasks_parser.has_section(section):
            cls.tasks_parser.add_section(section)
        cls.tasks_parser.set(section, key, value)
        config_path = os.path.join(cls.Config_Dir, "dvr_tasks.cfg")
        with open(config_path, "w") as cfg:
            cls.tasks_parser.write(cfg)

    @staticmethod
    def parse_string_list(str_list):
        """Convert a string representation of a Python list to an actual list."""
        try:
            return json.loads(str_list)
        except Exception as e:
            raise RuntimeError(f"Failed to parse string list:  {e}\n{traceback.format_exc()}")

    # Strings
    @classmethod
    def get_container_maintenance_inf_loop(cls):
        return cls.get_value("Tasks", "container_maintenance_inf_loop").lower()

    @classmethod
    def get_livestream_download(cls):
        return cls.get_value("Tasks", "livestream_download").lower()

    @classmethod
    def get_livestream_recovery_download(cls):
        return cls.get_value("Tasks", "livestream_recovery_download").lower()

    @classmethod
    def get_comments_download(cls):
        return cls.get_value("Tasks", "comments_download").lower()

    @classmethod
    def get_captions_download(cls):
        return cls.get_value("Tasks", "captions_download").lower()

    @classmethod
    def get_posted_videos_download(cls):
        return cls.get_value("Tasks", "posted_videos_download").lower()

    @classmethod
    def get_posted_notices_download(cls):
        return cls.get_value("Tasks", "posted_notices_download").lower()

    @classmethod
    def get_livestream_upload(cls):
        return cls.get_value("Tasks", "livestream_upload").lower()

    @classmethod
    def get_posted_videos_upload(cls):
        return cls.get_value("Tasks", "posted_videos_upload").lower()



