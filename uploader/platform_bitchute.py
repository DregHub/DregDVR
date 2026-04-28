import traceback
import os
import asyncio
import contextlib
import datetime
import threading
import shutil
import tempfile
from utils.logging_utils import LogManager, LogLevels
from utils.meta_utils import MetaDataManager
from utils.utils_playwright import PlaywrightUtils
from utils.playlist_manager import PlaylistManager
from config.config_settings import DVR_Config
from config.config_settings import DVR_Config

# Per-thread locks to prevent concurrent uploads within the same thread
# Each thread gets its own lock, allowing parallel uploads across different threads
_bitchute_upload_locks = {}  # {thread_number: threading.Lock()}
_bitchute_locks_lock = (
    threading.Lock()
)  # Lock for accessing _bitchute_upload_locks dict

# Persistent browser instances per thread to reuse logged-in browser processes
_bitchute_browsers = {}  # {thread_number: browser}
_bitchute_browsers_lock = threading.Lock()  # Lock for accessing _bitchute_browsers dict

# Global lock to serialize browser launches across all threads
_browser_launch_lock = threading.Lock()


async def _ensure_bitchute_session(thread_number=None, log_table=None, video_dir=None):
    """
    Create a fresh Bitchute browser/context session for this upload.

    Args:
        thread_number: Thread identifier for session logging only
        log_table: Log file for this operation
        video_dir: Directory for video recording

    Returns:
        (browser, context) tuple - newly created
    """
    if thread_number is None:
        thread_number = 1

    playwright_root = DVR_Config.get_playwright_dir()
    storage_dir = os.path.join(
        playwright_root, "_Session_Storage", f"Thread_{thread_number}"
    )
    storage_state_path = os.path.join(storage_dir, "bitchute_storage_state.json")

    LogManager.log_upload_bitchute(
        f"Creating Bitchute browser/context session for thread {thread_number}"
    )

    with _browser_launch_lock:
        if thread_number in _bitchute_browsers:
            browser = _bitchute_browsers[thread_number]
            try:
                if not browser.is_connected():
                    raise RuntimeError("Browser disconnected")
                LogManager.log_upload_bitchute(
                    f"Reusing existing Bitchute browser for thread {thread_number}"
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
        context_opts["record_video_dir"] = video_dir

    if os.path.exists(storage_state_path):
        context_opts["storage_state"] = storage_state_path

    context = await PlaywrightUtils.create_human_context(browser, **context_opts)

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


async def _invalidate_bitchute_session(thread_number=None, log_table=None):
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
                LogManager.log_upload_bitchute(
                    f"Invalidating Bitchute browser for thread {thread_number}"
                )

    finally:
        _bitchute_browsers_lock.release()


async def _submit_meta(page, title, description, tags, log_table=None):
    """
    Submit metadata and thumbnail to Bitchute upload form.

    Args:
        page: Playwright page object
        title: Video title
        description: Video description
        tags: Video tags/hashtags
        log_table: Log file path

    Returns:
        True if successful, False otherwise
    """
    try:
        # Fill metadata
        LogManager.log_upload_bitchute("Filling metadata...")
        await PlaywrightUtils.fill_form_input_by_id(
            page, "title", title, min_delay_ms=800, max_delay_ms=1500
        )
        await PlaywrightUtils.fill_form_textarea_by_id(
            page, "description", description, min_delay_ms=800, max_delay_ms=1500
        )
        await PlaywrightUtils.fill_form_input_by_id(
            page, "hashtags", tags, min_delay_ms=800, max_delay_ms=1500
        )

        # Upload thumbnail if available
        thumbnail_path = MetaDataManager.get_thumbnail_path("_Bitchute")
        if thumbnail_path and os.path.exists(thumbnail_path):
            LogManager.log_upload_bitchute(f"Uploading thumbnail: {thumbnail_path}")
            thumb_input = page.locator("input.filepond--browser[name='thumbnailInput']")
            await thumb_input.set_input_files(thumbnail_path)

            # Wait for thumbnail upload to complete
            await PlaywrightUtils.wait_for_upload_progress(
                page,
                "#thumbnailInput span.filepond--file-status-main",
                timeout_ms=60000,
                log_callback=lambda msg: LogManager.log_upload_bitchute(msg),
                progress_callback=lambda progress: LogManager.log_upload_bitchute(
                    f"Thumbnail upload progress: {progress}"
                ),
                completion_strings={"Upload complete": None},
            )
            # Allow page to stabilize after thumbnail upload
            await PlaywrightUtils.random_delay(2000, 3000)
            await PlaywrightUtils.wait_for_load_state(page, "networkidle", timeout=5000)

        return True
    except Exception as e:
        LogManager.log_upload_bitchute(f"Error submitting metadata: {e}")
        return False


async def _submit_file(page, filepath, filename, unique_id=None, log_table=None):
    """
    Submit video file to Bitchute upload form.

    Args:
        page: Playwright page object
        filepath: Full path to video file
        filename: Filename without extension
        unique_id: Unique ID of video entry
        log_table: Log file path

    Returns:
        Tuple of (success: bool, error_message: str or None, temp_file: str or None)
    """
    try:
        # Upload video file
        LogManager.log_upload_bitchute(f"Uploading video file: {filepath}")

        # Check if file is .mkv and create a temporary .ogv copy to spoof extension
        upload_filepath = filepath
        temp_file = None
        if filepath.lower().endswith(".mkv"):
            with tempfile.NamedTemporaryFile(suffix=".ogv", delete=False) as tf:
                temp_filepath = tf.name
            shutil.copy2(filepath, temp_filepath)  # Copy with metadata
            upload_filepath = temp_filepath
            temp_file = temp_filepath
            LogManager.log_upload_bitchute(
                f"Created temporary .ogv copy for upload: {temp_filepath}"
            )

        video_input = page.locator("input[name='videoInput']")
        await video_input.set_input_files(upload_filepath)

        # Wait for FilePond to validate the file and display any error messages
        await PlaywrightUtils.random_delay(1000, 2000)

        # Check for file validation errors before proceeding
        error_status = page.locator(
            "#videoInput div.filepond--file-status span.filepond--file-status-main"
        )
        error_sub_status = page.locator(
            "#videoInput div.filepond--file-status span.filepond--file-status-sub"
        )

        # Wait for error elements to become visible if they exist
        try:
            await error_status.wait_for(state="visible", timeout=5000)
        except:
            pass  # No error message appeared

        if await error_status.count() > 0 and await error_sub_status.count() > 0:
            error_text = await error_status.inner_text()
            sub_error_text = await error_sub_status.inner_text()

            if (
                error_text == "File is too small"
                and sub_error_text == "Minimum file size is 1 MB"
            ):
                LogManager.log_upload_bitchute(
                    "Upload failed: File is too small. Minimum file size is 1 MB."
                )
                if unique_id:
                    await PlaylistManager.mark_video_upload_error(
                        unique_id, "BC", "FileTooSmall_Min1MBForBitchute"
                    )
                return False, "FileTooSmall_Min1MBForBitchute", temp_file

            if error_text == "File is of invalid type":
                LogManager.log_upload_bitchute(
                    f"Upload failed: File is of invalid type. Sub-status: {sub_error_text}"
                )
                if unique_id:
                    await PlaylistManager.mark_video_upload_error(
                        unique_id, "BC", "FileInvalidType_NotSupportedForBitchute"
                    )
                return False, "FileInvalidType_NotSupportedForBitchute", temp_file

        return True, None, temp_file

    except Exception as e:
        LogManager.log_upload_bitchute(f"Error submitting file: {e}")
        return False, str(e), None


async def upload_to_bitchute(
    filepath, filename, title, log_table=None, thread_number=None, unique_id=None
):
    """
    Upload a video file to Bitchute using Playwright.

    Args:
        filepath: Full path to the video file
        filename: Filename without extension
        title: Video title to use for upload
        video_url: Video URL for tracking in playlist manager
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
                    LogManager.log_upload_bitchute(
                        f"Attempting upload of file: {filepath} to Bitchute (attempt {attempt + 1}/{max_retries})"
                    )

                    description = MetaDataManager.read_value(
                        "Description",
                        "_Bitchute",
                        log_table or LogManager.table_upload_platform_bc,
                    )
                    tags = MetaDataManager.read_value(
                        "Tags",
                        "_Bitchute",
                        log_table or LogManager.table_upload_platform_bc,
                    )

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

                    browser, context = await _ensure_bitchute_session(
                        thread_number, video_dir
                    )

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
                        LogManager.log_upload_bitchute(
                            f"Created new Bitchute upload page in thread {thread_number} session"
                        )
                    except asyncio.TimeoutError:
                        LogManager.log_upload_bitchute(
                            f"Timeout creating page in existing session, invalidating and recreating session"
                        )
                        await _invalidate_bitchute_session(thread_number, log_table)
                        browser, context = await _ensure_bitchute_session(
                            thread_number, video_dir
                        )

                        # Close any lingering pages to prevent issues with reused sessions
                        for p in context.pages:
                            if not p.is_closed():
                                try:
                                    await p.close()
                                except:
                                    pass

                        page = await asyncio.wait_for(context.new_page(), timeout=60.0)
                        LogManager.log_upload_bitchute(
                            f"Created new Bitchute upload page in thread {thread_number} session after session recreation"
                        )
                    except Exception as e:
                        LogManager.log_upload_bitchute(
                            f"Failed to create page in existing session: {e}, invalidating and recreating session"
                        )
                        await _invalidate_bitchute_session(thread_number, log_table)
                        browser, context = await _ensure_bitchute_session(
                            thread_number, video_dir
                        )

                        # Close any lingering pages to prevent issues with reused sessions
                        for p in context.pages:
                            if not p.is_closed():
                                try:
                                    await p.close()
                                except:
                                    pass

                        page = await asyncio.wait_for(context.new_page(), timeout=60.0)
                        LogManager.log_upload_bitchute(
                            f"Created new Bitchute upload page in thread {thread_number} session after session recreation"
                        )

                    # Mask webdriver detection - MUST be done before any navigation
                    await PlaywrightUtils.mask_webdriver(page)
                    await PlaywrightUtils.block_media_loading(page)

                    nav_ok = await PlaywrightUtils.goto(
                        page,
                        "https://old.bitchute.com",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    if not nav_ok:
                        LogManager.log_upload_bitchute(
                            "Navigation error: could not load upload page.",
                            LogLevels.Error,
                        )
                        return False, "Navigation error: could not load upload page."

                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(
                        page, "networkidle", timeout=10000
                    )

                    # Check if logged in
                    login_link = page.locator("div.unauth-link a:has-text('Login')")
                    is_logged_in = await login_link.count() == 0

                    if not is_logged_in:
                        LogManager.log_upload_bitchute(
                            "Not logged in, proceeding to login"
                        )

                        # Navigate to home for login
                        nav_ok = await PlaywrightUtils.goto(
                            page,
                            "https://old.bitchute.com/",
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        if not nav_ok:
                            LogManager.log_upload_bitchute(
                                "Navigation error (non-critical): could not load https://old.bitchute.com/"
                            )
                        await PlaywrightUtils.random_delay(800, 1200)
                        await PlaywrightUtils.wait_for_load_state(
                            page, "networkidle", timeout=10000
                        )

                        # Click "Login" link
                        await login_link.click()
                        await PlaywrightUtils.random_delay(1500, 2500)
                        await PlaywrightUtils.wait_for_load_state(
                            page, "networkidle", timeout=10000
                        )

                        # Get Bitchute credentials
                        bitchute_email = await Account_Config.get_bitchute_email()
                        bitchute_password = await Account_Config.get_bitchute_password()

                        if not bitchute_email or not bitchute_password:
                            return False, "Bitchute credentials missing in config"

                        LogManager.log_upload_bitchute("Filling email...")
                        # Fill email
                        await PlaywrightUtils.fill_form_input_by_id(
                            page,
                            "id_username",
                            bitchute_email,
                            min_delay_ms=800,
                            max_delay_ms=1500,
                        )

                        # Fill password
                        LogManager.log_upload_bitchute("Filling password...")
                        await PlaywrightUtils.fill_form_input_by_id(
                            page,
                            "id_password",
                            bitchute_password,
                            min_delay_ms=800,
                            max_delay_ms=1500,
                        )

                        # Click login button
                        await PlaywrightUtils.click_element(
                            page,
                            "#auth_submit",
                            min_delay_ms=800,
                            max_delay_ms=1500,
                            suppress_exceptions=False,
                        )
                        await PlaywrightUtils.random_delay(2000, 3000)
                        await PlaywrightUtils.wait_for_load_state(
                            page, "networkidle", timeout=15000
                        )

                        LogManager.log_upload_bitchute(
                            "Login completed, waiting for session to stabilize"
                        )
                        await PlaywrightUtils.random_delay(2000, 3000)
                        try:
                            os.makedirs(
                                os.path.dirname(context._bitchute_storage_state_path),
                                exist_ok=True,
                            )
                            await context.storage_state(
                                path=context._bitchute_storage_state_path
                            )
                            LogManager.log_upload_bitchute(
                                f"Saved Bitchute storage state to {context._bitchute_storage_state_path}"
                            )
                        except Exception as e:
                            LogManager.log_upload_bitchute(
                                f"Failed to save Bitchute storage state: {e}"
                            )
                    else:
                        LogManager.log_upload_bitchute("Already logged in")
                        if not os.path.exists(context._bitchute_storage_state_path):
                            try:
                                os.makedirs(
                                    os.path.dirname(
                                        context._bitchute_storage_state_path
                                    ),
                                    exist_ok=True,
                                )
                                await context.storage_state(
                                    path=context._bitchute_storage_state_path
                                )
                                LogManager.log_upload_bitchute(
                                    f"Saved Bitchute storage state to {context._bitchute_storage_state_path}"
                                )
                            except Exception as e:
                                LogManager.log_upload_bitchute(
                                    f"Failed to save Bitchute storage state: {e}",
                                    LogLevels.Error,
                                )

                    # Navigate to upload page
                    nav_ok = await PlaywrightUtils.goto(
                        page,
                        "https://old.bitchute.com/myupload/",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    if not nav_ok:
                        LogManager.log_upload_bitchute(
                            "Navigation error: could not load upload page.",
                            LogLevels.Error,
                        )
                        return False, "Navigation error: could not load upload page."

                    await PlaywrightUtils.random_delay(1500, 2500)
                    await PlaywrightUtils.wait_for_load_state(
                        page, "networkidle", timeout=10000
                    )

                    # Run metadata and file submission concurrently
                    LogManager.log_upload_bitchute(
                        "Starting concurrent metadata and file submission..."
                    )
                    meta_task = asyncio.create_task(
                        _submit_meta(page, title, description, tags, log_table)
                    )
                    file_task = asyncio.create_task(
                        _submit_file(page, filepath, filename, unique_id, log_table)
                    )

                    file_result = await file_task
                    if not meta_task.done():
                        meta_result = await meta_task
                    else:
                        meta_result = meta_task.result()

                    # Check results from concurrent submissions
                    file_success, file_error, temp_file = file_result
                    if not meta_result or not file_success:
                        error_msg = (
                            file_error if file_error else "Metadata submission failed"
                        )
                        LogManager.log_upload_bitchute(
                            f"Submission failed: {error_msg}"
                        )
                        # Clean up temp file if it exists
                        if temp_file and os.path.exists(temp_file):
                            try:
                                os.unlink(temp_file)
                            except Exception:
                                pass
                        return False, error_msg

                    # While the file subbission is being processed run the initial validation check

                    # Click the "Proceed" button to trigger validation while the video uploads
                    await PlaywrightUtils.click_element(
                        page,
                        "button.btn.btn-primary[type='submit']:text('Proceed')",
                        min_delay_ms=800,
                        max_delay_ms=1500,
                        suppress_exceptions=False,
                    )

                    # Wait for form validation feedback (both elements should be visible)
                    timeout_ms = 10000
                    start_time = datetime.datetime.now()
                    while True:
                        count = await page.locator(
                            "div.valid-feedback:has-text('Looks good!')"
                        ).count()
                        if count == 2:
                            break
                        elapsed_ms = (
                            datetime.datetime.now() - start_time
                        ).total_seconds() * 1000
                        if elapsed_ms > timeout_ms:
                            raise TimeoutError(
                                f"Timeout waiting for 2 valid-feedback elements. Found {count}"
                            )
                        await asyncio.sleep(0.1)

                    LogManager.log_upload_bitchute(
                        f"Form validation passed, waiting for file upload to complete..."
                    )
                    # Wait for FilePond to finish and log progress
                    try:
                        await PlaywrightUtils.wait_for_upload_progress(
                            page,
                            "#videoInput span.filepond--file-status-main",
                            timeout_ms=1800000,
                            log_callback=lambda msg: LogManager.log_upload_bitchute(
                                msg
                            ),
                            progress_callback=lambda progress: LogManager.log_upload_bitchute(
                                f"Upload progress: {progress}"
                            ),
                            completion_strings={"100": None, "Complete": None},
                            completion_alt_selector='button[aria-label="Menu"]',
                        )
                    except Exception as e:
                        if "Timeout" in str(e):
                            # Check if the page has already navigated to the success page (for small files that upload quickly)
                            try:
                                await page.locator(
                                    'button[aria-label="Menu"]'
                                ).wait_for(state="visible", timeout=5000)
                                LogManager.log_upload_bitchute(
                                    "Upload completed quickly, success page detected"
                                )
                                # Close the page to reset session state for next upload
                                try:
                                    if page and not page.is_closed():
                                        await asyncio.wait_for(
                                            page.close(), timeout=5.0
                                        )
                                except Exception as close_e:
                                    LogManager.log_upload_bitchute(
                                        f"Error closing page after quick success: {close_e}"
                                    )
                                # After successful upload, break out of retry loop and return success
                                LogManager.log_upload_bitchute(
                                    "Upload to Bitchute completed successfully!"
                                )
                                return True, None
                            except Exception:
                                # Not on success page, save HTML for debugging and re-raise the timeout
                                try:
                                    html_save_path = os.path.join(
                                        DVR_Config.get_playwright_html_dir(),
                                        f"Thread_{thread_number}",
                                        f"{filename}_quick_upload_timeout.html",
                                    )
                                    os.makedirs(
                                        os.path.dirname(html_save_path), exist_ok=True
                                    )
                                    if (
                                        DVR_Config.get_playwright_session_error_html_dump()
                                    ):
                                        await PlaywrightUtils.save_page_html(
                                            page, html_save_path
                                        )
                                        LogManager.log_upload_bitchute(
                                            f"Saved page HTML for quick upload timeout to {html_save_path}"
                                        )
                                    else:
                                        LogManager.log_upload_bitchute(
                                            "Skipping quick upload HTML dump because session_error_html_dump is disabled."
                                        )
                                except Exception as dump_err:
                                    LogManager.log_upload_bitchute(
                                        f"Failed to save error HTML dump: {dump_err}"
                                    )
                                raise e
                        else:
                            raise e

                    # the page may navigate automatically after upload, so wait for that to happen before proceeding with any further steps
                    # Inject and display waiting banner
                    LogManager.log_upload_bitchute(
                        "Form submitted, displaying waiting banner..."
                    )
                    try:
                        if not page.is_closed():
                            await page.evaluate(
                                """
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
                            """
                            )
                            await PlaywrightUtils.wait_for_load_state(
                                page, "networkidle", timeout=5000
                            )
                        else:
                            LogManager.log_upload_bitchute(
                                "Page closed before banner injection; skipping waiting banner."
                            )
                    except Exception as e:
                        if (
                            "Execution context was destroyed" in str(e)
                            or "Navigation" in str(e)
                            or "Target closed" in str(e)
                        ):
                            pass  # Page likely navigated or closed, which is expected; ignore this error
                        else:
                            raise

                    LogManager.log_upload_bitchute(
                        "Waiting for new bitchute webpage to appear..."
                    )
                    for attempt in range(3):
                        try:
                            # Click on the proceed button again to finish upload cycle
                            # If this element is not found skip
                            await PlaywrightUtils.click_element(
                                page,
                                "button.btn.btn-primary[type='submit']:text('Proceed')",
                                min_delay_ms=800,
                                max_delay_ms=1500,
                                suppress_exceptions=True,
                            )

                            await asyncio.sleep(
                                2
                            )  # Allow time for page navigation after click
                            await page.locator('button[aria-label="Menu"]').wait_for(
                                state="visible", timeout=30000
                            )
                            LogManager.log_upload_bitchute(
                                "new bitchute webpage is now visible"
                            )
                            # Close the page to reset session state for next upload
                            try:
                                if page and not page.is_closed():
                                    await asyncio.wait_for(page.close(), timeout=5.0)
                            except Exception as e:
                                LogManager.log_upload_bitchute(
                                    f"Error closing page after error: {e}"
                                )

                            # After successful upload and new bitchute webpage appearance, break out of retry loop and return success
                            LogManager.log_upload_bitchute(
                                "Upload to Bitchute completed successfully!",
                                LogLevels.Info,
                            )
                            return True, None
                        except Exception as e:
                            if attempt == 2:
                                raise e  # Reraise on final attempt after logging
                except Exception as e:
                    LogManager.log_upload_bitchute(
                        f"Attempt {attempt + 1} failed: {e}\n{traceback.format_exc()}",
                        LogLevels.Info,
                    )

                    # Save the page HTML if a timeout or strict mode error occurs and dumps are enabled
                    if DVR_Config.get_playwright_session_error_html_dump() and (
                        "Timeout" in str(e) or "strict mode" in str(e)
                    ):
                        try:
                            html_save_path = os.path.join(
                                DVR_Config.get_playwright_html_dir(),
                                f"Thread_{thread_number}",
                                f"{filename}.html",
                            )
                            os.makedirs(os.path.dirname(html_save_path), exist_ok=True)
                            await PlaywrightUtils.save_page_html(page, html_save_path)
                            LogManager.log_upload_bitchute(
                                f"Saved page HTML to {html_save_path}",
                                LogLevels.Info,
                            )
                        except Exception:
                            pass

                    # Close the page to reset session state for next upload
                    try:
                        if page and not page.is_closed():
                            await asyncio.wait_for(page.close(), timeout=5.0)
                    except Exception as e:
                        LogManager.log_upload_bitchute(
                            f"Error closing page after error: {e}",
                            LogLevels.Info,
                        )

                    if attempt < max_retries - 1:
                        retry_delay = retry_delay_base * (2**attempt)
                        LogManager.log_upload_bitchute(
                            f"Retrying in {retry_delay} seconds...",
                            LogLevels.Info,
                        )
                        await asyncio.sleep(retry_delay)
                    continue

    except Exception as e:
        LogManager.log_upload_bitchute(
            f"ERROR: Upload to Bitchute failed: {e}\n{traceback.format_exc()}"
        )

        # Dump HTML content if error dump is enabled and page is available
        if (
            page
            and not page.is_closed()
            and DVR_Config.get_playwright_session_error_html_dump()
        ):
            try:
                playwright_root = DVR_Config.get_playwright_dir()
                error_dump_dir = os.path.join(playwright_root, "_Error_HTML_Dumps")
                os.makedirs(error_dump_dir, exist_ok=True)

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                html_dump_file = os.path.join(
                    error_dump_dir, f"bitchute_error_{timestamp}.html"
                )
                page_content = await page.content()

                with open(html_dump_file, "w", encoding="utf-8") as f:
                    f.write(page_content)

                LogManager.log_upload_bitchute(
                    f"Error HTML dump saved to: {html_dump_file}", log_table
                )
            except Exception as dump_err:
                LogManager.log_upload_bitchute(
                    f"Failed to save error HTML dump: {dump_err}", log_table
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
            if browser and hasattr(browser, "_playwright_instance"):
                playwright_instance = getattr(browser, "_playwright_instance")
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
