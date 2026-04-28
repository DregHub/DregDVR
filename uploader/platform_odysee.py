from utils.logging_utils import LogManager, LogLevels
from utils.meta_utils import MetaDataManager
from utils.utils_playwright import PlaywrightUtils
from config.config_accounts import Account_Config
from config.config_settings import DVR_Config
import asyncio
import threading
import os
import datetime
import traceback

# Per-thread locks to prevent concurrent uploads within the same thread
# Each thread gets its own lock, allowing parallel uploads across different threads
_odysee_upload_locks = {}  # {thread_number: threading.Lock()}
_odysee_locks_lock = threading.Lock()  # Lock for accessing _odysee_upload_locks dict

# Persistent browser/context sessions per thread to reuse logged-in instances
_odysee_sessions = {}  # {thread_number: (browser, context, video_dir)}
_odysee_sessions_lock = asyncio.Lock()  # Lock for accessing _odysee_sessions dict


async def _ensure_odysee_session(thread_number=None, log_table=None, video_dir=None):
    """
    Get or create a persistent Odysee browser/context session for the given thread.
    Reuses existing logged-in sessions when possible to avoid repeated login overhead.

    Args:
        thread_number: Thread identifier for session caching
        log_table: Log file for this operation
        video_dir: Directory for video recording (only used on first creation)

    Returns:
        (browser, context) tuple - persistent or newly created
    """
    global _odysee_sessions

    if thread_number is None:
        thread_number = 1

    try:
        await _odysee_sessions_lock.acquire()

        # Check if session already exists and is still alive
        if thread_number in _odysee_sessions:
            browser, context, cached_video_dir = _odysee_sessions[thread_number]

            # If the requested video recording mode changed, recreate the session.
            if cached_video_dir != video_dir:
                LogManager.log_upload_odysee(
                    f"Video recording mode changed for thread {thread_number}, recreating session"
                )
                try:
                    await context.close()
                    await browser.close()
                except:
                    pass
                del _odysee_sessions[thread_number]
            else:
                try:
                    # Verify context is still valid by checking if it's closed
                    if not context.browser.is_connected():
                        raise RuntimeError("Browser disconnected")
                    LogManager.log_upload_odysee(
                        f"Reusing existing Odysee browser session for thread {thread_number}"
                    )
                    return browser, context
                except Exception:
                    # Session is dead, remove it and create new one
                    LogManager.log_upload_odysee(
                        f"Existing session for thread {thread_number} is dead, creating new one"
                    )
                    try:
                        await context.close()
                        await browser.close()
                    except:
                        pass
                    del _odysee_sessions[thread_number]

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
        storage_state_path = os.path.join(storage_dir, "odysee_storage_state.json")
        if os.path.exists(storage_state_path):
            context_opts["storage_state"] = storage_state_path

        context = await PlaywrightUtils.create_human_context(browser, **context_opts)

        # Attach storage path for saving after login
        context._odysee_storage_state_path = storage_state_path

        # Cache the session for reuse, keeping the recording directory state
        _odysee_sessions[thread_number] = (browser, context, video_dir)
        LogManager.log_upload_odysee(
            f"Created new persistent Odysee browser session for thread {thread_number}"
        )

        return browser, context

    finally:
        _odysee_sessions_lock.release()


async def close_odysee_session(thread_number=None):
    """
    Explicitly close and remove a cached Odysee session.

    Args:
        thread_number: Thread identifier of session to close
    """
    global _odysee_sessions

    if thread_number is None:
        thread_number = 1

    try:
        await _odysee_sessions_lock.acquire()

        if thread_number in _odysee_sessions:
            browser, context, _ = _odysee_sessions[thread_number]
            try:
                await context.close()
                await browser.close()
                LogManager.log_upload_odysee(
                    f"Closed Odysee session for thread {thread_number}"
                )
            except Exception as e:
                LogManager.log_upload_odysee(
                    f"Error closing Odysee session for thread {thread_number}: {e}"
                )
            finally:
                del _odysee_sessions[thread_number]

    finally:
        _odysee_sessions_lock.release()


