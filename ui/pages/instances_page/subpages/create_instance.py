"""
Create Instance Form
Handles new instance creation.
"""

import streamlit as st
from utils.ui_db_helpers import UIDBHelpers
from db.log_db import LogDB
from ui.components import (
    combined_dropdown_input,
    enhanced_checkbox,
    enhanced_selectbox,
    enhanced_button,
    enhanced_error,
    enhanced_success,
    async_operation,
    db_write_indicator,
)
from ui.css_loader import PageCSSLoader


def show_create_instance_form():
    """Show form to create a new instance."""
    # Load page-specific CSS themes
    PageCSSLoader.apply_to_page(
        PageCSSLoader.load_for_combined_input(),
        PageCSSLoader.load_for_inputs(),
        PageCSSLoader.load_for_buttons(),
    )

    st.write("Create a new DVR instance to manage a channel")

    # Show existing instances with start button
    all_instances = UIDBHelpers.get_all_instances()

    if all_instances:
        st.divider()
        st.subheader("Manage Instances")

        for instance in all_instances:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📺 {instance['instance_name']}")
            with col2:
                if st.button(
                    "▶️ Start",
                    key=f"start_instance_{instance['instance_name']}",
                    use_container_width=True,
                ):
                    try:
                        import asyncio
                        from dvr_main import DVRMain

                        dvr = DVRMain()
                        async_operation(
                            f"Starting instance: {instance['instance_name']}",
                            asyncio.run,
                            dvr.run_instance(instance["instance_name"]),
                        )
                        enhanced_success(
                            f"Started instance: {instance['instance_name']}"
                        )
                    except Exception as e:
                        enhanced_error(f"Error starting instance: {str(e)}")
        st.divider()

    # Initialize individual session state keys for new instance creation
    if "dvr_create_instance_dvr_data_in_other" not in st.session_state:
        st.session_state["dvr_create_instance_dvr_data_in_other"] = False

    if "dvr_create_instance_dvr_data_other_instance_name" not in st.session_state:
        st.session_state["dvr_create_instance_dvr_data_other_instance_name"] = ""

    # Use a temporary ID for form keys (since instance doesn't exist yet)
    form_key_id = "new_instance"

    # Platform dropdown and channel name input
    platforms = ["YouTube.com/@", "Twitch.com/@"]

    # Map platform display names to database values
    platform_names = {
        "YouTube.com/@": "youtube",
        "Twitch.com/@": "twitch"
    }

    selected_platform, channel_input = combined_dropdown_input(
        dropdown_options=platforms,
        dropdown_key=f"platform_select_{form_key_id}",
        input_key=f"channel_input_{form_key_id}",
        dropdown_label="Platform",
        input_label="Channel Name",
        input_placeholder="Enter channel name (e.g., @channelname)",
        dropdown_ratio=0.25,
    )

    # Instance name input (separate from channel name)
    instance_name_input = st.text_input(
        "Instance Name",
        placeholder="Enter instance name (e.g., MyChannelInstance)",
        key=f"instance_name_input_{form_key_id}",
    )

    # Generate channel_id from channel name (remove @ prefix if present)
    channel_id = channel_input.replace("@", "") if channel_input else ""

    # Validate inputs
    create_enabled = bool(
        channel_id
        and instance_name_input
        and instance_name_input.replace("_", "").replace("-", "").isalnum()
    )

    # Get existing instances to show in selector
    existing_instance_names = [inst["instance_name"] for inst in all_instances]
    show_instance_selector = len(existing_instance_names) > 1

    # Show checkbox for using data from another instance only if there are multiple instances
    if show_instance_selector:
        st.divider()
        st.subheader("Use Data from Another Instance")

        enhanced_checkbox(
            "Store DVR data in another instance",
            key="dvr_create_instance_dvr_data_in_other",
        )

        if st.session_state["dvr_create_instance_dvr_data_in_other"]:
            enhanced_selectbox(
                "Select instance to store data in",
                options=existing_instance_names,
                key="dvr_create_instance_dvr_data_other_instance_name",
            )
        else:
            st.session_state["dvr_create_instance_dvr_data_other_instance_name"] = ""

    col1, col2 = st.columns([1, 1])

    with col1:
        submit_clicked = enhanced_button(
            "✅ Create Instance",
            type="primary",
            use_container_width=True,
            disabled=not create_enabled,
        )

    if not create_enabled and instance_name_input:
        st.caption(
            "⚠️ Instance name can only contain letters, numbers, hyphens, and underscores"
        )

    # Handle button click (outside any form context)
    if submit_clicked:
        if not instance_name_input:
            enhanced_error("Instance name is required")
        elif not channel_id:
            enhanced_error("Channel name is required")
        elif not instance_name_input.replace("_", "").replace("-", "").isalnum():
            enhanced_error(
                "Instance name can only contain letters, numbers, hyphens, and underscores"
            )
        else:
            try:
                db = UIDBHelpers.get_db()

                # Add instance with loading indicator
                channel_id_result = db_write_indicator(
                    "Creating instance in database",
                    UIDBHelpers._run_async,
                    db.add_instance(
                        channel_id=channel_id,
                        instance_name=instance_name_input,
                        channel_name=channel_input,
                        source_platform=platform_names.get(selected_platform, selected_platform),
                        dvr_data_in_other_instance=st.session_state[
                            "dvr_create_instance_dvr_data_in_other"
                        ],
                        dvr_data_other_instance_name=(
                            st.session_state[
                                "dvr_create_instance_dvr_data_other_instance_name"
                            ]
                            if st.session_state["dvr_create_instance_dvr_data_in_other"]
                            else None
                        ),
                    ),
                )

                # Create playlist table and entry for the new instance
                channel_source = channel_input
                db = UIDBHelpers.get_db()

                # Ensure playlist table exists with loading indicator
                db_write_indicator(
                    "Creating playlist table",
                    lambda: UIDBHelpers._run_async(
                        db.ensure_playlist_table_exists(
                            instance_name_input, channel_source
                        )
                    ),
                )

                # Create playlist entry with loading indicator
                db_write_indicator(
                    "Creating playlist entries",
                    lambda: UIDBHelpers._run_async(
                        db.update_playlists(
                            channel_id=channel_id,
                            instance_name=instance_name_input,
                            download_playlist_name=db.get_playlist_download_table_name(
                                channel_source
                            ),
                            upload_playlist_name=db.get_playlist_upload_table_name(
                                channel_source
                            ),
                        )
                    ),
                )

                # Create initial index entry with loading indicator
                db_write_indicator(
                    "Creating index entries",
                    lambda: UIDBHelpers._run_async(
                        db.create_initial_index_entry(
                            instance_name=instance_name_input,
                            live_index=1,
                            posted_index=1
                        )
                    ),
                )

                # Set the selected instance to automatically switch to channel configuration tab
                st.session_state.selected_instance_name = instance_name_input
                enhanced_success(
                    f"Instance '{instance_name_input}' created successfully!"
                )

                # Clear form state for next use
                if "dvr_create_instance_dvr_data_in_other" in st.session_state:
                    del st.session_state["dvr_create_instance_dvr_data_in_other"]
                if (
                    "dvr_create_instance_dvr_data_other_instance_name"
                    in st.session_state
                ):
                    del st.session_state[
                        "dvr_create_instance_dvr_data_other_instance_name"
                    ]

                # Rerun to automatically switch to channel configuration tab
                st.rerun()
            except Exception as e:
                enhanced_error(f"Error creating instance: {str(e)}")
