import asyncio
import json
import random
import re
import time
import os
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from utils.logging_utils import LogManager
from utils.template_manager import TemplateManager


class PlaywrightUtils:
    # TemplateManager instance for JS scripts and configuration files
    # Resolve base path relative to this file's directory
    _base_path = os.path.dirname(os.path.abspath(__file__))
    _parent_path = os.path.dirname(_base_path)
    
    template_manager = TemplateManager({
        'log_upload_percent': 'templates/playwright_log_upload_percent.js',
        'block_media_loading': 'templates/playwright_block_media_loading.js',
        'mask_webdriver': 'templates/playwright_mask_webdriver.js',
        'wait_for_upload_progress': 'templates/playwright_wait_for_upload_progress.js',
        'wait_for_navigation': 'templates/playwright_wait_for_navigation.js',
        'launch_args': 'templates/playwright_launch_args.json',
        'viewport': 'templates/playwright_viewport.json',
        'headers': 'templates/playwright_headers.json',
        'console_log_filter_rumble': 'templates/console_log_filter_rumble.txt',
        'console_log_filter_odysee': 'templates/console_log_filter_odysee.txt',
        'console_log_filter_bitchute': 'templates/console_log_filter_bitchute.txt',
    }, base_path=_parent_path)

    # Cached config values
    _launch_args_cache = None
    _user_agent_cache = None
    _viewport_cache = None
    _headers_cache = None

    @staticmethod
    async def _load_config():
        """Load all configuration files from template manager."""
        await PlaywrightUtils.template_manager.load_templates()

        if PlaywrightUtils._launch_args_cache is None:
            launch_args_json = PlaywrightUtils.template_manager.get_template('launch_args')
            if launch_args_json:
                try:
                    PlaywrightUtils._launch_args_cache = json.loads(launch_args_json)
                except json.JSONDecodeError as e:
                    raise ValueError(f"launch_args template contains invalid JSON: {e}")
            else:
                raise ValueError("launch_args template is empty or not found")

        if PlaywrightUtils._viewport_cache is None:
            viewport_json = PlaywrightUtils.template_manager.get_template('viewport')
            if viewport_json:
                try:
                    PlaywrightUtils._viewport_cache = json.loads(viewport_json)
                except json.JSONDecodeError as e:
                    raise ValueError(f"viewport template contains invalid JSON: {e}")
            else:
                raise ValueError("viewport template is empty or not found")

        if PlaywrightUtils._headers_cache is None:
            headers_json = PlaywrightUtils.template_manager.get_template('headers')
            if headers_json:
                try:
                    PlaywrightUtils._headers_cache = json.loads(headers_json)
                except json.JSONDecodeError as e:
                    raise ValueError(f"headers template contains invalid JSON: {e}")
            else:
                raise ValueError("headers template is empty or not found")

    @staticmethod
    async def get_launch_args():
        """Get default launch arguments from config file."""
        if PlaywrightUtils._launch_args_cache is None:
            await PlaywrightUtils._load_config()
        return PlaywrightUtils._launch_args_cache

 

    @staticmethod
    async def get_viewport():
        """Get default viewport from config file."""
        if PlaywrightUtils._viewport_cache is None:
            await PlaywrightUtils._load_config()
        return PlaywrightUtils._viewport_cache

    @staticmethod
    async def get_headers():
        """Get default headers from config file."""
        if PlaywrightUtils._headers_cache is None:
            await PlaywrightUtils._load_config()
        return PlaywrightUtils._headers_cache

    @staticmethod
    async def random_delay(min_ms: int = 500, max_ms: int = 2000) -> None:
        """
        Add a random human-like delay between actions.

        Args:
            min_ms: Minimum delay in milliseconds (default: 500)
            max_ms: Maximum delay in milliseconds (default: 2000)
        """
        delay = random.uniform(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    @staticmethod
    async def launch_stealth_browser(
        headless: bool = True,
        launch_args: list = None,
        **kwargs
    ) -> Browser:
        """
        Launch a Chromium browser with stealth options to avoid detection.

        Args:
            headless: Whether to run in headless mode (default: True)
            launch_args: Additional launch arguments (uses defaults if None)
            **kwargs: Additional arguments passed to chromium.launch()

        Returns:
            Browser instance
        """
        p = await async_playwright().start()

        args = launch_args or await PlaywrightUtils.get_launch_args()

        browser = await p.chromium.launch(
            headless=headless,
            args=args,
            **kwargs
        )
        # Keep the playwright instance available for proper shutdown.
        try:
            browser._playwright_instance = p
        except Exception:
            pass
        return browser

    @staticmethod
    async def create_human_context(
        browser: Browser,
        user_agent: str = None,
        viewport: dict = None,
        headers: dict = None,
        **kwargs
    ) -> BrowserContext:
        """
        Create a browser context with human-like settings to avoid bot detection.
        Includes locale, timezone, and realistic device properties.

        Args:
            browser: Browser instance
            user_agent: User agent string (uses default if None)
            viewport: Viewport dimensions dict (uses default if None)
            headers: HTTP headers dict (uses default if None)
            **kwargs: Additional arguments passed to new_context()

        Returns:
            BrowserContext instance
        """
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport=viewport or await PlaywrightUtils.get_viewport(),
            extra_http_headers=headers or await PlaywrightUtils.get_headers(),
            locale='en-US',
            timezone_id='America/New_York',
            geolocation={'latitude': 40.7128, 'longitude': -74.0060},
            permissions=['geolocation'],
            device_scale_factor=1,
            bypass_csp=True,
            ignore_https_errors=True,
            **kwargs
        )
        return context

    @staticmethod
    async def mask_webdriver(page: Page) -> None:
        """
        Mask webdriver detection by hiding bot detection signals and spoofing browser properties.
        Comprehensive anti-detection for Cloudflare and other bot detection systems.

        Args:
            page: Page instance
        """
        await PlaywrightUtils.template_manager.load_templates()
        js_code = PlaywrightUtils.template_manager.get_template('mask_webdriver')
        await page.add_init_script(js_code)

    @staticmethod
    async def fill_form_field(
        page: Page,
        selector: str,
        value: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600
    ) -> None:
        """
        Fill a form field with human-like delays.

        Args:
            page: Page instance
            selector: CSS selector or Playwright locator
            value: Value to fill
            min_delay_ms: Minimum delay between actions
            max_delay_ms: Maximum delay between actions
        """
        await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
        await page.locator(selector).fill(value)

    @staticmethod
    async def click_element(
        page: Page,
        selector: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        suppress_exceptions: bool = False
    ) -> None:
        """
        Click an element with human-like delays.

        Args:
            page: Page instance
            selector: CSS selector or Playwright locator
            min_delay_ms: Minimum delay before click
            max_delay_ms: Maximum delay before click
            suppress_exceptions: If True, suppress exceptions instead of throwing them
        """
        await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
        try:
            await page.locator(selector).click()
        except Exception as e:
            if not suppress_exceptions:
                raise

    @staticmethod
    async def press_key(
        page: Page,
        key: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600
    ) -> None:
        """
        Press a keyboard key with human-like delays.

        Args:
            page: Page instance
            key: Key to press (e.g., "Enter", "Tab")
            min_delay_ms: Minimum delay before key press
            max_delay_ms: Maximum delay before key press
        """
        await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
        await page.keyboard.press(key)

    @staticmethod
    async def setup_console_logging(
        page: Page,
        log_callback=None
    ) -> None:
        """
        Set up console message capture from browser to logging system.

        Args:
            page: Page instance
            log_callback: Function to call with console messages.
                Should accept (msg_type, msg_text) parameters.
        """
        def handle_console_msg(msg):
            if log_callback:
                log_callback(msg.type.upper(), msg.text)

        page.on("console", handle_console_msg)

    @staticmethod
    def should_log_console_message(msg_text, filter_strings):
        """Return whether a Playwright console message should be logged."""
        if not msg_text:
            return True

        # Always filter out known noisy resource errors.
        if "ERR_CONNECTION_REFUSED" in msg_text or "Failed to load resource" in msg_text:
            return False

        if filter_strings:
            return not any(filter_value in msg_text for filter_value in filter_strings)

        return True

    @staticmethod
    async def get_console_log_filter(platform: str) -> list:
        """Load a platform-specific console log filter from templates."""
        await PlaywrightUtils.template_manager.load_templates()
        template_key = f"console_log_filter_{platform}"
        raw_filter = PlaywrightUtils.template_manager.get_template(template_key)
        if raw_filter is None:
            return []
        return [line.strip() for line in raw_filter.splitlines() if line.strip()]

    @staticmethod
    async def create_console_log_callback(
        log_file=None,
        platform=None,
        log_to_console=True
    ):
        """Create a reusable Playwright console logging callback with filtering."""
        filter_strings = []
        if platform:
            filter_strings = await PlaywrightUtils.get_console_log_filter(platform)

        def console_log(msg_type, msg_text):
            msg_text = msg_text or ""
            if not PlaywrightUtils.should_log_console_message(msg_text, filter_strings):
                return

            message = f"[Console/{msg_type}] {msg_text}"
            if log_to_console:
                print(message)
            if log_file:
                LogManager.log_message(message, log_file)

        return console_log

    @staticmethod
    async def check_cloudflare(
        page: Page,
        log_callback=None
    ) -> bool:
        """
        Check and handle Cloudflare challenge or error detection.
        Automatically waits for challenge resolution with multiple attempts.

        Args:
            page: Page instance
            log_callback: Function to call for logging. Should accept a string message.

        Returns:
            True if Cloudflare challenge/error detected, False otherwise
        """
        try:
            detected = False

            # Check page title and content for Cloudflare challenge
            title = await page.title()

            if "Just a moment" in title or "challenge" in title.lower():
                if log_callback:
                    log_callback(f"Cloudflare challenge detected (title: '{title}'). Waiting for automatic resolution...")

                detected = True

                # Wait MUCH longer for Cloudflare's JavaScript challenge to solve itself
                max_wait_time = 120  # 2 minutes total
                wait_interval = 5  # Check every 5 seconds
                elapsed = 0

                while elapsed < max_wait_time:
                    try:
                        # Get current title and wait for it to change
                        await page.wait_for_load_state('networkidle', timeout=10000)
                        new_title = await page.title()

                        if new_title != title and "Just a moment" not in new_title:
                            if log_callback:
                                log_callback(f"Cloudflare challenge resolved! Title changed from '{title}' to '{new_title}'")
                            detected = False
                            return detected

                        if log_callback:
                            log_callback(f"Still waiting for Cloudflare challenge... ({elapsed}s/{max_wait_time}s)")

                        await asyncio.sleep(wait_interval)
                        elapsed += wait_interval

                    except Exception as e:
                        if log_callback:
                            log_callback(f"Cloudflare wait attempt: {str(e)[:100]}")
                        await asyncio.sleep(wait_interval)
                        elapsed += wait_interval

                if elapsed >= max_wait_time:
                    if log_callback:
                        log_callback("WARNING: Cloudflare challenge did not resolve within 2 minutes. Continuing anyway...")

                # Check for Cloudflare error messages
                try:
                    page_content = await page.content()
                    if 'Error 1020' in page_content or 'Error 1010' in page_content or 'Error 1030' in page_content:
                        if log_callback:
                            log_callback("WARNING: Cloudflare error page detected (1020/1010/1030). Waiting before retry...")
                        await asyncio.sleep(10)
                        detected = True
                except:
                    pass

            return detected

        except Exception as e:
            if log_callback:
                log_callback(f"Cloudflare check error: {e}")
            return False

    @staticmethod
    async def wait_for_upload_progress(
        page: Page,
        progress_selector: str,
        timeout_ms: int = 1800000,  # 30 minutes default
        log_callback=None,
        progress_callback=None,
        completion_strings: dict = None,
        ignored_strings: str = "uploading"
    ) -> None:
        """
        Wait for upload progress to reach completion by monitoring element text.

        Args:
            page: Page instance
            progress_selector: CSS selector for progress bar element
            timeout_ms: Timeout in milliseconds
            log_callback: Function to call for logging progress updates
            progress_callback: Function to call with progress updates
            completion_strings: Dict of strings that indicate completion (case insensitive)
            ignored_strings: Substring to remove from progress text if present (case insensitive check)
        """
        if completion_strings is None:
            completion_strings = {"100": None, "Complete": None}

        # Wait for progress element to be visible
        progress_locator = page.locator(progress_selector)
        await progress_locator.wait_for(state='visible', timeout=timeout_ms)

        start_time = time.time()
        last_logged_percent = -5  # Start below 0 to ensure first log
        while True:
            try:
                # Extract progress text
                progress_text = await progress_locator.inner_text()
                
                # Remove ignored strings if present (case insensitive)
                if ignored_strings.lower() in progress_text.lower():
                    progress_text = re.sub(re.escape(ignored_strings), '', progress_text, flags=re.IGNORECASE)
                
                # Extract percentage for logging control
                percent_match = re.search(r'(\d+)', progress_text)
                current_percent = int(percent_match.group(1)) if percent_match else 0
                
                # Only log progress every 5% change
                if progress_callback and current_percent - last_logged_percent >= 5:
                    progress_callback(progress_text)
                    last_logged_percent = current_percent

                # Check for completion strings (case insensitive)
                if any(key.lower() in progress_text.lower() for key in completion_strings):
                    if log_callback:
                        log_callback(f"Upload progress reached completion: {progress_text}")
                    break

            except Exception as e:
                if log_callback:
                    log_callback(f"Error checking progress: {e}")

            # Check for timeout
            elapsed_time = (time.time() - start_time) * 1000
            if elapsed_time > timeout_ms:
                if log_callback:
                    log_callback("Timeout waiting for upload progress to complete")
                break

            await asyncio.sleep(1)

    @staticmethod
    async def wait_for_element(
        page: Page,
        selector: str,
        timeout_ms: int = 30000,
        state: str = 'visible',
        log_callback=None
    ) -> None:
        """
        Wait for an element to appear or reach a specific state.

        Args:
            page: Page instance
            selector: CSS selector for the element
            timeout_ms: Timeout in milliseconds
            state: State to wait for ('visible', 'hidden', 'attached', 'detached')
            log_callback: Function to call for logging
        """
        try:
            locator = page.locator(selector)
            await locator.wait_for(state=state, timeout=timeout_ms)
            if log_callback:
                log_callback(f"Element '{selector}' reached state '{state}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error waiting for element '{selector}': {e}")
            raise

    @staticmethod
    async def wait_for_element_by_id(
        page: Page,
        element_id: str,
        timeout_ms: int = 30000,
        state: str = 'visible',
        log_callback=None
    ) -> None:
        """
        Wait for an element by ID to appear or reach a specific state.

        Args:
            page: Page instance
            element_id: ID of the element
            timeout_ms: Timeout in milliseconds
            state: State to wait for ('visible', 'hidden', 'attached', 'detached')
            log_callback: Function to call for logging
        """
        selector = f'#{element_id}'
        await PlaywrightUtils.wait_for_element(page, selector, timeout_ms, state, log_callback)

    @staticmethod
    async def wait_for_element_by_name(
        page: Page,
        name: str,
        timeout_ms: int = 30000,
        state: str = 'visible',
        log_callback=None
    ) -> None:
        """
        Wait for an element by name attribute to appear or reach a specific state.

        Args:
            page: Page instance
            name: Name attribute of the element
            timeout_ms: Timeout in milliseconds
            state: State to wait for ('visible', 'hidden', 'attached', 'detached')
            log_callback: Function to call for logging
        """
        selector = f'[name="{name}"]'
        await PlaywrightUtils.wait_for_element(page, selector, timeout_ms, state, log_callback)

    @staticmethod
    async def wait_for_element_by_type_and_innertext(
        page: Page,
        element_type: str,
        inner_text: str,
        timeout_ms: int = 30000,
        state: str = 'visible',
        log_callback=None
    ) -> None:
        """
        Wait for an element by tag type and inner text to appear or reach a specific state.

        Args:
            page: Page instance
            element_type: HTML tag type (e.g., 'h2', 'div', 'span')
            inner_text: Inner text content of the element
            timeout_ms: Timeout in milliseconds
            state: State to wait for ('visible', 'hidden', 'attached', 'detached')
            log_callback: Function to call for logging
        """
        selector = f'{element_type}:has-text("{inner_text}")'
        await PlaywrightUtils.wait_for_element(page, selector, timeout_ms, state, log_callback)

    @staticmethod
    async def wait_for_text(
        page: Page,
        text: str,
        timeout_ms: int = 30000,
        log_callback=None
    ) -> None:
        """
        Wait for specific text to appear on the page.

        Args:
            page: Page instance
            text: Text to wait for
            timeout_ms: Timeout in milliseconds
            log_callback: Function to call for logging
        """
        try:
            await page.wait_for_selector(f'text="{text}"', timeout=timeout_ms)
            if log_callback:
                log_callback(f"Text '{text}' appeared on page")
        except Exception as e:
            if log_callback:
                log_callback(f"Error waiting for text '{text}': {e}")
            raise

    @staticmethod
    async def check_checkbox(
        page: Page,
        selector: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        timeout_ms: int = 120000,
        log_callback=None
    ) -> None:
        """
        Check a checkbox with human-like delays.

        Args:
            page: Page instance
            selector: CSS selector for the checkbox input
            min_delay_ms: Minimum delay before action
            max_delay_ms: Maximum delay before action
            timeout_ms: Timeout in milliseconds for locator ops
            log_callback: Function to call for logging
        """
        locator = page.locator(selector)
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)

            # Wait for element to be attached (not necessarily visible)
            if log_callback:
                log_callback(f"Waiting for checkbox '{selector}' to be attached...")
            await locator.wait_for(state='attached', timeout=timeout_ms)

            # Check if it's visible
            is_visible = await locator.is_visible()
            if not is_visible and log_callback:
                log_callback(f"Checkbox '{selector}' is hidden, attempting to check anyway...")

            # If already checked, return early.
            try:
                is_checked = await locator.is_checked(timeout=30000)
                if is_checked:
                    if log_callback:
                        log_callback(f"Checkbox '{selector}' already checked")
                    return
            except Exception as check_error:
                if log_callback:
                    log_callback(f"Could not determine checkbox state for '{selector}': {check_error}. Attempting to check anyway...")

            try:
                await locator.check(timeout=timeout_ms)
            except Exception as check_error:
                # Fallback to click for sites with non-standard checkbox controls.
                if log_callback:
                    log_callback(f"Check failed, trying click: {str(check_error)[:100]}")
                await locator.click(timeout=timeout_ms)

            if log_callback:
                log_callback(f"Checked checkbox '{selector}'")

        except Exception as e:
            if log_callback:
                log_callback(f"Error checking checkbox '{selector}': {e}")
            raise

    @staticmethod
    async def click_through_element(
        page: Page,
        selector: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Click an element and wait for any page navigation/reload.

        Args:
            page: Page instance
            selector: CSS selector for the element to click
            min_delay_ms: Minimum delay before click
            max_delay_ms: Maximum delay before click
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            # Use Promise.all to handle potential navigation
            await PlaywrightUtils.template_manager.load_templates()
            js_code = PlaywrightUtils.template_manager.get_template('wait_for_navigation')
            await page.evaluate(js_code)
            await page.locator(selector).click()
            await PlaywrightUtils.random_delay(500, 1000)
            if log_callback:
                log_callback(f"Clicked element '{selector}'")
        except Exception as e:
            # Don't log/raise navigation errors, they're expected
            if "timeout" not in str(e).lower():
                if log_callback:
                    log_callback(f"Clicked element '{selector}' (navigation completed or in progress)")

    @staticmethod
    async def block_media_loading(page: Page) -> None:
        """
        Block media (video/audio) resources from loading to speed up page navigation.
        
        Args:
            page: Page instance
        """
        await PlaywrightUtils.template_manager.load_templates()
        js_code = PlaywrightUtils.template_manager.get_template('block_media_loading')
        await page.add_init_script(js_code)

    @staticmethod
    async def goto(
        page: Page,
        url: str,
        wait_until: str = "load",
        timeout: int = 30000,
        log_callback=None
    ) -> bool:
        """
        Navigate to a URL with error handling.
        
        Args:
            page: Page instance
            url: URL to navigate to
            wait_until: Wait condition ("load", "domcontentloaded", "networkidle")
            timeout: Timeout in milliseconds
            log_callback: Function to call for logging
            
        Returns:
            True if navigation succeeded, False otherwise
        """
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"Navigation to {url} failed: {str(e)[:100]}")
            return False

    @staticmethod
    async def wait_for_load_state(
        page: Page,
        state: str = "load",
        timeout: int = 30000,
        log_callback=None
    ) -> None:
        """
        Wait for page to reach a specific load state.
        
        Args:
            page: Page instance
            state: Load state ("load", "domcontentloaded", "networkidle")
            timeout: Timeout in milliseconds
            log_callback: Function to call for logging
        """
        try:
            await page.wait_for_load_state(state, timeout=timeout)
            if log_callback:
                log_callback(f"Page reached '{state}' state")
        except Exception as e:
            if log_callback:
                log_callback(f"Error waiting for load state '{state}': {str(e)[:100]}")

    @staticmethod
    async def fill_form_input_by_name(
        page: Page,
        name: str,
        value: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Fill a form input field by name attribute with human-like delays.
        
        Args:
            page: Page instance
            name: Name attribute of the input
            value: Value to fill
            min_delay_ms: Minimum delay before action
            max_delay_ms: Maximum delay before action
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            locator = page.locator(f'input[name="{name}"], textarea[name="{name}"], select[name="{name}"]')
            await locator.fill(value)
            if log_callback:
                log_callback(f"Filled form field '{name}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error filling form field '{name}': {e}")
            raise

    @staticmethod
    async def fill_form_textarea_by_name(
        page: Page,
        name: str,
        value: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Fill a form textarea field by name attribute with human-like delays.
        
        Args:
            page: Page instance
            name: Name attribute of the textarea
            value: Value to fill
            min_delay_ms: Minimum delay before action
            max_delay_ms: Maximum delay before action
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            locator = page.locator(f'textarea[name="{name}"]')
            await locator.fill(value)
            if log_callback:
                log_callback(f"Filled textarea field '{name}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error filling textarea field '{name}': {e}")
            raise

    @staticmethod
    async def fill_form_input_by_id(
        page: Page,
        element_id: str,
        value: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Fill a form input field by ID with human-like delays.
        
        Args:
            page: Page instance
            element_id: ID of the input element
            value: Value to fill
            min_delay_ms: Minimum delay before action
            max_delay_ms: Maximum delay before action
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            locator = page.locator(f'#{element_id}')
            await locator.fill(value)
            if log_callback:
                log_callback(f"Filled form field with ID '{element_id}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error filling form field with ID '{element_id}': {e}")
            raise

    @staticmethod
    async def fill_form_textarea_by_id(
        page: Page,
        element_id: str,
        value: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Fill a form textarea field by ID with human-like delays.
        
        Args:
            page: Page instance
            element_id: ID of the textarea element
            value: Value to fill
            min_delay_ms: Minimum delay before action
            max_delay_ms: Maximum delay before action
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            locator = page.locator(f'#{element_id}')
            await locator.fill(value)
            if log_callback:
                log_callback(f"Filled textarea field with ID '{element_id}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error filling textarea field with ID '{element_id}': {e}")
            raise

    @staticmethod
    async def click_element_by_name(
        page: Page,
        name: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Click an element by name attribute with human-like delays.
        
        Args:
            page: Page instance
            name: Name attribute of the element
            min_delay_ms: Minimum delay before click
            max_delay_ms: Maximum delay before click
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            locator = page.locator(f'[name="{name}"]')
            await locator.click()
            if log_callback:
                log_callback(f"Clicked element with name '{name}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error clicking element with name '{name}': {e}")
            raise

    @staticmethod
    async def click_element_by_id(
        page: Page,
        element_id: str,
        min_delay_ms: int = 300,
        max_delay_ms: int = 600,
        log_callback=None
    ) -> None:
        """
        Click an element by ID with human-like delays.
        
        Args:
            page: Page instance
            element_id: ID of the element
            min_delay_ms: Minimum delay before click
            max_delay_ms: Maximum delay before click
            log_callback: Function to call for logging
        """
        try:
            await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
            locator = page.locator(f'#{element_id}')
            await locator.click()
            if log_callback:
                log_callback(f"Clicked element with ID '{element_id}'")
        except Exception as e:
            if log_callback:
                log_callback(f"Error clicking element with ID '{element_id}': {e}")
            raise

 
    @staticmethod
    async def log_upload_percent_by_selector(
        page: Page,
        selector: str,
        log_callback=None,
        interval_sec: int = 20,
        timeout_sec: int = 1800,
        completion_strings: dict = None
    ) -> None:
        """
        Periodically log upload progress percentage from an element until completion is reached.
        
        Args:
            page: Page instance
            selector: CSS selector for the element containing percentage
            log_callback: Function to call for logging progress
            interval_sec: Interval between checks in seconds
            timeout_sec: Timeout in seconds
            completion_strings: Dict of strings that indicate completion (case insensitive)
        """
        import re
        import time as time_module
        
        if completion_strings is None:
            completion_strings = {"100": None, "Complete": None}
        
        start_time = time_module.time()
        last_percent = 0
        
        while time_module.time() - start_time < timeout_sec:
            try:
                locator = page.locator(selector)
                is_visible = await locator.is_visible()
                
                if is_visible:
                    # Get full inner text content (e.g., "100% (486.7KB/s - 0s)")
                    full_text = await locator.inner_text()
                    
                    if full_text:
                        # Replace newlines with spaces to keep everything on one line
                        full_text = full_text.replace('\n', ' ')
                        
                        # Check for completion strings (case insensitive)
                        if any(key.lower() in full_text.lower() for key in completion_strings):
                            if log_callback:
                                log_callback(f"Upload completed: {full_text}")
                            return
                        
                        # Extract percentage value from text (e.g., "100%" -> 100)
                        percent_match = re.search(r'(\d+(?:\.\d+)?)', full_text)
                        percent = float(percent_match.group(1)) if percent_match else 0
                        
                        # Log if percentage changed
                        if percent != last_percent:
                            if log_callback:
                                log_callback(f"Upload progress: {full_text}")
                                last_percent = percent
                            
                            # Stop if reached 100%
                            if percent >= 100:
                                if log_callback:
                                    log_callback(f"Upload completed: {full_text}")
                                return
            except Exception as e:
                if log_callback:
                    log_callback(f"Error reading upload progress: {str(e)[:100]}")
            
            await asyncio.sleep(interval_sec)
        
        if log_callback:
            log_callback(f"Timeout waiting for upload to complete (timeout: {timeout_sec}s)")

    @staticmethod
    async def execute_template_script(
        page: Page,
        template_filename: str,
        return_value: bool = True,
        log_callback=None
    ):
        """
        Execute JavaScript code from a template file.
        
        Attempts to load template from TemplateManager first, then falls back to
        reading directly from the templates directory.
        
        Args:
            page: Page instance
            template_filename: Name of the template file (e.g., 'rumble_upload_check_rights.js')
            return_value: If True, returns the result of the script execution. If False, executes as init script.
            log_callback: Function to call for logging
            
        Returns:
            Result of the JavaScript execution if return_value is True, None otherwise
            
        Raises:
            ValueError: If template file cannot be found or loaded
        """
        try:
            js_code = None
            
            # First, try to load from registered templates in TemplateManager
            await PlaywrightUtils.template_manager.load_templates()
            template_key = template_filename.replace('.js', '').replace('.', '_')
            js_code = PlaywrightUtils.template_manager.get_template(template_key)
            
            # If not found in TemplateManager, try to load directly from file
            if not js_code:
                template_path = os.path.join(
                    PlaywrightUtils._parent_path,
                    'templates',
                    template_filename
                )
                
                if os.path.exists(template_path):
                    try:
                        with open(template_path, 'r', encoding='utf-8') as f:
                            js_code = f.read()
                    except Exception as e:
                        if log_callback:
                            log_callback(f"Error reading template file '{template_filename}': {e}")
                        raise ValueError(f"Cannot read template file '{template_filename}': {e}")
                else:
                    if log_callback:
                        log_callback(f"Template '{template_filename}' not found in templates directory")
                    raise ValueError(f"Template '{template_filename}' not found")
            
            if not js_code:
                raise ValueError(f"Template '{template_filename}' is empty")
            
            # Execute the script
            if return_value:
                result = await page.evaluate(js_code)
                if log_callback:
                    log_callback(f"Executed template '{template_filename}'")
                return result
            else:
                await page.add_init_script(js_code)
                if log_callback:
                    log_callback(f"Added init script from template '{template_filename}'")
                return None
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error executing template script '{template_filename}': {e}")
            raise

    @staticmethod
    async def set_file_input_by_id(
        page: Page,
        element_id: str,
        filepath: str,
        timeout_ms: int = 30000,
        log_callback=None
    ) -> None:
        """
        Set a file input field by ID and submit the file.
        
        Args:
            page: Page instance
            element_id: ID of the file input element
            filepath: Full path to the file to upload
            timeout_ms: Timeout in milliseconds
            log_callback: Function to call for logging
            
        Raises:
            FileNotFoundError: If the file does not exist
            Exception: If setting the file input fails
        """
        try:
            # Verify file exists
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"File not found: {filepath}")
            
            locator = page.locator(f'#{element_id}')
            
            # Wait for element to be attached
            if log_callback:
                log_callback(f"Waiting for file input element with ID '{element_id}'...")
            await locator.wait_for(state='attached', timeout=timeout_ms)
            
            # Set the input files
            await locator.set_input_files(filepath)
            
            if log_callback:
                log_callback(f"File input '{element_id}' set with file: {filepath}")
                
        except FileNotFoundError as e:
            if log_callback:
                log_callback(f"File not found for input '{element_id}': {e}")
            raise
        except Exception as e:
            if log_callback:
                log_callback(f"Error setting file input '{element_id}': {e}")
            raise

    @staticmethod
    async def set_file_input_by_name(
        page: Page,
        name: str,
        filepath: str,
        timeout_ms: int = 30000,
        log_callback=None
    ) -> None:
        """
        Set a file input field by name attribute and submit the file.
        
        Args:
            page: Page instance
            name: Name attribute of the file input element
            filepath: Full path to the file to upload
            timeout_ms: Timeout in milliseconds
            log_callback: Function to call for logging
            
        Raises:
            FileNotFoundError: If the file does not exist
            Exception: If setting the file input fails
        """
        try:
            # Verify file exists
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"File not found: {filepath}")
            
            locator = page.locator(f'input[name="{name}"]')
            
            # Wait for element to be attached
            if log_callback:
                log_callback(f"Waiting for file input element with name '{name}'...")
            await locator.wait_for(state='attached', timeout=timeout_ms)
            
            # Set the input files
            await locator.set_input_files(filepath)
            
            if log_callback:
                log_callback(f"File input '{name}' set with file: {filepath}")
                
        except FileNotFoundError as e:
            if log_callback:
                log_callback(f"File not found for input '{name}': {e}")
            raise
        except Exception as e:
            if log_callback:
                log_callback(f"Error setting file input '{name}': {e}")
            raise

    @staticmethod
    async def save_page_html(page: Page, file_path: str) -> None:
        """
        Save the current HTML content of the page to a specified file.

        Args:
            page: The Playwright Page instance.
            file_path: The file path where the HTML content will be saved.
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Get the page content
            html_content = await page.content()

            # Write the HTML content to the file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(html_content)
        except Exception as e:
            LogManager.log_message(f"Failed to save page HTML to {file_path}: {e}")
