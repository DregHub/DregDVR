import streamlit as st
import multipage_streamlit as mt
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from ui.pages.instances_page.subpages import (
    show_dvr_channel_tab,
    show_create_instance_form,
    show_playlist_tab,
    show_captions_tab,
    show_comments_tab,
    show_posts_tab,
    show_logs_tab,
    show_uploader_tab,
    show_downloader_tab
)
from utils.ui_db_helpers import UIDBHelpers
from ui.components import (
    enhanced_warning,
    enhanced_info,
)
from ui.css_loader import PageCSSLoader


def show_instance_sidebar():
    """Fetch and prepare instance data for the sidebar AgGrid."""
    # Get all instances from the database
    instances = UIDBHelpers.get_all_instances()

    if not instances:
        return None, None, None

    # Prepare data for DataFrame
    data = []
    instance_name_map = {}
    channel_id_map = {}

    for instance in instances:
        channel_id = instance.get('channel_id', 'Unknown')
        display_name = instance.get('instance_name', 'Unknown')
        channel_name = instance.get('channel_name', 'Not Set')
        source_platform = instance.get('source_platform', 'N/A')
        # Extract just the platform name (e.g., 'YouTube.com/@' -> 'YouTube')
        platform_display = source_platform.split('.')[0] if source_platform and source_platform != 'N/A' else 'N/A'

        data.append({
            'Instance': display_name,
            'Platform': platform_display,
            'Channel': channel_name
        })

        instance_name_map[display_name] = channel_id
        channel_id_map[channel_id] = display_name

    df = pd.DataFrame(data)
    return df, instance_name_map, channel_id_map


