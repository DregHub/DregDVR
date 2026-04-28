"""
Uploader Configuration Tab
Handles YouTube auth file configuration for instances.
"""

import streamlit as st
import json
from typing import Optional, Dict, Any
from utils.ui_db_helpers import UIDBHelpers
from ui.components import (
    enhanced_button,
    enhanced_info,
    enhanced_error,
    enhanced_success,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_uploader_tab(instance: Optional[Dict[str, Any]]):
    """
    Uploader configuration tab.
    Handles YouTube auth file configuration.

    Args:
        instance: Instance dict or None
    """
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_inputs(), PageCSSLoader.load_for_buttons()
    )

    if not instance:
        enhanced_info(
            "No instance selected. Select or create an instance to configure."
        )
        return

    _show_uploader_configuration(instance)


def _show_uploader_configuration(instance: Dict[str, Any]):
    """
    Show uploader configuration form.

    Args:
        instance: Instance dict
    """
    instance_name = instance["instance_name"]

    st.markdown("### YouTube Auth Files")
    st.markdown("Configure YouTube authentication files for this instance.")

    # Get current content from database
    db = UIDBHelpers.get_db()
    client_secret_content = UIDBHelpers._run_async(db.get_yt_client_secret_content(instance_name)) or ""
    oauth2_content = UIDBHelpers._run_async(db.get_yt_oauth2_content(instance_name)) or ""

    # Create two columns for side-by-side layout
    col_client, col_oauth = st.columns(2, gap="large")

    with col_client:
        st.markdown("#### Client Secret (client_secret.json)")
        client_secret_input = st.text_area(
            "Client Secret JSON",
            value=client_secret_content,
            height=300,
            key=f"client_secret_{instance_name}",
            help="Paste the JSON content from your Google API client_secret.json file",
        )

        if st.button("Save Client Secret", key=f"save_client_{instance_name}"):
            try:
                # Validate JSON
                json.loads(client_secret_input)
                db_write_indicator(
                    "Saving client secret",
                    UIDBHelpers._run_async,
                    db.set_yt_client_secret_content(instance_name, client_secret_input)
                )
                enhanced_success("Client Secret saved successfully!")
                st.rerun()
            except json.JSONDecodeError as e:
                enhanced_error(f"Invalid JSON: {e}")
            except Exception as e:
                enhanced_error(f"Failed to save: {e}")

    with col_oauth:
        st.markdown("#### OAuth2 Credentials (oauth2.json)")
        oauth2_input = st.text_area(
            "OAuth2 JSON",
            value=oauth2_content,
            height=300,
            key=f"oauth2_{instance_name}",
            help="Paste the JSON content from your OAuth2 credentials file",
        )

        if st.button("Save OAuth2 Credentials", key=f"save_oauth_{instance_name}"):
            try:
                # Validate JSON
                json.loads(oauth2_input)
                db_write_indicator(
                    "Saving OAuth2 credentials",
                    UIDBHelpers._run_async,
                    db.set_yt_oauth2_content(instance_name, oauth2_input)
                )
                enhanced_success("OAuth2 Credentials saved successfully!")
                st.rerun()
            except json.JSONDecodeError as e:
                enhanced_error(f"Invalid JSON: {e}")
            except Exception as e:
                enhanced_error(f"Failed to save: {e}")

    # Status information
    st.markdown("---")
    st.markdown("### Status")

    status_col1, status_col2 = st.columns(2)

    with status_col1:
        if client_secret_content:
            enhanced_success("Client Secret: Configured")
        else:
            enhanced_info("Client Secret: Not configured")

    with status_col2:
        if oauth2_content:
            enhanced_success("OAuth2 Credentials: Configured")
        else:
            enhanced_info("OAuth2 Credentials: Not configured")
