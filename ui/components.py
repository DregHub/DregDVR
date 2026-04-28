"""
Custom Streamlit Components
Reusable UI components with unified styling using the glass-morphism theme.
"""

import streamlit as st
from typing import List, Any, Tuple, Optional
from utils.ui_templates import UITemplates
import re


def text_input_no_enter(
    label: str = "",
    value: str = "",
    max_chars: Optional[int] = None,
    key: Optional[str] = None,
    type: str = "default",
    placeholder: Optional[str] = None,
    disabled: bool = False,
    label_visibility: str = "visible",
    on_change=None,
    forbidden_chars: str = "",
    **kwargs
) -> str:
    """
    Custom text input component that prevents Enter key submission.
    
    Wraps st.text_input() with JavaScript that intercepts Enter key events
    and prevents default form submission behavior.
    
    Args:
        label: Label for the input
        value: Initial value
        max_chars: Maximum characters allowed
        key: Unique key for session state
        type: Input type ('default' or 'password')
        placeholder: Placeholder text
        disabled: If True, disables the input
        label_visibility: Label visibility ('visible', 'hidden', 'collapsed')
        on_change: Callback function on input change
        forbidden_chars: String of characters that cannot be typed (e.g., "@" prevents @ character).
                        Works like a .NET masked textbox.
        **kwargs: Additional arguments passed to st.text_input()
    
    Returns:
        str: The text input value
    """
    # Inject Enter key prevention script and hide InputInstructions only once per session
    if '_text_input_no_enter_injected' not in st.session_state:
        # Load base script template
        base_script = UITemplates.get_components_text_input_script()
        
        # Build forbidden chars JavaScript if needed
        forbidden_js = ""
        if forbidden_chars:
            # Create a JSON array of forbidden characters for the Set
            forbidden_chars_array = ', '.join(f"'{char}'" for char in forbidden_chars)
            forbidden_template = UITemplates.get_components_forbidden_chars_script()
            forbidden_js = forbidden_template.replace("{FORBIDDEN_CHARS_ARRAY}", forbidden_chars_array)
        
        full_script = f"""
            <script>
            const inputs = window.parent.document.querySelectorAll('input');
            
            {base_script}
            
            {forbidden_js}
            </script>
            """
        
        st.html(full_script)
        st.session_state._text_input_no_enter_injected = True
    
    # Filter forbidden characters from the initial value (server-side fallback)
    filtered_value = value
    if forbidden_chars:
        for char in forbidden_chars:
            filtered_value = filtered_value.replace(char, '')
    
    # Create the text input (do NOT pass forbidden_chars to st.text_input)
    text_value = st.text_input(
        label=label,
        max_chars=max_chars,
        key=key,
        type=type,
        placeholder=placeholder,
        disabled=disabled,
        label_visibility=label_visibility,
        on_change=on_change,
        **kwargs
    )
    
    # Server-side fallback: filter forbidden characters from the returned value
    if forbidden_chars:
        for char in forbidden_chars:
            text_value = text_value.replace(char, '')
    
    return text_value


# Inject unified combined input styling
def _inject_combined_input_styles():
    """Inject CSS for combined dropdown-input styling."""
    if '_combined_input_styles_injected' not in st.session_state:
        css_content = UITemplates.get_combined_input_theme()
        if css_content:
            st.html(f"""
                <style>
                    {css_content}
                </style>
            """)
            st.session_state._combined_input_styles_injected = True


