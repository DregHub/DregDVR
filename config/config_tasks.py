from .config import BaseConfig
import traceback


class DVR_Tasks(BaseConfig):
    tasks_parser = None
    parser_attr_name = "tasks_parser"
    config_filename = "dvr_tasks.cfg"

    @staticmethod
    def _boolean_to_string(value):
        """Convert boolean values to lowercase string representation, or return original value if not boolean."""
        if isinstance(value, bool):
            return str(value).lower()
        return value.lower() if isinstance(value, str) else value

    # Strings
    @classmethod
    def get_container_maintenance_inf_loop(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "container_maintenance_inf_loop")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(
                f"Error in get_container_maintenance_inf_loop: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_livestream_download(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "livestream_download")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_livestream_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_livestream_recovery_download(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "livestream_recovery_download")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(
                f"Error in get_livestream_recovery_download: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_comments_download(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "comments_download")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_comments_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_comments_republish(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "comments_republish")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_comments_republish: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_captions_download(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "captions_download")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_captions_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_videos_download(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "posted_videos_download")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_posted_videos_download: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_notices_download(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "posted_notices_download")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(
                f"Error in get_posted_notices_download: {e}\n{traceback.format_exc()}"
            )
            raise

    @classmethod
    def get_livestream_upload(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "livestream_upload")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_livestream_upload: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_posted_videos_upload(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "posted_videos_upload")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(f"Error in get_posted_videos_upload: {e}\n{traceback.format_exc()}")
            raise

    @classmethod
    def get_dependency_package_update(cls):
        try:
            cls._init_parser()
            value = cls.get_value("Tasks", "dependency_package_update")
            return cls._boolean_to_string(value)
        except Exception as e:
            print(
                f"Error in get_dependency_package_update: {e}\n{traceback.format_exc()}"
            )
            raise
