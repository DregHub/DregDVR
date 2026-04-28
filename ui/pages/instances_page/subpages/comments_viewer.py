"""
Comments Tab
Displays and manages comments for videos in an instance.
"""

import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from ui.components import enhanced_info, enhanced_selectbox
from ui.css_loader import PageCSSLoader


def show_comments_tab(instance: Optional[Dict[str, Any]]):
    """
    Comments tab - select video and display comments.
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
    
    # Get videos with comments for this specific instance
    videos = UIDBHelpers.get_videos_with_comments(instance_name)
    
    if not videos:
        enhanced_info(f"No videos with comments downloaded for {instance.get('channel_name')}")
        return
    
    # Split into two columns
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.write("**Videos with Comments:**")
        
        video_options = {v['video_id']: f"{v['title'][:40]} ({v['comment_count']} comments)" for v in videos}
        
        if f'selected_comment_video_{instance_name}' not in st.session_state:
            st.session_state[f'selected_comment_video_{instance_name}'] = videos[0]['video_id'] if videos else None
        
        selected_video = enhanced_selectbox(
            "Select Video",
            options=list(video_options.keys()),
            placeholder="Choose a video",
            key=f"comment_video_select_{instance_name}",
        )
    
    with col_right:
        st.write("**Comments:**")
        
        if selected_video:
            # Get comments for selected video from this instance
            comments = UIDBHelpers.get_comments_for_video(instance_name, selected_video)
            
            if not comments:
                enhanced_info(f"No comments found for this video in {instance['instance_name']}")
            else:
                df_comments = pd.DataFrame(comments)
                
                # Truncate comment data for preview
                df_comments['Comment Preview'] = df_comments['comment_data'].str[:80].fillna('')
                
                gb = GridOptionsBuilder.from_dataframe(
                    df_comments[['author', 'Comment Preview', 'likes', 'replies', 'created_at']]
                )
                gb.configure_default_column(sortable=True, filterable=True, resizable=True)
                
                grid_options = gb.build()
                
                AgGrid(
                    df_comments[['author', 'Comment Preview', 'likes', 'replies', 'created_at']],
                    gridOptions=grid_options,
                    height=300,
                    key=f"comments_grid_{instance_name}_{selected_video}",
                    custom_css=PageCSSLoader.get_aggrid_custom_css()
                )
                
                # Show full comments in expanders
                for _, comment in df_comments.iterrows():
                    with st.expander(f"Comment by {comment['author']} ({comment['likes']} likes)"):
                        st.text_area(
                            "Comment Content",
                            value=comment['comment_data'] or '',
                            disabled=True,
                            height=150,
                            key=f"comment_full_{instance_name}_{comment['id']}"
                        )
