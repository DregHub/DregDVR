"""
Settings Page
Main entry point for all application settings (global and instance-specific).
"""

import streamlit as st
import multipage_streamlit as mt
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from ui.pages.settings_page.subpages import (
    show_global_settings,
    show_instance_settings_tab,
    show_tasks_tab,
    show_uploaders_tab,
)
from utils.ui_db_helpers import UIDBHelpers
from ui.components import (
    enhanced_warning,
    enhanced_info,
)
from ui.css_loader import PageCSSLoader


def show_instance_sidebar_settings():
    """Fetch and prepare instance data for the settings sidebar AgGrid."""
    instances = UIDBHelpers.get_all_instances()
    
    if not instances:
        return None, None
    
    # Prepare data for DataFrame
    data = []
    instance_name_map = {}
    
    for instance in instances:
        display_name = instance.get('instance_name', 'Unknown')
        channel_name = instance.get('channel_name', 'Not Set')
        source_platform = instance.get('source_platform', 'N/A')
        platform_display = source_platform.split('.')[0] if source_platform and source_platform != 'N/A' else 'N/A'
        
        data.append({
            'Instance': display_name,
            'Platform': platform_display,
            'Channel': channel_name
        })
        
        instance_name_map[display_name] = display_name
    
    df = pd.DataFrame(data)
    return df, instance_name_map


def show_settings():
    """Main settings page with navigation between global and instance settings."""
    
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_containers(),
        PageCSSLoader.load_for_tabs()
    )
    
    st.markdown("# Settings")
    st.markdown("Manage DVR configuration for global settings and individual instances.")
    
    # Create main navigation tabs
    main_tabs = st.tabs(["Global Settings", "Instance Settings"])
    
    # ==================== TAB 1: GLOBAL SETTINGS ====================
    with main_tabs[0]:
        st.markdown("---")
        show_global_settings()
    
    # ==================== TAB 2: INSTANCE SETTINGS ====================
    with main_tabs[1]:
        st.markdown("---")
        _show_instance_settings_manager()


def _show_instance_settings_manager():
    """Show instance-specific settings with sidebar selector."""
    
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_aggrid(),
        PageCSSLoader.load_for_containers(),
        PageCSSLoader.load_for_tabs()
    )
    
    # Initialize session state for instance selection if needed
    if 'settings_selected_instance_name' not in st.session_state:
        st.session_state.settings_selected_instance_name = None
    
    # Create container wrapper for both columns
    main_container = st.container(border=False)
    with main_container:
        # Create two-column layout: left sidebar (25%), right content (75%)
        col_sidebar, col_content = st.columns([0.25, 0.75], gap="medium")
        
        # ==================== Left Sidebar ====================
        with col_sidebar:
            # Get instance data from sidebar helper
            df, instance_name_map = show_instance_sidebar_settings()
            
            # Set first instance as default if no selection exists
            if df is not None and instance_name_map is not None and not df.empty:
                if st.session_state.settings_selected_instance_name is None:
                    first_instance_name = df.iloc[0]['Instance']
                    st.session_state.settings_selected_instance_name = instance_name_map[first_instance_name]
            
            if df is None or instance_name_map is None:
                # Show empty state banner
                enhanced_warning("No Instances")
                enhanced_info(
                    "Create your first instance using the **Instances** page "
                    "to configure instance-specific settings."
                )
                selected_instance_name = None
            else:
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
                
                grid_options = gb.build()
                
                # Load custom CSS for dark glass-morphism theme from template
                custom_css = PageCSSLoader.get_aggrid_custom_css()
                
                # Display AgGrid directly in sidebar
                grid_response = AgGrid(
                    df_with_button,
                    gridOptions=grid_options,
                    update_mode=GridUpdateMode.SELECTION_CHANGED,
                    key="settings_instance_grid",
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
                        st.session_state.settings_selected_instance_name = None
                        selected_instance_name = None
                    elif selected_display and selected_display in instance_name_map:
                        selected_name = instance_name_map[selected_display]
                        st.session_state.settings_selected_instance_name = selected_name
                        selected_instance_name = selected_name
                
                # Use stored selection if no current selection
                if not selected_instance_name:
                    selected_instance_name = st.session_state.settings_selected_instance_name
        
        # ==================== Right Content Panel ====================
        with col_content:
            # Get selected instance details
            selected_instance = None
            if selected_instance_name:
                selected_instance = UIDBHelpers.get_instance_by_name(selected_instance_name)
            
            # Create tabs for instance settings subpages
            tabs = st.tabs(["Settings", "Tasks", "Upload Platforms"])
            
            # Tab 1: Instance Settings
            with tabs[0]:
                if not selected_instance:
                    enhanced_info("Select an instance from the sidebar to view and edit its settings.")
                else:
                    show_instance_settings_tab(selected_instance)
            
            # Tab 2: Tasks Configuration
            with tabs[1]:
                if not selected_instance:
                    enhanced_info("Select an instance from the sidebar to configure tasks.")
                else:
                    show_tasks_tab(selected_instance)
            
            # Tab 3: Upload Platforms
            with tabs[2]:
                if not selected_instance:
                    enhanced_info("Select an instance from the sidebar to configure upload platforms.")
                else:
                    show_uploaders_tab(selected_instance)
   