async def upload_to_odysee(
    filepath, filename, title, log_table=None, thread_number=None, unique_id=None
):
    """
    Upload a video file to Odysee using Playwright.

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
    with _odysee_locks_lock:
        if thread_number not in _odysee_upload_locks:
            _odysee_upload_locks[thread_number] = threading.Lock()
        thread_lock = _odysee_upload_locks[thread_number]

    try:
        # Use thread-specific lock to ensure 1 upload per thread
        with thread_lock:
            for attempt in range(max_retries):
                page = None
                try:
                    LogManager.log_upload_odysee(
                        f"Attempting upload of file: {filepath} to Odysee (attempt {attempt + 1}/{max_retries})"
                    )

                    # Get Odysee credentials
                    odysee_email = await Account_Config.get_odysee_email()
                    odysee_password = await Account_Config.get_odysee_password()

                    if not odysee_email or not odysee_password:
                        LogManager.log_upload_odysee(
                            "Odysee credentials missing in config"
                        )
                        return False, "Odysee credentials missing in config"

                    # Get metadata from meta manager
                    description = MetaDataManager.read_value(
                        "Description",
                        "_Odysee",
                        log_table or LogManager.table_upload_platform_od,
                    )
                    tags = MetaDataManager.read_value(
                        "Tags",
                        "_Odysee",
                        log_table or LogManager.table_upload_platform_od,
                    )

                    # Create video recording directory with thread number
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    playwright_root = DVR_Config.get_playwright_dir()

                    # Conditionally set up video recording based on config
                    video_dir = None
                    if DVR_Config.get_playwright_session_video_recording():
                        video_dir = os.path.join(
                            playwright_root,
                            "_Session_Videos",
                            f"Thread_{thread_number}",
                        )

                    # Ensure browser/context session with video recording; reuse or create if needed
                    browser, context = await _ensure_odysee_session(
                        thread_number,  video_dir
                    )

                    # Create a new page in the persistent context
                    page = await context.new_page()
                    LogManager.log_upload_odysee(
                        f"New page created in Odysee browser session for thread {thread_number}. Session video dir: {video_dir}"
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

                    console_log = await PlaywrightUtils.create_console_log_callback(
                        platform="odysee", log_to_console=True
                    )
                    await PlaywrightUtils.setup_console_logging(page, console_log)

                    # Navigate to Odysee home page
                    LogManager.log_upload_odysee("Navigating to Odysee...")
                    nav_ok = await PlaywrightUtils.goto(
                        page,
                        "https://odysee.com/$/upload",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    if not nav_ok:
                        LogManager.log_upload_odysee(
                            "Navigation error (non-critical): could not load https://odysee.com/$/upload",
                            
                            LogLevels.Warning,
                        )
                    await PlaywrightUtils.random_delay(800, 1200)
                    await PlaywrightUtils.wait_for_load_state(
                        page, "networkidle", timeout=10000
                    )

                    # Detect whether the current page is the Odysee signup/login page
                    is_login_page = await page.locator("div.main__sign-up").count() > 0
                    if not is_login_page:
                        for retry in range(3):
                            LogManager.log_upload_odysee(
                                f"Login page not detected, navigating to Odysee signup page (attempt {retry + 1}/3)",
                                
                                LogLevels.Warning,
                            )
                            nav_ok = await PlaywrightUtils.goto(
                                page,
                                "https://odysee.com/$/signup",
                                wait_until="domcontentloaded",
                                timeout=30000,
                            )
                            if not nav_ok:
                                LogManager.log_upload_odysee(
                                    "Navigation error (non-critical): could not load https://odysee.com/$/signup",
                                    
                                    LogLevels.Warning,
                                )
                            await PlaywrightUtils.random_delay(1500, 2500)
                            await PlaywrightUtils.wait_for_load_state(
                                page, "networkidle", timeout=10000
                            )

                            if await page.locator("div.main__sign-up").count() > 0:
                                is_login_page = True
                                break

                        if not is_login_page:
                            raise RuntimeError(
                                "Unable to detect Odysee signup/login page after 3 attempts"
                            )

                    LogManager.log_upload_odysee(
                        "On Odysee signup/login page, filling credentials"
                    )
                    await PlaywrightUtils.wait_for_element(
                        page,
                        "input[name='sign_up_email']",
                        timeout_ms=30000,
                        log_callback=lambda msg: LogManager.log_upload_odysee(
                            msg,  LogLevels.Info
                        ),
                    )
                    await PlaywrightUtils.wait_for_element(
                        page,
                        "input[name='sign_in_password']",
                        timeout_ms=30000,
                        log_callback=lambda msg: LogManager.log_upload_odysee(
                            msg,  LogLevels.Info
                        ),
                    )

                    await PlaywrightUtils.fill_form_input_by_name(
                        page,
                        "sign_up_email",
                        odysee_email,
                        min_delay_ms=800,
                        max_delay_ms=1500,
                    )
                    await PlaywrightUtils.fill_form_input_by_name(
                        page,
                        "sign_in_password",
                        odysee_password,
                        min_delay_ms=800,
                        max_delay_ms=1500,
                    )

                    await PlaywrightUtils.click_element(
                        page,
                        "button[aria-label='Log In']",
                        min_delay_ms=800,
                        max_delay_ms=1500,
                        suppress_exceptions=False,
                    )
                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(
                        page, "networkidle", timeout=15000
                    )

                    LogManager.log_upload_odysee(
                        "Login completed, waiting for session to stabilize",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.random_delay(2000, 3000)

                    # Save storage state for future sessions
                    os.makedirs(
                        os.path.dirname(context._odysee_storage_state_path),
                        exist_ok=True,
                    )
                    await context.storage_state(path=context._odysee_storage_state_path)
                    LogManager.log_upload_odysee(
                        f"Saved Odysee storage state for thread {thread_number}"
                    )

                    # Navigate to the upload page on the same logged-in page
                    LogManager.log_upload_odysee(
                        "Navigating to Odysee upload page on the same session"
                    )
                    nav_ok = await PlaywrightUtils.goto(
                        page,
                        "https://odysee.com/$/upload",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    if not nav_ok:
                        LogManager.log_upload_odysee(
                            "Navigation error: could not load Odysee upload page."
                        )
                        return (
                            False,
                            "Navigation error: could not load Odysee upload page.",
                        )

                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(
                        page, "networkidle", timeout=10000
                    )

                    LogManager.log_upload_odysee(
                        "Waiting for the Odysee upload picker to appear..."
                    )
                    await PlaywrightUtils.wait_for_element(
                        page,
                        "div.publish-file-picker",
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_upload_odysee(msg),
                    )

                    # Upload video file using the new publish-file-picker input
                    LogManager.log_upload_odysee(
                        f"Setting video file input: {filepath}",
                        
                        LogLevels.Info,
                    )
                    video_input = page.locator(
                        "div.publish-file-picker input[type='file']"
                    )
                    if await video_input.count() == 0:
                        raise RuntimeError(
                            "Could not locate the video file input on the Odysee upload page"
                        )

                    await video_input.first.set_input_files(filepath)
                    await PlaywrightUtils.random_delay(2000, 3000)
                    LogManager.log_upload_odysee(
                        "Video file selected",  LogLevels.Info
                    )

                    # Wait for the metadata form to appear after file selection
                    await PlaywrightUtils.wait_for_element(
                        page,
                        "input[name='content_title']",
                        timeout_ms=120000,
                        log_callback=lambda msg: LogManager.log_upload_odysee(
                            msg,  LogLevels.Info
                        ),
                    )

                    # Fill title and description
                    LogManager.log_upload_odysee(
                        f"Filling title: {title}",  LogLevels.Info
                    )
                    await PlaywrightUtils.fill_form_input_by_name(
                        page,
                        "content_title",
                        title,
                        min_delay_ms=800,
                        max_delay_ms=1500,
                    )

                    LogManager.log_upload_odysee(
                        "Filling description...",  LogLevels.Info
                    )
                    await PlaywrightUtils.fill_form_textarea_by_id(
                        page,
                        "content_description",
                        description,
                        min_delay_ms=800,
                        max_delay_ms=1500,
                    )

                    # Upload thumbnail if available
                    thumbnail_path = MetaDataManager.get_thumbnail_path("_Odysee")
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        LogManager.log_upload_odysee(
                            f"Setting thumbnail: {thumbnail_path}",
                            
                            LogLevels.Info,
                        )
                        thumbnail_input = page.locator(
                            "div.thumbnail-picker__grid input[type='file'][accept*='image']"
                        )
                        if await thumbnail_input.count() == 0:
                            thumbnail_input = page.locator(
                                "div.thumbnail-picker__grid input[type='file']"
                            )

                        if await thumbnail_input.count() == 0:
                            LogManager.log_upload_odysee(
                                "No thumbnail file input found, skipping thumbnail upload",
                                
                                LogLevels.Info,
                            )
                        else:
                            LogManager.log_upload_odysee(
                                "Uploading thumbnail file",  LogLevels.Info
                            )
                            await thumbnail_input.first.set_input_files(thumbnail_path)
                            await PlaywrightUtils.random_delay(1000, 2000)

                            # Confirm thumbnail upload dialog
                            LogManager.log_upload_odysee(
                                "Waiting for thumbnail upload confirmation dialog...",
                                
                                LogLevels.Info,
                            )
                            await PlaywrightUtils.wait_for_element(
                                page,
                                "div.ReactModal__Content[aria-label='Confirm Thumbnail Upload']",
                                timeout_ms=30000,
                                log_callback=lambda msg: LogManager.log_upload_odysee(
                                    msg,  LogLevels.Info
                                ),
                            )
                            await PlaywrightUtils.click_element(
                                page,
                                "div.ReactModal__Content[aria-label='Confirm Thumbnail Upload'] button[aria-label='Upload']",
                                min_delay_ms=800,
                                max_delay_ms=1500,
                                suppress_exceptions=False,
                            )
                            await PlaywrightUtils.random_delay(1000, 2000)
                            LogManager.log_upload_odysee(
                                "Thumbnail upload confirmed",  LogLevels.Info
                            )
                    else:
                        LogManager.log_upload_odysee(
                            "No thumbnail found, skipping thumbnail upload",
                            
                            LogLevels.Info,
                        )

                    # Fill tags from comma-separated metadata list
                    if tags:
                        tag_values = [
                            tag.strip() for tag in tags.split(",") if tag.strip()
                        ]
                        if tag_values:
                            LogManager.log_upload_odysee(
                                f"Filling tags: {tag_values}",  LogLevels.Info
                            )
                            tag_input = page.locator("input[name='tag_search']")
                            if await tag_input.count() == 0:
                                tag_input = page.locator(
                                    "input[placeholder*='Search or add tags']"
                                )

                            if await tag_input.count() == 0:
                                LogManager.log_upload_odysee(
                                    "Tag input not found; skipping tags",
                                    
                                    LogLevels.Warning,
                                )
                            else:
                                for tag_value in tag_values:
                                    await tag_input.first.fill(tag_value)
                                    await PlaywrightUtils.press_key(
                                        page,
                                        "Enter",
                                        min_delay_ms=300,
                                        max_delay_ms=600,
                                    )
                                    await PlaywrightUtils.random_delay(500, 1000)
                        else:
                            LogManager.log_upload_odysee(
                                "Tags metadata provided but resolved to an empty list",
                                
                                LogLevels.Warning,
                            )

                    # Proceed through the upload wizard
                    LogManager.log_upload_odysee(
                        "Clicking Next to proceed to visibility selection...",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.click_element(
                        page,
                        "div.publish-wizard__footer-right button[aria-label='Next']",
                        min_delay_ms=800,
                        max_delay_ms=1500,
                        suppress_exceptions=False,
                    )
                    await PlaywrightUtils.random_delay(1500, 2500)

                    await PlaywrightUtils.wait_for_element(
                        page,
                        "div.publish-visibility",
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_upload_odysee(
                            msg,  LogLevels.Info
                        ),
                    )

                    LogManager.log_upload_odysee(
                        "Clicking Next after visibility selection...",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.click_element(
                        page,
                        "div.publish-wizard__footer-right button[aria-label='Next']",
                        min_delay_ms=800,
                        max_delay_ms=1500,
                        suppress_exceptions=False,
                    )
                    await PlaywrightUtils.random_delay(1500, 2500)

                    await PlaywrightUtils.wait_for_element(
                        page,
                        "div.publish-summary__left",
                        timeout_ms=60000,
                        log_callback=lambda msg: LogManager.log_upload_odysee(
                            msg,  LogLevels.Info
                        ),
                    )

                    LogManager.log_upload_odysee(
                        "Clicking Publish button on Odysee summary page...",
                        
                        LogLevels.Info,
                    )
                    await PlaywrightUtils.click_element(
                        page,
                        "div.publish-wizard__publish-group button[aria-label='Publish']",
                        min_delay_ms=800,
                        max_delay_ms=1500,
                        suppress_exceptions=False,
                    )
                    await PlaywrightUtils.random_delay(2000, 3000)

                    # Wait for final processing progress to reach completion
                    LogManager.log_upload_odysee(
                        "Monitoring upload progress...",  LogLevels.Info
                    )
                    await PlaywrightUtils.wait_for_upload_progress(
                        page,
                        "div.claim-upload__progress--outer",
                        timeout_ms=1800000,  # 30 minutes
                        log_callback=lambda msg: LogManager.log_upload_odysee(
                            msg,  LogLevels.Info
                        ),
                        progress_callback=lambda progress: LogManager.log_upload_odysee(
                            f"Upload progress: {progress}",  LogLevels.Info
                        ),
                        completion_strings={"100": None},
                        ignored_strings="Processing...",
                    )

                    LogManager.log_upload_odysee(
                        "Odysee upload process completed or progress reached 100%.",
                        
                        LogLevels.Info,
                    )

                    # Return success and keep the browser/context alive for reuse
                    return True, None

                except Exception as e:
                    LogManager.log_upload_odysee(
                        f"Attempt {attempt + 1} failed: {e}\n{traceback.format_exc()}",
                        
                    )

                    # Save the page HTML if a timeout or strict mode error occurs and dumps are enabled
                    if DVR_Config.get_playwright_session_error_html_dump() and (
                        "Timeout" in str(e) or "strict mode" in str(e)
                    ):
                        html_save_path = os.path.join(
                            DVR_Config.get_playwright_html_dir(),
                            f"Thread_{thread_number}",
                            f"{filename}.html",
                        )
                        os.makedirs(os.path.dirname(html_save_path), exist_ok=True)
                        await PlaywrightUtils.save_page_html(page, html_save_path)
                        LogManager.log_upload_odysee(
                            f"Saved page HTML to {html_save_path}"
                        )

                    # Close only the page, keep browser/context alive for reuse by next upload
                    if page:
                        try:
                            await page.close()
                        except:
                            pass

                    if attempt < max_retries - 1:
                        retry_delay = retry_delay_base * (2**attempt)
                        LogManager.log_upload_odysee(
                            f"Retrying in {retry_delay} seconds..."
                        )
                        await asyncio.sleep(retry_delay)
                    continue

    except Exception as e:
        LogManager.log_upload_odysee(
            f"ERROR: Upload to Odysee failed: {e}\n{traceback.format_exc()}"
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
                    error_dump_dir, f"odysee_error_{timestamp}.html"
                )
                page_content = await page.content()

                with open(html_dump_file, "w", encoding="utf-8") as f:
                    f.write(page_content)

                LogManager.log_upload_odysee(
                    f"Error HTML dump saved to: {html_dump_file}"
                )
            except Exception as dump_err:
                LogManager.log_upload_odysee(
                    f"Failed to save error HTML dump: {dump_err}"
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
                    pass
            except:
                pass
        except:
            pass
