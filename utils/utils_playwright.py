import asyncio
import random
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class PlaywrightUtils:
    """Utility class for common Playwright browser automation tasks."""
    
    # Default stealth browser launch arguments
    DEFAULT_LAUNCH_ARGS = [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-features=MediaSessionService',
        '--disable-features=PreloadMediaEngagementData',
        '--autoplay-policy=document-user-activation-required',
        '--disable-accelerated-video-decode',
        '--disable-accelerated-video-encode',
        '--disable-features=HardwareMediaKeyHandling',
    ]
    
    # Default user agent for human-like browsing (Chrome on Windows 10)
    DEFAULT_USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Default viewport dimensions
    DEFAULT_VIEWPORT = {'width': 1280, 'height': 720}
    
    # Default HTTP headers for human-like requests
    DEFAULT_HEADERS = {
        'Accept-Language': 'en-US,en;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }
    
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
        
        args = launch_args or PlaywrightUtils.DEFAULT_LAUNCH_ARGS
        
        browser = await p.chromium.launch(
            headless=headless,
            args=args,
            **kwargs
        )
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
            user_agent=user_agent or PlaywrightUtils.DEFAULT_USER_AGENT,
            viewport=viewport or PlaywrightUtils.DEFAULT_VIEWPORT,
            extra_http_headers=headers or PlaywrightUtils.DEFAULT_HEADERS,
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
        # Ultra-comprehensive anti-detection script
        anti_detection_script = """
        // === COMPREHENSIVE CLOUDFLARE & BOT DETECTION BYPASS ===
        
        // 1. CORE WEBDRIVER MASKING
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
            configurable: true
        });
        
        // 2. CHROME DETECTION
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {};
        window.chrome.loadTimes = function() {};
        window.chrome.csi = function() {};
        
        // 3. PLUGINS & LANGUAGES
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', description: ''},
                {name: 'Native Client Executable', description: ''},
                {name: 'Shockwave Flash', description: 'Shockwave Flash 32.0 r0'}
            ],
            configurable: true
        });
        
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true
        });
        
        Object.defineProperty(navigator, 'language', {
            get: () => 'en-US',
            configurable: true
        });
        
        // 4. VENDOR
        Object.defineProperty(navigator, 'vendor', {
            get: () => 'Google Inc.',
            configurable: true
        });
        
        // 5. PERMISSIONS API - Critical for Cloudflare
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(parameters)
        );
        
        // 6. SCREEN PROPERTIES
        Object.defineProperty(screen, 'availTop', {value: 0});
        Object.defineProperty(screen, 'availLeft', {value: 0});
        Object.defineProperty(screen, 'availHeight', {value: 1040});
        Object.defineProperty(screen, 'availWidth', {value: 1280});
        Object.defineProperty(screen, 'colorDepth', {value: 24});
        Object.defineProperty(screen, 'pixelDepth', {value: 24});
        
        // 7. PLATFORM
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
            configurable: true
        });
        
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 4,
            configurable: true
        });
        
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: true
        });
        
        // 8. TOUCH SUPPORT
        Object.defineProperty(navigator, 'maxTouchPoints', {
            get: () => 10,
            configurable: true
        });
        
        Object.defineProperty(navigator, 'ontouchstart', {
            value: null,
            configurable: true
        });
        
        // 9. CONNECTION INFO
        if (!navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                value: {
                    downlink: 10,
                    effectiveType: '4g',
                    rtt: 50,
                    saveData: false
                },
                configurable: true
            });
        }
        
        // 10. RUNTIME API MASKING
        Object.defineProperty(navigator, 'credentials', {
            get: () => ({
                get: async () => null,
                store: async (credential) => {},
                create: async (options) => null,
                preventSilentAccess: async () => {}
            }),
            configurable: true
        });
        
        // 11. MIME TYPES
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => [
                {type: 'application/pdf', description: 'PDF Plugin', enabledPlugin: {name: 'Chrome PDF Plugin'}},
                {type: 'application/x-google-chrome-extension', description: '', enabledPlugin: {name: 'Chrome PDF Plugin'}},
                {type: 'application/futuresplash', description: 'Shockwave Flash', enabledPlugin: {name: 'Shockwave Flash'}}
            ],
            configurable: true
        });
        
        // 12. SESSION STORAGE - Prevent detection via storage keys
        const originalSetItem = Storage.prototype.setItem;
        const originalGetItem = Storage.prototype.getItem;
        
        Storage.prototype.setItem = function(key, value) {
            if (key.includes('WebDriver') || key.includes('bot')) {
                return;
            }
            return originalSetItem.apply(this, arguments);
        };
        
        // 13. CHROME HEADLESS DETECTION
        window.__HEADLESS__ = false;
        Object.defineProperty(window, '__HEADLESS__', {
            get: () => false,
            configurable: true
        });
        
        // 14. CANVAS FINGERPRINT RANDOMIZATION (subtle)
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {
            if (this.width === 280 && this.height === 60) {
                // Don't give canvas fingerprint
                const context = this.getContext('2d');
                context.font = '16px Arial';
                context.fillStyle = '#000000';
                context.fillText('CANVAS', 50, 40);
            }
            return originalToDataURL.apply(this, arguments);
        };
        
        // 15. WEBGL SPOOFING
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (ANGLE)';
            if (parameter === 37446) return 'Google Inc. (ANGLE)';
            if (parameter === 7938) return 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)';
            return getParameter.apply(this, arguments);
        };
        
        // 16. CLOUDFLARE SPECIFIC - Override fetch to add proper headers
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            let url = args[0];
            if (typeof url === 'string' && url.includes('rumble.com')) {
                if (!args[1]) args[1] = {};
                if (!args[1].headers) args[1].headers = {};
                args[1].headers['Accept-Language'] = 'en-US,en;q=0.9';
                args[1].headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8';
                args[1].headers['Sec-Fetch-Dest'] = 'document';
                args[1].headers['Sec-Fetch-Mode'] = 'navigate';
                args[1].headers['Sec-Fetch-Site'] = 'none';
            }
            return originalFetch.apply(this, args);
        };
        
        // 17. PERFORMANCE TIMING RANDOMIZATION - Small random delays
        const originalNow = Performance.prototype.now;
        Performance.prototype.now = function() {
            return originalNow.apply(this) + Math.random() * 0.1;
        };
        """
        
        await page.add_init_script(anti_detection_script)
    
    
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
        max_delay_ms: int = 600
    ) -> None:
        """
        Click an element with human-like delays.
        
        Args:
            page: Page instance
            selector: CSS selector or Playwright locator
            min_delay_ms: Minimum delay before click
            max_delay_ms: Maximum delay before click
        """
        await PlaywrightUtils.random_delay(min_delay_ms, max_delay_ms)
        await page.locator(selector).click()
    
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
        log_callback=None
    ) -> None:
        """
        Wait for upload progress to reach 100% by monitoring element width.
        
        Args:
            page: Page instance
            progress_selector: CSS selector for progress bar element
            timeout_ms: Timeout in milliseconds
            log_callback: Function to call for logging progress updates
        """
        # Wait for progress element to be visible
        progress_locator = page.locator(progress_selector)
        await progress_locator.wait_for(state='visible', timeout=timeout_ms)
        
        # Wait for upload to reach 100%
        await page.wait_for_function(
            f"""() => {{
                const selector = '{progress_selector}';
                const el = document.querySelector(selector);
                if (!el) return false;
                
                // Set up logging if not already done
                if (!window.widthLogInterval) {{
                    window.widthLogInterval = setInterval(() => {{
                        const width = el.style.width || window.getComputedStyle(el).getPropertyValue('width');
                        const percentEl = document.querySelector('h2.num_percent');
                        if (percentEl) {{
                            const percentText = percentEl.textContent.trim();
                            console.log(`Upload progress: ${{percentText}}`);
                        }}
                    }}, 20000);
                }}
                
                const isComplete = el.style.width === '100%' || 
                                 window.getComputedStyle(el).getPropertyValue('width') === '100%';
                if (isComplete) {{
                    clearInterval(window.widthLogInterval);
                }}
                return isComplete;
            }}""",
            timeout=timeout_ms
        )
        
        if log_callback:
            log_callback("Upload progress reached 100%")
    
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
            await page.evaluate(
                f"""
                Promise.all([
                    page.waitForNavigation().catch(() => {{}})
                ]).catch(() => {{}})
                """
            )
            await page.locator(selector).click()
            await PlaywrightUtils.random_delay(500, 1000)
            if log_callback:
                log_callback(f"Clicked element '{selector}'")
        except Exception as e:
            # Don't log/raise navigation errors, they're expected
            if "timeout" not in str(e).lower():
                if log_callback:
                    log_callback(f"Clicked element '{selector}' (navigation completed or in progress)")
