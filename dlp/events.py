import traceback
import logging
import time
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config

# Configure logger for this module
logger = logging.getLogger(__name__)


class DLPEvents:
    """
    Event handler class for yt-dlp progress hooks.
    Instantiate with an optional `log_file_name` and two optional
    callbacks: `download_started(filename)` and `download_complete(filename)`.
    """

    def __init__(
        self,
        stream_url=None,
        log_file_name=None,
        download_started=None,
        download_complete=None,
        download_processing=None,
    ):
        self.stream_url = stream_url
        self.log_file_name = log_file_name
        self.download_started = (
            download_started if download_started is not None else (lambda: None)
        )
        self.download_complete = (
            download_complete if download_complete is not None else (lambda: None)
        )
        self.download_processing = (
            download_processing if download_processing is not None else (lambda: None)
        )
        # Get stall timeout from config
        self.stall_timeout = DVR_Config.get_dlp_stall_timeout()
        # Track active downloads and last-logged elapsed/bytes per stream and per-file
        self._active_downloads = set()  # filenames seen (legacy per-file tracking)
        # Map stream_key -> set(filenames)
        self._streams_files = {}
        # Per-file current values
        self._per_file_downloaded = {}
        self._per_file_total = {}
        self._per_file_speed = {}
        self._per_file_eta = {}
        # Per-file stall detection: track last update time and bytes
        self._per_file_last_update_time = {}
        self._per_file_last_update_bytes = {}
        # Global last update tracking for stall detection
        self._last_progress_update = None
        self._last_progress_bytes = 0
        # Per-stream last logged elapsed/bytes for throttling
        self._streams_last_logged_elapsed = {}
        self._streams_last_logged_bytes = {}

    def on_progress(self, d):
        """Event handler for yt-dlp progress hooks. Logs progress and calls callbacks."""
        try:
            current_status = d.get("status")
            filename = d.get("filename", "Unknown")

            # Diagnostic: log incoming event envelope for debugging why callbacks may not fire
            try:
                info_preview = d.get("info_dict") or {}
                preview_keys = list(info_preview.keys())
            except Exception:
                preview_keys = []

            # Derive stream key exclusively from instance stream_url (no fallback)
            stream_key = f"url:{self.stream_url}"

            # Ensure stream record exists
            files = self._streams_files.setdefault(stream_key, set())
            was_file_present = filename in files
            files.add(filename)
            # Update per-file values
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or None
            self._per_file_downloaded[filename] = downloaded
            if total is not None:
                self._per_file_total[filename] = total

            # Update global progress tracking for external stall detection
            current_time = time.time()
            self._last_progress_update = current_time
            self._last_progress_bytes = max(self._last_progress_bytes, downloaded)

            # Track per-file progress for reference
            if filename not in self._per_file_last_update_time:
                self._per_file_last_update_time[filename] = current_time
                self._per_file_last_update_bytes[filename] = downloaded
            else:
                # Update timestamps if progress was made
                if downloaded > self._per_file_last_update_bytes.get(filename, 0):
                    self._per_file_last_update_time[filename] = current_time
                    self._per_file_last_update_bytes[filename] = downloaded

            # If first time we see this stream, call started callback for the stream once
            if stream_key not in self._streams_last_logged_elapsed:
                # self.log_message(f"Initializing stream-level tracking for stream_key={stream_key}, files={list(files)}")
                try:
                    # Only call stream-level started if that file wasn't already considered started
                    first_file = next(iter(files))
                    if first_file not in self._active_downloads:
                        try:
                            self.download_started()
                            # Mark current files in this stream as started so we don't
                            # attempt per-file callbacks elsewhere (legacy behavior).
                            self._active_downloads.update(files)
                            # self.log_message(f"Stream-level download_started callback invoked for {first_file}")
                        except Exception as cb_exc2:
                            self.log_message(
                                f"Exception in stream-level download_started callback for {first_file}: {cb_exc2}\n{traceback.format_exc()}"
                            )
                            # Still mark one file as active to avoid repeated attempts if callback misbehaves
                            self._active_downloads.add(first_file)
                except Exception:
                    self.log_message(
                        "Exception while attempting to call stream-level download_started",
                    )
                self._streams_last_logged_elapsed[stream_key] = None
                self._streams_last_logged_bytes[stream_key] = 0

            # Update per-file speed/eta if provided in this event
            file_speed = d.get("speed")
            if file_speed is not None:
                self._per_file_speed[filename] = file_speed
            file_eta = d.get("eta")
            if file_eta is not None:
                self._per_file_eta[filename] = file_eta

            # Compute aggregated values across the stream
            total_downloaded = sum(self._per_file_downloaded.get(f, 0) for f in files)
            per_file_totals = [
                self._per_file_total.get(f)
                for f in files
                if self._per_file_total.get(f) is not None
            ]
            total_estimated = sum(per_file_totals) if per_file_totals else None
            # Prefer yt-dlp provided `elapsed` (use current event's elapsed for the stream)
            elapsed = d.get("elapsed")
            should_log = False
            prev_elapsed = self._streams_last_logged_elapsed.get(stream_key)
            prev_bytes = self._streams_last_logged_bytes.get(stream_key, 0)
            if elapsed is None:
                # Fallback to bytes-based logging when elapsed is not provided
                if total_downloaded - prev_bytes >= 10 * 1024 * 1024:
                    should_log = True

            elif (
                prev_elapsed is None
                and elapsed >= 60
                or prev_elapsed is not None
                and (elapsed - prev_elapsed) >= 60
            ):
                should_log = True
            elif prev_elapsed is None:
                # Start counting from the current elapsed so future
                # checks compare against this baseline.
                self._streams_last_logged_elapsed[stream_key] = elapsed
            if should_log:
                # Compute aggregated stream speed: prefer sum of per-file speeds, else estimate from deltas
                per_file_speeds = [v for v in self._per_file_speed.values() if v]
                stream_speed = sum(per_file_speeds) if per_file_speeds else None
                if (
                    stream_speed is None
                    and elapsed is not None
                    and prev_elapsed is not None
                    and (elapsed - prev_elapsed) > 0
                ):
                    stream_speed = (total_downloaded - prev_bytes) / (
                        elapsed - prev_elapsed
                    )

                # Update stored last-logged markers after computing speeds/eta
                if elapsed is not None:
                    self._streams_last_logged_elapsed[stream_key] = elapsed
                self._streams_last_logged_bytes[stream_key] = total_downloaded

                # Try to fill missing per-file total from yt-dlp's info_dict (provided in the event)
                if total_estimated is None:
                    info = d.get("info_dict") or {}
                    if filesize := info.get("filesize") or info.get("filesize_approx"):
                        # update this file's total and recompute total_estimated
                        try:
                            self._per_file_total[filename] = int(filesize)
                        except Exception:
                            # keep original value if it isn't an int
                            self._per_file_total[filename] = filesize
                        if per_file_totals := [
                            self._per_file_total.get(f)
                            for f in files
                            if self._per_file_total.get(f) is not None
                        ]:
                            total_estimated = sum(per_file_totals)

                elapsed_str = (
                    self.format_time(elapsed) if elapsed is not None else "Unknown"
                )
                downloaded_str = self.format_bytes(total_downloaded)
                speed_str = (
                    self.format_bytes_per_sec(stream_speed)
                    if stream_speed
                    else "Unknown"
                )

                self.log_message(
                    f"Download Duration: {elapsed_str} Total Download Size: {downloaded_str} At Rate: {speed_str}"
                )

            elif current_status == "processing":
                try:
                    self.download_processing()
                    self.log_message(
                        f"download_processing callback invoked for {filename}"
                    )
                except Exception as cb_proc_exc:
                    self.log_message(
                        f"Exception in download_processing callback for {filename}: {cb_proc_exc}\n{traceback.format_exc()}"
                    )
                self.log_message(f"Download processing: {filename}")

            elif current_status == "finished":
                self.log_message(
                    f"Status 'finished' observed for filename={filename}, invoking download_complete callback"
                )
                # finished -> call complete callback for the file and cleanup per-file tracking
                try:
                    self.download_complete()
                    self.log_message(
                        f"download_complete callback invoked for {filename}"
                    )
                except Exception as cb_exc3:
                    self.log_message(
                        f"Exception in download_complete callback for {filename}: {cb_exc3}\n{traceback.format_exc()}"
                    )
                self._active_downloads.discard(filename)
                # Cleanup per-file entries
                self._per_file_downloaded.pop(filename, None)
                self._per_file_total.pop(filename, None)

                # Remove file from its stream and if stream empty, cleanup stream tracking
                # Determine stream_key again (best-effort: match filename in streams)
                stream_to_clean = None
                for sk, fls in list(self._streams_files.items()):
                    if filename in fls:
                        fls.discard(filename)
                        if not fls:
                            stream_to_clean = sk
                        break
                if stream_to_clean:
                    self._streams_files.pop(stream_to_clean, None)
                    self._streams_last_logged_elapsed.pop(stream_to_clean, None)
                    self._streams_last_logged_bytes.pop(stream_to_clean, None)

                self.log_message(f"Download finished: {filename}")

            elif current_status == "error":
                self.log_message(
                    f"Download error occurred for filename={filename}: {d.get('_exception', 'Unknown error')}"
                )

        except Exception as e:
            # Include more context in the error log to help diagnose missing callbacks
            try:
                fname = (
                    d.get("filename", "Unknown") if isinstance(d, dict) else "Unknown"
                )
                keys = list(d.keys()) if isinstance(d, dict) else []
            except Exception:
                fname = "Unknown"
                keys = []
            self.log_message(
                f"Error in dlp_events handler for filename={fname} event_keys={keys}: {e}\n{traceback.format_exc()}"
            )

    @classmethod
    def format_bytes_per_sec(cls, bytes_per_sec):
        """Convert bytes per second to human-readable format."""
        return f"{cls.format_bytes(bytes_per_sec)}/s"

    @classmethod
    def format_bytes(cls, bytes_value):
        """Convert bytes to human-readable format."""
        if bytes_value is None:
            return "0 B"
        try:
            bytes_value = float(bytes_value)
        except Exception:
            return "Unknown"
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} TB"

    @staticmethod
    def format_time(seconds):
        """Convert seconds to human-readable time format."""
        if seconds is None or seconds < 0:
            return "Unknown"
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        parts = []
        if hours > 0:
            parts.append(f"{hours} h")
        if minutes > 0:
            parts.append(f"{minutes} m")
        if secs > 0:
            parts.append(f"{secs} s")
        return " ".join(parts) or "0s"

    def log_message(self, message):
        """
        Forward a log message to LogManager. If `log_file_name` is provided,
        pass it as the second positional argument, otherwise pass None.
        """
        try:
            LogManager.log_message(message, self.log_file_name)
        except Exception as e:
            logger.error(f"Failed to forward log message: {e}")

    def check_for_stall(self):
        """Check if download has stalled (no progress for stall_timeout seconds).
        
        Returns:
            (bool, str) - (is_stalled, stall_message)
        """
        if self._last_progress_update is None:
            return False, ""
        
        current_time = time.time()
        time_since_update = current_time - self._last_progress_update
        
        if time_since_update > self.stall_timeout:
            stall_msg = (
                f"Download stall detected: No progress for {int(time_since_update)}s "
                f"(timeout: {self.stall_timeout}s). Total bytes: {self.format_bytes(self._last_progress_bytes)}."
            )
            return True, stall_msg
        
        return False, ""

    RATE_LIMIT_STRINGS = [
        "429",
        "rate limit",
        "quota",
        "automated queries",
        "confirm you’re not a bot",
        "too many requests",
        "content isn't available",
    ]

    NO_LOG_EVENT_STRINGS = [
        "this live event will begin in a few moments",
        "the channel is not currently live",
    ]

    SIGNIN_REQUIRED_STRINGS = [
        "sign in to confirm your age",
        "this video may be inappropriate for some users",
    ]

    AGE_CONFIRMATION_STRINGS = [
        "sign in to confirm your age",
        "this video may be inappropriate for some users",
    ]

    DENO_JS_TIMEOUT_STRINGS = [
        "solving js challenges using deno",
        "jsc:deno",
    ]

    TLS_SSL_ERROR_STRINGS = [
        "tls",
        "ssl",
        "certificate",
        "handshake",
        "wrong_version",
        "connection reset",
        "connection refused",
        "curl: (35)",
        "curl: (52)",
        "tmp_download_archive",
    ]

    @classmethod
    def is_tls_ssl_error(cls, err: Exception) -> bool:
        """Detect TLS/SSL connection errors that are transient and retryable."""
        msg = str(err).lower()
        return any(s in msg for s in cls.TLS_SSL_ERROR_STRINGS)

    @classmethod
    def is_rate_limit_error(cls, err: Exception) -> bool:
        msg = str(err).lower()
        return any(s in msg for s in cls.RATE_LIMIT_STRINGS)

    @classmethod
    def is_signin_required_error(cls, err: Exception) -> bool:
        msg = str(err).lower()
        return any(s in msg for s in cls.SIGNIN_REQUIRED_STRINGS)

    @classmethod
    def is_age_confirmation_error(cls, err: Exception) -> bool:
        msg = str(err).lower()
        return any(s in msg for s in cls.AGE_CONFIRMATION_STRINGS)

    @classmethod
    def is_deno_js_timeout_error(cls, err: Exception) -> bool:
        """Detect if error occurred during Deno JS challenge solving (which can timeout)."""
        msg = str(err).lower()
        return any(s in msg for s in cls.DENO_JS_TIMEOUT_STRINGS)