from utils.logging_utils import LogManager
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
_odysee_sessions = {}  # {thread_number: (browser, context)}
_odysee_sessions_lock = asyncio.Lock()  # Lock for accessing _odysee_sessions dict


async def _ensure_odysee_session(thread_number=None, log_file=None, video_dir=None):
    """
    Get or create a persistent Odysee browser/context session for the given thread.
    Reuses existing logged-in sessions when possible to avoid repeated login overhead.

    Args:
        thread_number: Thread identifier for session caching
        log_file: Log file for this operation
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
            browser, context = _odysee_sessions[thread_number]
            try:
                # Verify context is still valid by checking if it's closed
                if not context.browser.is_connected():
                    raise RuntimeError("Browser disconnected")
                LogManager.log_message(
                    f"Reusing existing Odysee browser session for thread {thread_number}",
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
                del _odysee_sessions[thread_number]

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
        _odysee_sessions[thread_number] = (browser, context)
        LogManager.log_message(
            f"Created new persistent Odysee browser session for thread {thread_number}",
            log_file
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
            browser, context = _odysee_sessions[thread_number]
            try:
                await context.close()
                await browser.close()
                LogManager.log_message(f"Closed Odysee session for thread {thread_number}")
            except Exception as e:
                LogManager.log_message(
                    f"Error closing Odysee session for thread {thread_number}: {e}"
                )
            finally:
                del _odysee_sessions[thread_number]

    finally:
        _odysee_sessions_lock.release()


async def upload_to_odysee(filepath, filename, title, log_file=None, thread_number=None, uniqueid=None):
    """
    Upload a video file to Odysee using Playwright.

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
                    LogManager.log_message(
                        f"Attempting upload of file: {filepath} to Odysee (attempt {attempt + 1}/{max_retries})",
                        log_file
                    )

                    # Get Odysee credentials
                    odysee_email = Account_Config.get_odysee_email()
                    odysee_password = Account_Config.get_odysee_password()

                    if not odysee_email or not odysee_password:
                        LogManager.log_message("Odysee credentials missing in config", log_file)
                        return False, "Odysee credentials missing in config"

                    # Get metadata from meta manager
                    description = MetaDataManager.read_value(
                        "Description", "_Odysee", log_file or LogManager.UPLOAD_ODYSEE_LOG_FILE)
                    tags = MetaDataManager.read_value(
                        "Tags", "_Odysee", log_file or LogManager.UPLOAD_ODYSEE_LOG_FILE)

                    # Create video recording directory with thread number
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    playwright_root = DVR_Config.get_playwright_dir()
                    video_dir = os.path.join(playwright_root, "_PlayWright_Videos", f"Thread_{thread_number}")

                    # Ensure browser/context session with video recording; reuse or create if needed
                    browser, context = await _ensure_odysee_session(thread_number, log_file, video_dir)

                    # Create a new page in the persistent context
                    page = await context.new_page()
                    LogManager.log_message(
                        f"New page created in Odysee browser session for thread {thread_number}. Session video dir: {video_dir}",
                        log_file
                    )

                    # Mask webdriver detection - MUST be done before any navigation
                    await PlaywrightUtils.mask_webdriver(page)
                    # Block video/audio loading and playback
                    await PlaywrightUtils.block_media_loading(page)

                    # Log browser properties to check for bot detection BEFORE navigation
                    user_agent = await page.evaluate("navigator.userAgent")
                    is_headless = await page.evaluate("navigator.webdriver")
                    chrome_runtime = await page.evaluate("typeof chrome !== 'undefined' && typeof chrome.runtime !== 'undefined'")

                    console_log = await PlaywrightUtils.create_console_log_callback(
                        log_file=log_file,
                        platform='odysee',
                        log_to_console=True
                    )
                    await PlaywrightUtils.setup_console_logging(page, console_log)

                    # Navigate to Odysee home page
                    LogManager.log_message("Navigating to Odysee...", log_file)
                    nav_ok = await PlaywrightUtils.goto(page, "https://odysee.com", wait_until="domcontentloaded", timeout=30000)
                    if not nav_ok:
                        LogManager.log_message(
                            "Navigation error (non-critical): could not load https://odysee.com",
                            log_file,
                        )
                    await PlaywrightUtils.random_delay(800, 1200)
                    await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                    # Check if logged in
                    login_link = page.locator("a.button--link:has-text('Log In')")
                    is_logged_in = await login_link.count() == 0

                    if not is_logged_in:
                        LogManager.log_message("Not logged in, proceeding to login", log_file)

                        # Click "Log In" link
                        await login_link.click()
                        await PlaywrightUtils.random_delay(1500, 2500)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                        LogManager.log_message("Filling email...", log_file)
                        # Fill email
                        await PlaywrightUtils.fill_form_input_by_name(
                            page, "sign_in_email", odysee_email, min_delay_ms=800, max_delay_ms=1500)

                        # Click email submit button
                        await PlaywrightUtils.click_element(
                            page, "button[aria-label='Log In']", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=False)
                        await PlaywrightUtils.random_delay(1500, 2500)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                        LogManager.log_message("Filling password...", log_file)
                        # Fill password
                        await PlaywrightUtils.fill_form_input_by_name(
                            page, "sign_in_password", odysee_password, min_delay_ms=800, max_delay_ms=1500)

                        # Click password submit button
                        await PlaywrightUtils.click_element(
                            page, "button[aria-label='Continue']", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=False)
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=15000)

                        LogManager.log_message("Login completed, waiting for session to stabilize", log_file)
                        await PlaywrightUtils.random_delay(2000, 3000)
                    else:
                        LogManager.log_message("Already logged in", log_file)

                    # Close the current tab
                    LogManager.log_message("Closing current tab and starting a new one.", log_file)
                    await page.close()

                    # Create a new page in the persistent context
                    page = await context.new_page()
                    LogManager.log_message("New page created for upload process restart.", log_file)

                    # Navigate to the upload page
                    nav_ok = await PlaywrightUtils.goto(
                        page, "https://odysee.com/$/upload", wait_until="domcontentloaded", timeout=30000)
                    if not nav_ok:
                        LogManager.log_message(
                            "Navigation error: could not reload upload page. Aborting restart.", log_file
                        )
                        return False, "Navigation error: could not reload upload page. Aborting restart."

                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                    # Click on the "Next" button in the publish wizard footer
                    await PlaywrightUtils.click_element(
                        page,
                        "div.publish-wizard__footer-right button[aria-label='Next']",
                        min_delay_ms=800,
                        max_delay_ms=1500,
                        suppress_exceptions=False
                    )

                    # Input the updated title immediately
                    LogManager.log_message(f"Inputting updated title: {title}", log_file)
                    await PlaywrightUtils.fill_form_input_by_name(
                        page, "content_title", title, min_delay_ms=800, max_delay_ms=1500
                    )

                    # Upload video file
                    LogManager.log_message(f"Setting video file input: {filepath}", log_file)

                    # Select the specific hidden input[type=file] field within the card__main-actions div or the publish-file-picker__dropzone div
                    video_input = page.locator(
                        "div.card__main-actions input[type=file][style='display: none;'], div.publish-file-picker__dropzone input[type=file]"
                    )

                    if await video_input.count() == 0:
                        raise RuntimeError("Could not locate the specific video file input on Odysee upload page")

                    await video_input.first.set_input_files(filepath)
                    await PlaywrightUtils.random_delay(2000, 3000)
                    LogManager.log_message("Video file selected", log_file)

                    # Fill title
                    LogManager.log_message(f"Filling title: {title}", log_file)
                    # Check for title conflict
                    edit_claim_button = page.locator("button[aria-label='Edit existing claim instead']")
                    if await edit_claim_button.count() > 0:
                        LogManager.log_message("Title conflict detected. Restarting upload process with a unique title.", log_file)

                        # Append today's date to the title
                        today_date = datetime.datetime.now().strftime("%Y%m%d")
                        title = f"{title} {today_date}"

                        LogManager.log_message(f"Updated title: {title}", log_file)

                        # Restart the upload process for this thread only
                        LogManager.log_message("Restarting upload process for this thread with a unique title.", log_file)

                        # Navigate back to the upload page
                        nav_ok = await PlaywrightUtils.goto(
                            page, "https://odysee.com/$/upload", wait_until="domcontentloaded", timeout=30000
                        )
                        if not nav_ok:
                            LogManager.log_message(
                                "Navigation error: could not reload upload page. Aborting restart.", log_file
                            )
                            return False, "Navigation error: could not reload upload page. Aborting restart."

                        await PlaywrightUtils.random_delay(1500, 2500)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                        # Retry filling the title with the updated value
                        LogManager.log_message(f"Retrying with new title: {title}", log_file)
                        await PlaywrightUtils.fill_form_input_by_name(
                            page, "content_title", title, min_delay_ms=800, max_delay_ms=1500
                        )

                        # Submit the file again during the retry
                        LogManager.log_message(f"Retrying file submission: {filepath}", log_file)
                        await video_input.first.set_input_files(filepath)
                        await PlaywrightUtils.random_delay(2000, 3000)
                        LogManager.log_message("File resubmitted successfully during retry.", log_file)

                        # Continue the upload process from this point
                        LogManager.log_message("Continuing upload process with updated title.", log_file)
                    else:
                        LogManager.log_message("No title conflict detected, proceeding with upload.", log_file)
                    # Fill description
                    LogManager.log_message("Filling description...", log_file)
                    await PlaywrightUtils.fill_form_textarea_by_id(
                        page, "content_description", description, min_delay_ms=800, max_delay_ms=1500)

                    # Upload thumbnail if available
                    thumbnail_path = MetaDataManager.get_thumbnail_path("_Odysee")
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        LogManager.log_message(f"Setting thumbnail: {thumbnail_path}", log_file)
                        thumbnail_input = page.locator("input[type=file][accept*='image']")
                        if await thumbnail_input.count() == 0:
                            all_file_inputs = page.locator("input[type=file]")
                            total_file_inputs = await all_file_inputs.count()
                            if total_file_inputs >= 2:
                                thumbnail_input = all_file_inputs.nth(1)
                            elif total_file_inputs == 1:
                                thumbnail_input = all_file_inputs.first
                            else:
                                thumbnail_input = None

                        if thumbnail_input is None or await thumbnail_input.count() == 0:
                            LogManager.log_message("No thumbnail file input found, skipping thumbnail upload", log_file)
                        else:
                            LogManager.log_message("Setting Thumbnail File", log_file)
                            await thumbnail_input.set_input_files(thumbnail_path)
                            await PlaywrightUtils.random_delay(1000, 2000)
                            LogManager.log_message("Clicking the Thumbnail upload button", log_file)
                            # Click on the "Upload" button within the card__actions div
                            await PlaywrightUtils.click_element(
                                page,
                                "div.card__actions button.button--primary[aria-label='Upload']",
                                min_delay_ms=800,
                                max_delay_ms=1500,
                                suppress_exceptions=False
                            )
                            LogManager.log_message("Thumbnail uploaded", log_file)
                    else:
                        LogManager.log_message("No thumbnail found, skipping thumbnail upload", log_file)

                    # Fill tags
                    if tags:
                        LogManager.log_message(f"Filling tags: {tags}", log_file)
                        tag_box = page.locator("input.tag__input")
                        await tag_box.fill(tags)
                        await PlaywrightUtils.press_key(page, "Enter", min_delay_ms=300, max_delay_ms=600)
                        await PlaywrightUtils.random_delay(500, 1000)

                    # Click Upload button
                    LogManager.log_message("Clicking Upload Video Button...", log_file)
                    # Click on the "Upload" button
                    await PlaywrightUtils.click_element(
                            page,
                            "div.section__actions.publish__actions > button[aria-label='Upload'][type='button']",
                            min_delay_ms=800,
                            max_delay_ms=1500,
                            suppress_exceptions=False
                            )
                    await PlaywrightUtils.random_delay(2000, 3000)


                    # Click Confirm button
                    LogManager.log_message("Clicking confirm button...", log_file)
                    await PlaywrightUtils.click_element(
                        page, "button[aria-label='Confirm']", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=False)
                    await PlaywrightUtils.random_delay(1000, 2000)

                    # Monitor upload progress
                    LogManager.log_message("Monitoring upload progress...", log_file)
                    await PlaywrightUtils.wait_for_upload_progress(
                        page,
                        "div.card__main-actions input[type=file]",
                        timeout_ms=1800000,  # 30 minutes
                        log_callback=lambda msg: LogManager.log_message(msg, log_file),
                        progress_callback=lambda progress: LogManager.log_message(f"Upload progress: {progress}", log_file),
                        completion_strings={"100": None, "Complete": None}
                    )

                    # Click Confirm button
                    LogManager.log_message("Clicking confirm button...", log_file)
                    await PlaywrightUtils.click_element(
                        page, "button[aria-label='Confirm']", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=False)
                    await PlaywrightUtils.random_delay(1000, 2000)

                    # Wait for Success element within card__title-section
                    LogManager.log_message("Waiting for upload success confirmation...", log_file)
                    success_selector = "div.card__title-section > div.card__title-text > h2.card__title:has-text('Success')"

                    while True:
                        try:
                            await PlaywrightUtils.wait_for_element(
                                page,
                                success_selector,
                                timeout_ms=60000,
                                log_callback=lambda msg: LogManager.log_message(msg, log_file)
                            )
                            LogManager.log_message("Success message detected: Upload completed.", log_file)
                            break
                        except Exception as e:
                            LogManager.log_message(f"Waiting for success message failed: {e}. Retrying...", log_file)

                            # Dump HTML when waiting for success message fails
                            html_save_path = os.path.join(
                                DVR_Config.get_playwright_html_dir(),
                                f"Thread_{thread_number}",
                                f"{filename}_success_wait_error.html"
                            )
                            os.makedirs(os.path.dirname(html_save_path), exist_ok=True)
                            await PlaywrightUtils.save_page_html(page, html_save_path)
                            LogManager.log_message(f"Saved page HTML to {html_save_path} due to success wait error", log_file)

                            await PlaywrightUtils.random_delay(2000, 3000)

                    # Navigate back to prepare for the next upload
                    LogManager.log_message("Navigating back to prepare for the next upload...", log_file)
                    await page.go_back()
                    await PlaywrightUtils.random_delay(2000, 3000)

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
            f"ERROR: Upload to Odysee failed: {e}\n{traceback.format_exc()}",
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
                    pass
            except:
                pass
        except:
            pass
