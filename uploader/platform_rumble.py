import traceback
import os
import asyncio
import datetime
import threading
from utils.logging_utils import LogManager, LogLevels
from utils.meta_utils import MetaDataManager
from utils.utils_playwright import PlaywrightUtils
from config.config_accounts import Account_Config
from config.config_settings import DVR_Config

# Per-thread locks to prevent concurrent uploads within the same thread
# Each thread gets its own lock, allowing parallel uploads across different threads
_rumble_upload_locks = {}  # {thread_number: threading.Lock()}
_rumble_locks_lock = threading.Lock()  # Lock for accessing _rumble_upload_locks dict

# Persistent browser/context sessions per thread to reuse logged-in instances
_rumble_sessions = {}  # {thread_number: (browser, context, video_dir)}
_rumble_sessions_lock = asyncio.Lock()  # Lock for accessing _rumble_sessions dict


async def _ensure_rumble_session(thread_number=None, log_table=None, video_dir=None):
    """
    Get or create a persistent Rumble browser/context session for the given thread.
    Reuses existing logged-in sessions when possible to avoid repeated login overhead.

    Args:
        thread_number: Thread identifier for session caching
        log_table: Log file for this operation
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
            browser, context, cached_video_dir = _rumble_sessions[thread_number]

            # If the requested video recording mode changed, recreate the session.
            if cached_video_dir != video_dir:
                LogManager.log_upload_rumble(
                    f"Video recording mode changed for thread {thread_number}, recreating session",
                    
                    LogLevels.Info,
                )
                try:
                    await context.close()
                    await browser.close()
                except:
                    pass
                del _rumble_sessions[thread_number]
            else:
                try:
                    # Verify context is still valid by checking if it's closed
                    if not context.browser.is_connected():
                        raise RuntimeError("Browser disconnected")
                    LogManager.log_upload_rumble(
                        f"Reusing existing Rumble browser session for thread {thread_number}",
                        
                        LogLevels.Info,
                    )
                    return browser, context
                except Exception:
                    # Session is dead, remove it and create new one
                    LogManager.log_upload_rumble(
                        f"Existing session for thread {thread_number} is dead, creating new one",
                        
                        LogLevels.Warning,
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
            context_opts["record_video_dir"] = video_dir

        # Load storage state if exists
        playwright_root = DVR_Config.get_playwright_dir()
        storage_dir = os.path.join(
            playwright_root, "_Session_Storage", f"Thread_{thread_number}"
        )
        storage_state_path = os.path.join(storage_dir, "rumble_storage_state.json")
        if os.path.exists(storage_state_path):
            context_opts["storage_state"] = storage_state_path

        context = await PlaywrightUtils.create_human_context(browser, **context_opts)

        # Attach storage path for saving after login
        context._rumble_storage_state_path = storage_state_path

        # Cache the session for reuse, keeping the recording directory state
        _rumble_sessions[thread_number] = (browser, context, video_dir)
        LogManager.log_upload_rumble(
            f"Created new persistent Rumble browser session for thread {thread_number}",
            
            LogLevels.Info,
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
            browser, context, _ = _rumble_sessions[thread_number]
            try:
                await context.close()
                await browser.close()
                LogManager.log_upload_rumble(
                    f"Closed Rumble session for thread {thread_number}", LogLevels.Info
                )
            except Exception as e:
                LogManager.log_upload_rumble(
                    f"Error closing Rumble session for thread {thread_number}: {e}",
                    LogLevels.Error,
                )
            finally:
                del _rumble_sessions[thread_number]

    finally:
        _rumble_sessions_lock.release()


async def upload_to_rumble(
    filepath, filename, title, log_table=None, thread_number=None, unique_id=None
):
    """
    Upload a video file to Rumble using Playwright.

    Args:
        filepath: Full path to the video file
        filename: Filename without extension
        title: Video title to use for upload
        log_table: Optional thread-specific log file path
        thread_number: Thread number for this upload (1-6), used to isolate browser instances
        unique_id: Unique ID of the video entry
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
                    LogManager.log_upload_rumble(
                        f"Attempting upload of file: {filepath} to Rumble (attempt {attempt + 1}/{max_retries})",
                        
                        LogLevels.Info,
                    )

                    # Get Rumble credentials
                    rumble_email = await Account_Config.get_rumble_email()
                    rumble_password = await Account_Config.get_rumble_password()

                    if not rumble_email or not rumble_password:
                        LogManager.log_upload_rumble("Rumble credentials missing in config",LogLevels.Error,
                        )
                        return False, "Rumble credentials missing in config"

                    # Get description from meta
                    description = MetaDataManager.read_value(
                        "Description",
                        "_Rumble",
                        log_table or LogManager.table_upload_platform_od,
                    )

                    # Get categories and tags from config or meta
                    primary_category = (
                        await Account_Config.get_rumble_primary_category()
                    )
                    secondary_category = (
                        await Account_Config.get_rumble_secondary_category() or ""
                    )
                    tags = MetaDataManager.read_value(
                        "Tags",
                        "_Rumble",
                        log_table or LogManager.table_upload_platform_rm,
                    )

                    # Create video recording directory with thread number
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    playwright_root = DVR_Config.get_playwright_dir()

                    # Conditionally set up video recording based on config
                    video_dir = None
                    if DVR_Config.get_playwright_session_video_recording():
                        video_dir = os.path.join(playwright_root,"_PlayWright_Videos",f"Thread_{thread_number}",
                        )

                    # Ensure browser/context session with video recording; reuse or create if needed
                    browser, context = await _ensure_rumble_session(
                        thread_number,  video_dir
                    )

                    # Create a new page in the persistent context
                    page = await context.new_page()
                    LogManager.log_upload_rumble(
                        f"New page created in Rumble browser session for thread {thread_number}. Session video dir: {video_dir}",
                        
                        LogLevels.Info,
                    )

                    # Mask webdriver detection - MUST be done before any navigation
                    await PlaywrightUtils.mask_webdriver(page)
                    # Block video/audio loading and playback
                    await PlaywrightUtils.block_media_loading(page)

                    # Log browser properties to check for bot detection BEFORE navigation
                    user_agent = await page.evaluate("navigator.userAgent")
                    is_headless = await page.evaluate("navigator.webdriver")
                    chrome_runtime = await page.evaluate(
                        "typeof chrome !== 'undefined' && typeof chrome.runtime !== 'undefined'"
                    )

                    # Log platform detection
                    platform = await page.evaluate("navigator.platform")
                    touch_points = await page.evaluate("navigator.maxTouchPoints")

                    # DO NOT intercept routes - this triggers Cloudflare detection
                    # Instead, let Playwright handle requests naturally and Cloudflare challenges with JavaScript challenges

                    console_log = await PlaywrightUtils.create_console_log_callback(
                        log_table=log_table, platform="rumble", log_to_console=True
                    )
                    await PlaywrightUtils.setup_console_logging(page, console_log)

                    # Navigate to Rumble with aggressive Cloudflare handling

                    nav_ok = await PlaywrightUtils.goto(
                        page,
                        "https://rumble.com",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    if not nav_ok:
                        LogManager.log_upload_rumble(f"Navigation error (non-critical): could not load https://rumble.com",LogLevels.Warning,
                        )
                    await PlaywrightUtils.random_delay(800, 1200)
                    await PlaywrightUtils.wait_for_load_state(
                        page, "networkidle", timeout=10000
                    )

                    await PlaywrightUtils.check_cloudflare(
                        page, lambda msg: LogManager.log_upload_rumble(msg, log_table)
                    )
                    await PlaywrightUtils.random_delay(500, 800)

                    # Check if logged in
                    # Target the desktop sign-in link using element tag and button classes
                    sign_in_button = page.locator(
                        'a[href="/login.php"].btn.btn-medium.btn-grey'
                    )
                    is_logged_in = await sign_in_button.count() == 0

                    if not is_logged_in:
                        LogManager.log_upload_rumble("Not logged in, proceeding to login",LogLevels.Info,
                        )

                        # Click the sign-in button
                        await sign_in_button.click()
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000
                        )
                        LogManager.log_upload_rumble("Filling login credentials",  LogLevels.Info
                        )
                        await PlaywrightUtils.fill_form_input_by_name(page, "username", rumble_email
                        )
                        await PlaywrightUtils.fill_form_input_by_name(page, "password", rumble_password
                        )
                        login_btn = page.locator('button:has-text("Sign In")')
                        await login_btn.click()
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=15000
                        )
                        LogManager.log_upload_rumble("Login completed, waiting for session to stabilize",LogLevels.Info,
                        )
                        await PlaywrightUtils.random_delay(2000, 3000)
                    else:
                        LogManager.log_upload_rumble("Already logged in",  LogLevels.Info
                        )

                    # Save storage state for future sessions
                    os.makedirs(
                        os.path.dirname(context._rumble_storage_state_path),
                        exist_ok=True,
                    )
                    await context.storage_state(path=context._rumble_storage_state_path)
                    LogManager.log_upload_rumble(
                        f"Saved Rumble storage state for thread {thread_number}",
                        
                        LogLevels.Info,
                    )

                    # Navigate to upload page with better Cloudflare handling
                    LogManager.log_upload_rumble(
                        "Navigating to upload page...",  LogLevels.Info
                    )
                    nav_ok = await PlaywrightUtils.goto(
                        page,
                        "https://rumble.com/upload",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    if not nav_ok:
                        LogManager.log_upload_rumble(f"Upload page navigation error: could not load https://rumble.com/upload",LogLevels.Error,
                        )
                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.check_cloudflare(
                        page, lambda msg: LogManager.log_upload_rumble(msg, log_table)
                    )
                    await PlaywrightUtils.random_delay(1500, 2500)

                    # Upload file
                    await PlaywrightUtils.random_delay(800, 1500)

                    # Wait for the file input to be visible and ready, then set file
                    await PlaywrightUtils.set_file_input_by_id(
                        page, "Filedata", filepath, timeout_ms=30000
                    )

                    LogManager.log_upload_rumble(
                        "File selected for upload",  LogLevels.Info
                    )

                    # Periodically log upload percent and stop after reaching 100%
                    LogManager.log_upload_rumble(
                        "File upload started, monitoring progress...",
                        
                        LogLevels.Info,
                    )
                    try:
                        percent_task = asyncio.create_task(PlaywrightUtils.log_upload_percent_by_selector(    page,    "h2.num_percent",    log_callback=lambda msg: LogManager.log_upload_rumble(        msg, log_table    ),    interval_sec=20,    timeout_sec=3600,    progress_callback=lambda progress: LogManager.log_upload_rumble(        f"Upload progress: {progress}", log_table    ),    completion_strings={"100": None, "Complete": None},)
                        )
                        # Wait for percent_task to finish (reaches 100% or timeout)
                        await percent_task
                    except Exception as e:
                        LogManager.log_upload_rumble(f"Error during upload progress monitoring: {str(e)[:200]}\n{traceback.format_exc()[:500]}",LogLevels.Error,
                        )
                        raise

                    # Fill title
                    await PlaywrightUtils.fill_form_input_by_name(
                        page, "title", title, min_delay_ms=800, max_delay_ms=1500
                    )
                    # Fill description
                    await PlaywrightUtils.fill_form_textarea_by_name(
                        page, "description", description
                    )
                    # Upload custom thumbnail
                    thumbnail_path = MetaDataManager.get_thumbnail_path("_Rumble")
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        await PlaywrightUtils.set_file_input_by_id(page, "customThumb", thumbnail_path, timeout_ms=30000
                        )
                    else:
                        LogManager.log_upload_rumble("No thumbnail found, skipping thumbnail upload",LogLevels.Warning,
                        )

                    # Select primary category
                    LogManager.log_upload_rumble(
                        f"Selecting primary category: {primary_category}",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.click_element_by_name(
                        page, "primary-category"
                    )
                    await PlaywrightUtils.fill_form_input_by_name(
                        page, "primary-category", primary_category
                    )
                    await PlaywrightUtils.press_key(page, "Enter")

                    # Fill tags
                    await PlaywrightUtils.fill_form_input_by_name(page, "tags", tags)

                    # Click upload
                    await PlaywrightUtils.click_element_by_id(
                        page, "submitForm", min_delay_ms=800, max_delay_ms=1500
                    )

                    LogManager.log_upload_rumble(
                        "Form submitted, waiting for terms and conditions page...",
                        
                        LogLevels.Info,
                    )

                    # Wait for terms and conditions page to appear
                    LogManager.log_upload_rumble(
                        "Waiting for terms and conditions form to render...",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.wait_for_element_by_type_and_innertext(
                        page,
                        "h2",
                        "Your licensing options",
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_upload_rumble(msg, log_table),
                    )
                    # Check the two required checkboxes
                    LogManager.log_upload_rumble(
                        "Checking content rights checkbox...",  LogLevels.Info
                    )
                    await PlaywrightUtils.execute_template_script(
                        page=page,
                        template_filename="rumble_upload_check_rights.js",
                        return_value=True,
                        log_callback=lambda msg: LogManager.log_upload_rumble(msg, log_table),
                    )

                    # Click final submit button
                    LogManager.log_upload_rumble(
                        "Submitting final form...",  LogLevels.Info
                    )
                    await PlaywrightUtils.click_element_by_id(
                        page, "submitForm2", min_delay_ms=800, max_delay_ms=1500
                    )

                    LogManager.log_upload_rumble(
                        "Waiting for upload completion confirmation...",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.wait_for_element_by_type_and_innertext(
                        page,
                        "h3",
                        "Video Upload Complete!",
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_upload_rumble(msg, log_table),
                    )

                    # Wait for any pending navigations and let page stabilize
                    LogManager.log_upload_rumble(
                        "Stabilizing page after completion confirmation...",
                        
                        LogLevels.Info,
                    )
                    try:
                        # Wait briefly for any post-completion JavaScript to settle
                        await PlaywrightUtils.random_delay(1500, 2500)
                        # Force page to idle state before closing
                        await asyncio.wait_for(page.wait_for_load_state("networkidle", timeout=10000),timeout=15,
                        )
                    except asyncio.TimeoutError:
                        LogManager.log_upload_rumble("Page stabilization timeout (non-critical, continuing)",LogLevels.Warning,
                        )
                    except Exception as e:
                        LogManager.log_upload_rumble(f"Page stabilization error (non-critical): {e}",LogLevels.Warning,
                        )

                    # Close page with timeout to prevent indefinite hangs
                    LogManager.log_upload_rumble("Closing page...",  LogLevels.Info)
                    if page:
                        try:
                            await asyncio.wait_for(page.close(), timeout=5.0)
                            LogManager.log_upload_rumble("Page closed successfully", LogLevels.Info)
                        except asyncio.TimeoutError:
                            LogManager.log_upload_rumble("Page close timeout - forcing close via context", LogLevels.Warning)
                            try:
                                # Force close via context if page.close() hangs
                                await page.context.close()
                                LogManager.log_upload_rumble("Context closed (page force-closed)", LogLevels.Info)
                            except:
                                pass
                        except Exception as e:
                            LogManager.log_upload_rumble(f"Error closing page: {e}", LogLevels.Error)

                    return True, None

                except Exception as e:
                    LogManager.log_upload_rumble(
                        f"Attempt {attempt + 1} failed: {e}\n{traceback.format_exc()}",
                        
                        LogLevels.Error,
                    )

                    # Save the page HTML if a timeout or strict mode error occurs and dumps are enabled
                    if DVR_Config.get_playwright_session_error_html_dump() and (
                        "Timeout" in str(e) or "strict mode" in str(e)
                    ):
                        html_save_path = os.path.join(DVR_Config.get_playwright_html_dir(),f"Thread_{thread_number}",f"{filename}.html",
                        )
                        os.makedirs(os.path.dirname(html_save_path), exist_ok=True)
                        await PlaywrightUtils.save_page_html(page, html_save_path)
                        LogManager.log_upload_rumble(f"Saved page HTML to {html_save_path}",LogLevels.Info,
                        )

                    # Close only the page, keep browser/context alive for reuse by next upload
                    if page:
                        try:await page.close()
                        except:pass

                    if attempt < max_retries - 1:
                        retry_delay = retry_delay_base * (2**attempt)
                        LogManager.log_upload_rumble(f"Retrying in {retry_delay} seconds...",LogLevels.Warning,
                        )
                        await asyncio.sleep(retry_delay)
                    continue

    except Exception as e:
        LogManager.log_upload_rumble(
            f"ERROR: Upload to Rumble failed: {e}\n{traceback.format_exc()}",
            
            LogLevels.Error,
        )

        # Dump HTML content if error dump is enabled and page is available
        if (
            "page" in locals()
            and page
            and not page.is_closed()
            and DVR_Config.get_playwright_session_error_html_dump()
        ):
            try:
                playwright_root = DVR_Config.get_playwright_dir()
                error_dump_dir = os.path.join(playwright_root, "_Error_HTML_Dumps")
                os.makedirs(error_dump_dir, exist_ok=True)

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                html_dump_file = os.path.join(
                    error_dump_dir, f"rumble_error_{timestamp}.html"
                )
                page_content = await page.content()

                with open(html_dump_file, "w", encoding="utf-8") as f:
                    f.write(page_content)

                LogManager.log_upload_rumble(
                    f"Error HTML dump saved to: {html_dump_file}",
                    
                    LogLevels.Info,
                )
            except Exception as dump_err:
                LogManager.log_upload_rumble(
                    f"Failed to save error HTML dump: {dump_err}",
                    
                    LogLevels.Error,
                )

        return False, str(e)
    finally:
        # Page cleanup only - keep browser/context alive for session reuse in next upload
        try:
            if "page" in locals() and page:
                await asyncio.wait_for(page.close(), timeout=5.0)
        except asyncio.TimeoutError:
            # Force close via context if page.close() hangs
            try:
                if "page" in locals() and page:
                    await page.context.close()
            except:
                pass
        except:
            pass
