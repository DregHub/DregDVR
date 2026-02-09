import os
import re
import json
from config import BaseConfig


class Account_Config(BaseConfig):
    account_parser = None
    parser_attr_name = "account_parser"
    config_filename = "dvr_accounts.cfg"

    # Strings
    @classmethod
    def get_youtube_source(cls):
        cls._init_parser()
        return cls.get_value("YT_Sources", "source")

    @classmethod
    def get_youtube_handle(cls):
        cls._init_parser()
        # https://www.youtube.com/@ThoughtsOfPeterFaik
        youtube_source = cls.get_youtube_source().strip('"')
        youtube_channel = youtube_source[:-5] if youtube_source.lower().endswith("/live") else youtube_source
        return youtube_channel

    @classmethod
    def get_youtube_handle_name(cls):
        cls._init_parser()
        # @ThoughtsOfPeterFaik
        youtube_source = cls.get_youtube_source().strip('"')
        match = re.search(r"/@([^/]+)", youtube_source)
        if match:
            handle = match.group(1).strip("/")
            return f'@{handle}'
        return 'Unknown_Handle'

    @classmethod
    def get_caption_source(cls):
        cls._init_parser()
        return cls.get_value("YT_Sources", "caption_source")

    @classmethod
    def get_caption_handle(cls):
        cls._init_parser()
        # https://www.youtube.com/@ThoughtsOfPeterFaik
        youtube_source = cls.get_caption_source().strip('"')
        youtube_channel = youtube_source[:-5] if youtube_source.lower().endswith("/live") else youtube_source
        return youtube_channel

    @classmethod
    def get_caption_handle_name(cls):
        cls._init_parser()
        # @ThoughtsOfPeterFaik
        youtube_source = cls.get_caption_source().strip('"')
        match = re.search(r"/@([^/]+)", youtube_source)
        if match:
            handle = match.group(1).strip("/")
            return f'@{handle}'
        return 'Unknown_Handle'

    @classmethod
    def get_live_downloadprefix(cls):
        cls._init_parser()
        return cls.get_value("File_Naming", "live_downloadprefix").strip('"')

    @classmethod
    def get_posted_downloadprefix(cls):
        cls._init_parser()
        return cls.get_value("File_Naming", "posted_downloadprefix").strip('"')

    @classmethod
    def get_ia_itemid(cls):
        cls._init_parser()
        return cls.get_value("IA_Settings", "itemid").strip('"')

    @classmethod
    def get_ia_user_agent(cls):
        cls._init_parser()
        return cls.get_value("IA_Settings", "user_agent").strip('"')

    @classmethod
    def get_ia_email(cls):
        cls._init_parser()
        return cls.get_value("IA_Credentials", "email").strip('"')

    @classmethod
    def get_ia_password(cls):
        cls._init_parser()
        return cls.get_value("IA_Credentials", "password").strip('"')
