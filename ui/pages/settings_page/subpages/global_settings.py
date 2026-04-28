"""
Global Settings Configuration
Handles application-wide DVR settings that apply to all instances.
"""

import streamlit as st
from utils.ui_db_helpers import UIDBHelpers
from db.dvr_db import DVRDB
from config.config_settings import DVR_Config
from ui.components import (
    enhanced_button,
    enhanced_checkbox,
    enhanced_text_input,
    enhanced_selectbox,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    enhanced_warning,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_global_settings():
    """
    Global settings configuration tab.
    Handles application-wide DVR settings.
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_inputs(), PageCSSLoader.load_for_buttons()
    )

    st.markdown("### Global Settings")
    st.markdown("Configure application-wide DVR settings that apply to all instances.")

    db = UIDBHelpers.get_db()

    # Create tabs for different configuration sections
    config_tabs = st.tabs(
        [
            "Download Settings",
            "JavaScript & Processing",
            "Timeouts & Buffering",
            "Session & Logging",
            "Threading Configuration",
            "YouTube Authentication",
        ]
    )

    # ========== TAB 1: DOWNLOAD SETTINGS ==========
    with config_tabs[0]:
        _show_download_settings(db)

    # ========== TAB 2: JAVASCRIPT & PROCESSING ==========
    with config_tabs[1]:
        _show_javascript_processing(db)

    # ========== TAB 3: TIMEOUTS & BUFFERING ==========
    with config_tabs[2]:
        _show_timeouts_buffering(db)

    # ========== TAB 4: SESSION & LOGGING ==========
    with config_tabs[3]:
        _show_session_logging(db)

    # ========== TAB 5: THREADING CONFIGURATION ==========
    with config_tabs[4]:
        _show_threading_config(db)

    # ========== TAB 6: YOUTUBE AUTHENTICATION ==========
    with config_tabs[5]:
        _show_youtube_authentication(db)


def _show_download_settings(db: DVRDB):
    """Show download-related global settings."""
    settings = UIDBHelpers._run_async(db.get_global_settings()) or {}

    st.markdown("#### Download Configuration")
    st.markdown("Configure default behavior for yt-dlp downloads.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Download Timestamp Format
        timestamp_format = settings.get(
            "download_timestamp_format", "%(timestamp>%d-%m-%Y %I-%M%p)s"
        )
        timestamp_input = enhanced_text_input(
            "Download Timestamp Format",
            value=timestamp_format,
            key="download_timestamp_format",
            help="yt-dlp timestamp format (e.g., %(timestamp>%d-%m-%Y %I-%M%p)s)",
        )

        # Verbose Logging
        verbose = bool(settings.get("dlp_verbose_downloads", True))
        verbose_input = enhanced_checkbox(
            "Verbose Download Logging",
            value=verbose,
            key="dlp_verbose_downloads",
            help="Enable detailed logging from yt-dlp",
        )

    with col2:
        # Keep Fragments
        keep_fragments = bool(settings.get("dlp_keep_fragments_downloads", False))
        keep_fragments_input = enhanced_checkbox(
            "Keep Download Fragments",
            value=keep_fragments,
            key="dlp_keep_fragments_downloads",
            help="Keep temporary fragments after download completes (useful for recovery)",
        )

        # Max Download Retries
        max_retries = settings.get("dlp_max_download_retries", 10)
        max_retries_input = st.number_input(
            "Max Download Retries",
            min_value=0,
            max_value=100,
            value=max_retries,
            key="dlp_max_download_retries",
            help="Maximum retries for failed downloads",
        )

    # Max Fragment Retries (full width)
    max_fragment_retries = settings.get("dlp_max_fragment_retries", 10)
    max_fragment_retries_input = st.number_input(
        "Max Fragment Retries",
        min_value=0,
        max_value=100,
        value=max_fragment_retries,
        key="dlp_max_fragment_retries",
        help="Maximum retries for failed fragment downloads",
    )

    if enhanced_button("Save Download Settings", key="save_download_settings"):
        try:
            db_write_indicator(
                "Saving download settings",
                UIDBHelpers._run_async,
                db.update_global_settings(
                    download_timestamp_format=timestamp_input,
                    dlp_verbose_downloads=verbose_input,
                    dlp_keep_fragments_downloads=keep_fragments_input,
                    dlp_max_download_retries=int(max_retries_input),
                    dlp_max_fragment_retries=int(max_fragment_retries_input),
                ),
            )
            enhanced_success("Download settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_javascript_processing(db: DVRDB):
    """Show JavaScript runtime and processing settings."""
    settings = UIDBHelpers._run_async(db.get_global_settings()) or {}

    st.markdown("#### JavaScript & Processing Settings")
    st.markdown("Configure JavaScript engine and content processing options.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # JavaScript Runtime
        js_runtime = settings.get("dlp_js_runtime", "quickjs")
        js_runtime_options = ["quickjs", "jsc", "nodejs", "deno"]
        if js_runtime not in js_runtime_options:
            js_runtime_options.append(js_runtime)

        js_runtime_input = enhanced_selectbox(
            "JavaScript Runtime",
            options=js_runtime_options,
            index=js_runtime_options.index(js_runtime),
            key="dlp_js_runtime",
            help="JavaScript engine: quickjs (fastest), jsc, nodejs, or deno (auto-detect)",
        )

        st.caption("**Recommended**: QuickJS for best performance")

    with col2:
        # Truncate Title Length
        truncate_length = settings.get("dlp_truncate_title_after_x_chars", 60)
        truncate_length_input = st.number_input(
            "Truncate Title Length",
            min_value=10,
            max_value=500,
            value=truncate_length,
            key="dlp_truncate_title_after_x_chars",
            help="Maximum characters in downloaded video filename",
        )

    # Subtitle Use SRTFix (full width)
    srtfix = bool(settings.get("dlp_subtitle_use_srtfix", True))
    srtfix_input = enhanced_checkbox(
        "Use SRTFix for Subtitles",
        value=srtfix,
        key="dlp_subtitle_use_srtfix",
        help="Apply SRTFix tool to fix malformed subtitle files",
    )

    if enhanced_button("Save JavaScript Settings", key="save_javascript_settings"):
        try:
            db_write_indicator(
                "Saving JavaScript settings",
                UIDBHelpers._run_async,
                db.update_global_settings(
                    dlp_js_runtime=js_runtime_input,
                    dlp_truncate_title_after_x_chars=int(truncate_length_input),
                    dlp_subtitle_use_srtfix=srtfix_input,
                ),
            )
            enhanced_success("JavaScript settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_timeouts_buffering(db: DVRDB):
    """Show timeout and buffering settings."""
    settings = UIDBHelpers._run_async(db.get_global_settings()) or {}

    st.markdown("#### Timeouts & Buffering Settings")
    st.markdown("Configure download timeouts and error handling behavior.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # GetInfo Timeout
        getinfo_timeout = settings.get("dlp_getinfo_timeout_seconds", 800)
        getinfo_timeout_input = st.number_input(
            "GetInfo Timeout (seconds)",
            min_value=60,
            max_value=3600,
            value=getinfo_timeout,
            key="dlp_getinfo_timeout_seconds",
            help="Timeout for getting video information",
        )

    with col2:
        # Stall Timeout
        stall_timeout = settings.get("dlp_stall_timeout_seconds", 800)
        stall_timeout_input = st.number_input(
            "Stall Timeout (seconds)",
            min_value=60,
            max_value=3600,
            value=stall_timeout,
            key="dlp_stall_timeout_seconds",
            help="Timeout for stalled downloads",
        )

    # Buffer First Attempt Errors (full width)
    buffer_errors = bool(settings.get("dlp_buffer_first_attempt_errors", True))
    buffer_errors_input = enhanced_checkbox(
        "Buffer First Attempt Errors",
        value=buffer_errors,
        key="dlp_buffer_first_attempt_errors",
        help="Store errors from first download attempt for recovery",
    )

    if enhanced_button("Save Timeout Settings", key="save_timeout_settings"):
        try:
            db_write_indicator(
                "Saving timeout settings",
                UIDBHelpers._run_async,
                db.update_global_settings(
                    dlp_getinfo_timeout_seconds=int(getinfo_timeout_input),
                    dlp_stall_timeout_seconds=int(stall_timeout_input),
                    dlp_buffer_first_attempt_errors=buffer_errors_input,
                ),
            )
            enhanced_success("Timeout settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_session_logging(db: DVRDB):
    """Show session and logging settings."""
    settings = UIDBHelpers._run_async(db.get_global_settings()) or {}

    st.markdown("#### Session & Logging Settings")
    st.markdown("Configure diagnostic and logging options.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Video Recording
        video_recording = bool(settings.get("session_video_recording", False))
        video_recording_input = enhanced_checkbox(
            "Session Video Recording",
            value=video_recording,
            key="session_video_recording",
            help="Record browser sessions for debugging (uses more disk space)",
        )

    with col2:
        # Error HTML Dump
        error_html_dump = bool(settings.get("session_error_html_dump", False))
        error_html_dump_input = enhanced_checkbox(
            "Error HTML Dump",
            value=error_html_dump,
            key="session_error_html_dump",
            help="Save HTML snapshots when errors occur (helps with troubleshooting)",
        )

    st.markdown("---")
    enhanced_warning(
        "⚠️ **Note**: Enabling these options will use additional disk space. Use only for debugging purposes."
    )

    if enhanced_button("Save Session Settings", key="save_session_settings"):
        try:
            db_write_indicator(
                "Saving session settings",
                UIDBHelpers._run_async,
                db.update_global_settings(
                    session_video_recording=video_recording_input,
                    session_error_html_dump=error_html_dump_input,
                ),
            )
            enhanced_success("Session settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_threading_config(db: DVRDB):
    """Show threading and concurrency settings."""
    settings = UIDBHelpers._run_async(db.get_global_settings()) or {}

    st.markdown("#### Threading & Concurrency Configuration")
    st.markdown("Control the number of concurrent operations for different tasks.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Video Download Threads
        video_dl_threads = settings.get("video_download_max_threads", 6)
        video_dl_threads_input = st.number_input(
            "Video Download Threads",
            min_value=1,
            max_value=16,
            value=video_dl_threads,
            key="video_download_max_threads",
            help="Maximum concurrent video downloads",
        )

        # Caption Download Threads
        caption_dl_threads = settings.get("caption_download_max_threads", 6)
        caption_dl_threads_input = st.number_input(
            "Caption Download Threads",
            min_value=1,
            max_value=16,
            value=caption_dl_threads,
            key="caption_download_max_threads",
            help="Maximum concurrent caption downloads",
        )

        # Playlist Processing Threads
        playlist_threads = settings.get("playlist_processing_max_threads", 6)
        playlist_threads_input = st.number_input(
            "Playlist Processing Threads",
            min_value=1,
            max_value=16,
            value=playlist_threads,
            key="playlist_processing_max_threads",
            help="Maximum concurrent playlist operations",
        )

    with col2:
        # Caption Upload Threads
        caption_up_threads = settings.get("caption_upload_max_threads", 6)
        caption_up_threads_input = st.number_input(
            "Caption Upload Threads",
            min_value=1,
            max_value=16,
            value=caption_up_threads,
            key="caption_upload_max_threads",
            help="Maximum concurrent caption uploads",
        )

        # Video Upload Threads
        video_up_threads = settings.get("video_upload_max_threads", 6)
        video_up_threads_input = st.number_input(
            "Video Upload Threads",
            min_value=1,
            max_value=16,
            value=video_up_threads,
            key="video_upload_max_threads",
            help="Maximum concurrent video uploads",
        )

    st.markdown("---")
    enhanced_info(
        "💡 **Tip**: Higher thread counts = more parallelism but more resource usage. Default value is 6."
    )

    if enhanced_button("Save Threading Settings", key="save_threading_settings"):
        try:
            db_write_indicator(
                "Saving threading settings",
                UIDBHelpers._run_async,
                db.update_global_settings(
                    video_download_max_threads=int(video_dl_threads_input),
                    caption_download_max_threads=int(caption_dl_threads_input),
                    caption_upload_max_threads=int(caption_up_threads_input),
                    video_upload_max_threads=int(video_up_threads_input),
                    playlist_processing_max_threads=int(playlist_threads_input),
                ),
            )
            enhanced_success("Threading settings saved successfully!")
            st.rerun()
        except Exception as e:
            enhanced_error(f"Failed to save: {e}")


def _show_youtube_authentication(db: DVRDB):
    """Show YouTube authentication settings (global-level)."""
    settings = UIDBHelpers._run_async(db.get_global_settings()) or {}

    st.markdown("#### YouTube Authentication")
    st.markdown(
        "Configure YouTube credentials used by all instances for downloading and uploading content."
    )

    # Get current cookies content
    yt_cookies_content = UIDBHelpers._run_async(db.get_yt_cookies_content()) or ""

    # YouTube Cookies File Upload
    st.markdown("##### YouTube Cookies File")
    st.markdown(
        "Upload your `cookies.txt` file to enable yt-dlp to access age-restricted or members-only content."
    )

    cookies_file = st.file_uploader(
        "Choose cookies.txt file",
        type="txt",
        key="yt_cookies_uploader",
        help="YouTube cookies file exported from your browser using a cookie export extension",
    )

    col1, col2 = st.columns(2)

    with col1:
        if cookies_file is not None:
            cookies_content = cookies_file.read().decode("utf-8")
            if enhanced_button("Save YouTube Cookies", key="save_yt_cookies"):
                try:
                    db_write_indicator(
                        "Saving YouTube cookies",
                        UIDBHelpers._run_async,
                        db.set_yt_cookies_content(cookies_content),
                    )
                    # Ensure file is created in Auth/Download directory
                    file_path = DVR_Config.save_download_cookies(cookies_content)
                    if file_path:
                        enhanced_success("✓ YouTube cookies file saved successfully!")
                        st.caption(f"Saved to: {file_path}")
                    else:
                        enhanced_warning(
                            "⚠️ Cookies saved to database but file creation failed. Check directory permissions."
                        )
                    st.rerun()
                except Exception as e:
                    enhanced_error(f"Failed to save cookies: {e}")

    with col2:
        if yt_cookies_content:
            if enhanced_button("Clear Cookies", key="clear_yt_cookies"):
                try:
                    db_write_indicator(
                        "Clearing YouTube cookies",
                        UIDBHelpers._run_async,
                        db.set_yt_cookies_content(""),
                    )
                    enhanced_success("YouTube cookies cleared!")
                    st.rerun()
                except Exception as e:
                    enhanced_error(f"Failed to clear cookies: {e}")

    # Current status
    st.markdown("---")
    st.markdown("##### Status")
    if yt_cookies_content:
        enhanced_success("✓ YouTube cookies file is configured")
        st.caption(f"Cookies file size: {len(yt_cookies_content)} bytes")
    else:
        enhanced_warning("⚠️ No YouTube cookies file configured")
        st.caption("yt-dlp will attempt to download without authentication")
