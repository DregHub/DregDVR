"""
DVR Channel Configuration Tab
Handles channel configuration for existing instances.
"""

import streamlit as st
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from ui.components import (
    combined_dropdown_input,
    enhanced_checkbox,
    enhanced_button,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_dvr_channel_tab(instance: Optional[Dict[str, Any]]):
    """
    DVR Channel configuration tab.
    Handles channel configuration for existing instances.

    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_combined_input(),
        PageCSSLoader.load_for_inputs(),
        PageCSSLoader.load_for_buttons(),
    )

    if not instance:
        enhanced_info(
            "No instance selected. Select or create an instance to configure."
        )
        return

    _show_channel_configuration(instance)


def _show_channel_configuration(instance: Dict[str, Any]):
    """
    Show channel configuration form for existing instance.

    Args:
        instance: Instance dict
    """
    instance_name = instance["instance_name"]

    # Initialize form state with original values from instance
    if f"dvr_channel_form_{instance_name}" not in st.session_state:
        original_channel_name = instance.get("channel_name") or ""
        original_source_platform = instance.get("source_platform", "YouTube.com/@")

        st.session_state[f"dvr_channel_form_{instance_name}"] = {
            # Original values for change detection
            "original_channel_name": original_channel_name,
            "original_source_platform": original_source_platform,
            # Current form values
            "channel_name": original_channel_name,
            "source_platform": original_source_platform,
            # Task/platform collections
            "download_tasks": {},
            "upload_tasks": {},
            "upload_platforms": {},
        }

        # Also initialize the text input session state with the database value
        input_key = f"channel_input_{instance_name}"
        if input_key not in st.session_state:
            st.session_state[input_key] = original_channel_name

    form_state = st.session_state[f"dvr_channel_form_{instance_name}"]

    # Platform dropdown and channel name input
    platforms = ["YouTube.com/@", "Twitch.com/@"]

    selected_platform, channel_input = combined_dropdown_input(
        dropdown_options=platforms,
        dropdown_key=f"platform_select_{instance_name}",
        input_key=f"channel_input_{instance_name}",
        dropdown_label="Platform",
        input_label="Channel",
        input_placeholder="Enter channel name",
        dropdown_value=form_state["source_platform"],
        input_value=form_state["channel_name"],
        dropdown_ratio=0.25,
        forbidden_chars="@",
    )

    # Validate: reject @ character
    if "@" in channel_input:
        enhanced_error("Channel name cannot contain @ symbol")
        channel_input = channel_input.replace("@", "")
    form_state["channel_name"] = channel_input
    form_state["source_platform"] = selected_platform

    # Get current tasks
    tasks_data = UIDBHelpers.get_tasks_for_instance(instance_name)

    # Task names
    download_task_names = [
        "playlist_update",
        "livestream_download",
        "livestream_recovery_download",
        "captions_download",
        "comments_download",
        "posted_videos_download",
        "posted_notices_download",
    ]

    upload_task_names = [
        "livestream_upload",
        "posted_videos_upload",
        "captions_upload",
        "comments_republish",
    ]

    # Map UI task names to database column names
    # Some UI task names map to different database columns
    task_db_mapping = {
        "livestream_download": "livestream_download",
        "livestream_recovery_download": "livestream_recovery_download",
        "captions_download": "captions_download",
        "comments_download": "comments_download",
        "posted_videos_download": "posted_videos_download",
        "posted_notices_download": "posted_notices_download",
        "playlist_update": "update_playlist",
        "livestream_upload": "livestream_upload",
        "posted_videos_upload": "posted_videos_upload",
        "captions_upload": "captions_upload",
        "comments_republish": "captions_upload",
    }

    # Available upload platforms (must match platform_mapping in UIDBHelpers.update_instance_upload_platforms)
    available_platforms = [
        "YouTube",
        "Odysee",
        "Rumble",
        "BitChute",
        "Internet Archive",
    ]

    # Pre-initialize all checkbox session_state keys before rendering widgets
    for task in download_task_names:
        key = f"download_{task}_{instance_name}"
        if key not in st.session_state:
            db_column = task_db_mapping.get(task, task)
            is_checked = bool(tasks_data and tasks_data.get(db_column, False))
            st.session_state[key] = is_checked

    for task in upload_task_names:
        key = f"upload_{task}_{instance_name}"
        if key not in st.session_state:
            db_column = task_db_mapping.get(task, task)
            is_checked = bool(tasks_data and tasks_data.get(db_column, False))
            st.session_state[key] = is_checked

    # Pre-initialize platform checkboxes
    uploaders_data = None
    if instance_name:
        uploaders_data = UIDBHelpers._run_async(
            UIDBHelpers.get_db().get_uploaders(instance_name)
        )
    platform_db_mapping = {
        "YouTube": "upload_to_youtube",
        "Internet Archive": "upload_to_ia",
        "Rumble": "upload_to_rumble",
        "BitChute": "upload_to_bitchute",
        "Odysee": "upload_to_odysee",
    }

    for platform in available_platforms:
        key = f"platform_{platform}_{instance_name}"
        if key not in st.session_state:
            db_column = platform_db_mapping.get(platform)
            is_checked = bool(
                uploaders_data and uploaders_data.get(db_column, False)
                if db_column
                else False
            )
            st.session_state[key] = is_checked

    # Create three-column layout for task groups and upload platforms
    col_download, col_upload, col_platforms = st.columns(3, gap="large")

    selected_download = []
    selected_upload = []
    selected_platforms = []

    # Download tasks (left column)
    with col_download:
        st.markdown("### 📥 Download Tasks")
        for task in download_task_names:
            display_name = task.replace("_", " ").title()

            enhanced_checkbox(
                label=display_name,
                key=f"download_{task}_{instance_name}",
                value=st.session_state.get(f"download_{task}_{instance_name}", False)
            )

    # Collect selected download tasks from session_state
    for task in download_task_names:
        if st.session_state.get(f"download_{task}_{instance_name}", False):
            selected_download.append(task)

    # Upload tasks (middle column)
    with col_upload:
        st.markdown("### 📤 Upload Tasks")
        for task in upload_task_names:
            display_name = task.replace("_", " ").title()

            enhanced_checkbox(
                label=display_name,
                key=f"upload_{task}_{instance_name}",
                value=st.session_state.get(f"upload_{task}_{instance_name}", False)
            )

    # Collect selected upload tasks from session_state
    for task in upload_task_names:
        if st.session_state.get(f"upload_{task}_{instance_name}", False):
            selected_upload.append(task)

    # Upload platforms (right column)
    with col_platforms:
        st.markdown("### 🌐 Upload Platforms")

        for platform in available_platforms:
            enhanced_checkbox(
                label=platform,
                key=f"platform_{platform}_{instance_name}",
                value=st.session_state.get(f"platform_{platform}_{instance_name}", False)
            )

    # Collect selected platforms from session_state
    for platform in available_platforms:
        if st.session_state.get(f"platform_{platform}_{instance_name}", False):
            selected_platforms.append(platform)

    form_state["download_tasks"] = selected_download
    form_state["upload_tasks"] = selected_upload
    form_state["upload_platforms"] = selected_platforms

    # Save/Cancel buttons
    st.divider()
    col1, col2, col3 = st.columns([2, 2, 2])

    save_enabled = bool(channel_input.strip())

    with col1:
        if enhanced_button(
            "💾 Save",
            disabled=not save_enabled,
            use_container_width=True,
            type="primary",
            key=f"save_channel_{instance_name}",
        ):
            if _save_dvr_channel_config(
                instance_name,
                form_state,
                channel_input,
                selected_platform,
                selected_download,
                selected_upload,
                selected_platforms,
            ):
                st.rerun()

    with col2:
        if enhanced_button(
            "❌ Cancel", use_container_width=True, key=f"cancel_channel_{instance_name}"
        ):
            # Reset form
            if f"dvr_channel_form_{instance_name}" in st.session_state:
                del st.session_state[f"dvr_channel_form_{instance_name}"]
            st.rerun()

    if not save_enabled:
        st.caption("💡 Enter a channel name to enable Save button")


def _save_dvr_channel_config(
    instance_name: str,
    form_state: Dict[str, Any],
    channel_name: str,
    source_platform: str,
    download_tasks: list,
    upload_tasks: list,
    upload_platforms: list,
) -> bool:
    """Save DVR channel configuration.

    Only updates database fields that have been modified from their original values.

    Args:
        instance_name: Instance name
        form_state: Current form state containing original values
        channel_name: Channel name to save
        source_platform: Source platform to save
        download_tasks: Selected download tasks
        upload_tasks: Selected upload tasks
        upload_platforms: Selected upload platforms

    Returns:
        True if successful
    """
    try:
        changes_made = []

        # Check if channel name was modified
        channel_name_changed = channel_name != form_state.get(
            "original_channel_name", ""
        )
        if channel_name_changed:
            if not db_write_indicator(
                "Updating channel name",
                UIDBHelpers.update_instance_channel_name,
                instance_name, f"@{channel_name}"
            ):
                enhanced_error("Failed to save channel name")
                return False
            changes_made.append(f"Channel name: @{channel_name}")

        # Check if source platform was modified
        platform_changed = source_platform != form_state.get(
            "original_source_platform", "YouTube.com/@"
        )
        if platform_changed:
            if not db_write_indicator(
                "Updating source platform",
                UIDBHelpers.update_instance_source_platform,
                instance_name, source_platform
            ):
                enhanced_error("Failed to save platform")
                return False
            changes_made.append(f"Platform: {source_platform}")

        # Build task updates dict using database column names
        # Map UI task names to database columns and set all to False first
        all_db_task_names = [
            "livestream_download",
            "livestream_recovery_download",
            "captions_download",
            "comments_download",
            "posted_videos_download",
            "posted_notices_download",
            "update_playlist",
            "livestream_upload",
            "posted_videos_upload",
            "captions_upload",
        ]

        task_updates = {task: False for task in all_db_task_names}

        # Map UI task names to database column names and set selected ones to True
        task_db_mapping = {
            "livestream_download": "livestream_download",
            "livestream_recovery_download": "livestream_recovery_download",
            "captions_download": "captions_download",
            "comments_download": "comments_download",
            "posted_videos_download": "posted_videos_download",
            "posted_notices_download": "posted_notices_download",
            "playlist_update": "update_playlist",
            "livestream_upload": "livestream_upload",
            "posted_videos_upload": "posted_videos_upload",
            "captions_upload": "captions_upload",
            "comments_republish": "captions_upload",
        }

        # Set selected tasks to True (using their database column names)
        selected_values = download_tasks + upload_tasks
        for task in selected_values:
            db_column = task_db_mapping.get(task, task)
            task_updates[db_column] = True

        if not db_write_indicator(
            "Updating task configuration",
            UIDBHelpers.update_instance_tasks,
            instance_name, task_updates
        ):
            enhanced_error("Failed to save tasks")
            return False

        # Count enabled tasks for notification
        enabled_tasks_count = len(selected_values)
        if enabled_tasks_count > 0:
            changes_made.append(f"Tasks: {enabled_tasks_count} enabled")

        # Update upload platforms
        if not db_write_indicator(
            "Updating upload platforms",
            UIDBHelpers.update_instance_upload_platforms,
            instance_name, upload_platforms
        ):
            enhanced_error("Failed to save upload platforms")
            return False

        # Count enabled platforms for notification
        enabled_platforms_count = len(upload_platforms)
        if enabled_platforms_count > 0:
            changes_made.append(f"Upload platforms: {enabled_platforms_count} enabled")

        # Provide detailed success notification
        if changes_made:
            enhanced_success("✅ Configuration saved successfully!")
            st.markdown("**Changes applied:**")
            for change in changes_made:
                st.markdown(f"  • {change}")
        else:
            enhanced_info("ℹ️ No changes were made to save")

        return True
    except Exception as e:
        enhanced_error(f"Error saving configuration: {str(e)}")
        return False
