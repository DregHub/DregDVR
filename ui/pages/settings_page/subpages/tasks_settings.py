"""
Tasks Configuration Settings
Handles enabling/disabling background tasks per instance.
"""

import streamlit as st
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from db.dvr_db import DVRDB
from config.config_settings import DVR_Config
from ui.components import (
    enhanced_button,
    enhanced_checkbox,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_tasks_tab(instance: Optional[Dict[str, Any]]):
    """
    Tasks configuration tab.
    Handles enabling/disabling background tasks for an instance.

    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_inputs(), PageCSSLoader.load_for_buttons()
    )

    if not instance:
        enhanced_info(
            "No instance selected. Select or create an instance to configure."
        )
        return

    _show_tasks_configuration(instance)


def _show_tasks_configuration(instance: Dict[str, Any]):
    """
    Show tasks configuration form.

    Args:
        instance: Instance dict
    """
    instance_name = instance["instance_name"]
    db = UIDBHelpers.get_db()

    # Set the instance in DVR_Config for file path generation
    DVR_Config.set_instance(instance_name)

    st.markdown("### Task Configuration")
    st.markdown(f"Enable or disable background tasks for instance: **{instance_name}**")

    # Create tabs for different task categories
    task_tabs = st.tabs(["Download Tasks", "Processing Tasks", "Upload & Maintenance"])

    # ========== TAB 1: DOWNLOAD TASKS ==========
    with task_tabs[0]:
        _show_download_tasks(db, instance_name)

    # ========== TAB 2: PROCESSING TASKS ==========
    with task_tabs[1]:
        _show_processing_tasks(db, instance_name)

    # ========== TAB 3: UPLOAD & MAINTENANCE ==========
    with task_tabs[2]:
        _show_upload_maintenance_tasks(db, instance_name)


def _show_download_tasks(db: DVRDB, instance_name: str):
    """Show download-related tasks."""
    tasks = UIDBHelpers._run_async(db.get_tasks(instance_name)) or {}

    st.markdown("#### Download Tasks")
    st.markdown("Configure which download-related tasks are enabled.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Dependency Package Update
        dep_update = bool(tasks.get("dependency_package_update", True))
        dep_update_input = enhanced_checkbox(
            "Dependency Package Update",
            value=dep_update,
            key=f"dependency_package_update_{instance_name}",
            help="Check and update required Python packages",
        )

        # Livestream Download
        livestream_dl = bool(tasks.get("livestream_download", True))
        livestream_dl_input = enhanced_checkbox(
            "Livestream Download",
            value=livestream_dl,
            key=f"livestream_download_{instance_name}",
            help="Download active livestreams from the channel",
        )

        # Livestream Recovery Download
        livestream_recovery = bool(tasks.get("livestream_recovery_download", True))
        livestream_recovery_input = enhanced_checkbox(
            "Livestream Recovery Download",
            value=livestream_recovery,
            key=f"livestream_recovery_download_{instance_name}",
            help="Attempt to recover failed livestream downloads",
        )

    with col2:
        # Comments Download
        comments_dl = bool(tasks.get("comments_download", False))
        comments_dl_input = enhanced_checkbox(
            "Comments Download",
            value=comments_dl,
            key=f"comments_download_{instance_name}",
            help="Download comments from videos",
        )

        # Captions Download
        captions_dl = bool(tasks.get("captions_download", False))
        captions_dl_input = enhanced_checkbox(
            "Captions Download",
            value=captions_dl,
            key=f"captions_download_{instance_name}",
            help="Download captions/subtitles",
        )

        # Posted Videos Download
        posted_dl = bool(tasks.get("posted_videos_download", False))
        posted_dl_input = enhanced_checkbox(
            "Posted Videos Download",
            value=posted_dl,
            key=f"posted_videos_download_{instance_name}",
            help="Download previously posted videos",
        )

    # Posted Notices Download
    posted_notices = bool(tasks.get("posted_notices_download", False))
    posted_notices_input = enhanced_checkbox(
        "Posted Notices Download",
        value=posted_notices,
        key=f"posted_notices_download_{instance_name}",
        help="Download posted notices/community updates",
    )

    if enhanced_button(
        "Save Download Tasks", key=f"save_download_tasks_{instance_name}"
    ):
        try:
            db_write_indicator(
                "Saving download tasks configuration",
                UIDBHelpers._run_async,
                db.update_tasks(
                    instance_name,
                    dependency_package_update=dep_update_input,
                    livestream_download=livestream_dl_input,
                    livestream_recovery_download=livestream_recovery_input,
                    comments_download=comments_dl_input,
                    captions_download=captions_dl_input,
                    posted_videos_download=posted_dl_input,
                    posted_notices_download=posted_notices_input,
                ),
            )
            enhanced_success("Download tasks saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_processing_tasks(db: DVRDB, instance_name: str):
    """Show processing-related tasks."""
    tasks = UIDBHelpers._run_async(db.get_tasks(instance_name)) or {}

    st.markdown("#### Processing Tasks")
    st.markdown("Configure post-processing tasks.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Comments Republish
        comments_republish = bool(tasks.get("comments_republish", False))
        comments_republish_input = enhanced_checkbox(
            "Comments Republish",
            value=comments_republish,
            key=f"comments_republish_{instance_name}",
            help="Automatically republish or process downloaded comments",
        )

    with col2:
        # Captions Upload
        captions_upload = bool(tasks.get("captions_upload", False))
        captions_upload_input = enhanced_checkbox(
            "Captions Upload",
            value=captions_upload,
            key=f"captions_upload_{instance_name}",
            help="Automatically upload captions to platforms",
        )

    st.markdown("---")
    enhanced_info(
        "ℹ️ These tasks process already-downloaded content. Enable after configuring upload platforms."
    )

    if enhanced_button(
        "Save Processing Tasks", key=f"save_processing_tasks_{instance_name}"
    ):
        try:
            db_write_indicator(
                "Saving processing tasks configuration",
                UIDBHelpers._run_async,
                db.update_tasks(
                    instance_name,
                    comments_republish=comments_republish_input,
                    captions_upload=captions_upload_input,
                ),
            )
            enhanced_success("Processing tasks saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_upload_maintenance_tasks(db: DVRDB, instance_name: str):
    """Show upload and maintenance tasks."""
    tasks = UIDBHelpers._run_async(db.get_tasks(instance_name)) or {}

    st.markdown("#### Upload & Maintenance Tasks")
    st.markdown("Configure upload and playlist maintenance tasks.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Livestream Upload
        livestream_upload = bool(tasks.get("livestream_upload", False))
        livestream_upload_input = enhanced_checkbox(
            "Livestream Upload",
            value=livestream_upload,
            key=f"livestream_upload_{instance_name}",
            help="Automatically upload livestreams to configured platforms",
        )

        # Posted Videos Upload
        posted_upload = bool(tasks.get("posted_videos_upload", False))
        posted_upload_input = enhanced_checkbox(
            "Posted Videos Upload",
            value=posted_upload,
            key=f"posted_videos_upload_{instance_name}",
            help="Automatically upload posted videos to configured platforms",
        )

    with col2:
        # Update Playlist
        update_playlist = bool(tasks.get("update_playlist", False))
        update_playlist_input = enhanced_checkbox(
            "Update Playlist",
            value=update_playlist,
            key=f"update_playlist_{instance_name}",
            help="Automatically update and maintain playlists",
        )

    st.markdown("---")
    enhanced_info(
        "⚠️ Upload tasks require platform credentials to be configured in the Uploader settings."
    )

    if enhanced_button(
        "Save Upload & Maintenance Tasks",
        key=f"save_upload_maintenance_tasks_{instance_name}",
    ):
        try:
            db_write_indicator(
                "Saving upload & maintenance tasks configuration",
                UIDBHelpers._run_async,
                db.update_tasks(
                    instance_name,
                    livestream_upload=livestream_upload_input,
                    posted_videos_upload=posted_upload_input,
                    update_playlist=update_playlist_input,
                ),
            )
            enhanced_success("Upload & Maintenance tasks saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")
