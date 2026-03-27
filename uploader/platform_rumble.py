import traceback
import os
import asyncio
import datetime
from utils.logging_utils import LogManager
from utils.meta_utils import MetaDataManager
from utils.utils_playwright import PlaywrightUtils
from config.config_accounts import Account_Config

# Reused browser/context to avoid repeated login in consecutive calls
_rumble_browser = None
_rumble_context = None


async def _close_rumble_session():
    global _rumble_browser, _rumble_context
    try:
        if _rumble_context:
            await _rumble_context.close()
    except Exception:
        pass
    try:
        if _rumble_browser:
            await _rumble_browser.close()
    except Exception:
        pass
    _rumble_browser = None
    _rumble_context = None


async def _ensure_rumble_session():
    global _rumble_browser, _rumble_context

    if _rumble_browser and _rumble_context:
        try:
            # Try reading storage state to verify context is alive
            await _rumble_context.storage_state()
            return _rumble_browser, _rumble_context
        except Exception:
            await _close_rumble_session()

    _rumble_browser = await PlaywrightUtils.launch_stealth_browser(headless=True)
    _rumble_context = await PlaywrightUtils.create_human_context(_rumble_browser)
    return _rumble_browser, _rumble_context


async def upload_to_rumble(filepath, filename, title):
    """
    Upload a video file to Rumble using Playwright.
    
    Args:
        filepath: Full path to the video file
        filename: Filename without extension
    """
    # Retry mechanism with exponential backoff
    max_retries = 3
    retry_delay_base = 30  # seconds
    
    try:
        for attempt in range(max_retries):
            page = None
            try:
                LogManager.log_upload_rumble(f"Attempting upload of file: {filepath} to Rumble (attempt {attempt + 1}/{max_retries})")
                
                # Get Rumble credentials
                rumble_email = Account_Config.get_rumble_email()
                rumble_password = Account_Config.get_rumble_password()
                rumble_channel = Account_Config.get_rumble_channel()
                
                if not rumble_email or not rumble_password or not rumble_channel:
                    LogManager.log_upload_rumble(
                        "Rumble credentials incomplete. Skipping upload. "
                        "Please configure [Rumble_Credentials] in dvr_accounts.cfg"
                    )
                    return False
                
                
                # Get description from meta
                description = MetaDataManager.read_value("Description", LogManager.UPLOAD_RUMBLE_LOG_FILE)
               
                # Get categories and tags from config or meta
                primary_category = Account_Config.get_rumble_primary_category()
                secondary_category = Account_Config.get_rumble_secondary_category() or ""
                tags = MetaDataManager.read_value("Tags", LogManager.UPLOAD_RUMBLE_LOG_FILE)

                # Ensure browser/context session; reuse if already logged in
                browser, context = await _ensure_rumble_session()

                # Create video recording directory with timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                attempt_str = f"attempt{attempt + 1}"
                logs_dir = os.path.dirname(LogManager.UPLOAD_RUMBLE_LOG_FILE)
                video_dir = os.path.join(logs_dir, "session_videos")
                os.makedirs(video_dir, exist_ok=True)
                
                # Keep using the persistent context to preserve login session
                page = await context.new_page()
                LogManager.log_upload_rumble(f"Using reusable Rumble context. Session video dir: {video_dir} [{timestamp}_{attempt_str}]")

                # Mask webdriver detection - MUST be done before any navigation
                await PlaywrightUtils.mask_webdriver(page)
                
                # Disable video playback and media loading to speed up page loads
                await page.evaluate("""
                    () => {
                        // Block video and audio loading
                        const originalVideoLoad = HTMLVideoElement.prototype.load;
                        HTMLVideoElement.prototype.load = function() {
                            this.src = '';
                            this.removeAttribute('src');
                        };
                        
                        // Block audio loading
                        const originalAudioLoad = HTMLAudioElement.prototype.load;
                        HTMLAudioElement.prototype.load = function() {
                            this.src = '';
                            this.removeAttribute('src');
                        };
                        
                        // Prevent autoplay
                        Object.defineProperty(HTMLMediaElement.prototype, 'autoplay', {
                            set: () => {},
                            get: () => false
                        });
                        
                        // Block play() calls
                        HTMLMediaElement.prototype.play = function() {
                            return Promise.resolve();
                        };
                        HTMLMediaElement.prototype.pause = function() {};
                        
                        // Block src setting
                        Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                            set: () => {},
                            get: () => ''
                        });
                        
                        // Block currentSrc
                        Object.defineProperty(HTMLMediaElement.prototype, 'currentSrc', {
                            get: () => ''
                        });
                        
                        // Prevent <source> tags from loading
                        const originalAppendChild = Element.prototype.appendChild;
                        Element.prototype.appendChild = function(node) {
                            if (node.tagName === 'SOURCE' && (node.type?.includes('video') || node.type?.includes('audio'))) {
                                node.src = '';
                                node.removeAttribute('src');
                            }
                            return originalAppendChild.call(this, node);
                        };
                        
                        // Intercept setAttribute for video/audio elements
                        const originalSetAttribute = Element.prototype.setAttribute;
                        Element.prototype.setAttribute = function(name, value) {
                            if ((this.tagName === 'VIDEO' || this.tagName === 'AUDIO' || this.tagName === 'SOURCE') && name === 'src') {
                                return;
                            }
                            return originalSetAttribute.call(this, name, value);
                        };
                    }
                """)
                
                # Log browser properties to check for bot detection BEFORE navigation
                user_agent = await page.evaluate("navigator.userAgent")
                
                is_headless = await page.evaluate("navigator.webdriver")
               
                chrome_runtime = await page.evaluate("typeof chrome !== 'undefined' && typeof chrome.runtime !== 'undefined'")
                
                # Log platform detection
                platform = await page.evaluate("navigator.platform")
               
                touch_points = await page.evaluate("navigator.maxTouchPoints")
               
                # DO NOT intercept routes - this triggers Cloudflare detection
                # Instead, let Playwright handle requests naturally and Cloudflare challenges with JavaScript challenges
                
                
                # Set up console logging callback (filter out noisy framework/loader events)
                def console_log(msg_type, msg_text):
                    # Skip logging connection errors from ad networks being blocked
                    if "ERR_CONNECTION_REFUSED" in msg_text or "Failed to load resource" in msg_text:
                        return

                    # Skip noisy Rumblr loader/auth/debug messages that are not useful for upload flow
                    verbose_filters = [
                        "[rum-loader]",
                        "sentry initialized",
                        "[bugsnag] Loaded!",
                        "document.domain mutation is ignored",
                        "ES import onSuccess",
                        "Google fedmc loaded",
                    ]
                    if any(filter_key in msg_text for filter_key in verbose_filters):
                        return

                    LogManager.log_upload_rumble(f"{msg_type}: {msg_text}")

                await PlaywrightUtils.setup_console_logging(page, console_log)
                

                # Navigate to Rumble with aggressive Cloudflare handling
                try:
                    await page.goto("https://rumble.com/", wait_until='domcontentloaded')
                except Exception as nav_error:
                    LogManager.log_upload_rumble(f"Navigation error: {nav_error}")
                    try:
                        html_content = await page.content()
                        #LogManager.log_upload_rumble(f"FULL Page HTML after navigation error:\n{html_content}")
                    except:
                        pass
                    raise
                
                # Dump entire HTML immediately after loading
                try:
                    html_content = await page.content()
                    #LogManager.log_upload_rumble(f"FULL Page HTML after initial navigation:\n{html_content}")
                except:
                    pass
                
                await PlaywrightUtils.random_delay(800, 1200)
                
                # Wait for network and handle Cloudflare
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    LogManager.log_upload_rumble("Network idle timeout, checking Cloudflare...")
                    # Log page content on timeout
                    try:
                        html_content = await page.content()
                        #LogManager.log_upload_rumble(f"FULL Page HTML on network timeout:\n{html_content}")
                    except:
                        pass
                
                await PlaywrightUtils.check_cloudflare(page, LogManager.log_upload_rumble)
                await PlaywrightUtils.random_delay(500, 800)
                
                # Check if logged in
                # Target the desktop sign-in link using element tag and button classes
                sign_in_button = page.locator('a[href="/login.php"].btn.btn-medium.btn-grey')
                is_logged_in = await sign_in_button.count() == 0
                
                if not is_logged_in:
                    LogManager.log_upload_rumble("Not logged in, proceeding to login")
                    await PlaywrightUtils.click_element(page, 'a[href="/login.php"].btn.btn-medium.btn-grey', 600, 1200)
                    
                    # Wait for auth page with retry
                    await PlaywrightUtils.random_delay(2000, 3000)
                    try:
                        await page.wait_for_url("https://auth.rumble.com/**", timeout=30000)
                    except:
                        LogManager.log_upload_rumble("Timeout waiting for auth page, checking current state...")
                        await page.wait_for_load_state("networkidle", timeout=45000)
                    
                    await PlaywrightUtils.check_cloudflare(page, LogManager.log_upload_rumble)
                    await PlaywrightUtils.random_delay(1500, 2500)
                    
                    # Wait for form stability
                    await page.wait_for_load_state("networkidle", timeout=60000)
                    
                    # Verify username field exists before filling
                    username_field = page.locator('input[name="username"]')
                    if await username_field.count() == 0:
                        LogManager.log_upload_rumble("ERROR: Username field not found on auth page")
                        return
                    
                    # Fill username
                    LogManager.log_upload_rumble(f"Filling username: {rumble_email}")
                    await PlaywrightUtils.fill_form_field(page, 'input[name="username"]', rumble_email)
                    await PlaywrightUtils.random_delay(300, 600)
                    
                    # Verify username was filled
                    username_value = await page.locator('input[name="username"]').input_value()
                    if username_value != rumble_email:
                        LogManager.log_upload_rumble(f"WARNING: Username field not properly filled. Expected: {rumble_email}, Got: {username_value}")
                    
                    # Fill password
                    LogManager.log_upload_rumble("Filling password")
                    await PlaywrightUtils.fill_form_field(page, 'input[name="password"]', rumble_password)
                    await PlaywrightUtils.random_delay(300, 600)
                    
                    # Click sign in
                    LogManager.log_upload_rumble("Clicking submit button")
                    await PlaywrightUtils.click_element(page, 'button[type="submit"]')
                    
                    # Wait longer for auth response with retry logic
                    max_retries_login = 2
                    for attempt_login in range(max_retries_login):
                        try:
                            LogManager.log_upload_rumble(f"Waiting for redirect to Rumble (attempt {attempt_login + 1}/{max_retries_login})...")
                            await page.wait_for_url("https://rumble.com/**", timeout=45000)
                            break
                        except Exception as e:
                            LogManager.log_upload_rumble(f"Timeout waiting for redirect: {e}")
                            if attempt_login < max_retries_login - 1:
                                LogManager.log_upload_rumble("Retrying login...")
                                # Go back to login and retry
                                await page.goto("https://auth.rumble.com/login.php")
                                await page.wait_for_load_state("networkidle")
                                await PlaywrightUtils.random_delay(1000, 1500)
                            else:
                                raise
                    
                    await PlaywrightUtils.check_cloudflare(page, LogManager.log_upload_rumble)
                    await PlaywrightUtils.random_delay(800, 1500)
                    await page.wait_for_load_state("networkidle")
                    LogManager.log_upload_rumble("Login successful")
                else:
                    LogManager.log_upload_rumble("Already logged in")
                
                # Navigate to upload page with better Cloudflare handling
                LogManager.log_upload_rumble("Navigating to upload page...")
                try:
                    await page.goto("https://rumble.com/upload.php", wait_until='domcontentloaded')
                except Exception as upload_nav_error:
                    LogManager.log_upload_rumble(f"Upload page navigation error: {upload_nav_error}")
                    try:
                        html_content = await page.content()
                        LogManager.log_upload_rumble(f"FULL Page HTML after upload page error:\n{html_content}")
                    except:
                        pass
                    raise
                
                await PlaywrightUtils.random_delay(1500, 2500)
             
                
                await PlaywrightUtils.check_cloudflare(page, LogManager.log_upload_rumble)
                await PlaywrightUtils.random_delay(1500, 2500)
                
                # Upload file
                await PlaywrightUtils.random_delay(800, 1500)
                await page.locator('input#Filedata').set_input_files(filepath)
                await PlaywrightUtils.random_delay(1000, 2000)
                LogManager.log_upload_rumble("File selected for upload")

                # Wait for upload progress to reach 100%
                await PlaywrightUtils.wait_for_upload_progress(
                    page,
                    'div.loader_basic:not(.loader-initial) > span.green_percent',
                    timeout_ms=1800000,
                    log_callback=LogManager.log_upload_rumble
                )

                # Fill title
                await PlaywrightUtils.fill_form_field(page, 'input#title', title, 800, 1500)
                
                # Fill description
                await PlaywrightUtils.fill_form_field(page, 'textarea#description', description)
                
                # Upload custom thumbnail
                thumbnail_path = MetaDataManager.get_thumbnail_path()
                if thumbnail_path and os.path.exists(thumbnail_path):
                    LogManager.log_upload_rumble(f"Uploading custom thumbnail from: {thumbnail_path}")
                    await page.locator('input#customThumb').set_input_files(thumbnail_path)
                    await PlaywrightUtils.random_delay(800, 1500)
                    LogManager.log_upload_rumble("Custom thumbnail uploaded")
                else:
                    LogManager.log_upload_rumble(f"Thumbnail not found at: {thumbnail_path}. Using default")
                
                # Select primary category
                await PlaywrightUtils.click_element(page, 'input[name="primary-category"]')
                await PlaywrightUtils.fill_form_field(page, 'input[name="primary-category"]', primary_category)
                await PlaywrightUtils.press_key(page, "Enter")
                
                # Select secondary category if provided
                if secondary_category:
                    await PlaywrightUtils.click_element(page, 'input[name="secondary-category"]')
                    await PlaywrightUtils.fill_form_field(page, 'input[name="secondary-category"]', secondary_category)
                    await PlaywrightUtils.press_key(page, "Enter")
                
                # Fill tags
                await PlaywrightUtils.fill_form_field(page, 'input#tags', tags)
                
                # Click upload
                await PlaywrightUtils.click_element(page, 'input#submitForm', 800, 1500)
                await PlaywrightUtils.random_delay(1000, 2000)
                
                LogManager.log_upload_rumble("Form submitted, waiting for terms and conditions page...")
                
                # Wait for terms and conditions page to appear
                LogManager.log_upload_rumble("Waiting for terms and conditions form to render...")
                await PlaywrightUtils.wait_for_element(
                    page,
                    'div.video-more.form-wrap.terms-options',
                    timeout_ms=90000,
                    log_callback=LogManager.log_upload_rumble
                )
                
                # Extra wait for form to fully stabilize
                await PlaywrightUtils.random_delay(1500, 2500)
                
                # Check the two required checkboxes
                LogManager.log_upload_rumble("Checking content rights checkbox...")
                await page.evaluate("""
                document.querySelectorAll('input[name="crights"]').forEach(cb => {
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change', { bubbles: true }));
                    cb.dispatchEvent(new Event('input', { bubbles: true }));
                });
                """)
                
                # Click final submit button
                LogManager.log_upload_rumble("Submitting final form...")
                await PlaywrightUtils.click_element(
                    page,
                    'input#submitForm2',
                    800,
                    1500
                )
                
                # Wait for success message
                LogManager.log_upload_rumble("Waiting for upload completion confirmation...")
                await PlaywrightUtils.wait_for_element(
                    page,
                    'h3.title:has-text("Video Upload Complete!")',
                    timeout_ms=60000,
                    log_callback=LogManager.log_upload_rumble
                )
                
                LogManager.log_upload_rumble(f"Upload initiated for {filename} to Rumble channel: {rumble_channel}")
                try:
                    await page.close()
                except Exception:
                    pass
                return True  # Success - exit retry loop
            
            except Exception as e:
                LogManager.log_upload_rumble(
                    f"ERROR on attempt {attempt + 1}/{max_retries}: {e}\n{traceback.format_exc()}"
                )
                if page:
                    try:
                        await page.close()
                    except:
                        pass
                await _close_rumble_session()
                
                # If this was the last attempt, give up
                if attempt == max_retries - 1:
                    LogManager.log_upload_rumble(
                        f"FATAL: Upload failed after {max_retries} attempts. Giving up."
                    )
                    raise
                
                # Calculate exponential backoff delay
                delay = retry_delay_base * (2 ** attempt)
                LogManager.log_upload_rumble(
                    f"Retrying upload in {delay} seconds... ({max_retries - attempt - 1} attempts remaining)"
                )
                await asyncio.sleep(delay)
    
    except Exception as e:
        LogManager.log_upload_rumble(
            f"ERROR: Upload to Rumble failed: {e}\n{traceback.format_exc()}"
        )
        return False
