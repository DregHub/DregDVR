import traceback
import os
import asyncio
import datetime
import threading
from utils.logging_utils import LogManager
from utils.meta_utils import MetaDataManager
from utils.utils_playwright import PlaywrightUtils
from config.config_accounts import Account_Config
from config.config_settings import DVR_Config

# Per-thread locks to prevent concurrent uploads within the same thread
# Each thread gets its own lock, allowing parallel uploads across different threads
_rumble_upload_locks = {}  # {thread_number: threading.Lock()}
_rumble_locks_lock = threading.Lock()  # Lock for accessing _rumble_upload_locks dict

# Persistent browser/context sessions per thread to reuse logged-in instances
_rumble_sessions = {}  # {thread_number: (browser, context)}
_rumble_sessions_lock = asyncio.Lock()  # Lock for accessing _rumble_sessions dict


async def _ensure_rumble_session(thread_number=None, log_file=None, video_dir=None):
    """
    Get or create a persistent Rumble browser/context session for the given thread.
    Reuses existing logged-in sessions when possible to avoid repeated login overhead.
    
    Args:
        thread_number: Thread identifier for session caching
        log_file: Log file for this operation
        video_dir: Directory for video recording (only used on first creation)
    
    Returns:
        (browser, context) tuple - persistent or newly created
    """
    global _rumble_sessions

    if thread_number is None:
        thread_number = 1

    try:
        await _rumble_sessions_lock.acquire()

        # Check if session already exists and is still alive
        if thread_number in _rumble_sessions:
            browser, context = _rumble_sessions[thread_number]
            try:
                # Verify context is still valid by checking if it's closed
                if not context.browser.is_connected():
                    raise RuntimeError("Browser disconnected")
                LogManager.log_message(
                    f"Reusing existing Rumble browser session for thread {thread_number}",
                    log_file
                )
                return browser, context
            except Exception:
                # Session is dead, remove it and create new one
                LogManager.log_message(
                    f"Existing session for thread {thread_number} is dead, creating new one",
                    log_file
                )
                try:
                    await context.close()
                    await browser.close()
                except:
                    pass
                del _rumble_sessions[thread_number]

        # Create new persistent session
        browser = await PlaywrightUtils.launch_stealth_browser(headless=True)

        # Create context with video recording if video_dir is provided
        context_opts = {}
        if video_dir:
            os.makedirs(video_dir, exist_ok=True)
            context_opts['record_video_dir'] = video_dir

        context = await PlaywrightUtils.create_human_context(
            browser,
            **context_opts
        )

        # Cache the session for reuse
        _rumble_sessions[thread_number] = (browser, context)
        LogManager.log_message(
            f"Created new persistent Rumble browser session for thread {thread_number}",
            log_file
        )

        return browser, context

    finally:
        _rumble_sessions_lock.release()


async def close_rumble_session(thread_number=None):
    """
    Explicitly close and remove a cached Rumble session.
    
    Args:
        thread_number: Thread identifier of session to close
    """
    global _rumble_sessions

    if thread_number is None:
        thread_number = 1

    try:
        await _rumble_sessions_lock.acquire()

        if thread_number in _rumble_sessions:
            browser, context = _rumble_sessions[thread_number]
            try:
                await context.close()
                await browser.close()
                LogManager.log_message(f"Closed Rumble session for thread {thread_number}")
            except Exception as e:
                LogManager.log_message(
                    f"Error closing Rumble session for thread {thread_number}: {e}"
                )
            finally:
                del _rumble_sessions[thread_number]

    finally:
        _rumble_sessions_lock.release()


