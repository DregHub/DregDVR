import re
import traceback
import asyncio
import contextlib
from yt_dlp import YoutubeDL
from utils.logging_utils import LogManager
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config

class DLP_Logger:
    """Minimal yt-dlp logger that detects a specific single-line message.

    It sets `detected` True when a log line contains both the configured
    `message_source` and `message` substrings on the same line. When a match
    is found, the `match_found(result)` method is invoked with the configured
    `result` value.
    """

    def __init__(
        self,
        message_source: str = "",
        message: str = "",
        result=None,
        patterns: list = None,
    ):
        # Normalize patterns into a list of dicts: {message_source, message, result}
        self._patterns = []
        if patterns:
            for p in patterns:
                try:
                    if isinstance(p, dict):
                        src = p.get("message_source", "")
                        msg = p.get("message", "")
                        res = p.get("result", None)
                    else:
                        # treat as tuple/list
                        src = p[0] if len(p) > 0 else ""
                        msg = p[1] if len(p) > 1 else ""
                        res = p[2] if len(p) > 2 else None
                    self._patterns.append(
                        {
                            "message_source": str(src or ""),
                            "message": str(msg or ""),
                            "result": res,
                        }
                    )
                except Exception:
                    continue
        else:
            self._patterns.append(
                {
                    "message_source": str(message_source or ""),
                    "message": str(message or ""),
                    "result": result,
                }
            )

        self.detected = False
        self.last_match_result = None

    def inputs(self):
        """Return the configured detection patterns as a list of dicts."""
        return list(self._patterns)

    def _check(self, msg):
        try:
            s = str(msg or "")
        except Exception:
            s = ""
        for pat in self._patterns:
            try:
                if pat["message_source"] in s and pat["message"] in s:
                    self.detected = True
                    with contextlib.suppress(Exception):
                        self.match_found(pat.get("result"))
                    break
            except Exception:
                continue

    def match_found(self, result):
        """Called when a configured match is detected. Stores last result and logs."""
        with contextlib.suppress(Exception):
            self.last_match_result = result
            LogManager.log_message(f"YTDLP detect logger match found: {result}")

    def debug(self, msg):
        return None

    def info(self, msg):
        self._check(msg)

    def warning(self, msg):
        self._check(msg)

    def error(self, msg):
        self._check(msg)


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
        # Track active downloads and last-logged elapsed/bytes per stream and per-file
        self._active_downloads = set()  # filenames seen (legacy per-file tracking)
        # Map stream_key -> set(filenames)
        self._streams_files = {}
        # Per-file current values
        self._per_file_downloaded = {}
        self._per_file_total = {}
        self._per_file_speed = {}
        self._per_file_eta = {}
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
                    f"Download Duration {elapsed_str} Download Size {downloaded_str} At Rate {speed_str}"
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
            print(f"Failed to forward log message: {e}")

    RATE_LIMIT_STRINGS = [
        "429",
        "rate limit",
        "quota",
        "automated queries",
        "confirm you’re not a bot",
        "too many requests",
    ]

    @classmethod
    def is_rate_limit_error(cls, err: Exception) -> bool:
        msg = str(err).lower()
        return any(s in msg for s in cls.RATE_LIMIT_STRINGS)


DLP_Logger_Patterns = [
    {
        "message_source": "[youtube:tab]",
        "message": "not currently live",
        "result": "is_upcoming",
    },
    {
        "message_source": "[youtube]",
        "message": " This live event will begin in a few moments",
        "result": "is_upcoming",
    },
]


