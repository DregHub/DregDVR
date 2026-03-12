import os
import asyncio
import json
from yt_dlp import YoutubeDL
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from dlp.logger import DLP_Logger, DLP_Logger_Patterns
from dlp.events import DLPEvents


class DLPHelpers:
    """Class encapsulating DLP utility methods."""

    dlp_cookies_file = DVR_Config.get_yt_cookies_file()
    dlp_cookies_present = os.path.exists(dlp_cookies_file)
    dlp_verbose = DVR_Config.get_verbose_dlp_mode()
    dlp_no_progress = DVR_Config.no_progress_dlp_downloads()
    dlp_keep_fragments = DVR_Config.get_keep_fragments_dlp_downloads()
    dlp_max_fragment_retries = DVR_Config.get_max_dlp_fragment_retries()

    @classmethod
    async def download(cls, ydl_opts, url_or_list, log_file_name=None):
        """Core download helper that invokes YoutubeDL.download with given options.

        This function performs the single attempt; retry behavior is handled
        by `download_with_retry`.
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts["keep_fragments"] = cls.dlp_keep_fragments
        ydl_opts["fragment_retries"] = cls.dlp_max_fragment_retries
        LogManager.log_message(
            f"Starting youtube downloader helper with options {ydl_opts}",
            log_file_name,
        )
        with YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, url_or_list)
        LogManager.log_message("finished youtube downloader helper", log_file_name)

    @classmethod
    async def getinfo(cls, ydl_opts, url_or_list, log_file_name=None):
        """Core info helper that invokes YoutubeDL.extract_info with a detection logger.

        This function will return a synthetic upcoming status when the
        detection logger identifies the common "not live" message. It handles
        specific errors gracefully without raising exceptions.
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts["keep_fragments"] = cls.dlp_keep_fragments
        ydl_opts["fragment_retries"] = cls.dlp_max_fragment_retries
        if "logger" in ydl_opts:
            DLPLogger = ydl_opts["logger"]
        else:
            DLPLogger = DLP_Logger(patterns=DLP_Logger_Patterns)
            ydl_opts["logger"] = DLPLogger
        info = None
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = await asyncio.to_thread(ydl.extract_info, url_or_list, False)
            except Exception as e:
                if not DLPLogger.detected:
                    LogManager.log_message(
                        f"Exception in getinfo helper {e}",
                        log_file_name,
                    )

            if DLPLogger.detected:
                return {"live_status": DLPLogger.last_match_result}
            elif info is None:
                LogManager.log_message(
                    "Failed to determine current live_status for this video returning none ",
                    log_file_name,
                )
                return None
            else:
                return info

    @classmethod
    async def getentries(
        cls, ydl_opts, videos_url=None, shorts_url=None, log_file_name=None
    ):
        """Fetch entries for provided section URLs (videos/shorts).

        Returns a combined list of entries from the provided section URLs.
        """
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts["keep_fragments"] = cls.dlp_keep_fragments
        ydl_opts["fragment_retries"] = cls.dlp_max_fragment_retries
        collected = []

        if "logger" in ydl_opts:
            dlp_logger = ydl_opts["logger"]
        else:
            dlp_logger = DLP_Logger(
                patterns=DLP_Logger_Patterns, log_file_name=log_file_name
            )

        flat_opts = dict(ydl_opts)
        flat_opts["extract_flat"] = True
        if "logger" not in flat_opts:
            flat_opts["logger"] = dlp_logger
        with YoutubeDL(flat_opts) as flat_ydl:
            for section_url in (videos_url, shorts_url):
                if not section_url:
                    continue
                try:
                    info = await asyncio.to_thread(
                        flat_ydl.extract_info, section_url, False
                    )
                except Exception as e:
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
                entries = info.get("entries") or []
                collected.extend(entries)

        persistent_playlist_file = DVR_Config.get_posted_persistent_playlist()
        persistent_urls = set()
        persistent_ids = set()
        if persistent_playlist_file and os.path.exists(persistent_playlist_file):
            try:
                with open(persistent_playlist_file, "r", encoding="utf-8") as pf:
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
                    f"Failed to read persistent playlist {persistent_playlist_file}: {e}",
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

        if entries_to_fetch and (len(entries_to_fetch)):
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
                        info = await asyncio.to_thread(ydl.extract_info, url, False)
                        detailed_entries.append(info)
                    except Exception as e:
                        LogManager.log_message(
                            f"Failed to fetch metadata for entry {url}: {e}",
                            log_file_name,
                        )
            return detailed_entries
        else:
            return []

    @classmethod
    async def download_with_retry(cls, ydl_opts, url_or_list, log_file_name=None):
        """Download using YoutubeDL; retry once without cookiefile on rate-limit.

        Detects rate limits from both exception messages and logger warnings.
        Raises the final exception if retry also fails with rate-limit or other errors.
        """
        dlp_logger = DLP_Logger(
            patterns=DLP_Logger_Patterns, log_file_name=log_file_name
        )
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts["logger"] = dlp_logger

        orig_had_cookie = False
        if cls.dlp_cookies_present:
            ydl_opts["cookiefile"] = cls.dlp_cookies_file
            orig_had_cookie = True

        try:
            await cls.download(ydl_opts, url_or_list, log_file_name)
        except Exception as e:
            LogManager.log_message(
                f"Exception in download helper {e}",
                log_file_name,
            )
            is_rate_limit_by_exception = DLPEvents.is_rate_limit_error(e)
            is_rate_limit_by_logger = dlp_logger.detected

            if (
                is_rate_limit_by_exception or is_rate_limit_by_logger
            ) and orig_had_cookie:
                LogManager.log_message(
                    f"Rate limit detected during download using cookiefile (exception: {is_rate_limit_by_exception}, logger: {is_rate_limit_by_logger}), retrying without cookiefile: {e}",
                    log_file_name,
                )
                retry_logger = DLP_Logger(
                    patterns=DLP_Logger_Patterns, log_file_name=log_file_name
                )
                retry_opts = dict(ydl_opts)
                retry_opts.pop("cookiefile", None)
                retry_opts["logger"] = retry_logger
                try:
                    await cls.download(retry_opts, url_or_list, log_file_name)
                except Exception as e2:
                    is_rate_limit_by_exception_2 = DLPEvents.is_rate_limit_error(e2)
                    is_rate_limit_by_logger_2 = retry_logger.detected
                    if is_rate_limit_by_exception_2 or is_rate_limit_by_logger_2:
                        LogManager.log_message(
                            f"Rate limit persists after retry without cookiefile for download (exception: {is_rate_limit_by_exception_2}, logger: {is_rate_limit_by_logger_2}): {e2}",
                            log_file_name,
                        )
                    else:
                        LogManager.log_message(
                            f"Download failed on retry without cookiefile for non-rate-limit reason: {e2}",
                            log_file_name,
                        )
            else:
                LogManager.log_message(
                    f"Download failed for non-rate-limit reason (exception: {is_rate_limit_by_exception}, logger: {is_rate_limit_by_logger}): {e}",
                    log_file_name,
                )

    @classmethod
    async def getinfo_with_retry(cls, ydl_opts, url_or_list, log_file_name=None):
        """Retrieve info using YoutubeDL.extract_info without downloading.

        Mirrors the retry behavior of `download_with_retry`: if a rate-limit
        error occurs and the original options contained a `cookiefile`, retry
        once without the cookiefile. Detects rate limits from both exception
        messages and logger warnings. Returns the extracted info on success or
        `None` on failure (errors are logged to `LogManager`).
        """
        dlp_logger = DLP_Logger(
            patterns=DLP_Logger_Patterns, log_file_name=log_file_name
        )
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts["logger"] = dlp_logger

        YT_Cookies_File = DVR_Config.get_yt_cookies_file()
        orig_had_cookie = False
        if cls.dlp_cookies_present:
            ydl_opts["cookiefile"] = cls.dlp_cookies_file
            orig_had_cookie = True

        try:
            return await cls.getinfo(ydl_opts, url_or_list, log_file_name)
        except Exception as e:
            LogManager.log_message(
                f"Exception in getinfo helper {e}",
                log_file_name,
            )
            is_rate_limit_by_exception = DLPEvents.is_rate_limit_error(e)
            is_rate_limit_by_logger = dlp_logger.detected

            if (
                is_rate_limit_by_exception or is_rate_limit_by_logger
            ) and orig_had_cookie:
                LogManager.log_message(
                    f"Rate limit detected during getinfo using cookiefile (exception: {is_rate_limit_by_exception}, logger: {is_rate_limit_by_logger}), retrying without cookiefile: {e}",
                    log_file_name,
                )
                retry_logger = DLP_Logger(
                    patterns=DLP_Logger_Patterns, log_file_name=log_file_name
                )
                retry_opts = dict(ydl_opts)
                retry_opts.pop("cookiefile", None)
                retry_opts["logger"] = retry_logger
                try:
                    return await cls.getinfo(retry_opts, url_or_list, log_file_name)
                except Exception as e2:
                    is_rate_limit_by_exception_2 = DLPEvents.is_rate_limit_error(e2)
                    is_rate_limit_by_logger_2 = retry_logger.detected
                    if is_rate_limit_by_exception_2 or is_rate_limit_by_logger_2:
                        LogManager.log_message(
                            f"Rate limit persists after retry without cookiefile for getinfo (exception: {is_rate_limit_by_exception_2}, logger: {is_rate_limit_by_logger_2}): {e2}",
                            log_file_name,
                        )
                    else:
                        LogManager.log_message(
                            f"getinfo failed on retry without cookiefile for non-rate-limit reason: {e2}",
                            log_file_name,
                        )
            else:
                LogManager.log_message(
                    f"getinfo failed for non-rate-limit reason (exception: {is_rate_limit_by_exception}, logger: {is_rate_limit_by_logger}): {e}",
                    log_file_name,
                )
        return None

    @classmethod
    async def getentries_with_retry(
        cls, ydl_opts, videos_url=None, shorts_url=None, log_file_name=None
    ):
        """Fetch entries for provided section URLs (videos/shorts).

        Tries once with the configured cookiefile, and if a rate-limit error
        occurs and a cookie was used, retries once without the cookiefile.
        Detects rate limits from both exception messages and logger warnings.
        Returns a list of entries on success, or None on failure.
        """
        dlp_logger = DLP_Logger(
            patterns=DLP_Logger_Patterns, log_file_name=log_file_name
        )
        ydl_opts = dict(ydl_opts) if ydl_opts is not None else {}
        ydl_opts["logger"] = dlp_logger

        YT_Cookies_File = DVR_Config.get_yt_cookies_file()
        orig_had_cookie = False
        if cls.dlp_cookies_present:
            ydl_opts["cookiefile"] = cls.dlp_cookies_file
            orig_had_cookie = True

        try:
            return await cls.getentries(ydl_opts, videos_url, shorts_url, log_file_name)
        except Exception as e:
            LogManager.log_message(
                f"Exception in getentries helper {e}",
                log_file_name,
            )
            is_rate_limit_by_exception = DLPEvents.is_rate_limit_error(e)
            is_rate_limit_by_logger = dlp_logger.detected

            if (
                is_rate_limit_by_exception or is_rate_limit_by_logger
            ) and orig_had_cookie:
                LogManager.log_message(
                    f"Rate limit detected during getentries using cookiefile (exception: {is_rate_limit_by_exception}, logger: {is_rate_limit_by_logger}), retrying without cookiefile: {e}",
                    log_file_name,
                )
                retry_logger = DLP_Logger(
                    patterns=DLP_Logger_Patterns, log_file_name=log_file_name
                )
                retry_opts = dict(ydl_opts)
                retry_opts.pop("cookiefile", None)
                retry_opts["logger"] = retry_logger
                try:
                    return await cls.getentries(
                        retry_opts, videos_url, shorts_url, log_file_name
                    )
                except Exception as e2:
                    is_rate_limit_by_exception_2 = DLPEvents.is_rate_limit_error(e2)
                    is_rate_limit_by_logger_2 = retry_logger.detected
                    if is_rate_limit_by_exception_2 or is_rate_limit_by_logger_2:
                        LogManager.log_message(
                            f"Rate limit persists after retry without cookiefile for getentries (exception: {is_rate_limit_by_exception_2}, logger: {is_rate_limit_by_logger_2}): {e2}",
                            log_file_name,
                        )
                    else:
                        LogManager.log_message(
                            f"getentries failed on retry without cookiefile for non-rate-limit reason: {e2}",
                            log_file_name,
                        )
            else:
                LogManager.log_message(
                    f"getentries failed for non-rate-limit reason (exception: {is_rate_limit_by_exception}, logger: {is_rate_limit_by_logger}): {e}",
                    log_file_name,
                )
        return None