async def upload_to_rumble(filepath, filename, title, log_file=None, thread_number=None, uniqueid=None):
    """
    Upload a video file to Rumble using Playwright.

    Args:
        filepath: Full path to the video file
        filename: Filename without extension
        title: Video title to use for upload
        log_file: Optional thread-specific log file path
        thread_number: Thread number for this upload (1-6), used to isolate browser instances
        uniqueid: Unique ID of the video entry
    """
    # Retry mechanism with exponential backoff
    max_retries = 3
    retry_delay_base = 30  # seconds

    if thread_number is None:
        thread_number = 1  # Default to thread 1 if not specified

    # Get or create per-thread lock
    with _rumble_locks_lock:
        if thread_number not in _rumble_upload_locks:
            _rumble_upload_locks[thread_number] = threading.Lock()
        thread_lock = _rumble_upload_locks[thread_number]

    try:
        # Use thread-specific lock to ensure 1 upload per thread
        with thread_lock:
            for attempt in range(max_retries):
                page = None
                try:
                    LogManager.log_message(
                        f"Attempting upload of file: {filepath} to Rumble (attempt {attempt + 1}/{max_retries})", log_file)

                    # Get Rumble credentials
                    rumble_email = Account_Config.get_rumble_email()
                    rumble_password = Account_Config.get_rumble_password()

                    if not rumble_email or not rumble_password:
                        LogManager.log_message("Rumble credentials missing in config", log_file)
                        return False, "Rumble credentials missing in config"

                    # Get description from meta
                    description = MetaDataManager.read_value(
                        "Description", "_Rumble", log_file or LogManager.UPLOAD_RUMBLE_LOG_FILE)

                    # Get categories and tags from config or meta
                    primary_category = Account_Config.get_rumble_primary_category()
                    secondary_category = Account_Config.get_rumble_secondary_category() or ""
                    tags = MetaDataManager.read_value("Tags", "_Rumble", log_file or LogManager.UPLOAD_RUMBLE_LOG_FILE)

                    # Create video recording directory with thread number
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    playwright_root = DVR_Config.get_playwright_dir()
                    video_dir = os.path.join(playwright_root, "_PlayWright_Videos", f"Thread_{thread_number}")

                    # Ensure browser/context session with video recording; reuse or create if needed
                    browser, context = await _ensure_rumble_session(thread_number, log_file, video_dir)

                    # Create a new page in the persistent context
                    page = await context.new_page()
                    LogManager.log_message(
                        f"New page created in Rumble browser session for thread {thread_number}. Session video dir: {video_dir}", log_file)

                    # Mask webdriver detection - MUST be done before any navigation
                    await PlaywrightUtils.mask_webdriver(page)
                    # Block video/audio loading and playback
                    await PlaywrightUtils.block_media_loading(page)

                    # Log browser properties to check for bot detection BEFORE navigation
                    user_agent = await page.evaluate("navigator.userAgent")
                    is_headless = await page.evaluate("navigator.webdriver")
                    chrome_runtime = await page.evaluate("typeof chrome !== 'undefined' && typeof chrome.runtime !== 'undefined'")

                    # Log platform detection
                    platform = await page.evaluate("navigator.platform")
                    touch_points = await page.evaluate("navigator.maxTouchPoints")

                    # DO NOT intercept routes - this triggers Cloudflare detection
                    # Instead, let Playwright handle requests naturally and Cloudflare challenges with JavaScript challenges

                    console_log = await PlaywrightUtils.create_console_log_callback(
                        log_file=log_file,
                        platform='rumble',
                        log_to_console=True
                    )
                    await PlaywrightUtils.setup_console_logging(page, console_log)

                    # Navigate to Rumble with aggressive Cloudflare handling

                    nav_ok = await PlaywrightUtils.goto(page, "https://rumble.com", wait_until="domcontentloaded", timeout=30000)
                    if not nav_ok:
                        LogManager.log_message(
                            f"Navigation error (non-critical): could not load https://rumble.com", log_file)
                    await PlaywrightUtils.random_delay(800, 1200)
                    await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                    await PlaywrightUtils.check_cloudflare(page, lambda msg: LogManager.log_message(msg, log_file))
                    await PlaywrightUtils.random_delay(500, 800)

                    # Check if logged in
                    # Target the desktop sign-in link using element tag and button classes
                    sign_in_button = page.locator('a[href="/login.php"].btn.btn-medium.btn-grey')
                    is_logged_in = await sign_in_button.count() == 0

                    if not is_logged_in:
                        LogManager.log_message("Not logged in, proceeding to login", log_file)

                        # Click the sign-in button
                        await sign_in_button.click()
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)
                        LogManager.log_message("Filling login credentials", log_file)
                        await PlaywrightUtils.fill_form_input_by_name(page, 'username', rumble_email)
                        await PlaywrightUtils.fill_form_input_by_name(page, 'password', rumble_password)
                        login_btn = page.locator('button:has-text("Sign In")')
                        await login_btn.click()
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=15000)
                        LogManager.log_message("Login completed, waiting for session to stabilize", log_file)
                        await PlaywrightUtils.random_delay(2000, 3000)
                    else:
                        LogManager.log_message("Already logged in", log_file)

                    # Navigate to upload page with better Cloudflare handling
                    LogManager.log_message("Navigating to upload page...", log_file)
                    nav_ok = await PlaywrightUtils.goto(page, "https://rumble.com/upload", wait_until="domcontentloaded", timeout=30000)
                    if not nav_ok:
                        LogManager.log_message(
                            f"Upload page navigation error: could not load https://rumble.com/upload", log_file)
                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.check_cloudflare(page, lambda msg: LogManager.log_message(msg, log_file))
                    await PlaywrightUtils.random_delay(1500, 2500)

                    # Upload file
                    await PlaywrightUtils.random_delay(800, 1500)

                    # Wait for the file input to be visible and ready, then set file
                    await PlaywrightUtils.set_file_input_by_id(page, "Filedata", filepath, timeout_ms=30000)

                    LogManager.log_message("File selected for upload", log_file)

                    # Periodically log upload percent and stop after reaching 100%
                    LogManager.log_message("File upload started, monitoring progress...", log_file)
                    try:
                        percent_task = asyncio.create_task(
                            PlaywrightUtils.log_upload_percent_by_selector(
                                page,
                                'h2.num_percent',
                                log_callback=lambda msg: LogManager.log_message(msg, log_file),
                                interval_sec=20,
                                timeout_sec=3600,
                                progress_callback=lambda progress: LogManager.log_message(f"Upload progress: {progress}", log_file),
                                completion_strings={"100": None, "Complete": None}
                            )
                        )
                        # Wait for percent_task to finish (reaches 100% or timeout)
                        await percent_task
                    except Exception as e:
                        LogManager.log_message(
                            f"Error during upload progress monitoring: {str(e)[:200]}\n{traceback.format_exc()[:500]}", log_file)
                        raise

                    # Fill title
                    await PlaywrightUtils.fill_form_input_by_name(page, 'title', title, min_delay_ms=800, max_delay_ms=1500)
                    # Fill description
                    await PlaywrightUtils.fill_form_textarea_by_name(page, 'description', description)
                    # Upload custom thumbnail
                    thumbnail_path = MetaDataManager.get_thumbnail_path("_Rumble")
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        await PlaywrightUtils.set_file_input_by_id(page, "customThumb", thumbnail_path, timeout_ms=30000)
                    else:
                        LogManager.log_message("No thumbnail found, skipping thumbnail upload", log_file)

                    # Select primary category
                    LogManager.log_message(f"Selecting primary category: {primary_category}", log_file)
                    await PlaywrightUtils.click_element_by_name(page, 'primary-category')
                    await PlaywrightUtils.fill_form_input_by_name(page, 'primary-category', primary_category)
                    await PlaywrightUtils.press_key(page, "Enter")

                    # Fill tags
                    await PlaywrightUtils.fill_form_input_by_name(page, 'tags', tags)

                    # Click upload
                    await PlaywrightUtils.click_element_by_id(page, 'submitForm', min_delay_ms=800, max_delay_ms=1500)

                    LogManager.log_message("Form submitted, waiting for terms and conditions page...", log_file)

                    # Wait for terms and conditions page to appear
                    LogManager.log_message("Waiting for terms and conditions form to render...", log_file)
                    await PlaywrightUtils.wait_for_element_by_type_and_innertext(
                        page,
                        'h2',
                        'Your licensing options',
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_message(msg, log_file)
                    )
                    # Check the two required checkboxes
                    LogManager.log_message("Checking content rights checkbox...", log_file)
                    await PlaywrightUtils.execute_template_script(
                        page=page,
                        template_filename='rumble_upload_check_rights.js',
                        return_value=True,
                        log_callback=lambda msg: LogManager.log_message(msg, log_file)
                    )

                    # Click final submit button
                    LogManager.log_message("Submitting final form...", log_file)
                    await PlaywrightUtils.click_element_by_id(page, 'submitForm2', min_delay_ms=800, max_delay_ms=1500)

                    LogManager.log_message("Waiting for upload completion confirmation...", log_file)
                    await PlaywrightUtils.wait_for_element_by_type_and_innertext(
                        page,
                        'h3',
                        'Video Upload Complete!',
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_message(msg, log_file)
                    )

                    # Wait for any pending navigations and let page stabilize
                    LogManager.log_message("Stabilizing page after completion confirmation...", log_file)
                    try:
                        # Wait briefly for any post-completion JavaScript to settle
                        await PlaywrightUtils.random_delay(1500, 2500)
                        # Force page to idle state before closing
                        await asyncio.wait_for(
                            page.wait_for_load_state("networkidle", timeout=10000),
                            timeout=15
                        )
                    except asyncio.TimeoutError:
                        LogManager.log_message("Page stabilization timeout (non-critical, continuing)", log_file)
                    except Exception as e:
                        LogManager.log_message(f"Page stabilization error (non-critical): {e}", log_file)

                    # Close page with timeout to prevent indefinite hangs
                    LogManager.log_message("Closing page...", log_file)
                    if page:
                        try:
                            await asyncio.wait_for(page.close(), timeout=5.0)
                            LogManager.log_message("Page closed successfully", log_file)
                        except asyncio.TimeoutError:
                            LogManager.log_message("Page close timeout - forcing close via context", log_file)
                            try:
                                # Force close via context if page.close() hangs
                                await page.context.close()
                                LogManager.log_message("Context closed (page force-closed)", log_file)
                            except:
                                pass
                        except Exception as e:
                            LogManager.log_message(f"Error closing page: {e}", log_file)
                    
                    return True, None

                except Exception as e:
                    LogManager.log_message(
                        f"Attempt {attempt + 1} failed: {e}\n{traceback.format_exc()}",
                        log_file
                    )

                    # Save the page HTML if a timeout or strict mode error occurs
                    if "Timeout" in str(e) or "strict mode" in str(e):
                        html_save_path = os.path.join(
                            DVR_Config.get_playwright_html_dir(),
                            f"Thread_{thread_number}",
                            f"{filename}.html"
                        )
                        os.makedirs(os.path.dirname(html_save_path), exist_ok=True)
                        await PlaywrightUtils.save_page_html(page, html_save_path)
                        LogManager.log_message(f"Saved page HTML to {html_save_path}", log_file)

                    # Close only the page, keep browser/context alive for reuse by next upload
                    if page:
                        try:
                            await page.close()
                        except:
                            pass

                    if attempt < max_retries - 1:
                        retry_delay = retry_delay_base * (2 ** attempt)
                        LogManager.log_message(f"Retrying in {retry_delay} seconds...", log_file)
                        await asyncio.sleep(retry_delay)
                    continue

    except Exception as e:
        LogManager.log_message(
            f"ERROR: Upload to Rumble failed: {e}\n{traceback.format_exc()}",
            log_file
        )
        return False, str(e)
    finally:
        # Page cleanup only - keep browser/context alive for session reuse in next upload
        try:
            if 'page' in locals() and page:
                await asyncio.wait_for(page.close(), timeout=5.0)
        except asyncio.TimeoutError:
            # Force close via context if page.close() hangs
            try:
                if 'page' in locals() and page:
                    await page.context.close()
            except:
                pass
        except:
            pass
