"""
Settings subpages package
Exports all settings UI components for the settings page.
"""

from .global_settings import show_global_settings
from .instance_settings import show_instance_settings_tab
from .tasks_settings import show_tasks_tab
from .uploaders_settings import show_uploaders_tab

__all__ = [
    "show_global_settings",
    "show_instance_settings_tab",
    "show_tasks_tab",
    "show_uploaders_tab",
]
