"""
Downloader Configuration Tab
Handles DLP settings and YouTube cookies configuration for instances.
"""

import streamlit as st
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from config.config_settings import DVR_Config
from db.dvr_db import DVRDB
from ui.components import (
    enhanced_button,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_downloader_tab(instance: Optional[Dict[str, Any]]):
    """
    Downloader configuration tab.
    Handles DLP settings and YouTube cookies configuration.

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

    _show_downloader_configuration(instance)


def _show_downloader_configuration(instance: Dict[str, Any]):
    """
    Show downloader configuration form.

    Args:
        instance: Instance dict
    """
    instance_name = instance["instance_name"]
    db = UIDBHelpers.get_db()

    # Set the instance in DVR_Config for file path generation
    DVR_Config.set_instance(instance_name)

    st.markdown("### Download Configuration")
    st.markdown("Configure yt-dlp download settings and YouTube authentication.")

    # Create tabs for different configuration sections
    config_tabs = st.tabs(["General", "YouTube Cookies", "Advanced"])

    # ========== TAB 1: GENERAL SETTINGS ==========
    with config_tabs[0]:
        _show_general_settings(db, instance_name)

    # ========== TAB 2: YOUTUBE COOKIES ==========
    with config_tabs[1]:
        _show_youtube_cookies(db)

    # ========== TAB 3: ADVANCED SETTINGS ==========
    with config_tabs[2]:
        _show_advanced_settings(db, instance_name)


def _show_general_settings(db: DVRDB, instance_name: str):
    """Show general DLP settings."""
    settings = UIDBHelpers._run_async(db.get_settings(instance_name)) or {}

    st.markdown("#### Core Download Settings")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Keep Fragments
        keep_fragments = bool(settings.get("dlp_keep_fragments_downloads", False))
        keep_fragments_input = st.checkbox(
            "Keep Download Fragments",
            value=keep_fragments,
            key=f"keep_fragments_{instance_name}",
            help="Keep temporary fragments after download completes (useful for recovery)",
        )

        # Verbose Mode
        verbose = bool(settings.get("dlp_verbose_downloads", True))
        verbose_input = st.checkbox(
            "Verbose Download Logging",
            value=verbose,
            key=f"verbose_{instance_name}",
            help="Enable detailed logging from yt-dlp",
        )

    with col2:
        # Max Download Retries
        max_retries = settings.get("dlp_max_download_retries", 10)
        max_retries_input = st.number_input(
            "Max Download Retries",
            min_value=0,
            max_value=100,
            value=max_retries,
            key=f"max_retries_{instance_name}",
            help="Maximum retries for failed downloads",
        )

        # Truncate Title Length
        truncate_length = settings.get("dlp_truncate_title_after_x_chars", 60)
        truncate_length_input = st.number_input(
            "Truncate Title Length",
            min_value=10,
            max_value=500,
            value=truncate_length,
            key=f"truncate_length_{instance_name}",
            help="Maximum characters in downloaded video filename",
        )

    if st.button("Save General Settings", key=f"save_general_{instance_name}"):
        try:
            db_write_indicator(
                "Saving general download settings",
                UIDBHelpers._run_async,
                db.update_settings(
                    instance_name,
                    dlp_keep_fragments_downloads=keep_fragments_input,
                    dlp_verbose_downloads=verbose_input,
                    dlp_max_download_retries=int(max_retries_input),
                    dlp_truncate_title_after_x_chars=int(truncate_length_input),
                ),
            )
            enhanced_success("General settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_youtube_cookies(db: DVRDB):
    """Show YouTube cookies configuration."""
    st.markdown("#### YouTube Authentication Cookies")
    st.markdown("Paste your exported YouTube cookies (text format from yt-dlp).")

    cookies_content = UIDBHelpers._run_async(db.get_yt_cookies_content()) or ""

    cookies_input = st.text_area(
        "Cookies File Content",
        value=cookies_content,
        height=250,
        key=f"cookies.txt",
        help="Export cookies using: yt-dlp --cookies-from-browser firefox --write-cookies cookies.txt https://youtube.com",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Save Cookies", key=f"save_cookies"):
            try:
                db_write_indicator(
                    "Saving YouTube cookies",
                    UIDBHelpers._run_async,
                    db.set_yt_cookies_content(cookies_input),
                )
                enhanced_success("Cookies saved successfully!")
                st.rerun()
            except Exception as e:
                enhanced_error(f"Failed to save: {e}")

    with col2:
        status = "✓ Configured" if cookies_content else "✗ Not configured"
        if cookies_content:
            enhanced_success(f"Status: {status}")
        else:
            enhanced_info(f"Status: {status}")


def _show_advanced_settings(db: DVRDB, instance_name: str):
    """Show advanced DLP settings."""
    settings = UIDBHelpers._run_async(db.get_settings(instance_name)) or {}

    st.markdown("#### Advanced Download Settings")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # JavaScript Runtime
        js_runtime = settings.get("dlp_js_runtime", "quickjs")
        js_runtime_options = ["quickjs", "jsc", "nodejs"]
        if js_runtime not in js_runtime_options:
            js_runtime_options.append(js_runtime)

        js_runtime_input = st.selectbox(
            "JavaScript Runtime",
            options=js_runtime_options,
            index=js_runtime_options.index(js_runtime),
            key=f"js_runtime_{instance_name}",
            help="JavaScript engine for downloading: quickjs (fastest), jsc, or nodejs",
        )

        st.markdown("**Info**: QuickJS is recommended for best performance")

    with col2:
        # Max Fragment Retries
        max_fragment_retries = settings.get("dlp_max_fragment_retries", 10)
        max_fragment_retries_input = st.number_input(
            "Max Fragment Retries",
            min_value=0,
            max_value=100,
            value=max_fragment_retries,
            key=f"max_fragment_retries_{instance_name}",
            help="Maximum retries for failed fragment downloads",
        )

    if st.button("Save Advanced Settings", key=f"save_advanced_{instance_name}"):
        try:
            db_write_indicator(
                "Saving advanced download settings",
                UIDBHelpers._run_async,
                db.update_settings(
                    instance_name,
                    dlp_js_runtime=js_runtime_input,
                    dlp_max_fragment_retries=int(max_fragment_retries_input),
                ),
            )
            enhanced_success("Advanced settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")

    # Additional information
    st.markdown("---")
    st.markdown("#### System Information")

    # Show current file paths
    cookies_file = DVR_Config.get_yt_cookies_file()
    cookies_status = "✓ File exists" if cookies_file else "✗ Not configured"

    info_col1, info_col2 = st.columns(2)

    with info_col1:
        st.markdown(f"**Cookies File**")
        st.code(cookies_file if cookies_file else "Not configured")

    with info_col2:
        st.markdown(f"**Status**: {cookies_status}")