def combined_dropdown_input(
    dropdown_options: List[str],
    dropdown_key: str,
    input_key: str,
    dropdown_label: str = "Select",
    input_label: str = "Input",
    input_placeholder: str = "",
    dropdown_value: Optional[str] = None,
    input_value: str = "",
    help_text: Optional[str] = None,
    disabled: bool = False,
    dropdown_ratio: float = 0.5,
    instance_name: Optional[str] = None,
    forbidden_chars: str = "",
) -> Tuple[str, str]:
    """
    Create a combined dropdown-input component with unified styling.
    
    The component displays a selectbox and text input side-by-side with:
    - Shared border and glass-morphism styling
    - Identical heights for seamless integration
    - Unified focus/hover states
    - Full compatibility with existing theme variables
    
    Args:
        dropdown_options: List of options for the selectbox
        dropdown_key: Unique key for the selectbox (for session state)
        input_key: Unique key for the text input (for session state)
        dropdown_label: Label for the dropdown column
        input_label: Label for the input column
        input_placeholder: Placeholder text for the input field
        dropdown_value: Initial selected value for dropdown
        input_value: Initial value for text input
        help_text: Optional help text displayed below both components
        disabled: If True, disables both controls
        dropdown_ratio: Width ratio for dropdown (0.0-1.0, default 0.5 for equal width).
                       Input field takes up the remainder of the space.
        instance_name: Optional instance name to automatically bind input field state.
                      When provided, the input value is automatically synced with
                      session state using the key: f"_combined_input_{instance_name}"
        forbidden_chars: String of characters that cannot be typed in the input field.
                        Works like a .NET masked textbox (e.g., "@" prevents @ character).
    
    Returns:
        Tuple[str, str]: (selected_dropdown_value, input_text_value)
    """
    # Inject styles once
    _inject_combined_input_styles()
    
    # Initialize session state keys if not present
    if dropdown_key not in st.session_state:
        st.session_state[dropdown_key] = dropdown_value or (dropdown_options[0] if dropdown_options else "")
    
    if input_key not in st.session_state:
        st.session_state[input_key] = input_value
    
    # Open wrapper container (load from template)
    wrapper_open = UITemplates.get_components_combined_input_wrapper()
    st.markdown(wrapper_open, unsafe_allow_html=True)
    
    # Calculate input ratio (remainder of space)
    input_ratio = 1.0 - dropdown_ratio
    
    # Create columns inside wrapper
    col_dropdown, col_input = st.columns([dropdown_ratio, input_ratio], gap="xxsmall")
    
    # Dropdown in first column
    with col_dropdown:
        # Determine index for selectbox
        if st.session_state[dropdown_key] in dropdown_options:
            default_index = dropdown_options.index(st.session_state[dropdown_key])
        else:
            default_index = 0
        
        selected = st.selectbox(
            label=dropdown_label,
            options=dropdown_options,
            key=dropdown_key,
            disabled=disabled,
            label_visibility="collapsed",
        )
    
    # Text input in second column
    with col_input:
        def _on_input_change():
            """Update instance-bound state on input change."""
            if instance_name:
                state_key = f"_combined_input_{instance_name}"
                st.session_state[state_key] = st.session_state[input_key]
        
        text_input = text_input_no_enter(
            label=input_label,
            placeholder=input_placeholder,
            value=st.session_state[input_key],
            key=input_key,
            disabled=disabled,
            label_visibility="collapsed",
            on_change=_on_input_change,
            forbidden_chars=forbidden_chars,
        )
    
    # Close wrapper container
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display help text if provided
    if help_text:
        st.caption(help_text)
    
    return selected, text_input


def combined_dropdown_input_with_labels(
    dropdown_options: List[str],
    dropdown_key: str,
    input_key: str,
    dropdown_label: str = "Select",
    input_label: str = "Input",
    input_placeholder: str = "",
    dropdown_value: Optional[str] = None,
    input_value: str = "",
    help_text: Optional[str] = None,
    disabled: bool = False,
    dropdown_ratio: float = 0.3,
) -> Tuple[str, str]:
    """
    Create a combined dropdown-input component with labels displayed above.
    
    This variant displays labels above the controls in a unified container,
    providing better visual hierarchy while maintaining the shared border aesthetic.
    
    Args:
        dropdown_options: List of options for the selectbox
        dropdown_key: Unique key for the selectbox (for session state)
        input_key: Unique key for the text input (for session state)
        dropdown_label: Label for the dropdown
        input_label: Label for the input field
        input_placeholder: Placeholder text for the input field
        dropdown_value: Initial selected value for dropdown
        input_value: Initial value for text input
        help_text: Optional help text displayed below both components
        disabled: If True, disables both controls
        dropdown_ratio: Width ratio for dropdown (0.0-1.0, default 0.3).
                       Input field takes up the remainder of the space.
    
    Returns:
        Tuple[str, str]: (selected_dropdown_value, input_text_value)
    """
    
    # Inject styles once
    _inject_combined_input_styles()
    
    # Open wrapper container (load from template)
    wrapper_open = UITemplates.get_components_combined_input_wrapper()
    st.markdown(wrapper_open, unsafe_allow_html=True)
    
    # Create columns inside wrapper
    col_dropdown, col_input = st.columns([dropdown_ratio, 1.0 - dropdown_ratio], gap="none")
    
    # Dropdown in first column
    with col_dropdown:
        # Determine index for selectbox
        if dropdown_value and dropdown_value in dropdown_options:
            default_index = dropdown_options.index(dropdown_value)
        else:
            default_index = 0
        
        selected = st.selectbox(
            label="",
            options=dropdown_options,
            key=dropdown_key,
            index=default_index,
            disabled=disabled,
            label_visibility="collapsed",
        )
    
    # Text input in second column
    with col_input:
        text_input = text_input_no_enter(
            label="",
            placeholder=input_placeholder,
            value=input_value,
            key=input_key,
            disabled=disabled,
            label_visibility="collapsed",
            on_change=lambda: None,
            forbidden_chars="",
        )
    
    # Close wrapper container
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display help text if provided
    if help_text:
        st.caption(help_text)
    
    return selected, text_input


