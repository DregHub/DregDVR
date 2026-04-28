"""
Instance Subpage Modules
Organized subpage components for the instance manager.
"""

from .channel_config import show_dvr_channel_tab
from .create_instance import show_create_instance_form
from .playlist_viewer import show_playlist_tab
from .captions_viewer import show_captions_tab
from .comments_viewer import show_comments_tab
from .posts_viewer import show_posts_tab
from .logs_viewer import show_logs_tab
from .uploader import show_uploader_tab
from .downloader import show_downloader_tab

__all__ = [
    'show_dvr_channel_tab',
    'show_create_instance_form',
    'show_playlist_tab',
    'show_captions_tab',
    'show_comments_tab',
    'show_posts_tab',
    'show_logs_tab',
    'show_uploader_tab',
    'show_downloader_tab'
]
