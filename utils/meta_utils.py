import os
import xml.etree.ElementTree as ET
import traceback
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config


class MetaDataManager:

    def __init__(self):
        pass

    @classmethod
    def init_reader(cls):
        try:
            MetaData_Dir = DVR_Config.get_meta_data_dir()
            return os.path.join(MetaData_Dir, "Default.xml")
        except Exception as e:
            LogManager.log_core(
                f"Failed to read value from meta:  {e}\n{traceback.format_exc()}"
            )
            return None

    @classmethod
    def get_thumbnail_path(cls):
        """
        Get the full path to Thumbnail.png in the metadata directory.
        
        Returns:
            str: Full path to Thumbnail.png, or None if metadata directory is not found
        """
        try:
            MetaData_Dir = DVR_Config.get_meta_data_dir()
            thumbnail_path = os.path.join(MetaData_Dir, "Thumbnail.png")
            return thumbnail_path
        except Exception as e:
            LogManager.log_core(
                f"Failed to get thumbnail path:  {e}\n{traceback.format_exc()}"
            )
            return None

    @classmethod
    def read_value(cls, xpath, logfile):
        try:
            meta_path = cls.init_reader()
            if not meta_path or not os.path.exists(meta_path):
                LogManager.log_message(
                    f"Meta file not found at path: {meta_path}", logfile
                )
                return None
            tree = ET.parse(meta_path)
            root = tree.getroot()
            value = root.find(xpath)
            return value.text if value is not None else None
        except Exception as e:
            LogManager.log_message(
                f"Failed to read value from meta:  {e}\n{traceback.format_exc()}",
                logfile,
            )
            return None

    @classmethod
    def write_value(cls, xpath, value, logfile):
        try:
            meta_path = cls.init_reader()
            if not meta_path or not os.path.exists(meta_path):
                LogManager.log_message(
                    f"Meta file not found at path: {meta_path}", logfile
                )
                return
            tree = ET.parse(meta_path)
            root = tree.getroot()
            element = root.find(xpath)
            if element is not None:
                element.text = value
                tree.write(meta_path)
            else:
                LogManager.log_message(
                    f"XPath '{xpath}' not found in the metadata.", logfile
                )
        except Exception as e:
            LogManager.log_message(
                f"Failed to write value to meta:  {e}\n{traceback.format_exc()}",
                logfile,
            )