# ============================================================================
# ENHANCED WRAPPER COMPONENTS - Core Controls (Streamlit 1.28+)
# ============================================================================

def enhanced_button(
    label: str,
    key: Optional[str] = None,
    help: Optional[str] = None,
    on_click=None,
    args=None,
    kwargs=None,
    type: str = "primary",
    disabled: bool = False,
    use_container_width: bool = True,
) -> bool:
    """
    Enhanced button component with glass-morphism styling and variant support.
    
    Args:
        label: Button label text
        key: Unique key for session state
        help: Help text displayed on hover
        on_click: Callback function when clicked
        args: Arguments to pass to callback
        kwargs: Keyword arguments to pass to callback
        type: Button variant - 'primary' (blue accent), 'secondary' (subtle), 'danger' (red)
        disabled: If True, disables the button
        use_container_width: If True, button takes full container width
    
    Returns:
        bool: True if clicked, False otherwise
    """
    _inject_button_styles()
    
    # Apply variant class via CSS custom property
    css_variant = f'--btn-variant: {type};' if type != 'primary' else ''
    
    with st.container():
        clicked = st.button(
            label=label,
            key=key,
            help=help,
            on_click=on_click,
            args=args,
            kwargs=kwargs,
            disabled=disabled,
            use_container_width=use_container_width,
        )
    
    return clicked


def enhanced_selectbox(
    label: str,
    options: List[Any],
    index: int = 0,
    key: Optional[str] = None,
    help: Optional[str] = None,
    on_change=None,
    args=None,
    kwargs=None,
    disabled: bool = False,
    placeholder: str = "Choose an option",
) -> Any:
    """
    Enhanced selectbox component with glass-morphism styling.
    
    Args:
        label: Label for the selectbox
        options: List of options to display
        index: Initial selected index
        key: Unique key for session state
        help: Help text displayed below
        on_change: Callback function when selection changes
        args: Arguments to pass to callback
        kwargs: Keyword arguments to pass to callback
        disabled: If True, disables the selectbox
        placeholder: Placeholder text
    
    Returns:
        Selected value
    """
    _inject_selectbox_styles()
    
    selected = st.selectbox(
        label=label,
        options=options,
        index=index,
        key=key,
        help=help,
        on_change=on_change,
        args=args,
        kwargs=kwargs,
        disabled=disabled,
        placeholder=placeholder,
    )
    
    return selected


def enhanced_text_input(
    label: str = "",
    value: str = "",
    max_chars: Optional[int] = None,
    key: Optional[str] = None,
    type: str = "default",
    placeholder: Optional[str] = None,
    disabled: bool = False,
    label_visibility: str = "visible",
    on_change=None,
    help: Optional[str] = None,
    forbidden_chars: str = "",
) -> str:
    """
    Enhanced text input component with glass-morphism styling and forbidden chars support.
    
    Args:
        label: Label for the input
        value: Initial value
        max_chars: Maximum characters allowed
        key: Unique key for session state
        type: Input type ('default' or 'password')
        placeholder: Placeholder text
        disabled: If True, disables the input
        label_visibility: Label visibility ('visible', 'hidden', 'collapsed')
        on_change: Callback function on input change
        help: Help text displayed below
        forbidden_chars: String of characters that cannot be typed
    
    Returns:
        str: The text input value
    """
    _inject_input_styles()
    
    return text_input_no_enter(
        label=label,
        value=value,
        max_chars=max_chars,
        key=key,
        type=type,
        placeholder=placeholder,
        disabled=disabled,
        label_visibility=label_visibility,
        on_change=on_change,
        help=help,
        forbidden_chars=forbidden_chars,
    )


