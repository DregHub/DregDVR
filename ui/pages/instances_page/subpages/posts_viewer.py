"""
Posts Tab
Displays and manages posts for an instance.
"""

import streamlit as st
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from ui.components import enhanced_info, enhanced_selectbox
from ui.css_loader import PageCSSLoader


def show_posts_tab(instance: Optional[Dict[str, Any]]):
    """
    Posts tab - select post and display HTML rendered content.
    Loads data only from the selected instance.
    
    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_html_content(),
        PageCSSLoader.load_for_containers()
    )
    
    if not instance or not instance.get('channel_name'):
        enhanced_info("Channel not configured. Configure DVR Channel first.")
        return
    
    instance_name = instance['instance_name']
    
    st.caption(f"Instance: **{instance['instance_name']}** | Channel: **{instance.get('channel_name', 'Unknown')}**")
    
    # Get posts for this specific instance
    posts = UIDBHelpers.get_posts(instance_name, limit=50)
    
    if not posts:
        enhanced_info(f"No posts found for {instance.get('channel_name')}")
        return
    
    # Split into two columns
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.write("**Posts:**")
        
        post_options = {p['id']: p['title'][:50] for p in posts}
        
        if f'selected_post_{instance_name}' not in st.session_state:
            st.session_state[f'selected_post_{instance_name}'] = posts[0]['id'] if posts else None
        
        selected_post_id = enhanced_selectbox(
            "Select Post",
            options=list(post_options.keys()),
            placeholder="Choose a post",
            key=f"post_select_{instance_name}",
        )
    
    with col_right:
        st.write("**Content:**")
        
        if selected_post_id:
            # Get post for this instance
            post = UIDBHelpers.get_post_by_id(selected_post_id)
            
            if post:
                st.markdown(f"**{post['title']}**")
                
                # Display metadata
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"Posted: {post['created_at']}")
                with col2:
                    st.caption(f"Comments: {post['comment_count']}")
                
                st.divider()
                
                # Display HTML content with safety
                if post.get('html_content'):
                    st.markdown(post['html_content'], unsafe_allow_html=True)
                elif post.get('text_content'):
                    st.markdown(post['text_content'])
                else:
                    enhanced_info("No content available")