def show_instances():
    """Main instances page with sidebar and tabbed subpages."""
    
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_aggrid(),
        PageCSSLoader.load_for_containers(),
        PageCSSLoader.load_for_tabs()
    )
    
    # Initialize session state for instance selection if needed
    if 'selected_instance_name' not in st.session_state:
        st.session_state.selected_instance_name = None
    
    # Apply CSS to ensure equal column heights
    st.markdown("""
    <style>
    </style>
    """, unsafe_allow_html=True)
    
    # Create container wrapper for both columns
    main_container = st.container(border=False)
    with main_container:
        # Create two-column layout: left sidebar (25%), right content (75%)
        col_sidebar, col_content = st.columns([0.25, 0.75], gap="medium")
        
        # ==================== Left Sidebar ====================
        with col_sidebar:
            # Get instance data from sidebar helper
            df, instance_name_map, channel_id_map = show_instance_sidebar()

            # Set first instance as default if no selection exists
            if df is not None and instance_name_map is not None and not df.empty:
                if st.session_state.selected_instance_name is None:
                    first_instance_name = df.iloc[0]['Instance']
                    st.session_state.selected_instance_name = first_instance_name

            if df is None or instance_name_map is None:
                # Show empty state banner
                enhanced_warning("No Instances")
                enhanced_info(
                    "Create your first instance using the **Create New Instance** option "
                    "in the DVR Channel tab to get started."
                )
                selected_instance_name = None
            else:
                # Build AgGrid configuration
                gb = GridOptionsBuilder.from_dataframe(df)
                gb.configure_default_column(
                    sortable=False,
                    filterable=False,
                    resizable=False,
                    wrapText=False,
                    autoHeight=False
                )
                gb.configure_selection(selection_mode="single", use_checkbox=False)
                gb.configure_column("Instance", width=100)
                gb.configure_column("Platform", width=75)
                gb.configure_column("Channel", width=85)
                
                grid_options = gb.build()
                
                # Load custom CSS for dark glass-morphism theme from template
                custom_css = PageCSSLoader.get_aggrid_custom_css()
                
                # Add a special "Add New" row to the dataframe
                add_new_row = pd.DataFrame({
                    'Instance': ['➕ Add New Instance'],
                    'Platform': [''],
                    'Channel': ['']
                })
                df_with_button = pd.concat([df, add_new_row], ignore_index=True)
                
                # Build AgGrid configuration
                gb = GridOptionsBuilder.from_dataframe(df_with_button)
                gb.configure_default_column(
                    sortable=False,
                    filterable=False,
                    resizable=False,
                    wrapText=False,
                    autoHeight=False
                )
                gb.configure_selection(selection_mode="single", use_checkbox=False)
                gb.configure_column("Instance", width=100)
                gb.configure_column("Platform", width=75)
                gb.configure_column("Channel", width=85)
                
                # Style the Add New row
                gb.configure_grid_options(
                    rowClassRules={
                        '"ag-row-add-new"': 'data.Instance == "➕ Add New Instance"',
                    },
                    suppressHorizontalScroll=True
                )
                
                grid_options = gb.build()
                
                # Display AgGrid directly in sidebar
                grid_response = AgGrid(
                    df_with_button,
                    gridOptions=grid_options,
                    update_mode=GridUpdateMode.SELECTION_CHANGED,
                    key="instance_grid",
                    allow_unsafe_jscode=False,
                    fit_columns_on_grid_load=False,
                    theme="dark",
                    custom_css=custom_css,
                    height=600
                )
                
                # Handle row selection
                selected_instance_name = None
                if (grid_response is not None and 
                    'selected_rows' in grid_response and 
                    grid_response['selected_rows'] is not None and 
                    not grid_response['selected_rows'].empty):
                    selected_row = grid_response['selected_rows'].iloc[0].to_dict()
                    selected_display = selected_row.get('Instance')
                    
                    # Check if "Add New Instance" row was clicked
                    if selected_display == "➕ Add New Instance":
                        st.session_state.selected_instance_name = None
                        selected_instance_name = None
                    elif selected_display and selected_display in instance_name_map:
                        selected_channel_id = instance_name_map[selected_display]
                        st.session_state.selected_instance_name = selected_display
                        selected_instance_name = selected_display
                
                # Use stored selection if no current selection
                if not selected_instance_name:
                    selected_instance_name = st.session_state.selected_instance_name
        
        # ==================== Right Content Panel ====================
        with col_content:
            # Get selected instance details
            selected_instance = None
            if selected_instance_name:
                # Try to get instance by channel_id first, then by instance_name
                selected_instance = UIDBHelpers.get_instance_by_name(selected_instance_name)
                if not selected_instance:
                    # Try getting by instance_name as fallback
                    selected_instance = UIDBHelpers.get_instance_by_name(selected_instance_name)
            
            # Create tabs for instance manager subpages
            tabs = st.tabs(["DVR Channel", "Downloader", "Uploader", "Playlist", "Comments", "Captions", "Posts", "Logs"])
            
            # Tab 1: DVR Channel (show create form if no instance, otherwise show channel config)
            with tabs[0]:
                if not selected_instance:
                    show_create_instance_form()
                else:
                    show_dvr_channel_tab(selected_instance)
            
            # Tab 2: Downloader (enabled only if channel configured)
            with tabs[1]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_downloader_tab(selected_instance)
            
            # Tab 3: Uploader (enabled only if channel configured)
            with tabs[2]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_uploader_tab(selected_instance)
            
            # Tab 4: Playlist (enabled only if channel configured)
            with tabs[3]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_playlist_tab(selected_instance)
            
            # Tab 5: Comments (enabled only if channel configured)
            with tabs[4]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_comments_tab(selected_instance)
            
            # Tab 6: Captions (enabled only if channel configured)
            with tabs[5]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_captions_tab(selected_instance)
            
            # Tab 7: Posts (enabled only if channel configured)
            with tabs[6]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_posts_tab(selected_instance)
            
            # Tab 8: Logs (enabled only if channel configured)
            with tabs[7]:
                if not selected_instance or not selected_instance.get('channel_name'):
                    enhanced_info("Configure DVR Channel first to enable this tab")
                else:
                    show_logs_tab(selected_instance)