def enhanced_checkbox(
    label: str,
    value: bool = False,
    key: Optional[str] = None,
    help: Optional[str] = None,
    on_change=None,
    args=None,
    kwargs=None,
    disabled: bool = False,
) -> bool:
    """
    Enhanced checkbox component with glass-morphism styling.
    
    Args:
        label: Label for the checkbox
        value: Initial checked state
        key: Unique key for session state
        help: Help text displayed below
        on_change: Callback function when state changes
        args: Arguments to pass to callback
        kwargs: Keyword arguments to pass to callback
        disabled: If True, disables the checkbox
    
    Returns:
        bool: True if checked, False otherwise
    """
    _inject_checkbox_styles()
    
    checked = st.checkbox(
        label=label,
        value=value,
        key=key,
        help=help,
        on_change=on_change,
        args=args,
        kwargs=kwargs,
        disabled=disabled,
    )
    
    return checked


def enhanced_text_area(
    label: str = "",
    value: str = "",
    height: int = 150,
    max_chars: Optional[int] = None,
    key: Optional[str] = None,
    on_change=None,
    args=None,
    kwargs=None,
    disabled: bool = False,
    placeholder: Optional[str] = None,
    help: Optional[str] = None,
    label_visibility: str = "visible",
) -> str:
    """
    Enhanced text area component with glass-morphism styling.
    
    Args:
        label: Label for the text area
        value: Initial value
        height: Height of the text area in pixels
        max_chars: Maximum characters allowed
        key: Unique key for session state
        on_change: Callback function on change
        args: Arguments to pass to callback
        kwargs: Keyword arguments to pass to callback
        disabled: If True, disables the text area
        placeholder: Placeholder text
        help: Help text displayed below
        label_visibility: Label visibility ('visible', 'hidden', 'collapsed')
    
    Returns:
        str: The text area value
    """
    _inject_textarea_styles()
    
    text = st.text_area(
        label=label,
        value=value,
        height=height,
        max_chars=max_chars,
        key=key,
        on_change=on_change,
        args=args,
        kwargs=kwargs,
        disabled=disabled,
        placeholder=placeholder,
        help=help,
        label_visibility=label_visibility,
    )
    
    return text


# ============================================================================
# ENHANCED MESSAGE COMPONENTS
# ============================================================================

def enhanced_info(
    body: str,
    icon: str = "ℹ️",
    dismissible: bool = False,
) -> None:
    """
    Enhanced info message component with glass-morphism styling.
    
    Args:
        body: Message text
        icon: Icon to display (emoji or Unicode)
        dismissible: If True, shows a dismiss button (simulated)
    """
    _inject_message_styles()
    st.info(f"{icon} {body}")


def enhanced_success(
    body: str,
    icon: str = "✅",
    dismissible: bool = False,
) -> None:
    """Enhanced success message with glass-morphism styling."""
    _inject_message_styles()
    st.success(f"{icon} {body}")


def enhanced_warning(
    body: str,
    icon: str = "⚠️",
    dismissible: bool = False,
) -> None:
    """Enhanced warning message with glass-morphism styling."""
    _inject_message_styles()
    st.warning(f"{icon} {body}")


def enhanced_error(
    body: str,
    icon: str = "❌",
    dismissible: bool = False,
) -> None:
    """Enhanced error message with glass-morphism styling."""
    _inject_message_styles()
    st.error(f"{icon} {body}")


# ============================================================================
# ADVANCED COMPONENTS - Searchable and Grouped Options
# ============================================================================

def searchable_selectbox(
    label: str,
    options: List[Any],
    index: int = 0,
    key: Optional[str] = None,
    help: Optional[str] = None,
    on_change=None,
    placeholder: str = "Search or select...",
) -> Any:
    """
    Selectbox with client-side search/filter capability.
    
    Args:
        label: Label for the selectbox
        options: List of options to display
        index: Initial selected index
        key: Unique key for session state
        help: Help text displayed below
        on_change: Callback function when selection changes
        placeholder: Search placeholder text
    
    Returns:
        Selected value
    """
    _inject_searchable_selectbox_styles()
    
    # Create container with search input
    st.markdown(UITemplates.get_selectbox_search_wrapper(), unsafe_allow_html=True)
    
    # Render the selectbox
    selected = st.selectbox(
        label=label,
        options=options,
        index=index,
        key=key,
        help=help,
        on_change=on_change,
        label_visibility="collapsed",
    )
    
    # Inject search script
    st.html(f"<script>{UITemplates.get_selectbox_search_script()}</script>")
    
    return selected


