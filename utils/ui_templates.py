"""UI Templates Loader - Manages dynamic loading of UI templates using TemplateManager."""

import json
import os
import asyncio
from utils.template_manager import TemplateManager


class UITemplates:
    """Centralized UI templates loader for Streamlit UI components."""

    _manager = None
    _templates_cache = {}

    @classmethod
    def _get_manager(cls):
        """Lazy-initialize TemplateManager for UI templates."""
        if cls._manager is None:
            template_dir = os.path.join(
                os.path.dirname(__file__), "..", "templates", "ui"
            )
            
            templates_config = {
                # instances.py templates
                "instances_aggrid_styles": os.path.join(
                    template_dir, "instances_aggrid_styles.json"
                ),
                # app.py templates
                "app_hide_elements_styles": os.path.join(
                    template_dir, "app_hide_elements_styles.css"
                ),
                "app_navbar_styles": os.path.join(
                    template_dir, "app_navbar_styles.json"
                ),
                "app_navbar_shadow_styles": os.path.join(
                    template_dir, "app_navbar_shadow_styles.css"
                ),
                "app_navbar_3d_enhance": os.path.join(
                    template_dir, "app_navbar_3d_enhance.js"
                ),
                # Glass-morphism theme variables and core components
                "app_theme_variables": os.path.join(
                    template_dir, "app_theme_variables.css"
                ),
                "app_text_theme": os.path.join(
                    template_dir, "app_text_theme.css"
                ),
                "app_buttons_theme": os.path.join(
                    template_dir, "app_buttons_theme.css"
                ),
                "app_inputs_theme": os.path.join(
                    template_dir, "app_inputs_theme.css"
                ),
                "app_containers_theme": os.path.join(
                    template_dir, "app_containers_theme.css"
                ),
                "app_tabs_theme": os.path.join(
                    template_dir, "app_tabs_theme.css"
                ),
                "app_expanders_theme": os.path.join(
                    template_dir, "app_expanders_theme.css"
                ),
                "app_messages_theme": os.path.join(
                    template_dir, "app_messages_theme.css"
                ),
                "app_data_display_theme": os.path.join(
                    template_dir, "app_data_display_theme.css"
                ),
                "app_third_party_theme": os.path.join(
                    template_dir, "app_third_party_theme.css"
                ),
                "app_html_content_theme": os.path.join(
                    template_dir, "app_html_content_theme.css"
                ),
                "app_combined_input_theme": os.path.join(
                    template_dir, "app_combined_input_theme.css"
                ),
                # Themes for unused controls (lazy-loaded)
                "app_radio_theme": os.path.join(
                    template_dir, "app_radio_theme.css"
                ),
                "app_multiselect_theme": os.path.join(
                    template_dir, "app_multiselect_theme.css"
                ),
                "app_slider_theme": os.path.join(
                    template_dir, "app_slider_theme.css"
                ),
                "app_number_input_theme": os.path.join(
                    template_dir, "app_number_input_theme.css"
                ),
                "app_date_input_theme": os.path.join(
                    template_dir, "app_date_input_theme.css"
                ),
                "app_time_input_theme": os.path.join(
                    template_dir, "app_time_input_theme.css"
                ),
                "app_file_uploader_theme": os.path.join(
                    template_dir, "app_file_uploader_theme.css"
                ),
                "app_metric_theme": os.path.join(
                    template_dir, "app_metric_theme.css"
                ),
                "app_color_picker_theme": os.path.join(
                    template_dir, "app_color_picker_theme.css"
                ),
                # Enhancement templates for searchable/grouped controls
                "selectbox_search_wrapper": os.path.join(
                    template_dir, "selectbox_search_wrapper.html"
                ),
                "selectbox_search_script": os.path.join(
                    template_dir, "selectbox_search_script.js"
                ),
                "grouped_options_styles": os.path.join(
                    template_dir, "grouped_options_styles.css"
                ),
                # components.py templates
                "components_text_input_script": os.path.join(
                    template_dir, "components_text_input_script.js"
                ),
                "components_forbidden_chars_script": os.path.join(
                    template_dir, "components_forbidden_chars_script.js"
                ),
                "components_combined_input_wrapper": os.path.join(
                    template_dir, "components_combined_input_wrapper.html"
                ),
                "components_combined_labels": os.path.join(
                    template_dir, "components_combined_labels.html"
                ),
                # Loading overlay templates
                "loading_overlay_css": os.path.join(
                    template_dir, "loading_overlay.css"
                ),
                "loading_overlay_html": os.path.join(
                    template_dir, "loading_overlay.html"
                ),
                "loading_overlay_js": os.path.join(
                    template_dir, "loading_overlay.js"
                ),
            }
            
            cls._manager = TemplateManager(
                templates=templates_config,
                base_path=template_dir,
            )
        
        return cls._manager

    @classmethod
    def load_templates_sync(cls):
        """Load all templates synchronously (blocking)."""
        if not cls._templates_cache:
            manager = cls._get_manager()
            try:
                # Run async loader in event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def load_with_registration():
                    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager
                    try:
                        AsyncioLifecycleManager.register_loop(loop, loop_name="ui_templates")
                    except Exception as e:
                        print(f"Failed to register UI templates event loop: {e}")
                    return await manager.load_templates()

                cls._templates_cache = loop.run_until_complete(load_with_registration())
                loop.close()
            except RuntimeError:
                # If event loop already exists, use it
                async def run_with_registration():
                    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager
                    loop = asyncio.get_running_loop()
                    try:
                        AsyncioLifecycleManager.register_loop(loop, loop_name="ui_templates_fallback")
                    except Exception as e:
                        print(f"Failed to register UI templates fallback event loop: {e}")
                    return await manager.load_templates()
                cls._templates_cache = asyncio.run(run_with_registration())

        return cls._templates_cache

    @classmethod
    def get_aggrid_styles(cls) -> dict:
        """
        Get AgGrid custom CSS styles loaded from template.

        Returns:
            Dictionary of AgGrid CSS styles, or empty dict if loading fails.
        """
        cls.load_templates_sync()
        styles_json = cls._templates_cache.get("instances_aggrid_styles", "{}")
        
        try:
            return json.loads(styles_json)
        except json.JSONDecodeError:
            return {}

    @classmethod
    def get_template(cls, template_name: str) -> str:
        """
        Get raw template content by name.

        Args:
            template_name: Name of the template (without extension).

        Returns:
            Template content as string.
        """
        cls.load_templates_sync()
        return cls._templates_cache.get(template_name, "")

    @classmethod
    def get_app_hide_elements_css(cls) -> str:
        """Get CSS for hiding Streamlit elements (header, sidebar, etc)."""
        return cls.get_template("app_hide_elements_styles")

    @classmethod
    def get_app_navbar_styles(cls) -> dict:
        """Get navbar styles dictionary loaded from template."""
        styles_json = cls.get_template("app_navbar_styles")
        try:
            return json.loads(styles_json)
        except json.JSONDecodeError:
            return {}

    @classmethod
    def get_app_navbar_shadow_css(cls) -> str:
        """Get CSS for navbar iframe shadow styling."""
        return cls.get_template("app_navbar_shadow_styles")

    @classmethod
    def get_app_navbar_3d_enhance_js(cls) -> str:
        """Get JavaScript for 3D glass morphism navbar enhancement."""
        return cls.get_template("app_navbar_3d_enhance")

    @classmethod
    def get_theme_variables(cls) -> str:
        """Get CSS custom properties for glass-morphism theme."""
        return cls.get_template("app_theme_variables")

    @classmethod
    def get_text_theme(cls) -> str:
        """Get CSS for text components (headers, paragraphs, captions, etc)."""
        return cls.get_template("app_text_theme")

    @classmethod
    def get_buttons_theme(cls) -> str:
        """Get CSS for button components."""
        return cls.get_template("app_buttons_theme")

    @classmethod
    def get_inputs_theme(cls) -> str:
        """Get CSS for input components (text_input, selectbox, text_area)."""
        return cls.get_template("app_inputs_theme")

    @classmethod
    def get_containers_theme(cls) -> str:
        """Get CSS for container components (container, columns, divider)."""
        return cls.get_template("app_containers_theme")

    @classmethod
    def get_tabs_theme(cls) -> str:
        """Get CSS for tabs component."""
        return cls.get_template("app_tabs_theme")

    @classmethod
    def get_expanders_theme(cls) -> str:
        """Get CSS for expander components."""
        return cls.get_template("app_expanders_theme")

    @classmethod
    def get_messages_theme(cls) -> str:
        """Get CSS for message components (info, success, warning, error)."""
        return cls.get_template("app_messages_theme")

    @classmethod
    def get_data_display_theme(cls) -> str:
        """Get CSS for data display components (AgGrid, DataFrame)."""
        return cls.get_template("app_data_display_theme")

    @classmethod
    def get_third_party_theme(cls) -> str:
        """Get CSS for third-party components (tree_select, st_navbar)."""
        return cls.get_template("app_third_party_theme")

    @classmethod
    def get_html_content_theme(cls) -> str:
        """Get CSS for rendered HTML content (posts, comments)."""
        return cls.get_template("app_html_content_theme")

    @classmethod
    def get_combined_input_theme(cls) -> str:
        """Get CSS for combined dropdown-input component."""
        return cls.get_template("app_combined_input_theme")

    @classmethod
    def get_components_text_input_script(cls) -> str:
        """Get JavaScript for text input key press handling."""
        return cls.get_template("components_text_input_script")

    @classmethod
    def get_components_forbidden_chars_script(cls) -> str:
        """Get JavaScript for forbidden character filtering."""
        return cls.get_template("components_forbidden_chars_script")

    @classmethod
    def get_components_combined_input_wrapper(cls) -> str:
        """Get HTML for combined input wrapper container."""
        return cls.get_template("components_combined_input_wrapper")

    @classmethod
    def get_components_combined_labels(cls) -> str:
        """Get HTML for combined input labels."""
        return cls.get_template("components_combined_labels")

    # ========== LOADING OVERLAY TEMPLATES ==========

    @classmethod
    def get_loading_overlay_css(cls) -> str:
        """Get CSS for loading overlay component."""
        return cls.get_template("loading_overlay_css")

    @classmethod
    def get_loading_overlay_html(cls) -> str:
        """Get HTML structure for loading overlay."""
        return cls.get_template("loading_overlay_html")

    @classmethod
    def get_loading_overlay_js(cls) -> str:
        """Get JavaScript for loading overlay control."""
        return cls.get_template("loading_overlay_js")

    # ========== LAZY-LOADED THEMES FOR UNUSED CONTROLS ==========
    # These themes are registered but not loaded globally; use PageCSSLoader
    # or load_unused_controls_theme() to load them only when needed.

    @classmethod
    def get_radio_theme(cls) -> str:
        """Get CSS for radio button components."""
        return cls.get_template("app_radio_theme")

    @classmethod
    def get_multiselect_theme(cls) -> str:
        """Get CSS for multi-select components."""
        return cls.get_template("app_multiselect_theme")

    @classmethod
    def get_slider_theme(cls) -> str:
        """Get CSS for slider and select-slider components."""
        return cls.get_template("app_slider_theme")

    @classmethod
    def get_number_input_theme(cls) -> str:
        """Get CSS for number input components."""
        return cls.get_template("app_number_input_theme")

    @classmethod
    def get_date_input_theme(cls) -> str:
        """Get CSS for date input components."""
        return cls.get_template("app_date_input_theme")

    @classmethod
    def get_time_input_theme(cls) -> str:
        """Get CSS for time input components."""
        return cls.get_template("app_time_input_theme")

    @classmethod
    def get_file_uploader_theme(cls) -> str:
        """Get CSS for file uploader components."""
        return cls.get_template("app_file_uploader_theme")

    @classmethod
    def get_metric_theme(cls) -> str:
        """Get CSS for metric display components."""
        return cls.get_template("app_metric_theme")

    @classmethod
    def get_color_picker_theme(cls) -> str:
        """Get CSS for color picker components."""
        return cls.get_template("app_color_picker_theme")

    # ========== ENHANCEMENT TEMPLATES ==========

    @classmethod
    def get_selectbox_search_wrapper(cls) -> str:
        """Get HTML wrapper for searchable selectbox functionality."""
        return cls.get_template("selectbox_search_wrapper")

    @classmethod
    def get_selectbox_search_script(cls) -> str:
        """Get JavaScript for client-side selectbox search/filtering."""
        return cls.get_template("selectbox_search_script")

    @classmethod
    def get_grouped_options_styles(cls) -> str:
        """Get CSS for grouped options styling across controls."""
        return cls.get_template("grouped_options_styles")

    # ========== CONVENIENCE METHODS FOR LAZY LOADING ==========

    @classmethod
    def load_unused_controls_theme(cls) -> str:
        """
        Load CSS for all unused controls as a bundle.
        Use this in pages that may use multiple unused controls.

        Returns:
            Combined CSS string for all unused control themes.
        """
        return (
            cls.get_radio_theme() +
            cls.get_multiselect_theme() +
            cls.get_slider_theme() +
            cls.get_number_input_theme() +
            cls.get_date_input_theme() +
            cls.get_time_input_theme() +
            cls.get_file_uploader_theme() +
            cls.get_metric_theme() +
            cls.get_color_picker_theme()
        )

    @classmethod
    def load_enhancement_templates(cls) -> str:
        """
        Load CSS for all enhancement templates (search/grouping support).
        Use this when using searchable_selectbox, grouped_selectbox, etc.

        Returns:
            Combined CSS string for all enhancement templates.
        """
        return (
            cls.get_grouped_options_styles()
        )

    @classmethod
    def load_all_control_themes(cls) -> str:
        """
        Load ALL themes for all 19 control types.
        WARNING: This is a large bundle. Prefer using PageCSSLoader
        or load_unused_controls_theme() for specific subsets.

        Returns:
            Combined CSS string for all themes.
        """
        return (
            cls.get_theme_variables() +
            cls.get_buttons_theme() +
            cls.get_inputs_theme() +
            cls.get_messages_theme() +
            cls.load_unused_controls_theme() +
            cls.load_enhancement_templates()
        )
