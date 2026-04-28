"""
Instance-Scoped Settings Configuration
Handles per-instance DVR settings for upload and authentication.
"""

import streamlit as st
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from db.dvr_db import DVRDB
from config.config_settings import DVR_Config
from ui.components import (
    enhanced_button,
    enhanced_selectbox,
    enhanced_text_input,
    enhanced_text_area,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_instance_settings_tab(instance: Optional[Dict[str, Any]]):
    """
    Instance settings configuration tab.
    Handles instance-scoped settings like upload visibility and authentication.

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

    _show_instance_configuration(instance)


def _show_instance_configuration(instance: Dict[str, Any]):
    """
    Show instance configuration form.

    Args:
        instance: Instance dict
    """
    instance_name = instance["instance_name"]
    db = UIDBHelpers.get_db()

    # Set the instance in DVR_Config for file path generation
    DVR_Config.set_instance(instance_name)

    st.markdown("### Instance Settings")
    st.markdown(f"Configure settings for instance: **{instance_name}**")

    # Create tabs for different configuration sections
    config_tabs = st.tabs(
        ["Upload Settings", "YouTube Authentication", "Advanced Options"]
    )

    # ========== TAB 1: UPLOAD SETTINGS ==========
    with config_tabs[0]:
        _show_upload_settings(db, instance_name)

    # ========== TAB 2: YOUTUBE AUTHENTICATION ==========
    with config_tabs[1]:
        _show_youtube_authentication(db, instance_name)

    # ========== TAB 3: ADVANCED OPTIONS ==========
    with config_tabs[2]:
        _show_advanced_options(db, instance_name)


def _show_upload_settings(db: DVRDB, instance_name: str):
    """Show upload-related instance settings."""
    settings = UIDBHelpers._run_async(db.get_instance_settings(instance_name)) or {}

    st.markdown("#### Upload Configuration")
    st.markdown("Configure default upload visibility and category.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Upload Visibility
        visibility = settings.get("upload_visibility", "Public")
        visibility_options = ["Public", "Unlisted", "Private"]

        visibility_input = enhanced_selectbox(
            "Upload Visibility",
            options=visibility_options,
            index=(
                visibility_options.index(visibility)
                if visibility in visibility_options
                else 0
            ),
            key=f"upload_visibility_{instance_name}",
            help="Default visibility for uploaded videos",
        )

    with col2:
        # Upload Category (YouTube standard categories)
        category = settings.get("upload_category", "22")

        # YouTube category IDs and names
        category_options = {
            "1": "Film & Animation",
            "2": "Autos & Vehicles",
            "10": "Music",
            "15": "Pets & Animals",
            "17": "Sports",
            "18": "Short Movies",
            "19": "Travel & Events",
            "20": "Gaming",
            "21": "Videoblogging",
            "22": "People & Blogs",
            "23": "Comedy",
            "24": "Entertainment",
            "25": "News & Politics",
            "26": "Howto & Style",
            "27": "Education",
            "28": "Science & Technology",
            "30": "Movies",
            "31": "Anime/Animation",
            "32": "Action/Adventure",
            "33": "Classics",
            "34": "Comedies",
            "35": "Documentaries",
            "36": "Dramas",
            "37": "Family",
            "38": "Foreign",
            "39": "Horror",
            "40": "Sci-Fi/Fantasy",
            "41": "Thrillers",
            "42": "Shorts",
            "43": "Shows",
            "44": "Trailers",
        }

        category_display = [f"{k}: {v}" for k, v in category_options.items()]
        category_index = 0

        for idx, (cat_id, _) in enumerate(category_options.items()):
            if cat_id == category:
                category_index = idx
                break

        category_selected = enhanced_selectbox(
            "Default Upload Category",
            options=category_display,
            index=category_index,
            key=f"upload_category_{instance_name}",
            help="YouTube category for uploaded videos",
        )

        # Extract category ID from selection
        category_id = category_selected.split(":")[0]

    if enhanced_button(
        "Save Upload Settings", key=f"save_upload_settings_{instance_name}"
    ):
        try:
            db_write_indicator(
                "Saving upload settings",
                UIDBHelpers._run_async,
                db.update_instance_settings(
                    instance_name,
                    upload_visibility=visibility_input,
                    upload_category=category_id,
                ),
            )
            enhanced_success("Upload settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_youtube_authentication(db: DVRDB, instance_name: str):
    """Show YouTube authentication settings."""
    st.markdown("#### YouTube Authentication")
    st.markdown("Configure YouTube API credentials for this instance.")

    settings = UIDBHelpers._run_async(db.get_instance_settings(instance_name)) or {}

    # Client Secret
    client_secret = settings.get("yt_client_secret_content", "")

    st.markdown("**Client Secret JSON**")
    client_secret_input = enhanced_text_area(
        "Client Secret",
        value=client_secret,
        height=150,
        key=f"yt_client_secret_{instance_name}",
        help="Paste your YouTube API client_secret.json content here",
    )

    col1, col2 = st.columns(2)

    with col1:
        if enhanced_button(
            "Save Client Secret", key=f"save_client_secret_{instance_name}"
        ):
            try:
                db_write_indicator(
                    "Saving client secret",
                    UIDBHelpers._run_async,
                    db.update_instance_settings(
                        instance_name, yt_client_secret_content=client_secret_input
                    ),
                )
                enhanced_success("Client Secret saved successfully!")
                st.rerun()
            except Exception as e:
                enhanced_error(f"Failed to save: {e}")

    with col2:
        status = "✓ Configured" if client_secret else "✗ Not configured"
        if client_secret:
            enhanced_success(f"Status: {status}")
        else:
            enhanced_info(f"Status: {status}")

    st.markdown("---")

    # OAuth2 Credentials
    oauth2 = settings.get("yt_oauth2_content", "")

    st.markdown("**OAuth2 Credentials**")
    oauth2_input = enhanced_text_area(
        "OAuth2",
        value=oauth2,
        height=150,
        key=f"yt_oauth2_{instance_name}",
        help="Paste your YouTube OAuth2 credentials here",
    )

    col3, col4 = st.columns(2)

    with col3:
        if enhanced_button(
            "Save OAuth2 Credentials", key=f"save_oauth2_{instance_name}"
        ):
            try:
                db_write_indicator(
                    "Saving OAuth2 credentials",
                    UIDBHelpers._run_async,
                    db.update_instance_settings(
                        instance_name, yt_oauth2_content=oauth2_input
                    ),
                )
                enhanced_success("OAuth2 credentials saved successfully!")
                st.rerun()
            except Exception as e:
                enhanced_error(f"Failed to save: {e}")

    with col4:
        status = "✓ Configured" if oauth2 else "✗ Not configured"
        if oauth2:
            enhanced_success(f"Status: {status}")
        else:
            enhanced_info(f"Status: {status}")


def _show_advanced_options(db: DVRDB, instance_name: str):
    """Show advanced instance settings."""
    st.markdown("#### Advanced Options")
    st.markdown("Configure additional instance-specific options.")

    settings = UIDBHelpers._run_async(db.get_instance_settings(instance_name)) or {}

    enhanced_info(
        "ℹ️ Advanced settings are reserved for future enhancements. Check back soon!"
    )

    # Placeholder for future advanced settings
    st.markdown("**Planned Advanced Features:**")
    st.markdown("- Custom metadata templates")
    st.markdown("- Upload scheduling")
    st.markdown("- Automatic retry policies")
    st.markdown("- Custom filename patterns")
