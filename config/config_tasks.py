from .config import BaseConfig
import traceback
import logging

# Configure logger for this module
logger = logging.getLogger(__name__)


class DVR_Tasks(BaseConfig):
    tasks_parser = None
    parser_attr_name = "tasks_parser"
    config_filename = "dvr_tasks.cfg"
    # Strings
    @classmethod
    def get_container_maintenance_inf_loop(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "container_maintenance_inf_loop")
        except Exception as e:
            logger.error(
                f"Error in get_container_maintenance_inf_loop: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_livestream_download(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "livestream_download")
        except Exception as e:
            logger.error(f"Error in get_livestream_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_livestream_recovery_download(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "livestream_recovery_download")
        except Exception as e:
            logger.error(
                f"Error in get_livestream_recovery_download: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_comments_download(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "comments_download")
        except Exception as e:
            logger.error(f"Error in get_comments_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_comments_republish(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "comments_republish")
        except Exception as e:
            logger.error(f"Error in get_comments_republish: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_captions_download(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "captions_download")
        except Exception as e:
            logger.error(f"Error in get_captions_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_videos_download(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "posted_videos_download")
        except Exception as e:
            logger.error(f"Error in get_posted_videos_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_notices_download(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "posted_notices_download")
        except Exception as e:
            logger.error(
                f"Error in get_posted_notices_download: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_livestream_upload(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "livestream_upload")
        except Exception as e:
            logger.error(f"Error in get_livestream_upload: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_videos_upload(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "posted_videos_upload")
        except Exception as e:
            logger.error(f"Error in get_posted_videos_upload: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_captions_upload(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "captions_upload")
        except Exception as e:
            logger.error(f"Error in get_captions_upload: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_dependency_package_update(cls):
        try:
            cls._init_parser()
            return cls.get_value_as_bool("Tasks", "dependency_package_update")
        except Exception as e:
            logger.error(
                f"Error in get_dependency_package_update: {e}\n{traceback.format_exc()}"
            )
            raise
