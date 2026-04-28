"""
Uploaders Configuration Settings
Handles enabling/disabling upload platforms per instance.
"""

import streamlit as st
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from config.config_settings import DVR_Config
from ui.components import (
    enhanced_button,
    enhanced_checkbox,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    enhanced_warning,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_uploaders_tab(instance: Optional[Dict[str, Any]]):
    """
    Uploaders configuration tab.
    Handles enabling/disabling upload platforms for an instance.

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

    _show_uploaders_configuration(instance)


def _show_uploaders_configuration(instance: Dict[str, Any]):
    """
    Show uploaders configuration form.

    Args:
        instance: Instance dict
    """
    instance_name = instance["instance_name"]
    db = UIDBHelpers.get_db()

    # Set the instance in DVR_Config for file path generation
    DVR_Config.set_instance(instance_name)

    st.markdown("### Upload Platforms Configuration")
    st.markdown(
        f"Configure which upload platforms are enabled for instance: **{instance_name}**"
    )

    uploaders = UIDBHelpers._run_async(db.get_uploaders(instance_name)) or {}

    st.markdown("#### Enabled Platforms")
    st.markdown("Select which platforms you want to enable for uploading content.")

    # Create a grid layout for platform toggles
    col1, col2, col3 = st.columns(3, gap="medium")

    with col1:
        # YouTube
        youtube_enabled = bool(uploaders.get("upload_to_youtube", False))
        youtube_input = enhanced_checkbox(
            "🔴 YouTube",
            value=youtube_enabled,
            key=f"upload_to_youtube_{instance_name}",
            help="Upload videos to YouTube",
        )

        # Internet Archive
        ia_enabled = bool(uploaders.get("upload_to_ia", False))
        ia_input = enhanced_checkbox(
            "📚 Internet Archive",
            value=ia_enabled,
            key=f"upload_to_ia_{instance_name}",
            help="Upload videos to Internet Archive",
        )

        # Rumble
        rumble_enabled = bool(uploaders.get("upload_to_rumble", False))
        rumble_input = enhanced_checkbox(
            "🎥 Rumble",
            value=rumble_enabled,
            key=f"upload_to_rumble_{instance_name}",
            help="Upload videos to Rumble",
        )

    with col2:
        # BitChute
        bitchute_enabled = bool(uploaders.get("upload_to_bitchute", False))
        bitchute_input = enhanced_checkbox(
            "⚡ BitChute",
            value=bitchute_enabled,
            key=f"upload_to_bitchute_{instance_name}",
            help="Upload videos to BitChute",
        )

        # Odysee
        odysee_enabled = bool(uploaders.get("upload_to_odysee", False))
        odysee_input = enhanced_checkbox(
            "🎬 Odysee",
            value=odysee_enabled,
            key=f"upload_to_odysee_{instance_name}",
            help="Upload videos to Odysee (LBRY)",
        )

        # GitHub
        github_enabled = bool(uploaders.get("upload_to_github", False))
        github_input = enhanced_checkbox(
            "🐙 GitHub",
            value=github_enabled,
            key=f"upload_to_github_{instance_name}",
            help="Upload metadata/captions to GitHub",
        )

    with col3:
        st.markdown("**Platform Status**")

        enabled_platforms = []
        if youtube_input:
            enabled_platforms.append("YouTube")
        if ia_input:
            enabled_platforms.append("Internet Archive")
        if rumble_input:
            enabled_platforms.append("Rumble")
        if bitchute_input:
            enabled_platforms.append("BitChute")
        if odysee_input:
            enabled_platforms.append("Odysee")
        if github_input:
            enabled_platforms.append("GitHub")

        if enabled_platforms:
            st.success(f"✓ {len(enabled_platforms)} platform(s) enabled")
            for platform in enabled_platforms:
                st.caption(f"  • {platform}")
        else:
            st.warning("⚠️ No platforms enabled")
            st.caption("  • Enable at least one platform to upload")

    st.markdown("---")

    st.markdown("#### Important Notes")

    notes_col1, notes_col2 = st.columns(2)

    with notes_col1:
        enhanced_info(
            "📋 **Credentials Required**: Ensure you have configured credentials for "
            "each enabled platform in the Account settings before enabling uploads."
        )

    with notes_col2:
        enhanced_warning(
            "⚠️ **Task Configuration**: Enable the corresponding upload tasks in the "
            "Task Configuration tab to automatically upload to these platforms."
        )

    st.markdown("---")

    if enhanced_button(
        "Save Uploader Configuration",
        key=f"save_uploaders_{instance_name}",
        use_container_width=True,
    ):
        try:
            db_write_indicator(
                "Saving uploader configuration",
                UIDBHelpers._run_async,
                db.update_uploaders(
                    instance_name,
                    upload_to_youtube=youtube_input,
                    upload_to_ia=ia_input,
                    upload_to_rumble=rumble_input,
                    upload_to_bitchute=bitchute_input,
                    upload_to_odysee=odysee_input,
                    upload_to_github=github_input,
                ),
            )
            enhanced_success("Uploader configuration saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")
