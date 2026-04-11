import traceback
import os
import asyncio
import contextlib
import datetime
import threading
import shutil
import tempfile
from utils.logging_utils import LogManager
from utils.meta_utils import MetaDataManager
from utils.utils_playwright import PlaywrightUtils
from utils.playlist_manager import PlaylistManager
from config.config_accounts import Account_Config
from config.config_settings import DVR_Config

# Per-thread locks to prevent concurrent uploads within the same thread
# Each thread gets its own lock, allowing parallel uploads across different threads
_bitchute_upload_locks = {}  # {thread_number: threading.Lock()}
_bitchute_locks_lock = threading.Lock()  # Lock for accessing _bitchute_upload_locks dict

# Persistent browser instances per thread to reuse logged-in browser processes
_bitchute_browsers = {}  # {thread_number: browser}
_bitchute_browsers_lock = threading.Lock()  # Lock for accessing _bitchute_browsers dict

# Global lock to serialize browser launches across all threads
_browser_launch_lock = threading.Lock()


async def _ensure_bitchute_session(thread_number=None, log_file=None, video_dir=None):
    """
    Create a fresh Bitchute browser/context session for this upload.

    Args:
        thread_number: Thread identifier for session logging only
        log_file: Log file for this operation
        video_dir: Directory for video recording

    Returns:
        (browser, context) tuple - newly created
    """
    if thread_number is None:
        thread_number = 1

    playwright_root = DVR_Config.get_playwright_dir()
    storage_dir = os.path.join(playwright_root, "_Session_Storage", f"Thread_{thread_number}")
    storage_state_path = os.path.join(storage_dir, "bitchute_storage_state.json")

    LogManager.log_message(
        f"Creating Bitchute browser/context session for thread {thread_number}",
        log_file
    )

    with _browser_launch_lock:
        if thread_number in _bitchute_browsers:
            browser = _bitchute_browsers[thread_number]
            try:
                if not browser.is_connected():
                    raise RuntimeError("Browser disconnected")
                LogManager.log_message(
                    f"Reusing existing Bitchute browser for thread {thread_number}",
                    log_file
                )
            except Exception:
                try:
                    await browser.close()
                except Exception:
                    pass
                del _bitchute_browsers[thread_number]
                browser = await PlaywrightUtils.launch_stealth_browser(headless=True)
        else:
            browser = await PlaywrightUtils.launch_stealth_browser(headless=True)

        _bitchute_browsers[thread_number] = browser

    context_opts = {}
    if video_dir:
        os.makedirs(video_dir, exist_ok=True)
        context_opts['record_video_dir'] = video_dir

    if os.path.exists(storage_state_path):
        context_opts['storage_state'] = storage_state_path

    context = await PlaywrightUtils.create_human_context(
        browser,
        **context_opts
    )

    # Attach storage path so upload_to_bitchute can persist login after a successful login.
    context._bitchute_storage_state_path = storage_state_path

    return browser, context


async def close_bitchute_session(thread_number=None):
    """
    Explicitly close and remove a cached Bitchute browser.

    Args:
        thread_number: Thread identifier of session to close
    """
    global _bitchute_browsers

    if thread_number is None:
        thread_number = 1

    try:
        _bitchute_browsers_lock.acquire()

        if thread_number in _bitchute_browsers:
            browser = _bitchute_browsers[thread_number]
            try:
                if browser and browser.is_connected():
                    await browser.close()
            except Exception:
                pass
            finally:
                del _bitchute_browsers[thread_number]

    finally:
        _bitchute_browsers_lock.release()


