import os
import traceback
import json
from configparser import ConfigParser, NoSectionError, NoOptionError


class BaseConfig:
    """Base configuration class with common functionality for all config parsers."""
    
    Root_Dir = None
    Data_Root_Dir = None
    Runtime_Profile_Dir = None
    Config_Dir = None
    parser = None
    parser_attr_name = "parser"  # Override this in subclasses if needed
    config_filename = None  # Override this in subclasses

    @classmethod
    def _init_parser(cls):
        """Initialize the configuration parser. Override in subclasses for custom behavior."""
        if getattr(cls, cls.parser_attr_name) is None:
            cls.Root_Dir = os.getcwd()
            cls.Runtime_Profile_Dir = os.path.join(cls.Root_Dir, "_DVR_Runtime")
            cls.Config_Dir = os.path.join(cls.Runtime_Profile_Dir, "_Config")
            config_path = os.path.join(cls.Config_Dir, cls.config_filename)

            # Disable interpolation to allow raw % in values
            parser = ConfigParser(interpolation=None)
            if not os.path.exists(config_path):
                # Create an empty config file if it does not exist
                os.makedirs(cls.Config_Dir, exist_ok=True)
                with open(config_path, "w") as f:
                    f.write("")
            parser.read(config_path)
            setattr(cls, cls.parser_attr_name, parser)

    @classmethod
    def get_value(cls, section, key):
        """Get a value from the configuration."""
        cls._init_parser()
        parser = getattr(cls, cls.parser_attr_name)
        if parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        try:
            return parser.get(section, key)
        except (NoSectionError, NoOptionError) as e:
            # Use print instead of log_core to avoid circular import
            print(f"Config error: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def set_value(cls, section, key, value):
        """Set a value in the config file and save it."""
        cls._init_parser()
        parser = getattr(cls, cls.parser_attr_name)
        if parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, key, value)
        config_path = os.path.join(cls.Config_Dir, cls.config_filename)
        with open(config_path, "w") as cfg:
            parser.write(cfg)

    @staticmethod
    def parse_string_list(str_list):
        """Convert a string representation of a Python list to an actual list."""
        try:
            return json.loads(str_list)
        except Exception as e:
            raise RuntimeError(f"Failed to parse string list:  {e}\n{traceback.format_exc()}")
