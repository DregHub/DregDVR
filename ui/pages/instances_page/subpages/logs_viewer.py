"""
Logs Tab
Displays logs for an instance with type and level filtering.
"""

import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd
from typing import Optional, Dict, Any, List
from utils.ui_db_helpers import UIDBHelpers
from ui.css_loader import PageCSSLoader
from ui.components import enhanced_selectbox, enhanced_info, enhanced_button

# Log type categories based on channel_config grouping
LOG_TYPE_CATEGORIES = {
    'Download': [
        'download_live',
        'download_live_recovery',
        'download_captions',
        'download_comments',
        'download_posted',
        'download_posted_notices',
        'channel_playlist'
    ],
    'Upload': [
        'upload_live',
        'upload_posted',
        'upload_ia',
        'upload_yt',
        'upload_rumble',
        'upload_bitchute',
        'upload_odysee',
        'upload_captions'
    ],
    'Misc': [
        'core'
    ]
}


def show_logs_tab(instance: Optional[Dict[str, Any]]):
    """
    Logs tab - display instance logs with type and level filtering.
    Displays logs for the selected instance with level filtering options.
    
    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_aggrid(),
        PageCSSLoader.load_for_inputs(),
        PageCSSLoader.load_for_containers()
    )
    
    if not instance or not instance.get('channel_name'):
        enhanced_info("⚠️ Channel not configured. Configure DVR Channel first.")
        return
    
    instance_name = instance['instance_name']
    
    st.caption(f"Instance: **{instance['instance_name']}** | Channel: **{instance.get('channel_name', 'Unknown')}**")
    
    # Get all available log types from database
    all_log_types = UIDBHelpers.get_log_types()
    
    # Categorize log types
    categorized_logs = _categorize_log_types(all_log_types)
    
    # Log type category and level selectors
    col1, col2, col3, col4, col5 = st.columns([2, 2, 1.5, 1.5, 1])
    
    with col1:
        selected_category = enhanced_selectbox(
            "Log Category",
            options=['Download', 'Upload', 'Misc', 'All'],
            key=f"log_category_select_{instance_name}"
        )
    
    # Get log types for selected category
    if selected_category == 'All':
        selected_log_types = all_log_types
    else:
        selected_log_types = categorized_logs[selected_category]
    
    with col2:
        selected_log_type = enhanced_selectbox(
            "Specific Log Type",
            options=selected_log_types if selected_log_types else ['None'],
            key=f"log_type_select_{instance_name}",
            placeholder="Select a log type"
        )
    
    with col3:
        selected_level = enhanced_selectbox(
            "Log Level",
            options=[None, "DEBUG", "INFO", "WARNING", "ERROR"],
            key=f"log_level_select_{instance_name}",
            placeholder="All Levels"
        )
    
    # Get available thread numbers for selected log type
    available_threads = UIDBHelpers.get_thread_numbers(selected_log_type if selected_log_type != 'None' else "core")
    thread_options = [None] + available_threads if available_threads else [None]
    
    with col4:
        selected_thread = enhanced_selectbox(
            "Thread Number",
            options=thread_options,
            key=f"log_thread_select_{instance_name}",
            placeholder="All Threads"
        )
    
    with col5:
        if enhanced_button("🔄 Refresh", key=f"refresh_logs_{instance_name}"):
            st.rerun()
    
    # Skip if no log types available
    if not selected_log_types or selected_log_type == 'None':
        enhanced_info(f"No logs available for the '{selected_category}' category.")
        return
    
    # Get logs for this specific instance with level and thread filters
    logs = UIDBHelpers.get_instance_logs(
        selected_log_type, 
        level=selected_level,
        thread_number=selected_thread,
        limit=100
    )
    
    if not logs:
        level_text = f" with {selected_level} level" if selected_level else ""
        enhanced_info(f"No {selected_log_type.replace('_', ' ')} logs found{level_text} for {instance['instance_name']}")
        return
    
    # Convert to DataFrame
    df_logs = pd.DataFrame(logs)
    
    # Ensure level and thread_number columns exist (for backward compatibility with old logs)
    if 'level' not in df_logs.columns:
        df_logs['level'] = 'INFO'
    if 'thread_number' not in df_logs.columns:
        df_logs['thread_number'] = None
    
    # Build and display grid with level and thread columns
    display_cols = ['timestamp', 'level', 'thread_number', 'message', 'aggregation_count', 'first_occurrence']
    gb = GridOptionsBuilder.from_dataframe(df_logs[display_cols])
    
    gb.configure_pagination(paginationPageSize=20)
    gb.configure_side_bar()
    gb.configure_default_column(sortable=True, filterable=True, resizable=True, wrapText=True)
    
    # Configure level column with styling
    gb.configure_column(
        'level',
        width=80,
        sortable=True,
        filterable=True,
        resizable=False,
    )
    # Configure thread_number column
    gb.configure_column(
        'thread_number',
        width=100,
        sortable=True,
        filterable=True,
        resizable=False,
    )
    gb.configure_column('message', wrapText=True)
    gb.configure_column('timestamp', width=150)
    gb.configure_column('aggregation_count', width=80)
    gb.configure_column('first_occurrence', width=150)
    
    grid_options = gb.build()
    
    AgGrid(
        df_logs[display_cols],
        gridOptions=grid_options,
        height=500,
        key=f"logs_grid_{instance_name}_{selected_log_type}_{selected_level}_{selected_thread}",
        custom_css=PageCSSLoader.get_aggrid_custom_css()
    )
    
    # Summary with level breakdown and thread count
    if 'level' in df_logs.columns:
        level_order = ["DEBUG", "INFO", "WARNING", "ERROR"]
        level_counts = df_logs['level'].value_counts().to_dict()
        level_summary = " | ".join([
            f"{level}: {level_counts.get(level, 0)}" 
            for level in level_order 
            if level in level_counts
        ])
        
        # Add thread count information
        if 'thread_number' in df_logs.columns:
            unique_threads = df_logs[df_logs['thread_number'].notna()]['thread_number'].nunique()
            thread_info = f" | Threads: {unique_threads}" if unique_threads > 0 else ""
        else:
            thread_info = ""
        
        st.caption(f"Total: {len(logs)} log entries | {level_summary}{thread_info}")
    else:
        st.caption(f"Total: {len(logs)} log entries from {instance['instance_name']}")


def _categorize_log_types(all_log_types: List[str]) -> Dict[str, List[str]]:
    """
    Categorize available log types into Download, Upload, and Misc categories.
    
    Args:
        all_log_types: List of all available log types from database
        
    Returns:
        Dictionary with categories as keys and lists of log types as values
    """
    categorized = {
        'Download': [],
        'Upload': [],
        'Misc': []
    }
    
    for log_type in all_log_types:
        if log_type in LOG_TYPE_CATEGORIES['Download']:
            categorized['Download'].append(log_type)
        elif log_type in LOG_TYPE_CATEGORIES['Upload']:
            categorized['Upload'].append(log_type)
        else:
            categorized['Misc'].append(log_type)
    
    return categorized
