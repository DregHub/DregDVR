import os
import traceback
import json
import logging
from configparser import ConfigParser, NoSectionError, NoOptionError

# Configure logger for this module
logger = logging.getLogger(__name__)


class ReadOnlyConfigParser(ConfigParser):
    """A ConfigParser that prevents any write operations to prevent file corruption."""

    def write(self, fp, space_around_delimiters=True):
        """Prevent writing to file."""
        raise RuntimeError(
            "Writing to config files is disabled to prevent file corruption. "
            "Config files are read-only. Use environment variables or other methods to modify runtime behavior."
        )

    def add_section(self, section):
        """Prevent adding sections to prevent in-memory modifications."""
        raise RuntimeError(
            "Config modifications are disabled. Config files are read-only."
        )

    def remove_section(self, section):
        """Prevent removing sections."""
        raise RuntimeError(
            "Config modifications are disabled. Config files are read-only."
        )

    def set(self, section, option, value):
        """Prevent setting values to prevent in-memory modifications."""
        raise RuntimeError(
            "Config modifications are disabled. Config files are read-only."
        )

    def remove_option(self, section, option):
        """Prevent removing options."""
        raise RuntimeError(
            "Config modifications are disabled. Config files are read-only."
        )


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
        try:
            if getattr(cls, cls.parser_attr_name) is None:
                cls.Root_Dir = os.getcwd()
                cls.Runtime_Profile_Dir = os.path.join(cls.Root_Dir, "_DVR_Runtime")
                cls.Config_Dir = os.path.join(cls.Runtime_Profile_Dir, "_Config")
                config_path = os.path.join(cls.Config_Dir, cls.config_filename)

                # Disable interpolation to allow raw % in values
                # Use ReadOnlyConfigParser to prevent accidental writes
                parser = ReadOnlyConfigParser(interpolation=None)
                if not os.path.exists(config_path):
                    # Create an empty config file if it does not exist
                    os.makedirs(cls.Config_Dir, exist_ok=True)
                    with open(config_path, "w") as f:
                        f.write("")
                parser.read(config_path)
                setattr(cls, cls.parser_attr_name, parser)
        except Exception as e:
            logger.error(f"Config initialization error: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_value(cls, section, key):
        """Get a value from the configuration."""
        cls._init_parser()
        parser = getattr(cls, cls.parser_attr_name)
        if parser is None:
            raise RuntimeError(
                "Config parser is not initialized. Check if the config file exists and is readable."
            )
        try:
            value = parser.get(section, key)
            # Convert string representations of booleans to actual boolean values
            if isinstance(value, str):
                stripped_value = value.strip().lower()
                if stripped_value == "true":
                    return True
                elif stripped_value == "false":
                    return False
            return value
        except (NoSectionError, NoOptionError) as e:
            # Use logger instead of print to avoid circular import
            logger.error(f"Config error: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_value_as_bool(cls, section, key):
        """Get a value from the configuration and ensure it returns a boolean."""
        value = cls.get_value(section, key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            stripped_value = value.strip().lower()
            if stripped_value == "true":
                return True
            elif stripped_value == "false":
                return False
            raise ValueError(f"Cannot convert '{value}' to boolean for {section}.{key}")
        raise ValueError(
            f"Expected boolean or string value for {section}.{key}, got {type(value).__name__}"
        )

    @staticmethod
    def parse_string_list(str_list):
        """Convert a string representation of a Python list to an actual list."""
        try:
            return json.loads(str_list)
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse string list:  {e}\n{traceback.format_exc()}"
            ) from e
