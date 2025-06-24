import os
import traceback
from configparser import ConfigParser, NoSectionError, NoOptionError


class Config:
    ProjRoot_Dir = os.path.dirname(os.path.abspath(__file__))

    _parser = None

    @classmethod
    def _init_parser(cls):
        if cls._parser is None:
            config_path = os.path.join(cls.ProjRoot_Dir, "config.cfg")
            # Disable interpolation to allow raw % in values
            cls._parser = ConfigParser(interpolation=None)
            if not os.path.exists(config_path):
                # Create an empty config file if it does not exist
                with open(config_path, "w") as f:
                    f.write("")
            cls._parser.read(config_path)

    @classmethod
    def get_value(cls, section, key):
        cls._init_parser()
        if cls._parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        try:
            return cls._parser.get(section, key)
        except (NoSectionError, NoOptionError) as e:
            # Use print instead of log_core to avoid circular import
            print(f"Config error: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def set_value(cls, section, key, value):
        """
        Set a value in the config file and save it.
        """
        cls._init_parser()
        if cls._parser is None:
            raise RuntimeError("Config parser is not initialized. Check if the config file exists and is readable.")
        if not cls._parser.has_section(section):
            cls._parser.add_section(section)
        cls._parser.set(section, key, value)
        config_path = os.path.join(cls.ProjRoot_Dir, "config.cfg")
        with open(config_path, "w") as cfg:
            cls._parser.write(cfg)