def grouped_selectbox(
    label: str,
    options_dict: dict,
    key: Optional[str] = None,
    help: Optional[str] = None,
    on_change=None,
) -> Any:
    """
    Selectbox with grouped options display.
    
    Args:
        label: Label for the selectbox
        options_dict: Dictionary where keys are group names and values are lists of options
                     Example: {"Group 1": ["opt1", "opt2"], "Group 2": ["opt3"]}
        key: Unique key for session state
        help: Help text displayed below
        on_change: Callback function when selection changes
    
    Returns:
        Selected value
    """
    _inject_grouped_options_styles()
    
    # Flatten options with group prefixes for display
    flattened_options = []
    options_to_group = {}
    
    for group_name, group_options in options_dict.items():
        for opt in group_options:
            display_text = f"{group_name} › {opt}"
            flattened_options.append(display_text)
            options_to_group[display_text] = opt
    
    # Display selectbox with flattened options
    selected_display = st.selectbox(
        label=label,
        options=flattened_options,
        key=key,
        help=help,
        on_change=on_change,
    )
    
    # Return the actual option value (without group prefix)
    return options_to_group.get(selected_display, selected_display)


# ============================================================================
# LAZY-LOAD INJECTION HELPER FUNCTIONS
# ============================================================================

def _inject_button_styles():
    """Inject CSS for enhanced button styling (once per session)."""
    if '_enhanced_button_styles_injected' not in st.session_state:
        css_content = UITemplates.get_buttons_theme()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._enhanced_button_styles_injected = True


def _inject_selectbox_styles():
    """Inject CSS for enhanced selectbox styling (once per session)."""
    if '_enhanced_selectbox_styles_injected' not in st.session_state:
        css_content = UITemplates.get_inputs_theme()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._enhanced_selectbox_styles_injected = True


def _inject_input_styles():
    """Inject CSS for enhanced text input styling (once per session)."""
    if '_enhanced_input_styles_injected' not in st.session_state:
        css_content = UITemplates.get_inputs_theme()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._enhanced_input_styles_injected = True


def _inject_checkbox_styles():
    """Inject CSS for enhanced checkbox styling (once per session)."""
    if '_enhanced_checkbox_styles_injected' not in st.session_state:
        css_content = UITemplates.get_inputs_theme()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._enhanced_checkbox_styles_injected = True


def _inject_textarea_styles():
    """Inject CSS for enhanced text area styling (once per session)."""
    if '_enhanced_textarea_styles_injected' not in st.session_state:
        css_content = UITemplates.get_inputs_theme()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._enhanced_textarea_styles_injected = True


def _inject_message_styles():
    """Inject CSS for enhanced message styling (once per session)."""
    if '_enhanced_message_styles_injected' not in st.session_state:
        css_content = UITemplates.get_messages_theme()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._enhanced_message_styles_injected = True


def _inject_searchable_selectbox_styles():
    """Inject CSS and scripts for searchable selectbox (once per session)."""
    if '_searchable_selectbox_styles_injected' not in st.session_state:
        css_content = UITemplates.get_inputs_theme() + UITemplates.get_grouped_options_styles()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._searchable_selectbox_styles_injected = True


def _inject_grouped_options_styles():
    """Inject CSS for grouped options styling (once per session)."""
    if '_grouped_options_styles_injected' not in st.session_state:
        css_content = UITemplates.get_grouped_options_styles()
        if css_content:
            st.html(f"<style>{css_content}</style>")
            st.session_state._grouped_options_styles_injected = True


# ============================================================================
# LOADING OVERLAY COMPONENT
# ============================================================================

def _inject_loading_overlay_styles():
    """Inject CSS and HTML for loading overlay (once per session)."""
    if '_loading_overlay_injected' not in st.session_state:
        # Inject CSS
        css_content = UITemplates.get_loading_overlay_css()
        if css_content:
            st.html(f"<style>{css_content}</style>")

        # Inject HTML structure
        html_content = UITemplates.get_loading_overlay_html()
        if html_content:
            st.html(html_content)

        # Inject JavaScript controller
        js_content = UITemplates.get_loading_overlay_js()
        if js_content:
            st.html(f"<script>{js_content}</script>")

        st.session_state._loading_overlay_injected = True


