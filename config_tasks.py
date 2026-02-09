import os
import re
import json
from config import BaseConfig


class DVR_Tasks(BaseConfig):
    tasks_parser = None
    parser_attr_name = "tasks_parser"
    config_filename = "dvr_tasks.cfg"

    # Strings
    @classmethod
    def get_container_maintenance_inf_loop(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "container_maintenance_inf_loop").lower()

    @classmethod
    def get_livestream_download(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "livestream_download").lower()

    @classmethod
    def get_livestream_recovery_download(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "livestream_recovery_download").lower()

    @classmethod
    def get_comments_download(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "comments_download").lower()

    @classmethod
    def get_captions_download(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "captions_download").lower()

    @classmethod
    def get_posted_videos_download(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "posted_videos_download").lower()

    @classmethod
    def get_posted_notices_download(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "posted_notices_download").lower()

    @classmethod
    def get_livestream_upload(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "livestream_upload").lower()

    @classmethod
    def get_posted_videos_upload(cls):
        cls._init_parser()
        return cls.get_value("Tasks", "posted_videos_upload").lower()



