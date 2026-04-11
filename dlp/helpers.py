import os
import asyncio
import json
import time
from yt_dlp import YoutubeDL
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from dlp.logger import DLP_Logger, DLP_Logger_Patterns
from dlp.events import DLPEvents


class LogBuffer:
    """Buffers log messages for conditional output."""
    def __init__(self):
        self.messages = []
    
    def add(self, message, log_file_name=None):
        """Add a message to the buffer."""
        self.messages.append((message, log_file_name))
    
    def flush(self):
        """Output all buffered messages via LogManager."""
        for message, log_file_name in self.messages:
            LogManager.log_message(message, log_file_name)
    
    def clear(self):
        """Clear the buffer without outputting."""
        self.messages.clear()


class DLPHelpers:
    """Class encapsulating DLP utility methods."""

    dlp_cookies_file = DVR_Config.get_yt_cookies_file()
    dlp_cookies_present = os.path.exists(dlp_cookies_file)
    dlp_verbose = DVR_Config.get_verbose_dlp_mode()
    dlp_no_progress = DVR_Config.no_progress_dlp_downloads()
    dlp_keep_fragments = DVR_Config.get_keep_fragments_dlp_downloads()
    dlp_max_fragment_retries = int(DVR_Config.get_max_dlp_fragment_retries() or 10)
    dlp_download_timeout = DVR_Config.get_dlp_download_timeout()
    dlp_getinfo_timeout = DVR_Config.get_dlp_getinfo_timeout()
    dlp_stall_timeout = DVR_Config.get_dlp_stall_timeout()

    @staticmethod
    def _is_signin_or_age_error(dlp_logger):
        """Check if logger detected signin or age confirmation error."""
        return dlp_logger.detected and dlp_logger.last_match_result in (
            "is_age_confirmation_required", "is_signin_required"
        )

    @staticmethod
    def _is_rate_limit_error_logger(dlp_logger):
        """Check if logger detected rate limit error."""
        return dlp_logger.detected and dlp_logger.last_match_result == "is_rate_limited"

    @staticmethod
    def _is_deno_js_timeout_logger(dlp_logger):
        """Check if logger detected Deno JS timeout error."""
        return dlp_logger.detected and dlp_logger.last_match_result == "is_deno_js_timeout"

    @staticmethod
    def _reset_logger(log_file_name, log_warnings_and_above_only=False):
        """Create a fresh logger instance."""
        return DLP_Logger(
            patterns=DLP_Logger_Patterns,
            log_file_name=log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )

    @classmethod
    def _apply_js_runtime(cls, ydl_opts, log_file_name=None):
        """Apply js_runtime configuration to ydl_opts if not 'deno' (the default).
        
        Args:
            ydl_opts: Dictionary of yt-dlp options to modify
            log_file_name: Optional log file for messages
        
        Returns:
            Modified ydl_opts dictionary
        """
        if ydl_opts is None:
            ydl_opts = {}
        
        js_runtime = DVR_Config.get_dlp_js_runtime()
        # Only add the option if it's not the default 'deno'
        if js_runtime != "deno":
            ydl_opts["compat_opts"] = ["no-deno", f"js-{js_runtime}"]
        return ydl_opts

    @staticmethod
    def _setup_attempt1_buffer():
        """Setup buffering for attempt 1 logs."""
        attempt1_buffer = LogBuffer()
        original_log_message = LogManager.log_message
        
        def buffered_log(message, log_file=None):
            attempt1_buffer.add(message, log_file)
        
        return attempt1_buffer, original_log_message, buffered_log

    @classmethod
    async def _retry_with_cookies(
        cls, ydl_opts, operation_func, operation_args, error_reason, log_file_name=None,
        log_warnings_and_above_only=False,
    ):
        """Attempt an operation with cookies after initial failure.
        
        Args:
            ydl_opts: Base YoutubeDL options
            operation_func: The async function to call (e.g., cls.getinfo, cls.getentries)
            operation_args: Dict of kwargs for operation_func (excluding ydl_opts, which is updated)
            error_reason: String describing why retry is needed
            log_file_name: Log file for messages
            log_warnings_and_above_only: Whether to ignore DLP messages below warning level

        Returns:
            Result from operation if successful, or raises exception if it fails
        """
        if not cls.dlp_cookies_present:
            error_msg = (
                f"{error_reason.replace('_', ' ').title()}: No cookies file available to authenticate. "
                f"Please export YouTube cookies using yt-dlp."
            )
            LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
            raise Exception(error_msg)
        
        LogManager.log_message(
            f"First DLP Attempt Failed: {error_reason} [RESOLVED]",
            log_file_name,
        )
        LogManager.log_message(
            f"Attempt 2: Retrying with cookies file: {cls.dlp_cookies_file}",
            log_file_name,
        )
        
        # Prepare options with cookies
        ydl_opts_with_cookies = dict(ydl_opts)
        ydl_opts_with_cookies["cookiefile"] = cls.dlp_cookies_file
        ydl_opts_with_cookies["logger"] = cls._reset_logger(
            log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )
        
        # Build retry args with updated ydl_opts
        retry_args = dict(operation_args) if isinstance(operation_args, dict) else operation_args
        if isinstance(retry_args, dict):
            retry_args["ydl_opts"] = ydl_opts_with_cookies
            retry_args["log_warnings_and_above_only"] = log_warnings_and_above_only
        
        try:
            return await operation_func(**retry_args)
        except Exception as retry_error:
            error_msg = f"{error_reason.replace('_', ' ').title()}: Failed even with cookies: {retry_error}"
            LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
            raise Exception(error_msg)

    @staticmethod
    def _handle_signin_error(
        error_msg, attempt1_buffer=None, log_file_name=None
    ):
        """Log and raise a signin-related error."""
        if attempt1_buffer != None:
            attempt1_buffer.flush()
        LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
        raise Exception(error_msg)

    @staticmethod
    async def _attempt_operation(operation_func, operation_args, attempt1_buffer, buffered_log, log_file_name=None):
        """Execute an operation with buffered logging.
        
        Returns: (result, error_reason, success)
            result: The result from the operation (or None if failed)
            error_reason: Error description if failed
            success: Whether operation succeeded
        """
        try:
            result = await operation_func(**operation_args)
            return result, None, True
        except Exception as e:
            error_reason = f"{type(e).__name__}: {str(e)[:100]}"
            buffered_log(
                f"Exception on first attempt: {error_reason}",
                log_file_name,
            )
            return None, error_reason, False

    @classmethod
    async def download(
        cls,
        ydl_opts,
        url_or_list,
        timeout_enabled=True,
        log_file_name=None,
        log_warnings_and_above_only=False,
    ):
        """Core download helper that invokes YoutubeDL.download with given options.
        
        Uses dual timeout protection: overall limit + stall detection.
        Stall timeout triggers faster than overall timeout.
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts = cls._apply_js_runtime(ydl_opts, log_file_name)

        if "logger" in ydl_opts:
            logger = ydl_opts["logger"]
            if isinstance(logger, DLP_Logger):
                logger.log_warnings_and_above_only = log_warnings_and_above_only
        elif log_warnings_and_above_only:
            ydl_opts["logger"] = cls._reset_logger(
                log_file_name,
                log_warnings_and_above_only=log_warnings_and_above_only,
            )

        ydl_opts["keep_fragments"] = cls.dlp_keep_fragments == True
        ydl_opts["fragment_retries"] = cls.dlp_max_fragment_retries
        
        if cls.dlp_verbose == True:
            LogManager.log_message(
                f"Starting youtube download helper with options {ydl_opts}",
                log_file_name,
            )
        
        # Wrap download in timeout
        try:
            with YoutubeDL(ydl_opts) as ydl:
                download_task = asyncio.create_task(
                    asyncio.to_thread(ydl.download, url_or_list)
                )
                
                if timeout_enabled:
                    # Use a stall timeout to detect hung downloads faster
                    stall_check_interval = 10
                    download_start_time = time.time()
                    
                    def get_progress_hooks():
                        """Extract DLPEvents from progress hooks if present."""
                        hooks = ydl_opts.get("progress_hooks", [])
                        events = []
                        for hook in hooks:
                            if hasattr(hook, "__self__"):
                                obj = hook.__self__
                                if hasattr(obj, "check_for_stall"):
                                    events.append(obj)
                        return events
                    
                    # Get DLPEvents instances for stall monitoring
                    dlp_events_list = get_progress_hooks()
                    
                    # Monitor for stalls while download runs
                    while not download_task.done():
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(download_task),
                                timeout=stall_check_interval
                            )
                            break  # Download completed
                        except asyncio.TimeoutError:
                            # Check for stalls
                            for dlp_events in dlp_events_list:
                                is_stalled, stall_msg = dlp_events.check_for_stall()
                                if is_stalled:
                                    download_task.cancel()
                                    LogManager.log_message(f"ERROR: {stall_msg}", log_file_name)
                                    raise TimeoutError(stall_msg)
                        
                        # Overall timeout safeguard (30 minutes)
                        elapsed = time.time() - download_start_time
                        if elapsed > cls.dlp_download_timeout:
                            download_task.cancel()
                            error_msg = f"Download exceeded maximum time limit ({cls.dlp_download_timeout}s)"
                            LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
                            raise TimeoutError(error_msg)
                else:
                    # No timeout detection
                    pass
                
                # Get final result
                await download_task
                
            LogManager.log_message("finished youtube downloader helper", log_file_name)
        except TimeoutError:
            # Re-raise TimeoutError as-is
            raise
        except asyncio.CancelledError:
            error_msg = "Download was cancelled due to stall detection"
            LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
            raise TimeoutError(error_msg)
        except Exception as e:
            # Log unexpected errors but let them propagate
            LogManager.log_message(f"Unexpected error in download: {e}", log_file_name)
            raise

    @classmethod
    async def getinfo(
        cls,
        ydl_opts,
        url_or_list,
        log_file_name=None,
        log_warnings_and_above_only=False,
    ):
        """Core info helper that invokes YoutubeDL.extract_info with a detection logger."""
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts = cls._apply_js_runtime(ydl_opts, log_file_name)
        ydl_opts["keep_fragments"] = cls.dlp_keep_fragments == True
        ydl_opts["fragment_retries"] = cls.dlp_max_fragment_retries
        if "logger" in ydl_opts:
            DLPLogger = ydl_opts["logger"]
            if isinstance(DLPLogger, DLP_Logger):
                DLPLogger.log_warnings_and_above_only = log_warnings_and_above_only
        else:
            DLPLogger = DLP_Logger(
                patterns=DLP_Logger_Patterns,
                log_file_name=log_file_name,
                log_warnings_and_above_only=log_warnings_and_above_only,
            )
            ydl_opts["logger"] = DLPLogger

        if cls.dlp_verbose == True:
            LogManager.log_message(
                f"Starting youtube getinfo helper with options {ydl_opts}",
                log_file_name,
            )
        info = None
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = await asyncio.wait_for(
                    asyncio.to_thread(ydl.extract_info, url_or_list, False),
                    timeout=cls.dlp_getinfo_timeout
                )
            except asyncio.TimeoutError:
                error_msg = f"Getinfo timeout exceeded ({cls.dlp_getinfo_timeout}s). Metadata retrieval stalled."
                LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
                raise TimeoutError(error_msg)
            except Exception as e:
                if not DLPLogger.detected:
                    LogManager.log_message(
                        f"Exception in getinfo helper {e}",
                        log_file_name,
                    )
            
            # Check logger detection using centralized patterns
            if cls._is_signin_or_age_error(DLPLogger):
                error_type = DLPLogger.last_match_result
                LogManager.log_message(
                    f"[getinfo] Signin/age error detected by logger ({error_type}), will retry with cookies",
                    log_file_name,
                )
                return {"_needs_signin": True, "_error_type": error_type}
            
            if cls._is_rate_limit_error_logger(DLPLogger):
                LogManager.log_message(
                    "[getinfo] Rate limit detected by logger, will retry with cookies",
                    log_file_name,
                )
                return {"_needs_signin": True, "_error_type": "is_rate_limited"}
            
            if info is None:
                if ydl_opts.get("skip_download") == True:
                    return {"status": "success", "skip_download": True}
                LogManager.log_message(
                    "Failed to determine current live_status for this video returning none ",
                    log_file_name,
                )
                return None
            else:
                # SUCCESS: info was extracted
                # Check if this looks like signin requirement (no formats were extracted)
                # This happens when YouTube returns a page that requires authentication
                if isinstance(info, dict):
                    # If we got a response but no formats, likely need signin
                    formats = info.get("formats") or []
                    video_id = info.get("id")
                    entry_count = len(info.get("entries") or [])
                    is_playlist = info.get("_type") in ("playlist", "multi_video") or entry_count > 0
                    
                    if not formats and video_id:
                        # Check if this is a playlist/channel (which naturally has no formats)
                        if is_playlist:
                            LogManager.log_message(
                                f"[getinfo] Channel/Playlist {video_id} with {entry_count} entries returned successfully",
                                log_file_name,
                            )
                            return info
                        
                        # We have a video ID but no formats - likely authentication issue
                        LogManager.log_message(
                            f"[getinfo fallback] Video {video_id} returned but with no formats available - likely authentication required, will retry with cookies",
                            log_file_name,
                        )
                        return {"_needs_signin": True, "_error_type": "is_signin_required"}
                
                return info

    @classmethod
    async def getentries(
        cls,
        ydl_opts,
        videos_url=None,
        shorts_url=None,
        log_file_name=None,
        log_warnings_and_above_only=False,
    ):
        """Fetch entries for provided section URLs (videos/shorts)."""
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts = cls._apply_js_runtime(ydl_opts, log_file_name)
        ydl_opts["keep_fragments"] = cls.dlp_keep_fragments == True
        ydl_opts["fragment_retries"] = cls.dlp_max_fragment_retries
        collected = []

        if "logger" in ydl_opts:
            dlp_logger = ydl_opts["logger"]
            if isinstance(dlp_logger, DLP_Logger):
                dlp_logger.log_warnings_and_above_only = log_warnings_and_above_only
        else:
            dlp_logger = DLP_Logger(
                patterns=DLP_Logger_Patterns,
                log_file_name=log_file_name,
                log_warnings_and_above_only=log_warnings_and_above_only,
            )

        flat_opts = dict(ydl_opts)
        flat_opts["extract_flat"] = True
        if "logger" not in flat_opts:
            flat_opts["logger"] = dlp_logger

        if cls.dlp_verbose == True:
            LogManager.log_message(
                f"Starting youtube getentries helper with options {ydl_opts}",
                log_file_name,
            )
        
        last_exception = None
        with YoutubeDL(flat_opts) as flat_ydl:
            for section_url in (videos_url, shorts_url):
                if not section_url:
                    continue
                try:
                    info = await asyncio.wait_for(
                        asyncio.to_thread(flat_ydl.extract_info, section_url, False),
                        timeout=cls.dlp_getinfo_timeout
                    )
                except asyncio.TimeoutError:
                    error_msg = f"Getentries timeout exceeded ({cls.dlp_getinfo_timeout}s) for {section_url}"
                    LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
                    raise TimeoutError(error_msg)
                except Exception as e:
                    last_exception = e
                    try:
                        msg = str(e) or ""
                    except Exception:
                        msg = ""
                    if "does not have a shorts tab" in msg.lower():
                        LogManager.log_message(
                            f"Warning: shorts tab missing for {section_url}: {msg}",
                            log_file_name,
                        )
                        continue
                    elif "does not have a videos tab" in msg.lower():
                        LogManager.log_message(
                            f"Warning: videos tab missing for {section_url}: {msg}",
                            log_file_name,
                        )
                        continue
                    raise

                # Check for signin/age errors after fetching entries
                if cls._is_signin_or_age_error(dlp_logger):
                    error_type = dlp_logger.last_match_result
                    return {"_needs_signin": True, "_error_type": error_type}
                if cls._is_rate_limit_error_logger(dlp_logger):
                    log_prefix = "[getentries]"
                    LogManager.log_message(
                        f"{log_prefix} Rate limit detected in logger, will need retry",
                        log_file_name,
                    )
                    return {"_needs_signin": True, "_error_type": "is_rate_limited"}

                entries = info.get("entries") or []
                collected.extend(entries)

        channel_playlist_file = DVR_Config.get_channel_playlist()
        persistent_urls = set()
        persistent_ids = set()
        if channel_playlist_file and os.path.exists(channel_playlist_file):
            try:
                with open(channel_playlist_file, "r", encoding="utf-8") as pf:
                    data = json.load(pf) or []
                for item in data:
                    try:
                        if isinstance(item, dict):
                            uid = item.get("UniqueID") or item.get("UniqueId")
                            if uid is not None:
                                persistent_ids.add(str(uid))
                            url = item.get("URL") or item.get("webpage_url")
                            if url:
                                persistent_urls.add(str(url))
                        else:
                            persistent_urls.add(str(item))
                    except Exception:
                        continue
            except Exception as e:
                LogManager.log_message(
                    f"Failed to read persistent playlist {channel_playlist_file}: {e}",
                    log_file_name,
                )

        def _entry_url(e):
            if not isinstance(e, dict):
                return None
            return (
                e.get("webpage_url")
                or e.get("url")
                or e.get("original_url")
                or e.get("id")
                or None
            )

        entries_to_fetch = []
        for ent in collected:
            try:
                ent_url = _entry_url(ent)
                ent_id = None
                try:
                    ent_id = (
                        str(ent.get("id"))
                        if isinstance(ent, dict) and ent.get("id") is not None
                        else None
                    )
                except Exception:
                    ent_id = None

                if ent_id and ent_id in persistent_ids:
                    continue
                if ent_url and ent_url in persistent_urls:
                    continue

                entries_to_fetch.append(ent)
            except Exception:
                entries_to_fetch.append(ent)

        if entries_to_fetch and entries_to_fetch:
            LogManager.log_message(
                f"Fetching full metadata for {len(entries_to_fetch)} new entries (out of {len(collected)})",
                log_file_name,
            )
            detailed_entries = []
            with YoutubeDL(ydl_opts) as ydl:
                for ent in entries_to_fetch:
                    url = _entry_url(ent)
                    if not url:
                        continue
                    try:
                        info = await asyncio.wait_for(
                            asyncio.to_thread(ydl.extract_info, url, False),
                            timeout=cls.dlp_getinfo_timeout
                        )

                        # Check for signin/age errors after each entry fetch
                        if cls._is_signin_or_age_error(dlp_logger):
                            error_type = dlp_logger.last_match_result
                            return {"_needs_signin": True, "_error_type": error_type}
                        if cls._is_rate_limit_error_logger(dlp_logger):
                            return {"_needs_signin": True, "_error_type": "is_rate_limited"}

                        # Check if entry was fetched but has no formats (indicates auth failure)
                        if isinstance(info, dict):
                            formats = info.get("formats") or []
                            video_id = info.get("id")
                            entry_count = len(info.get("entries") or [])
                            is_playlist = info.get("_type") in ("playlist", "multi_video") or entry_count > 0
                            
                            if not formats and video_id:
                                # Check if this is a nested playlist (which naturally has no formats)
                                if is_playlist:
                                    LogManager.log_message(
                                        f"[getentries] Entry {video_id} is a nested playlist with {entry_count} items (no formats expected)",
                                        log_file_name,
                                    )
                                    detailed_entries.append(info)
                                    continue
                                
                                # We have a video ID but no formats - likely authentication issue
                                LogManager.log_message(
                                    f"[getentries fallback] Entry {video_id} returned but with no formats - likely authentication required",
                                    log_file_name,
                                )
                                return {"_needs_signin": True, "_error_type": "is_signin_required"}

                        detailed_entries.append(info)
                    except Exception as e:
                        # Fallback: check exception message for signin/rate-limit errors
                        exc_str = str(e).lower()
                        if "confirm you're not a bot" in exc_str or "signin required" in exc_str:
                            LogManager.log_message(
                                f"Signin/bot confirmation detected in exception for entry {url}: {e}",
                                log_file_name,
                            )
                            return {"_needs_signin": True, "_error_type": "is_signin_required"}
                        
                        LogManager.log_message(
                            f"Failed to fetch metadata for entry {url}: {e}",
                            log_file_name,
                        )

            return detailed_entries
        else:
            # Fallback: check if we failed to collect entries due to signin
            if last_exception:
                exc_str = str(last_exception).lower()
                if "confirm you're not a bot" in exc_str or "signin required" in exc_str:
                    LogManager.log_message(
                        f"Signin/bot confirmation detected in exception (logger missed it): {last_exception}",
                        log_file_name,
                    )
                    return {"_needs_signin": True, "_error_type": "is_signin_required"}
            
            return []

    @classmethod
    async def download_with_retry(
        cls,
        ydl_opts,
        url_or_list,
        timeout_enabled=True,
        log_file_name=None,
        log_warnings_and_above_only=False,
    ):
        """Download using YoutubeDL; retry on transient TLS errors and signin-required errors.
        
        Buffers attempt 1 logs and outputs conditionally based on success/failure (if enabled in config).
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts = cls._apply_js_runtime(ydl_opts, log_file_name)
        
        # Check if buffered logging is enabled
        use_buffering = DVR_Config.get_dlp_buffer_first_attempt_errors()
        if use_buffering:
            attempt1_buffer, original_log_message, buffered_log = cls._setup_attempt1_buffer()
        else:
            attempt1_buffer = None
            original_log_message = LogManager.log_message
            buffered_log = LogManager.log_message  # Use direct logging when buffering disabled

        first_attempt_error = None
        first_attempt_logger = None
        first_error_reason = None

        # First attempt without cookies (with optional buffering)
        dlp_logger = cls._reset_logger(
            log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )
        ydl_opts["logger"] = dlp_logger

        if use_buffering:
            LogManager.log_message = buffered_log
        try:
            buffered_log(
                "[download_with_retry] Attempt 1: Calling [download] without cookies",
                log_file_name,
            )
            try:
                await cls.download(
                    ydl_opts,
                    url_or_list,
                    timeout_enabled,
                    log_file_name,
                    log_warnings_and_above_only,
                )
                buffered_log(
                    "[download_with_retry] SUCCESS: Downloaded without cookies needed",
                    log_file_name,
                )
                # Success - restore logger and flush the buffer
                if use_buffering:
                    LogManager.log_message = original_log_message
                if attempt1_buffer != None:
                    attempt1_buffer.flush()
                return
            except Exception as e:
                first_attempt_error = e
                first_attempt_logger = dlp_logger
                first_error_reason = f"{type(e).__name__}: {str(e)[:100]}"
                buffered_log(
                    f"[download_with_retry] Exception on attempt 1: {first_error_reason}",
                    log_file_name,
                )
                # Log logger state
                logger_detected = first_attempt_logger.detected if first_attempt_logger else False
                logger_match = first_attempt_logger.last_match_result if first_attempt_logger and hasattr(first_attempt_logger, 'last_match_result') else None
                buffered_log(
                    f"[download_with_retry] Logger state after exception: detected={logger_detected}, last_match_result={logger_match}",
                    log_file_name,
                )
        finally:
            if use_buffering:
                LogManager.log_message = original_log_message

        # Attempt 1 failed, now check what kind of error and retry if possible
        if cls._is_signin_or_age_error(first_attempt_logger):
            error_type = first_attempt_logger.last_match_result

            if not cls.dlp_cookies_present:
                error_msg = (
                    f"{error_type.replace('_', ' ').title()}: No cookies file available to authenticate. "
                    f"Please export YouTube cookies using yt-dlp."
                )
                if use_buffering and attempt1_buffer != None:
                    attempt1_buffer.flush()
                LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                raise Exception(error_msg)

            # Attempt 2 with cookies
            LogManager.log_message(
                f"[download_with_retry] First DLP Attempt Failed: {first_error_reason} [RESOLVED]",
                log_file_name,
            )
            LogManager.log_message(
                f"[download_with_retry] Attempt 2: Retrying with cookies file: {cls.dlp_cookies_file}",
                log_file_name,
            )
            ydl_opts_with_cookies = dict(ydl_opts)
            ydl_opts_with_cookies["cookiefile"] = cls.dlp_cookies_file
            ydl_opts_with_cookies["logger"] = cls._reset_logger(
                log_file_name,
                log_warnings_and_above_only=log_warnings_and_above_only,
            )

            try:
                await cls.download(
                    ydl_opts_with_cookies,
                    url_or_list,
                    timeout_enabled,
                    log_file_name,
                    log_warnings_and_above_only,
                )
                LogManager.log_message(
                    f"[download_with_retry] SUCCESS: Downloaded with cookies after {error_type}",
                    log_file_name,
                )
                return
            except Exception as retry_error:
                # Check if retry logger also detected signin
                retry_logger = ydl_opts_with_cookies.get("logger")
                if retry_logger and cls._is_signin_or_age_error(retry_logger):
                    error_msg = (
                        f"{error_type.replace('_', ' ').title()}: Even with cookies, YouTube is still requiring authentication. "
                        f"Please update your cookies and try again."
                    )
                    if attempt1_buffer != None:
                        attempt1_buffer.flush()
                    LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                    raise Exception(error_msg)
                error_msg = f"{error_type.replace('_', ' ').title()}: Failed even with cookies: {retry_error}"
                if use_buffering and attempt1_buffer != None:
                    attempt1_buffer.flush()
                LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                raise Exception(error_msg)

        # Fallback: check if exception message contains signin keywords
        exc_str = str(first_attempt_error).lower()
        if "confirm you're not a bot" in exc_str or "signin required" in exc_str:

            if not cls.dlp_cookies_present:
                error_msg = 'Signin Required: No cookies file available to authenticate. Please export YouTube cookies using yt-dlp.'
                if use_buffering and attempt1_buffer != None:
                    attempt1_buffer.flush()
                LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                raise Exception(error_msg)

            # Attempt 2 (fallback) with cookies
            LogManager.log_message(
                f"[download_with_retry] First DLP Attempt Failed: {first_error_reason} [RESOLVED]",
                log_file_name,
            )
            LogManager.log_message(
                f"[download_with_retry] Attempt 2 (fallback): Retrying with cookies file: {cls.dlp_cookies_file}",
                log_file_name,
            )
            ydl_opts_with_cookies = dict(ydl_opts)
            ydl_opts_with_cookies["cookiefile"] = cls.dlp_cookies_file
            ydl_opts_with_cookies["logger"] = cls._reset_logger(
                log_file_name,
                log_warnings_and_above_only=log_warnings_and_above_only,
            )

            try:
                await cls.download(
                    ydl_opts_with_cookies,
                    url_or_list,
                    timeout_enabled,
                    log_file_name,
                    log_warnings_and_above_only,
                )
                LogManager.log_message(
                    "[download_with_retry] SUCCESS: Downloaded with cookies after bot confirmation",
                    log_file_name,
                )
                return
            except Exception as retry_error:
                error_msg = f"Signin Required: Failed even with cookies: {retry_error}"
                if use_buffering and attempt1_buffer != None:
                    attempt1_buffer.flush()
                LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                raise Exception(error_msg)

        # Check for "No video formats found" which often indicates signin requirement
        if "no video formats found" in exc_str:
            if not cls.dlp_cookies_present:
                if use_buffering and attempt1_buffer != None:
                    attempt1_buffer.flush()
                LogManager.log_message(
                    "[download_with_retry] No formats and no cookies available - cannot retry",
                    log_file_name,
                )
            else:
                # Attempt 2 with cookies
                LogManager.log_message(
                    f"[download_with_retry] First DLP Attempt Failed: {first_error_reason} [RESOLVED]",
                    log_file_name,
                )
                LogManager.log_message(
                    "[download_with_retry] Attempting retry with cookies to handle potential hidden signin requirement",
                    log_file_name,
                )
                ydl_opts_with_cookies = dict(ydl_opts)
                ydl_opts_with_cookies["cookiefile"] = cls.dlp_cookies_file
                ydl_opts_with_cookies["logger"] = cls._reset_logger(
                    log_file_name,
                    log_warnings_and_above_only=log_warnings_and_above_only,
                )

                try:
                    await cls.download(
                        ydl_opts_with_cookies,
                        url_or_list,
                        timeout_enabled,
                        log_file_name,
                        log_warnings_and_above_only,
                    )
                    LogManager.log_message(
                        "[download_with_retry] SUCCESS: Downloaded with cookies after 'no formats' error",
                        log_file_name,
                    )
                    return
                except Exception as retry_error:
                    retry_error_str = str(retry_error).lower()
                    if "no video formats found" in retry_error_str:
                        error_msg = (
                            f"No Video Formats: Video formats still unavailable even with cookies. "
                            f"The video may be age-restricted, geo-blocked, or have DRM protection. "
                            f"Original error: {retry_error}"
                        )
                    else:
                        error_msg = f"Failed with cookies: {retry_error}"
                    if use_buffering and attempt1_buffer:
                        attempt1_buffer.flush()
                    LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                    raise Exception(error_msg)

        # Handle timeout/stall errors - these should fail immediately
        if timeout_enabled and isinstance(first_attempt_error, (TimeoutError, asyncio.TimeoutError)):
            error_str = str(first_attempt_error).lower()
            if "stall" in error_str or "timeout" in error_str:
                if use_buffering and attempt1_buffer != None:
                    attempt1_buffer.flush()
                error_msg = (
                    f"Download Timeout/Stall: {first_attempt_error}. "
                    f"This typically indicates a network issue or the video server is unresponsive. "
                    f"Retries will not help as the issue is likely server-side."
                )
                LogManager.log_message(f"[download_with_retry] ERROR: {error_msg}", log_file_name)
                raise Exception(error_msg)

        # Handle TLS/SSL errors with retries
        if DLPEvents.is_tls_ssl_error(first_attempt_error):
            retry_delay = 2

            max_retries = 3
            for attempt in range(1, max_retries + 1):
                LogManager.log_message(
                    f"[download_with_retry] TLS/SSL error, retrying in {retry_delay}s (attempt {attempt}/{max_retries}): {first_attempt_error}",
                    log_file_name,
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2

                dlp_logger = cls._reset_logger(
                    log_file_name,
                    log_warnings_and_above_only=log_warnings_and_above_only,
                )
                retry_ydl_opts = dict(ydl_opts)
                retry_ydl_opts["logger"] = dlp_logger

                try:
                    await cls.download(
                        retry_ydl_opts,
                        url_or_list,
                        timeout_enabled,
                        log_file_name,
                        log_warnings_and_above_only,
                    )
                    LogManager.log_message(
                        "[download_with_retry] SUCCESS: Downloaded after TLS/SSL retry",
                        log_file_name,
                    )
                    return
                except Exception as retry_error:
                    if DLPEvents.is_tls_ssl_error(retry_error) and attempt < max_retries:
                        continue
                    raise retry_error

        # If we get here, re-raise the first error
        if use_buffering and attempt1_buffer != None:
            attempt1_buffer.flush()
        LogManager.log_message(
            f"[download_with_retry] FAILED: No recovery possible for error: {first_attempt_error}",
            log_file_name,
        )
        raise first_attempt_error

    @classmethod
    async def getinfo_with_retry(
        cls,
        ydl_opts,
        url_or_list,
        log_file_name=None,
        log_warnings_and_above_only=False,
        desired_dicts=None,
    ):
        """Retrieve info using YoutubeDL.extract_info without downloading.
        
        Automatically attempts retry with cookies if signin/age errors are detected.
        Automatically attempts retry with QuickJS if Deno JS challenge timeout is detected.
        Buffers attempt 1 logs and outputs conditionally based on success/failure (if enabled in config).
        
        Args:
            ydl_opts: YoutubeDL options dictionary
            url_or_list: URL or list of URLs to extract info from
            log_file_name: Optional log file name
            desired_dicts: Optional set/list of dictionary keys that indicate successful info retrieval.
                          If info is not None and contains all these keys, returns immediately
                          without checking for signin/age errors.
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts = cls._apply_js_runtime(ydl_opts, log_file_name)
        
        # Add JS runtime options to avoid Deno JS challenge timeouts
        ydl_opts["compat_opts"] = ["no-deno"]
        if "extractor_args" not in ydl_opts:
            ydl_opts["extractor_args"] = {}
        if "youtube" not in ydl_opts["extractor_args"]:
            ydl_opts["extractor_args"]["youtube"] = {}
        ydl_opts["extractor_args"]["youtube"]["player_skip"] = ["js"]
        
        # Check if buffered logging is enabled
        use_buffering = DVR_Config.get_dlp_buffer_first_attempt_errors()
        if use_buffering:
            attempt1_buffer, original_log_message, buffered_log = cls._setup_attempt1_buffer()
        else:
            attempt1_buffer = None
            original_log_message = LogManager.log_message
            buffered_log = LogManager.log_message  # Use direct logging when buffering disabled
        
        dlp_logger = cls._reset_logger(
            log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )
        ydl_opts["logger"] = dlp_logger
        
        first_error_reason = None
        deno_js_timeout_detected = False
        
        # First attempt without cookies (with optional buffering)
        if use_buffering:
            LogManager.log_message = buffered_log
        try:
            buffered_log(
                "[getinfo_with_retry] Attempt 1: Calling [getinfo] without cookies",
                log_file_name,
            )
            result = await cls.getinfo(
                ydl_opts,
                url_or_list,
                log_file_name,
                log_warnings_and_above_only,
            )
            
            # If desired_dicts is specified and result contains all desired keys, return immediately
            if result is not None and desired_dicts and isinstance(result, dict):
                has_all_desired = all(key in result for key in desired_dicts)
                if has_all_desired:
                    buffered_log(
                        "[getinfo_with_retry] Result contains all desired keys, returning immediately without signin check",
                        log_file_name,
                    )
                    if use_buffering:
                        LogManager.log_message = original_log_message
                    if use_buffering and attempt1_buffer != None:
                        attempt1_buffer.flush()
                    return result
            
            # Check if the result indicates we need signin/age verification
            if isinstance(result, dict) and result.get("_needs_signin"):
                first_error_reason = result.get("_error_type", "unknown")
                buffered_log(
                    f"[getinfo_with_retry] Signin/age confirmation required ({first_error_reason}) detected",
                    log_file_name,
                )
            else:
                buffered_log(
                    "[getinfo_with_retry] SUCCESS: Retrieved info without cookies needed",
                    log_file_name,
                )
                if use_buffering:
                    LogManager.log_message = original_log_message
                if attempt1_buffer != None:
                    attempt1_buffer.flush()
                return result
                
        except Exception as e:
            first_error_reason = f"{type(e).__name__}: {str(e)[:100]}"
            buffered_log(
                f"[getinfo_with_retry] Exception on first attempt: {first_error_reason}",
                log_file_name,
            )
            # Check if this is a Deno JS timeout error
            if isinstance(e, TimeoutError) and cls._is_deno_js_timeout_logger(dlp_logger):
                deno_js_timeout_detected = True
                buffered_log(
                    "[getinfo_with_retry] Deno JS challenge timeout detected - will retry with QuickJS",
                    log_file_name,
                )
        finally:
            if use_buffering:
                LogManager.log_message = original_log_message

        # If Deno JS timeout was detected, retry with QuickJS runtime
        if deno_js_timeout_detected:
            LogManager.log_message(
                f"First DLP Attempt Failed: {first_error_reason} [DENO_JS_TIMEOUT] [RESOLVED]",
                log_file_name,
            )
            LogManager.log_message(
                f"Attempt 2: Retrying with QuickJS runtime instead of Deno",
                log_file_name,
            )
            
            # Prepare options with QuickJS
            ydl_opts_quickjs = dict(ydl_opts)
            ydl_opts_quickjs["js_runtimes"] = ["quickjs"]
            ydl_opts_quickjs["compat_opts"] = ["no-deno"]
            ydl_opts_quickjs["logger"] = cls._reset_logger(
                log_file_name,
                log_warnings_and_above_only=log_warnings_and_above_only,
            )
            
            try:
                result = await cls.getinfo(
                    ydl_opts_quickjs,
                    url_or_list,
                    log_file_name,
                    log_warnings_and_above_only,
                )
                LogManager.log_message(
                    f"[getinfo_with_retry] SUCCESS: Retrieved info with QuickJS after {first_error_reason}",
                    log_file_name,
                )
                return result
            except Exception as quickjs_error:
                LogManager.log_message(
                    f"[getinfo_with_retry] QuickJS retry also failed: {quickjs_error}",
                    log_file_name,
                )
                raise

        # Attempt 1 failed with non-Deno error, retry with cookies
        retry_result = await cls._retry_with_cookies(
            ydl_opts,
            cls.getinfo,
            {
                "url_or_list": url_or_list,
                "log_file_name": log_file_name,
                "log_warnings_and_above_only": log_warnings_and_above_only,
            },
            first_error_reason,
            log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )
        
        # Check if retry was successful
        if isinstance(retry_result, dict) and retry_result.get("_needs_signin"):
            error_type = retry_result.get("_error_type", "unknown")
            error_msg = (
                f"{error_type.replace('_', ' ').title()}: Even with cookies, YouTube is still requiring authentication. "
                f"Please update your cookies and try again."
            )
            LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
            raise Exception(error_msg)
        
        LogManager.log_message(
            f"[getinfo_with_retry] SUCCESS: Retrieved info with cookies after {first_error_reason}",
            log_file_name,
        )
        return retry_result

    @classmethod
    async def getentries_with_retry(
        cls,
        ydl_opts,
        videos_url=None,
        shorts_url=None,
        log_file_name=None,
        log_warnings_and_above_only=False,
    ):
        """Fetch entries for provided section URLs (videos/shorts).
        
        Automatically attempts retry with cookies if signin/age errors are detected.
        Buffers attempt 1 logs and outputs conditionally based on success/failure (if enabled in config).
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts = cls._apply_js_runtime(ydl_opts, log_file_name)
        
        # Check if buffered logging is enabled
        use_buffering = DVR_Config.get_dlp_buffer_first_attempt_errors()
        if use_buffering:
            attempt1_buffer, original_log_message, buffered_log = cls._setup_attempt1_buffer()
        else:
            attempt1_buffer = None
            original_log_message = LogManager.log_message
            buffered_log = LogManager.log_message  # Use direct logging when buffering disabled
        
        dlp_logger = cls._reset_logger(
            log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )
        ydl_opts["logger"] = dlp_logger
        
        first_error_reason = None
        
        # First attempt without cookies (with optional buffering)
        if use_buffering:
            LogManager.log_message = buffered_log
        try:
            buffered_log(
                "[getentries_with_retry] Attempt 1: Calling [getentries] without cookies",
                log_file_name,
            )
            result = await cls.getentries(
                ydl_opts,
                videos_url,
                shorts_url,
                log_file_name,
                log_warnings_and_above_only,
            )
            
            # Check if result indicates we need signin/age verification
            if isinstance(result, dict) and result.get("_needs_signin"):
                first_error_reason = result.get("_error_type", "unknown")
                buffered_log(
                    f"[getentries_with_retry] Signin/age confirmation required ({first_error_reason}) detected",
                    log_file_name,
                )
            else:
                buffered_log(
                    "[getentries_with_retry] SUCCESS: Retrieved entries without cookies needed",
                    log_file_name,
                )
                if use_buffering:
                    LogManager.log_message = original_log_message
                if attempt1_buffer != None:
                    attempt1_buffer.flush()
                return result
                
        except Exception as e:
            first_error_reason = f"{type(e).__name__}: {str(e)[:100]}"
            buffered_log(
                f"[getentries_with_retry] Exception on first attempt: {first_error_reason}",
                log_file_name,
            )
        finally:
            if use_buffering:
                LogManager.log_message = original_log_message

        # Attempt 1 failed, retry with cookies
        retry_result = await cls._retry_with_cookies(
            ydl_opts,
            cls.getentries,
            {
                "videos_url": videos_url,
                "shorts_url": shorts_url,
                "log_file_name": log_file_name,
                "log_warnings_and_above_only": log_warnings_and_above_only,
            },
            first_error_reason,
            log_file_name,
            log_warnings_and_above_only=log_warnings_and_above_only,
        )
        
        # Check if retry was successful
        if isinstance(retry_result, dict) and retry_result.get("_needs_signin"):
            error_type = retry_result.get("_error_type", "unknown")
            error_msg = (
                f"{error_type.replace('_', ' ').title()}: Even with cookies, YouTube is still requiring authentication. "
                f"Please update your cookies and try again."
            )
            LogManager.log_message(f"ERROR: {error_msg}", log_file_name)
            raise Exception(error_msg)
        
        LogManager.log_message(
            f"[getentries_with_retry] SUCCESS: Retrieved entries with cookies after {first_error_reason}",
            log_file_name,
        )
        return retry_result