async def _invalidate_bitchute_session(thread_number=None, log_file=None):
    """
    Remove a cached Bitchute browser if it is no longer valid.
    """
    global _bitchute_browsers

    if thread_number is None:
        thread_number = 1

    try:
        _bitchute_browsers_lock.acquire()

        if thread_number in _bitchute_browsers:
            browser = _bitchute_browsers[thread_number]
            try:
                if browser and browser.is_connected():
                    await browser.close()
            except Exception:
                pass
            finally:
                del _bitchute_browsers[thread_number]
                LogManager.log_message(
                    f"Invalidated Bitchute browser for thread {thread_number}",
                    log_file
                )

    finally:
        _bitchute_browsers_lock.release()


async def _submit_meta(page, title, description, tags, log_file=None):
    """
    Submit metadata and thumbnail to Bitchute upload form.
    
    Args:
        page: Playwright page object
        title: Video title
        description: Video description
        tags: Video tags/hashtags
        log_file: Log file path
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Fill metadata
        LogManager.log_message("Filling metadata...", log_file)
        await PlaywrightUtils.fill_form_input_by_id(page, "title", title, min_delay_ms=800, max_delay_ms=1500)
        await PlaywrightUtils.fill_form_textarea_by_id(page, "description", description, min_delay_ms=800, max_delay_ms=1500)
        await PlaywrightUtils.fill_form_input_by_id(page, "hashtags", tags, min_delay_ms=800, max_delay_ms=1500)

        # Upload thumbnail if available
        thumbnail_path = MetaDataManager.get_thumbnail_path("_Bitchute")
        if thumbnail_path and os.path.exists(thumbnail_path):
            LogManager.log_message(f"Uploading thumbnail: {thumbnail_path}", log_file)
            thumb_input = page.locator("input.filepond--browser[name='thumbnailInput']")
            await thumb_input.set_input_files(thumbnail_path)

            # Wait for thumbnail upload to complete
            await PlaywrightUtils.wait_for_upload_progress(
                page,
                "#thumbnailInput span.filepond--file-status-main",
                timeout_ms=60000,
                log_callback=lambda msg: LogManager.log_message(msg, log_file),
                progress_callback=lambda progress: LogManager.log_message(f"Thumbnail upload progress: {progress}", log_file),
                completion_strings={"Upload complete": None}
            )
            # Allow page to stabilize after thumbnail upload
            await PlaywrightUtils.random_delay(2000, 3000)
            await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=5000)
        
        return True
    except Exception as e:
        LogManager.log_message(f"Error submitting metadata: {e}", log_file)
        return False


async def _submit_file(page, filepath, filename, uniqueid=None, log_file=None):
    """
    Submit video file to Bitchute upload form.
    
    Args:
        page: Playwright page object
        filepath: Full path to video file
        filename: Filename without extension
        uniqueid: Unique ID of video entry
        log_file: Log file path
        
    Returns:
        Tuple of (success: bool, error_message: str or None, temp_file: str or None)
    """
    try:
        # Upload video file
        LogManager.log_message(f"Uploading video file: {filepath}", log_file)
        
        # Check if file is .mkv and create a temporary .ogv copy to spoof extension
        upload_filepath = filepath
        temp_file = None
        if filepath.lower().endswith('.mkv'):
            with tempfile.NamedTemporaryFile(suffix='.ogv', delete=False) as tf:
                temp_filepath = tf.name
            shutil.copy2(filepath, temp_filepath)  # Copy with metadata
            upload_filepath = temp_filepath
            temp_file = temp_filepath
            LogManager.log_message(f"Created temporary .ogv copy for upload: {temp_filepath}", log_file)
        
        video_input = page.locator("input[name='videoInput']")
        await video_input.set_input_files(upload_filepath)

        # Wait for FilePond to validate the file and display any error messages
        await PlaywrightUtils.random_delay(1000, 2000)

        # Check for file validation errors before proceeding
        error_status = page.locator("#videoInput div.filepond--file-status span.filepond--file-status-main")
        error_sub_status = page.locator("#videoInput div.filepond--file-status span.filepond--file-status-sub")

        # Wait for error elements to become visible if they exist
        try:
            await error_status.wait_for(state="visible", timeout=5000)
        except:
            pass  # No error message appeared

        if await error_status.count() > 0 and await error_sub_status.count() > 0:
            error_text = await error_status.inner_text()
            sub_error_text = await error_sub_status.inner_text()

            if error_text == "File is too small" and sub_error_text == "Minimum file size is 1 MB":
                LogManager.log_message(
                    "Upload failed: File is too small. Minimum file size is 1 MB.", log_file
                )
                if uniqueid:
                    await PlaylistManager.mark_video_upload_error(uniqueid, "BC", "FileTooSmall_Min1MBForBitchute")
                return False, "FileTooSmall_Min1MBForBitchute", temp_file
            
            if error_text == "File is of invalid type":
                LogManager.log_message(
                    f"Upload failed: File is of invalid type. Sub-status: {sub_error_text}", log_file
                )
                if uniqueid:
                    await PlaylistManager.mark_video_upload_error(uniqueid, "BC", "FileInvalidType_NotSupportedForBitchute")
                return False, "FileInvalidType_NotSupportedForBitchute", temp_file

        return True, None, temp_file

    except Exception as e:
        LogManager.log_message(f"Error submitting file: {e}", log_file)
        return False, str(e), None


async def upload_to_bitchute(filepath, filename, title, log_file=None, thread_number=None, uniqueid=None):
    """
    Upload a video file to Bitchute using Playwright.

    Args:
        filepath: Full path to the video file
        filename: Filename without extension
        title: Video title to use for upload
        video_url: Video URL for tracking in playlist manager
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
    with _bitchute_locks_lock:
        if thread_number not in _bitchute_upload_locks:
            _bitchute_upload_locks[thread_number] = threading.Lock()
        thread_lock = _bitchute_upload_locks[thread_number]

    browser = None
    context = None
    page = None
    temp_file = None
    try:
        # Use thread-specific lock to ensure 1 upload per thread
        with thread_lock:
            for attempt in range(max_retries):
                page = None
                try:
                    LogManager.log_message(
                        f"Attempting upload of file: {filepath} to Bitchute (attempt {attempt + 1}/{max_retries})",
                        log_file
                    )

                    description = MetaDataManager.read_value(
                        "Description", "_Bitchute", log_file or LogManager.UPLOAD_BITCHUTE_LOG_FILE)
                    tags = MetaDataManager.read_value(
                        "Tags", "_Bitchute", log_file or LogManager.UPLOAD_BITCHUTE_LOG_FILE)

                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    playwright_root = DVR_Config.get_playwright_dir()
                    video_dir = os.path.join(playwright_root, "_Session_Videos", f"Thread_{thread_number}")

                    browser, context = await _ensure_bitchute_session(thread_number, log_file, video_dir)
                    
                    try:
                        # Close any lingering pages to prevent issues with reused sessions
                        for p in context.pages:
                            if not p.is_closed():
                                try:
                                    await p.close()
                                except:
                                    pass
                        
                        # Wrap page creation with a timeout to detect unresponsive contexts
                        page = await asyncio.wait_for(context.new_page(), timeout=60.0)
                        LogManager.log_message(
                            f"Created new Bitchute upload page in thread {thread_number} session",
                            log_file
                        )
                    except asyncio.TimeoutError:
                        LogManager.log_message(
                            f"Timeout creating page in existing session, invalidating and recreating session",
                            log_file
                        )
                        await _invalidate_bitchute_session(thread_number, log_file)
                        browser, context = await _ensure_bitchute_session(thread_number, log_file, video_dir)
                        
                        # Close any lingering pages to prevent issues with reused sessions
                        for p in context.pages:
                            if not p.is_closed():
                                try:
                                    await p.close()
                                except:
                                    pass
                        
                        page = await asyncio.wait_for(context.new_page(), timeout=60.0)
                        LogManager.log_message(
                            f"Created new Bitchute upload page in thread {thread_number} session after session recreation",
                            log_file
                        )
                    except Exception as e:
                        LogManager.log_message(
                            f"Failed to create page in existing session: {e}, invalidating and recreating session",
                            log_file
                        )
                        await _invalidate_bitchute_session(thread_number, log_file)
                        browser, context = await _ensure_bitchute_session(thread_number, log_file, video_dir)
                        
                        # Close any lingering pages to prevent issues with reused sessions
                        for p in context.pages:
                            if not p.is_closed():
                                try:
                                    await p.close()
                                except:
                                    pass
                        
                        page = await asyncio.wait_for(context.new_page(), timeout=60.0)
                        LogManager.log_message(
                            f"Created new Bitchute upload page in thread {thread_number} session after session recreation",
                            log_file
                        )

                    # Mask webdriver detection - MUST be done before any navigation
                    await PlaywrightUtils.mask_webdriver(page)
                    await PlaywrightUtils.block_media_loading(page)

                    nav_ok = await PlaywrightUtils.goto(
                        page, "https://old.bitchute.com", wait_until="domcontentloaded", timeout=30000)
                    if not nav_ok:
                        LogManager.log_message(
                            "Navigation error: could not load upload page.", log_file
                        )
                        return False, "Navigation error: could not load upload page."

                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                    # Check if logged in
                    login_link = page.locator("div.unauth-link a:has-text('Login')")
                    is_logged_in = await login_link.count() == 0

                    if not is_logged_in:
                        LogManager.log_message("Not logged in, proceeding to login", log_file)

                        # Navigate to home for login
                        nav_ok = await PlaywrightUtils.goto(page, "https://old.bitchute.com/", wait_until="domcontentloaded", timeout=30000)
                        if not nav_ok:
                            LogManager.log_message(
                                "Navigation error (non-critical): could not load https://old.bitchute.com/",
                                log_file,
                            )
                        await PlaywrightUtils.random_delay(800, 1200)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                        # Click "Login" link
                        await login_link.click()
                        await PlaywrightUtils.random_delay(1500, 2500)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                        # Get Bitchute credentials
                        bitchute_email = Account_Config.get_bitchute_email()
                        bitchute_password = Account_Config.get_bitchute_password()

                        if not bitchute_email or not bitchute_password:
                            return False, "Bitchute credentials missing in config"

                        LogManager.log_message("Filling email...", log_file)
                        # Fill email
                        await PlaywrightUtils.fill_form_input_by_id(
                            page, "id_username", bitchute_email, min_delay_ms=800, max_delay_ms=1500)

                        # Fill password
                        LogManager.log_message("Filling password...", log_file)
                        await PlaywrightUtils.fill_form_input_by_id(
                            page, "id_password", bitchute_password, min_delay_ms=800, max_delay_ms=1500)

                        # Click login button
                        await PlaywrightUtils.click_element(
                            page, "#auth_submit", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=False)
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=15000)

                        LogManager.log_message("Login completed, waiting for session to stabilize", log_file)
                        await PlaywrightUtils.random_delay(2000, 3000)
                        try:
                            os.makedirs(os.path.dirname(context._bitchute_storage_state_path), exist_ok=True)
                            await context.storage_state(path=context._bitchute_storage_state_path)
                            LogManager.log_message(
                                f"Saved Bitchute storage state to {context._bitchute_storage_state_path}",
                                log_file
                            )
                        except Exception as e:
                            LogManager.log_message(
                                f"Failed to save Bitchute storage state: {e}",
                                log_file
                            )
                    else:
                        LogManager.log_message("Already logged in", log_file)
                        if not os.path.exists(context._bitchute_storage_state_path):
                            try:
                                os.makedirs(os.path.dirname(context._bitchute_storage_state_path), exist_ok=True)
                                await context.storage_state(path=context._bitchute_storage_state_path)
                                LogManager.log_message(
                                    f"Saved Bitchute storage state to {context._bitchute_storage_state_path}",
                                    log_file
                                )
                            except Exception as e:
                                LogManager.log_message(
                                    f"Failed to save Bitchute storage state: {e}",
                                    log_file
                                )

                    # Navigate to upload page
                    nav_ok = await PlaywrightUtils.goto(
                        page, "https://old.bitchute.com/myupload/", wait_until="domcontentloaded", timeout=30000)
                    if not nav_ok:
                        LogManager.log_message(
                            "Navigation error: could not load upload page.", log_file
                        )
                        return False, "Navigation error: could not load upload page."

                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=10000)

                    # Run metadata and file submission concurrently
                    LogManager.log_message("Starting concurrent metadata and file submission...", log_file)
                    meta_task = asyncio.create_task(_submit_meta(page, title, description, tags, log_file))
                    file_task = asyncio.create_task(_submit_file(page, filepath, filename, uniqueid, log_file))

                    file_result = await file_task
                    if not meta_task.done():
                        meta_result = await meta_task
                    else:
                        meta_result = meta_task.result()

                    # Check results from concurrent submissions
                    file_success, file_error, temp_file = file_result
                    if not meta_result or not file_success:
                        error_msg = file_error if file_error else "Metadata submission failed"
                        LogManager.log_message(f"Submission failed: {error_msg}", log_file)
                        # Clean up temp file if it exists
                        if temp_file and os.path.exists(temp_file):
                            try:
                                os.unlink(temp_file)
                            except Exception:
                                pass
                        return False, error_msg

                    #While the file subbission is being processed run the initial validation check

                    #Click the "Proceed" button to trigger validation while the video uploads
                    await PlaywrightUtils.click_element(
                        page, "button.btn.btn-primary[type='submit']:text('Proceed')", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=False)
                    
                    # Wait for form validation feedback (both elements should be visible)
                    timeout_ms = 10000
                    start_time = datetime.datetime.now()
                    while True:
                        count = await page.locator("div.valid-feedback:has-text('Looks good!')").count()
                        if count == 2:
                            break
                        elapsed_ms = (datetime.datetime.now() - start_time).total_seconds() * 1000
                        if elapsed_ms > timeout_ms:
                            raise TimeoutError(f"Timeout waiting for 2 valid-feedback elements. Found {count}")
                        await asyncio.sleep(0.1)
                    
                    LogManager.log_message(
                        f"Form validation passed, waiting for file upload to complete...",
                        log_file
                    )
                    # Wait for FilePond to finish and log progress
                    await PlaywrightUtils.wait_for_upload_progress(
                        page,
                        "#videoInput span.filepond--file-status-main",
                        timeout_ms=1800000,
                        log_callback=lambda msg: LogManager.log_message(msg, log_file),
                        progress_callback=lambda progress: LogManager.log_message(f"Upload progress: {progress}", log_file),
                        completion_strings={"100": None, "Complete": None}
                    )

                    #the page may navigate automatically after upload, so wait for that to happen before proceeding with any further steps
                    # Inject and display waiting banner
                    LogManager.log_message("Form submitted, displaying waiting banner...", log_file)
                    try:
                        if not page.is_closed():
                            await page.evaluate("""
                                () => {
                                    const banner = document.createElement('div');
                                    banner.id = 'upload-waiting-banner';
                                    banner.style.cssText = `
                                        position: fixed;
                                        top: 50%;
                                        left: 50%;
                                        transform: translate(-50%, -50%);
                                        background-color: rgba(0, 0, 0, 0.9);
                                        color: white;
                                        padding: 40px 60px;
                                        border-radius: 10px;
                                        font-size: 24px;
                                        font-weight: bold;
                                        z-index: 10000;
                                        text-align: center;
                                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                                        pointer-events: none;
                                    `;
                                    banner.textContent = 'Waiting for form to submit...';
                                    document.body.appendChild(banner);
                                }
                            """)
                            await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=5000)
                        else:
                            LogManager.log_message("Page closed before banner injection; skipping waiting banner.", log_file)
                    except Exception as e:
                        if "Execution context was destroyed" in str(e) or "Navigation" in str(e) or "Target closed" in str(e):
                            pass  # Page likely navigated or closed, which is expected; ignore this error
                        else:
                            raise

                    LogManager.log_message("Waiting for new bitchute webpage to appear...", log_file)
                    for attempt in range(3):
                        try:
                            #Click on the proceed button again to finish upload cycle 
                            #If this element is not found skip
                            await PlaywrightUtils.click_element(
                                page, "button.btn.btn-primary[type='submit']:text('Proceed')", min_delay_ms=800, max_delay_ms=1500, suppress_exceptions=True)
                            
                            await asyncio.sleep(2)  # Allow time for page navigation after click
                            await page.locator('button[aria-label="Menu"]').wait_for(state="visible", timeout=30000)
                            LogManager.log_message("new bitchute webpage is now visible", log_file)
                            # Close the page to reset session state for next upload
                            try:
                                if page and not page.is_closed():
                                    await asyncio.wait_for(page.close(), timeout=5.0)
                            except Exception as e:
                                LogManager.log_message(f"Error closing page after error: {e}", log_file)
                    
                            #After successful upload and new bitchute webpage appearance, break out of retry loop and return success
                            LogManager.log_message("Upload to Bitchute completed successfully!", log_file)
                            return True, None    
                        except Exception as e:
                            if attempt == 2:
                                raise e  # Reraise on final attempt after logging
                except Exception as e:
                    LogManager.log_message(
                        f"Attempt {attempt + 1} failed: {e}\n{traceback.format_exc()}",
                        log_file
                    )
                    
                    # Save the page HTML if a timeout or strict mode error occurs
                    if "Timeout" in str(e) or "strict mode" in str(e):
                        try:
                            html_save_path = os.path.join(
                                DVR_Config.get_playwright_html_dir(),
                                f"Thread_{thread_number}",
                                f"{filename}.html"
                            )
                            os.makedirs(os.path.dirname(html_save_path), exist_ok=True)
                            await PlaywrightUtils.save_page_html(page, html_save_path)
                            LogManager.log_message(f"Saved page HTML to {html_save_path}", log_file)
                        except Exception:
                            pass
                    
                  
                    # Close the page to reset session state for next upload
                    try:
                        if page and not page.is_closed():
                            await asyncio.wait_for(page.close(), timeout=5.0)
                    except Exception as e:
                        LogManager.log_message(f"Error closing page after error: {e}", log_file)

                    if attempt < max_retries - 1:
                        retry_delay = retry_delay_base * (2 ** attempt)
                        LogManager.log_message(f"Retrying in {retry_delay} seconds...", log_file)
                        await asyncio.sleep(retry_delay)
                    continue

    except Exception as e:
        LogManager.log_message(
            f"ERROR: Upload to Bitchute failed: {e}\n{traceback.format_exc()}",
            log_file
        )
        return False, str(e)
    finally:
        # Close any open page first
        try:
            if page and not page.is_closed():
                await asyncio.wait_for(page.close(), timeout=5.0)
        except asyncio.TimeoutError:
            with contextlib.suppress(Exception):
                if page:
                    await page.context.close()
        except Exception:
            pass

        # Close the context if it was created
        try:
            if context and not context.is_closed():
                await context.close()
        except Exception:
            pass

        # Close the browser if it was created
        try:
            if browser and browser.is_connected():
                await browser.close()
        except Exception:
            pass

        # Stop the Playwright instance if it was started
        try:
            if browser and hasattr(browser, '_playwright_instance'):
                playwright_instance = getattr(browser, '_playwright_instance')
                if playwright_instance:
                    await playwright_instance.stop()
        except Exception:
            pass

        # Clean up temp file if it exists
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception:
                pass