async def download_with_retry(ydl_opts, url_or_list, log_file_name=None):
    """Download using YoutubeDL; retry once without cookiefile on rate-limit.

    Raises the final exception if retry also fails with rate-limit or other errors.
    """
    try:
        #add on the cookie to our dlp options for the first try
        YT_Cookies_File = DVR_Config.get_yt_cookies_file()
        if YT_Cookies_File and os.path.exists(YT_Cookies_File):
                ydl_opts["cookiefile"] = YT_Cookies_File
        LogManager.log_message(
            f"Starting youtube downloader helper with options {ydl_opts}",
            log_file_name,
        )
        with YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, url_or_list)
        LogManager.log_message("finished youtube downloader helper", log_file_name)
    except Exception as e:
        LogManager.log_message(
            f"Exception in download helper {e}",
            log_file_name,
        )
        if DLPEvents.is_rate_limit_error(e):
            LogManager.log_message(
                f"Rate limit detected during download using cookiefile, retrying without cookiefile: {e}",
                log_file_name,
            )
            retry_opts = dict(ydl_opts)
            retry_opts.pop("cookiefile", None)
            try:
                with YoutubeDL(retry_opts) as ydl_retry:
                    await asyncio.to_thread(ydl_retry.download, url_or_list)
            except Exception as e2:
                if DLPEvents.is_rate_limit_error(e2):
                    LogManager.log_message(
                        f"Rate limit persists after retry without cookiefile for download: {e2}",
                        log_file_name,
                    )
                else:
                    LogManager.log_message(
                        f"Download failed on retry without cookiefile for non-rate-limit reason: {e2}",
                        log_file_name,
                    )
        else:
            LogManager.log_message(
                f"Download failed for non-rate-limit reason: {e}",
                log_file_name,
            )


async def getinfo_with_retry(ydl_opts, url_or_list, log_file_name=None):
    """Retrieve info using YoutubeDL.extract_info without downloading.

    Mirrors the retry behavior of `download_with_retry`: if a rate-limit
    error occurs and the original options contained a `cookiefile`, retry
    once without the cookiefile. Returns the extracted info on success or
    `None` on failure (errors are logged to `LogManager`).
    """
    #add on the cookie to our dlp options for the first try
    YT_Cookies_File = DVR_Config.get_yt_cookies_file()
    if YT_Cookies_File and os.path.exists(YT_Cookies_File):
        ydl_opts["cookiefile"] = YT_Cookies_File
    DLPLogger = DLP_Logger(patterns=DLP_Logger_Patterns)
    try:
        # Attach our detection logger to a shallow copy of the options so we don't mutate caller's dict
        opts = dict(ydl_opts) if ydl_opts is not None else {}

        opts["logger"] = DLPLogger
        with YoutubeDL(opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url_or_list, False)
            if DLPLogger.detected and DLPLogger.last_match_result == "is_upcoming":
                # Common stream is not live exception return it as an upcoming stream
                return {"live_status": "is_upcoming"}
            else:
                return info
    except Exception as e:
        # If our logger observed the "not currently live" message during the failed attempt,
        # return the synthetic info immediately rather than retrying.
        with contextlib.suppress(Exception):
            if DLPLogger.detected and DLPLogger.last_match_result == "is_upcoming":
                # Common stream is not live exception return it as an upcoming stream
                return {"live_status": "is_upcoming"}
        if DLPEvents.is_rate_limit_error(e) and orig_had_cookie:
            LogManager.log_message(
                f"Rate limit detected during extract_info using cookiefile, retrying without cookiefile: {e}",
                log_file_name,
            )
            retry_opts = dict(ydl_opts)
            retry_opts.pop("cookiefile", None)
            retry_opts["logger"] = DLPLogger
            try:
                with YoutubeDL(retry_opts) as ydl_retry:
                    info = await asyncio.to_thread(
                        ydl_retry.extract_info, url_or_list, False
                    )
                    return info
            except Exception as e2:
                if DLPEvents.is_rate_limit_error(e2):
                    LogManager.log_message(
                        f"Rate limit persists after retry without cookiefile for getinfo: {e2}",
                        log_file_name,
                    )
                else:
                    LogManager.log_message(
                        f"getinfo failed on retry without cookiefile for non-rate-limit reason: {e2}",
                        log_file_name,
                    )
        else:
            LogManager.log_message(
                f"getinfo failed for non-rate-limit reason: {e} {DLPLogger.last_match_result}",
                log_file_name,
            )
    return None