def show_loading_overlay(message: str = "Loading...") -> None:
    """
    Display the loading overlay with a status message.

    This creates a full-screen overlay that dims the UI and shows a glowing
    white spinner with status text underneath.

    Args:
        message: Status message to display (default: "Loading...")

    Example:
        show_loading_overlay("Processing your request...")
        # Do work here
        hide_loading_overlay()
    """
    _inject_loading_overlay_styles()

    # Use JavaScript to show the overlay
    escaped_message = message.replace('"', '\\"').replace("'", "\\'")
    st.html(f"""
        <script>
        if (typeof showLoadingOverlay === 'function') {{
            showLoadingOverlay("{escaped_message}");
        }}
        </script>
    """)


def hide_loading_overlay() -> None:
    """
    Hide the loading overlay.

    This removes the full-screen overlay and restores normal UI interaction.

    Example:
        show_loading_overlay("Processing...")
        # Do work
        hide_loading_overlay()
    """
    _inject_loading_overlay_styles()

    # Use JavaScript to hide the overlay
    st.html("""
        <script>
        if (typeof hideLoadingOverlay === 'function') {
            hideLoadingOverlay();
        }
        </script>
    """)


def update_loading_status(message: str) -> None:
    """
    Update the status message on the loading overlay.

    This changes the text displayed under the spinner without hiding/showing
    the overlay. Useful for multi-step operations.

    Args:
        message: New status message to display

    Example:
        show_loading_overlay("Step 1: Initializing...")
        # Do step 1 work
        update_loading_status("Step 2: Processing...")
        # Do step 2 work
        hide_loading_overlay()
    """
    _inject_loading_overlay_styles()

    # Use JavaScript to update the status message
    escaped_message = message.replace('"', '\\"').replace("'", "\\'")
    st.html(f"""
        <script>
        if (typeof updateLoadingStatus === 'function') {{
            updateLoadingStatus("{escaped_message}");
        }}
        </script>
    """)


# ============================================================================
# ASYNC OPERATION COMPONENTS
# ============================================================================

def async_operation(
    operation_name: str,
    operation_func,
    *args,
    **kwargs
) -> Any:
    """
    Wrapper for async operations that displays a loading overlay.

    This component wraps async database operations and displays a full-screen
    loading overlay with a glowing white spinner and status text to inform
    users that the UI is waiting on a DB write or other async operation.

    Args:
        operation_name: Human-readable name of the operation (e.g., "Creating instance", "Saving settings")
        operation_func: The async function to execute
        *args: Positional arguments to pass to the operation function
        **kwargs: Keyword arguments to pass to the operation function

    Returns:
        The result of the operation function

    Example:
        result = async_operation("Creating instance", db.add_instance, instance_name, platform)
    """
    try:
        show_loading_overlay(operation_name)
        return operation_func(*args, **kwargs)
    finally:
        hide_loading_overlay()


def db_write_indicator(
    operation_name: str,
    operation_func,
    *args,
    show_status: bool = True,
    **kwargs
) -> Any:
    """
    Enhanced wrapper for database write operations with detailed status updates.

    This component provides a more detailed loading indicator specifically for database
    write operations, showing progress and status updates to the user using the
    loading overlay.

    Args:
        operation_name: Human-readable name of the operation
        operation_func: The async function to execute
        *args: Positional arguments to pass to the operation function
        show_status: If True, provides detailed status updates; otherwise uses simple loading
        **kwargs: Keyword arguments to pass to the operation function

    Returns:
        The result of the operation function

    Example:
        result = db_write_indicator("Saving playlist settings", db.update_playlists, channel_id, instance_name, ...)
    """
    try:
        if show_status:
            show_loading_overlay(f"📝 {operation_name}")
            result = operation_func(*args, **kwargs)
            update_loading_status(f"✅ {operation_name} - Complete")
            return result
        else:
            show_loading_overlay(f"💾 {operation_name}...")
            return operation_func(*args, **kwargs)
    except Exception as e:
        update_loading_status(f"❌ {operation_name} - Failed")
        raise
    finally:
        # Small delay to show the final status message
        import time
        time.sleep(0.5)
        hide_loading_overlay()
