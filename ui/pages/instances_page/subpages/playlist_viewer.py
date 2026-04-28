"""
Playlist Tab
Displays videos and livestreams from playlist for an instance.
"""

import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from ui.components import enhanced_info, enhanced_button
from ui.css_loader import PageCSSLoader


def _get_status_badge(item: Dict[str, Any]) -> str:
    """Generate status badge text for a playlist item."""
    statuses = []

    if bool(item.get("downloaded_video")):
        statuses.append("✓ Downloaded")
    else:
        statuses.append("◌ Pending Download")

    if bool(item.get("downloaded_caption")):
        statuses.append("✓ Captions")

    if bool(item.get("uploaded_video_all_hosts")):
        statuses.append("✓ Uploaded All")
    elif any(
        [
            bool(item.get("uploaded_video_yt")),
            bool(item.get("uploaded_video_ia")),
            bool(item.get("uploaded_video_rm")),
            bool(item.get("uploaded_video_bc")),
            bool(item.get("uploaded_video_od")),
        ]
    ):
        statuses.append("◐ Partial Upload")

    if bool(item.get("was_live")):
        statuses.append("📡 Was Live")

    if bool(item.get("isshort")):
        statuses.append("📱 Short")

    return " | ".join(statuses) if statuses else "No Data"


def _format_upload_status(item: Dict[str, Any]) -> str:
    """Format upload status for display."""
    uploaded_to = []
    if bool(item.get("uploaded_video_yt")):
        uploaded_to.append("YT")
    if bool(item.get("uploaded_video_ia")):
        uploaded_to.append("IA")
    if bool(item.get("uploaded_video_rm")):
        uploaded_to.append("RM")
    if bool(item.get("uploaded_video_bc")):
        uploaded_to.append("BC")
    if bool(item.get("uploaded_video_od")):
        uploaded_to.append("OD")

    return ", ".join(uploaded_to) if uploaded_to else "Not Uploaded"


def _format_datetime(datetime_str: str) -> str:
    """Format datetime string to human-readable 12-hour format."""
    if not datetime_str:
        return "N/A"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %I:%M:%S %p")
    except Exception:
        return datetime_str[:10] if datetime_str else "N/A"


def show_playlist_tab(instance: Optional[Dict[str, Any]]):
    """
    Playlist tab - display videos/livestreams from playlist with comprehensive filtering and searching.

    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_aggrid(), PageCSSLoader.load_for_containers()
    )

    if not instance or not instance.get("channel_name"):
        enhanced_info("Channel not configured. Configure DVR Channel first.")
        return

    instance_name = instance["instance_name"]

    st.caption(
        f"Instance: **{instance['instance_name']}** | Channel: **{instance.get('channel_name', 'Unknown')}**"
    )

    # Control row
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        search_query = st.text_input(
            "🔍 Search (Title or URL)",
            key=f"search_{instance_name}",
            placeholder="Enter title or URL to search...",
        )
    with col2:
        status_filter = st.selectbox(
            "Filter Status",
            options=[
                "All",
                "Downloaded",
                "Not Downloaded",
                "Uploaded",
                "Not Uploaded",
                "Live Videos",
                "Posted Videos",
            ],
            key=f"status_filter_{instance_name}",
        )
    with col3:
        page_size = st.selectbox(
            "Items per page",
            options=[10, 20, 50, 100],
            index=1,
            key=f"page_size_{instance_name}",
        )
    with col4:
        if enhanced_button("🔄 Refresh", key=f"refresh_playlist_{instance_name}"):
            st.rerun()

    # Map filter label to filter value
    filter_map = {
        "All": None,
        "Downloaded": "downloaded",
        "Not Downloaded": "not_downloaded",
        "Uploaded": "uploaded",
        "Not Uploaded": "not_uploaded",
        "Live Videos": "live",
        "Posted Videos": "not_live",
    }

    # Get playlist items with filters
    items = UIDBHelpers.get_playlist_items(
        instance_name,
        limit=page_size,
        offset=0,
        search_query=search_query if search_query else None,
        status_filter=filter_map.get(status_filter),
    )

    total_count = UIDBHelpers.get_playlist_count(
        instance_name,
        search_query=search_query if search_query else None,
        status_filter=filter_map.get(status_filter),
    )

    if not items:
        enhanced_info(
            f"No videos found matching your filters for {instance.get('channel_name')}"
        )
        st.info(
            f"Total videos in playlist: {UIDBHelpers.get_playlist_count(instance_name)}"
        )
        return

    # Add status and upload columns to dataframe
    display_data = []
    for item in items:
        display_item = {
            "Title": item.get("title", "N/A")[:50],
            "URL": item.get("url", "")[:40],
            "Date": _format_datetime(item.get("datetime", "")),
            "Type": (
                "📱 Short"
                if item.get("isshort")
                else ("📡 Live" if item.get("was_live") else "Video")
            ),
            "Downloaded": "✓" if item.get("downloaded_video") else "◌",
            "Captions": "✓" if item.get("downloaded_caption") else "◌",
            "Uploaded To": _format_upload_status(item),
            "DL Attempts": item.get("video_download_attempts", 0),
            "Cap Attempts": item.get("caption_download_attempts", 0),
        }
        display_data.append(display_item)

    df = pd.DataFrame(display_data)

    # Build and display grid
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_pagination(paginationPageSize=page_size)
    gb.configure_side_bar()
    gb.configure_default_column(sortable=True, filterable=True, resizable=True)

    # Configure specific columns
    gb.configure_column("Title", width=150)
    gb.configure_column("URL", width=120)
    gb.configure_column("Type", width=80)
    gb.configure_column("Downloaded", width=80, type=["centerAligned"])
    gb.configure_column("Captions", width=80, type=["centerAligned"])

    grid_options = gb.build()

    # Display grid
    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        height=500,
        key=f"playlist_grid_{instance_name}",
        custom_css=PageCSSLoader.get_aggrid_custom_css(),
    )

    # Display summary stats
    st.divider()

    # Calculate statistics
    total_downloaded = sum(1 for item in items if item.get("downloaded_video"))
    total_uploaded = sum(1 for item in items if item.get("uploaded_video_all_hosts"))
    total_with_captions = sum(1 for item in items if item.get("downloaded_caption"))
    total_live = sum(1 for item in items if item.get("was_live"))
    total_shorts = sum(1 for item in items if item.get("isshort"))

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric("Total Videos", total_count)
    with col2:
        st.metric(
            "Downloaded",
            f"{total_downloaded}/{len(items)}",
            delta=int((total_downloaded / len(items) * 100)) if items else 0,
        )
    with col3:
        st.metric("Uploaded (All)", f"{total_uploaded}/{len(items)}")
    with col4:
        st.metric("With Captions", f"{total_with_captions}/{len(items)}")
    with col5:
        st.metric("Live Videos", total_live)
    with col6:
        st.metric("Shorts", total_shorts)

    st.caption(
        f"Showing {len(items)} of {total_count} videos | " f"Instance: {instance_name}"
    )
