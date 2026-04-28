"""
Captions Tab
Displays and manages captions for videos in an instance.
"""

import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from ui.components import enhanced_info, enhanced_selectbox
from ui.css_loader import PageCSSLoader


def show_captions_tab(instance: Optional[Dict[str, Any]]):
    """
    Captions tab - select video and display captions.
    Loads data only from the selected instance.
    
    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_aggrid(),
        PageCSSLoader.load_for_expanders(),
        PageCSSLoader.load_for_inputs(),
        PageCSSLoader.load_for_containers()
    )
    
    if not instance or not instance.get('channel_name'):
        enhanced_info("Channel not configured. Configure DVR Channel first.")
        return
    
    instance_name = instance['instance_name']
    
    st.caption(f"Instance: **{instance['instance_name']}** | Channel: **{instance.get('channel_name', 'Unknown')}**")
    
    # Get videos with captions for this specific instance
    videos = UIDBHelpers.get_videos_with_captions(instance_name)
    
    if not videos:
        enhanced_info(f"No videos with captions downloaded for {instance.get('channel_name')}")
        return
    
    # Split into two columns: left for video selector, right for captions
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.write("**Videos with Captions:**")
        
        # Create video options
        video_options = {v['video_id']: f"{v['title'][:40]} ({v['caption_count']} captions)" for v in videos}
        
        # Initialize session state for selected video
        if f'selected_caption_video_{instance_name}' not in st.session_state:
            st.session_state[f'selected_caption_video_{instance_name}'] = videos[0]['video_id'] if videos else None
        
        selected_video = enhanced_selectbox(
            "Select Video",
            options=list(video_options.keys()),
            placeholder="Choose a video",
            key=f"caption_video_select_{instance_name}",
        )
    
    with col_right:
        st.write("**Captions:**")
        
        if selected_video:
            # Get captions for selected video from this instance
            captions = UIDBHelpers.get_captions_for_video(instance_name, selected_video)
            
            if not captions:
                enhanced_info(f"No captions found for this video in {instance['instance_name']}")
            else:
                # Display captions in grid
                df_captions = pd.DataFrame(captions)
                
                # Preview caption data (first 100 chars)
                df_captions['Preview'] = df_captions['caption_data'].str[:100].fillna('')
                
                gb = GridOptionsBuilder.from_dataframe(df_captions[['language', 'Preview', 'downloaded_at']])
                gb.configure_default_column(sortable=True, filterable=True, resizable=True)
                gb.configure_column('language', width=100)
                
                grid_options = gb.build()
                
                AgGrid(
                    df_captions[['language', 'Preview', 'downloaded_at']],
                    gridOptions=grid_options,
                    height=300,
                    key=f"captions_grid_{instance_name}_{selected_video}",
                    custom_css=PageCSSLoader.get_aggrid_custom_css()
                )
                
                # Show full caption in expander
                for _, caption in df_captions.iterrows():
                    with st.expander(f"View Full Caption - {caption['language']}"):
                        st.text_area(
                            "Caption Content",
                            value=caption['caption_data'] or '',
                            disabled=True,
                            height=200,
                            key=f"caption_full_{instance_name}_{caption['id']}"
                        )
