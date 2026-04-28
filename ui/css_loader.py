"""
Page CSS Loader - Helper to dynamically load themed CSS for Streamlit pages.

This module provides a PageCSSLoader class that simplifies loading component-specific
CSS themes from templates for use across different pages. It wraps UITemplates methods
to compose CSS for different component types (AgGrid, inputs, expanders, etc.).

Usage:
    # In your page:
    from ui.css_loader import PageCSSLoader
    
    # Load CSS and apply it
    css = PageCSSLoader.load_for_aggrid()
    st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
    
    # For AgGrid custom_css parameter:
    aggrid_css = PageCSSLoader.get_aggrid_custom_css()
    AgGrid(..., custom_css=aggrid_css)
"""

from utils.ui_templates import UITemplates


class PageCSSLoader:
    """Helper class to load and compose themed CSS for different component types."""

    @staticmethod
    def load_for_aggrid() -> str:
        """
        Load CSS themed for AgGrid components.
        Use with st.markdown() for general grid styling in the page.
        
        Returns:
            CSS string containing AgGrid and data display theme styles
        """
        return UITemplates.get_data_display_theme()

    @staticmethod
    def get_aggrid_custom_css() -> dict:
        """
        Get AgGrid custom_css dictionary for use with AgGrid(..., custom_css=...).
        This provides the dark glass-morphism theme for grid rendering.
        
        Returns:
            Dictionary of AgGrid custom CSS styles
        """
        return UITemplates.get_aggrid_styles()

    @staticmethod
    def load_for_inputs() -> str:
        """
        Load CSS themed for input components (selectbox, text_input, text_area, etc).
        
        Returns:
            CSS string containing input theme styles
        """
        return UITemplates.get_inputs_theme()

    @staticmethod
    def load_for_containers() -> str:
        """
        Load CSS themed for container components (columns, divider, container, etc).
        
        Returns:
            CSS string containing container theme styles
        """
        return UITemplates.get_containers_theme()

    @staticmethod
    def load_for_expanders() -> str:
        """
        Load CSS themed for expander components.
        
        Returns:
            CSS string containing expander theme styles
        """
        return UITemplates.get_expanders_theme()

    @staticmethod
    def load_for_buttons() -> str:
        """
        Load CSS themed for button components (st.button, st.checkbox, etc).
        
        Returns:
            CSS string containing button theme styles
        """
        return UITemplates.get_buttons_theme()

    @staticmethod
    def load_for_messages() -> str:
        """
        Load CSS themed for message components (st.info, st.warning, st.error, st.success).
        
        Returns:
            CSS string containing message theme styles
        """
        return UITemplates.get_messages_theme()

    @staticmethod
    def load_for_html_content() -> str:
        """
        Load CSS themed for rendered HTML content (posts, comments, etc).
        
        Returns:
            CSS string containing HTML content theme styles
        """
        return UITemplates.get_html_content_theme()

    @staticmethod
    def load_for_combined_input() -> str:
        """
        Load CSS themed for combined dropdown-input component.
        
        Returns:
            CSS string containing combined input theme styles
        """
        return UITemplates.get_combined_input_theme()

    @staticmethod
    def load_for_tabs() -> str:
        """
        Load CSS themed for tabs component.
        
        Returns:
            CSS string containing tabs theme styles
        """
        return UITemplates.get_tabs_theme()

    # ========== LAZY-LOAD METHODS FOR UNUSED CONTROLS ==========
    # Use these to load CSS for controls only when they're actually used

    @staticmethod
    def load_for_radio() -> str:
        """Load CSS themed for radio button components (lazy-load)."""
        return UITemplates.get_radio_theme()

    @staticmethod
    def load_for_multiselect() -> str:
        """Load CSS themed for multi-select components (lazy-load)."""
        return UITemplates.get_multiselect_theme()

    @staticmethod
    def load_for_slider() -> str:
        """Load CSS themed for slider components (lazy-load)."""
        return UITemplates.get_slider_theme()

    @staticmethod
    def load_for_number_input() -> str:
        """Load CSS themed for number input components (lazy-load)."""
        return UITemplates.get_number_input_theme()

    @staticmethod
    def load_for_date_input() -> str:
        """Load CSS themed for date input components (lazy-load)."""
        return UITemplates.get_date_input_theme()

    @staticmethod
    def load_for_time_input() -> str:
        """Load CSS themed for time input components (lazy-load)."""
        return UITemplates.get_time_input_theme()

    @staticmethod
    def load_for_file_uploader() -> str:
        """Load CSS themed for file uploader components (lazy-load)."""
        return UITemplates.get_file_uploader_theme()

    @staticmethod
    def load_for_metric() -> str:
        """Load CSS themed for metric display components (lazy-load)."""
        return UITemplates.get_metric_theme()

    @staticmethod
    def load_for_color_picker() -> str:
        """Load CSS themed for color picker components (lazy-load)."""
        return UITemplates.get_color_picker_theme()

    @staticmethod
    def load_all_unused_controls() -> str:
        """
        Load CSS for all unused controls as a bundle.
        Use this in pages that might use multiple unused control types.
        
        Returns:
            Combined CSS string for all unused control themes
        """
        return UITemplates.load_unused_controls_theme()

    # ========== ENHANCEMENT TEMPLATES ==========

    @staticmethod
    def load_for_grouped_options() -> str:
        """Load CSS for grouped options styling (search/grouped controls)."""
        return UITemplates.get_grouped_options_styles()

    @staticmethod
    def load_for_searchable_selectbox() -> str:
        """Load CSS and templates for searchable selectbox functionality."""
        return PageCSSLoader.compose(
            UITemplates.get_inputs_theme(),
            UITemplates.get_grouped_options_styles()
        )

    @staticmethod
    def load_all_enhancements() -> str:
        """Load all enhancement templates (search, grouping, etc.)."""
        return UITemplates.load_enhancement_templates()

    # ========== CONVENIENCE METHODS ==========

    @staticmethod
    def load_core_themes() -> str:
        """
        Load only core control themes (currently used controls).
        Excludes unused control themes for faster initial load.
        Includes: buttons, inputs, messages, containers, tabs, expanders, text, HTML content.
        
        Returns:
            Combined CSS string for core themes
        """
        return PageCSSLoader.compose(
            UITemplates.get_theme_variables(),
            UITemplates.get_text_theme(),
            UITemplates.get_buttons_theme(),
            UITemplates.get_inputs_theme(),
            UITemplates.get_containers_theme(),
            UITemplates.get_tabs_theme(),
            UITemplates.get_expanders_theme(),
            UITemplates.get_messages_theme(),
            UITemplates.get_data_display_theme(),
            UITemplates.get_html_content_theme(),
            UITemplates.get_third_party_theme(),
        )

    @staticmethod
    def load_all_themes() -> str:
        """
        Load ALL themes for all 19 control types.
        WARNING: Large bundle. Use only for apps that use many control types.
        Prefer load_core_themes() or selective lazy-loading.
        
        Returns:
            Combined CSS string for all themes
        """
        return UITemplates.load_all_control_themes()

    @staticmethod
    def compose(*css_parts: str) -> str:
        """
        Compose multiple CSS strings into a single CSS block.
        Useful when a page needs multiple component themes.
        
        Args:
            *css_parts: Variable number of CSS strings to compose
            
        Returns:
            Combined CSS string
        """
        return "\n".join(part for part in css_parts if part)

    @staticmethod
    def apply_to_page(*css_parts: str) -> None:
        """
        Apply composed CSS to the current Streamlit page.
        Convenience method that combines css parts and applies via st.markdown().
        
        Args:
            *css_parts: Variable number of CSS strings to apply
        """
        import streamlit as st
        
        combined_css = PageCSSLoader.compose(*css_parts)
        if combined_css:
            st.markdown(f"<style>{combined_css}</style>", unsafe_allow_html=True)
