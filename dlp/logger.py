import os
import contextlib
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from dlp.events import DLPEvents


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
        log_file_name: str = None,
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
        self.dlp_verbose = DVR_Config.get_verbose_dlp_mode()
        self.dlp_keep_fragments = DVR_Config.get_keep_fragments_dlp_downloads()
        self.dlp_no_progress = DVR_Config.no_progress_dlp_downloads()
        self.detected = False
        self.last_match_result = None
        # optional file name to forward logs to LogManager
        self.log_file_name = log_file_name

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
        # forward debug messages to centralized LogManager when available
        with contextlib.suppress(Exception):
            if self.dlp_verbose == True:
                LogManager.log_message(str(f"DLP Debug: {msg}"), self.log_file_name)
            else:
                return None
        return None

    def info(self, msg):
        # forward debug messages to centralized LogManager when available
        with contextlib.suppress(Exception):
            if self.dlp_verbose == True:
                LogManager.log_message(str(f"DLP Info: {msg}"), self.log_file_name)
            else:
                return None
        return None

    def warning(self, msg):
        self._check(msg)
        with contextlib.suppress(Exception):
            # We should forward all messages at this level except those containing substrings on the ignore list
            if all(s not in str(msg).lower() for s in DLPEvents.NO_LOG_EVENT_STRINGS):
                LogManager.log_message(str(f"DLP Warning: {msg}"), self.log_file_name)
        return None

    def error(self, msg):
        self._check(msg)
        with contextlib.suppress(Exception):
            # We should forward all messages at this level except those containing substrings on the ignore list
            if all(s not in str(msg).lower() for s in DLPEvents.NO_LOG_EVENT_STRINGS):
                LogManager.log_message(str(f"DLP Error: {msg}"), self.log_file_name)


DLP_Logger_Patterns = [
    {
        "message_source": "[youtube:tab]",
        "message": "not currently live",
        "result": "not_live",
    },
    {
        "message_source": "[youtube]",
        "message": "This live event will begin in a few moments",
        "result": "is_upcoming",
    },
    {
        "message_source": "[youtube]",
        "message": "Sign in to confirm your age",
        "result": "is_age_confirmation_required",
    },
    {
        "message_source": "[youtube]",
        "message": "rate limit",
        "result": "is_rate_limited",
    },
    {
        "message_source": "[youtube]",
        "message": "rate-limited",
        "result": "is_rate_limited",
    },
    {
        "message_source": "[youtube]",
        "message": "isn't available",
        "result": "is_rate_limited",
    },
    {
        "message_source": "[youtube]",
        "message": "not available",
        "result": "is_rate_limited",
    },
    {
        "message_source": "[youtube]",
        "message": "confirm you're not a bot",
        "result": "is_signin_required",
    },
]
