import os
import streamlit as st
from utils.ui_templates import UITemplates
from utils.ui_db_helpers import UIDBHelpers
from ui.css_loader import PageCSSLoader

# Load CSS bundle with lazy-loading strategy
# Core themes are loaded globally, unused control themes are lazy-loaded on demand
css_bundle = (
    UITemplates.get_app_hide_elements_css() +
    PageCSSLoader.load_core_themes()
)

st.html(f"""
    <style>
        {css_bundle}
    </style>
""")


from streamlit_community_navigation_bar import st_navbar
import pages as pg

# --------------------------------------------------
# Streamlit base configuration
# --------------------------------------------------
st.set_page_config(initial_sidebar_state="collapsed")

parent_dir = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(parent_dir, "cubes.svg")

 

# --------------------------------------------------
# Navbar iframe shadow
# --------------------------------------------------
navbar_shadow_css = UITemplates.get_app_navbar_shadow_css()
st.markdown(f"""
<style>
{navbar_shadow_css}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# 3D Glass Navbar Styles (NO HOVER)
# --------------------------------------------------
styles = UITemplates.get_app_navbar_styles()

options = {
    "show_menu": False,
    "show_sidebar": False,
}

# Initialize default page in session state if not set
if 'current_page' not in st.session_state:
    st.session_state.current_page = "DVR Instances"

# --------------------------------------------------
# Render navbar
# --------------------------------------------------
page = st_navbar(
    pages=["DVR Instances", "DVR Monitor", "DVR Global Settings"],
    logo_path=logo_path,
    urls=None,
    styles=styles,
    options=options,
    selected=st.session_state.current_page,  # Set default selected page
)

# Update session state if a new page is selected
if page:
    st.session_state.current_page = page

# --------------------------------------------------
# Page routing
# --------------------------------------------------
functions = {
    "DVR Instances": pg.show_instances,
    "DVR Monitor": pg.show_monitor,
    "DVR Global Settings": pg.show_settings,
}

# Use the current page from session state (fallback to default)
current_page = st.session_state.current_page
go_to = functions.get(current_page)
if go_to:
    go_to()