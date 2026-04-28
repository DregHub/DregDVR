"""
Log Manager Module
Handles all logging operations using SQLite database storage.
Provides backward-compatible API while using database backend instead of text files.
"""

import datetime
import traceback
import logging
import threading
import queue
import time
import atexit
import os
import asyncio
from config.config_settings import DVR_Config
from db.log_db import LogDB
from utils.thread_context import ThreadContext

# Configure logger for this module
logger = logging.getLogger(__name__)


def _get_python_log_level(level_str):
    """Convert string log level to Python logging level constant."""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return level_map.get(level_str, logging.INFO)


class LogLevels:
    """Log level constants for the logging system."""

    Debug = "DEBUG"
    Info = "INFO"
    Warning = "WARNING"
    Error = "ERROR"
    ALL = [Debug, Info, Warning, Error]


class LogManager:
    _initialized = False
    _db = None
    _log_lock = threading.Lock()

    # Queue-based logging for thread safety
    _log_queue = None
    _logger_thread = None
    _logger_thread_stop = False

    # Log type constants (now match table names in database)
    table_core = "core"
    table_download_captions = "download_captions"
    table_download_comments = "download_comments"
    table_download_live = "download_live"
    table_download_live_recovery = "download_live_recovery"
    table_download_posted = "download_posted"
    table_download_posted_notices = "download_posted_notices"
    table_playlist_update = "playlist_update"
    table_upload_posted = "upload_posted"
    table_upload_live = "upload_live"
    table_upload_platform_ia = "upload_ia"
    table_upload_platform_yt = "upload_yt"
    table_upload_platform_rm = "upload_rumble"
    table_upload_platform_bc = "upload_bitchute"
    table_upload_platform_od = "upload_odysee"
    table_upload_platform_gh = "upload_captions"

    # For backward compatibility with file operations
    log_tables = [
        "core",
        "download_captions",
        "download_live",
        "download_live_recovery",
        "download_posted",
        "channel_playlist",
        "download_posted_notices",
        "playlist_update",
        "upload_live",
        "upload_ia",
        "upload_yt",
        "upload_rumble",
        "upload_bitchute",
        "upload_odysee",
        "upload_captions",
    ]

    @classmethod
    def _get_runtime_dir(cls):
        """Get the writable runtime directory, with fallback to /_DVR_Runtime."""
        # Try environment variable first
        runtime_dir = os.environ.get("DVR_RUNTIME_DIR")
        if (
            runtime_dir
            and os.path.isdir(runtime_dir)
            and os.access(runtime_dir, os.W_OK)
        ):
            return runtime_dir

        # Fallback to /_DVR_Runtime
        return "/_DVR_Runtime"

    @classmethod
    def _initialize_log_db(cls):
        """Initialize logging database on first use to avoid recursion."""
        if cls._initialized:
            return

        try:
            # Use the global logging database manager singleton
            # Don't initialize the database schema yet - wait until we have a running loop
            # This prevents creating temporary event loops during startup
            cls._db = LogDB.get_global_sync()

        except Exception as e:
            print(
                f"[LOGGING_INIT_ERROR] Failed to initialize logging database manager: {e}",
                flush=True,
            )
            raise

        cls._initialized = True
        # Start the logger thread on first initialization
        cls._start_logger_thread()

    @classmethod
    async def _ensure_database_schema(cls):
        """Ensure database schema is initialized (call this when you have a running loop)."""
        # Make sure the log manager is initialized first
        if not cls._initialized:
            cls._initialize_log_db()

        # Use the global singleton to ensure database schema is initialized
        try:
            cls._db = await LogDB.get_global()
        except Exception as e:
            print(
                f"[LOGGING_INIT_ERROR] Failed to get global logging database: {e}",
                flush=True,
            )
            import traceback as tb

            print(f"[LOGGING_INIT_ERROR] Traceback: {tb.format_exc()}", flush=True)
            raise

    @classmethod
    def _start_logger_thread(cls):
        """Start the background thread that processes queued log messages."""
        if (
            cls._log_queue is not None
            and cls._logger_thread is not None
            and cls._logger_thread.is_alive()
        ):
            return  # Already started

        if cls._log_queue is None:
            cls._log_queue = queue.Queue(maxsize=10000)
        else:
            print(
                f"[LOGGING_INIT] Restarting logger thread with existing queue...",
                flush=True,
            )

        cls._logger_thread_stop = False
        cls._logger_thread = threading.Thread(
            target=cls._logger_thread_worker, daemon=False
        )
        cls._logger_thread.start()

        # Register shutdown handler to flush logs on program exit
        atexit.register(cls.shutdown_logging)

    @classmethod
    def _logger_thread_worker(cls):
        """Background thread that writes all queued log messages to database."""
        message_count = 0
        while not cls._logger_thread_stop:
            try:
                # Get message from queue with timeout to check stop flag
                try:
                    log_entry = cls._log_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if log_entry is None:  # Sentinel value for shutdown
                    break

                # Unpack the log entry (now includes thread number and aggregation flag)
                message, log_type, level, thread_number, is_aggregation = log_entry
                message_count += 1

                # Write to database
                try:
                    cls._write_message_to_database(
                        message, log_type, level, thread_number, is_aggregation
                    )
                except Exception as e:
                    # Even if writing fails, log to console using standard logging
                    try:
                        python_level = _get_python_log_level(level)
                        logger.log(
                            python_level,
                            f"[LOGGING ERROR] Failed to write to {log_type}: {e}",
                        )
                    except Exception:
                        pass

                cls._log_queue.task_done()
            except Exception as e:
                try:
                    logger.error(f"[LOGGER THREAD ERROR] {e}")
                except Exception:
                    pass

    @classmethod
    def _write_message_to_database(
        cls,
        message,
        log_type,
        level=LogLevels.Info,
        thread_number=None,
        is_aggregation=False,
    ):
        """Write a single message to database (called by logger thread).

        If the database schema is not yet initialized, prints to console instead.
        This prevents attempting to write from a thread context before the main
        event loop has been created and schema initialized.
        """
        if not cls._db:
            return

        # If schema is not yet initialized, just log to console using standard logging
        # The schema will be initialized when the main event loop starts
        if not cls._db.is_initialized():
            python_level = _get_python_log_level(level)
            logger.log(python_level, message)
            return

        with cls._log_lock:
            try:
                # Try to get the main event loop from lifecycle manager
                # This allows us to schedule coroutines from background threads
                try:
                    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

                    # Get the first registered loop (should be the main loop)
                    # Use lock to ensure thread-safe access
                    loop = None
                    with AsyncioLifecycleManager._lock:
                        loops = AsyncioLifecycleManager._loops
                        if not loops:
                            # No loops registered yet, log to console using standard logging
                            python_level = _get_python_log_level(level)
                            logger.log(
                                python_level,
                                f"[DB_LOG] No loops registered yet, using console fallback: {message}",
                            )
                            return

                        # Get the main loop (first registered)
                        loop_entry = next(iter(loops.values()))
                        loop = loop_entry["loop"]

                    # Check if loop is running (outside the lock)
                    if not loop or not loop.is_running():
                        python_level = _get_python_log_level(level)
                        logger.log(
                            python_level,
                            f"[DB_LOG] Loop is not running, using console fallback: {message}",
                        )
                        return

                    # Schedule the coroutine on the main loop using run_coroutine_threadsafe

                    future = asyncio.run_coroutine_threadsafe(
                        cls._db.log_message(
                            log_type,
                            message,
                            level,
                            thread_number=thread_number,
                            is_aggregation=is_aggregation,
                        ),
                        loop,
                    )

                    # Wait for the result with a timeout
                    try:
                        success = future.result(timeout=5.0)
                        if success != True:
                            python_level = _get_python_log_level(level)
                            logger.log(
                                python_level,
                                f"[DB_LOG] Failed to write to database: {log_type} - {message}",
                            )
                    except asyncio.TimeoutError:
                        python_level = _get_python_log_level(level)
                        logger.log(
                            python_level,
                            f"[DB_LOG] Timeout writing to database: {log_type} - {message}",
                        )
                    except Exception as e:
                        python_level = _get_python_log_level(level)
                        logger.log(
                            python_level,
                            f"[DB_LOG] Error writing to database: {log_type} - {e} - {message}",
                        )

                except Exception as e:
                    # Fallback to console logging if anything goes wrong
                    python_level = _get_python_log_level(level)
                    logger.log(
                        python_level, f"[DB_LOG_FALLBACK] {message} (error: {e})"
                    )
                    logger.error(f"Failed to schedule log on main loop: {e}")

            except Exception as e:
                python_level = _get_python_log_level(level)
                logger.log(
                    python_level,
                    f"[LOGGING_ERROR] Failed to write to database {log_type}: {message} (error: {e})",
                )
                logger.error(f"Failed to write to database {log_type}: {e}")

    @classmethod
    def _queue_log_message(cls, message, log_type, level="INFO", thread_number=None):
        """Add a message to the logging queue."""
        cls._initialize_log_db()

        if not log_type or not isinstance(log_type, str):
            return

        # Ensure the logger thread is running before queuing the message.
        if (
            cls._log_queue is None
            or cls._logger_thread is None
            or not cls._logger_thread.is_alive()
        ):
            cls._start_logger_thread()

        try:
            cls._log_queue.put_nowait((message, log_type, level, thread_number, False))
        except queue.Full:
            # Queue is full, write directly (blocking)
            try:
                cls._write_message_to_database(
                    message, log_type, level, thread_number, False
                )
            except Exception:
                pass
        except Exception as e:
            # If queue operations fail, fallback to direct write
            try:
                cls._write_message_to_database(
                    message, log_type, level, thread_number, False
                )
            except Exception:
                pass

    @classmethod
    def log_message(cls, message, log_type, level=LogLevels.Info, thread_number=None):
        """Log a message with a timestamp to the specified log type.

        Uses queue-based async logging for thread safety in multi-threaded contexts.

        Args:
            message: The message to log
            log_type: The log type identifier (e.g., 'core', 'download_live')
            level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
            thread_number: Optional thread identifier to store in the log database.
        """
        cls._initialize_log_db()
        if not log_type:
            return

        if not isinstance(log_type, str):
            return

        # Queue message for async logging - ensures thread safety
        if thread_number is None:
            # Try to get logical thread number from context first, then fall back to 0 (non-threaded)
            thread_number = ThreadContext.get_thread_context()
            if thread_number is None:
                thread_number = 0
        cls._queue_log_message(message, log_type, level, thread_number)

    @classmethod
    def log_message_with_console(
        cls, message, log_type, level="INFO", thread_number=None
    ):
        """Log a message to BOTH database and console (stdout) for visibility in container shell.

        Useful for thread-specific logging where database issues need to be diagnosed.
        Only outputs to console if console_thread_logging is enabled in config.
        Always queues to database if provided.

        Args:
            message: The message to log
            log_type: The log type identifier
            level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
            thread_number: Optional thread identifier to store in the log database.
        """
        cls._initialize_log_db()

        # Check if console logging is enabled
        try:
            console_logging_enabled = DVR_Config.get_console_thread_logging()
        except Exception:
            console_logging_enabled = False

        # Output to console only if enabled
        if console_logging_enabled:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            console_output = f"[{timestamp}] [{level}] {message}"
            print(console_output, flush=True)

        # Also log to database if provided
        if log_type and isinstance(log_type, str):
            if thread_number is None:
                # Try to get logical thread number from context first, then fall back to 0 (non-threaded)
                thread_number = ThreadContext.get_thread_context()
                if thread_number is None:
                    thread_number = 0
            cls._queue_log_message(message, log_type, level, thread_number)

    @classmethod
    def log_message_debug(cls, message, log_type, thread_number=None):
        """Log a debug-level message."""
        cls.log_message(message, log_type, LogLevels.Debug, thread_number=thread_number)

    @classmethod
    def log_message_info(cls, message, log_type, thread_number=None):
        """Log an info-level message."""
        cls.log_message(message, log_type, LogLevels.Info, thread_number=thread_number)

    @classmethod
    def log_message_warning(cls, message, log_type, thread_number=None):
        """Log a warning-level message."""
        cls.log_message(
            message, log_type, LogLevels.Warning, thread_number=thread_number
        )

    @classmethod
    def log_message_error(cls, message, log_type, thread_number=None):
        """Log an error-level message."""
        cls.log_message(
            message, log_type, cls.LOG_LEVEL_ERROR, thread_number=thread_number
        )

    @classmethod
    def log_core(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the core dreggs dvr log."""
        cls._initialize_log_db()
        cls.log_message(message, cls.table_core, level, thread_number=thread_number)

    @classmethod
    def log_download_live(cls, message, level="INFO", thread_number=None):
        """Log a message to the Download YouTube Live log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_download_live, level, thread_number=thread_number
        )

    @classmethod
    def log_download_live_recovery(
        cls, message, level=LogLevels.Info, thread_number=None
    ):
        """Log a message to the Download YouTube Live Recovery log."""
        cls._initialize_log_db()
        cls.log_message(
            message,
            cls.table_download_live_recovery,
            level,
            thread_number=thread_number,
        )

    @classmethod
    def log_download_captions(cls, message, level="INFO", thread_number=None):
        """Log a message to the Download YouTube Captions log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_download_captions, level, thread_number=thread_number
        )

    @classmethod
    def log_download_comments(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Download YouTube Comments log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_download_comments, level, thread_number=thread_number
        )

    @classmethod
    def log_download_posted(cls, message, level="INFO", thread_number=None):
        """Log a message to the Download YouTube Posted log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_download_posted, level, thread_number=thread_number
        )

    @classmethod
    def log_channel_playlist(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Posted Playlist log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_playlist_update, level, thread_number=thread_number
        )

    @classmethod
    def log_download_posted_notices(cls, message, level="INFO", thread_number=None):
        """Log a message to the Download YouTube Posted Notices log."""
        cls._initialize_log_db()
        cls.log_message(
            message,
            cls.table_download_posted_notices,
            level,
            thread_number=thread_number,
        )

    @classmethod
    def log_upload_posted(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Upload YouTube Posted log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_posted, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_live(cls, message, level="INFO", thread_number=None):
        """Log a message to the Upload YouTube live log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_live, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_ia(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Upload Internet Archive log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_platform_ia, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_yt(cls, message, level="INFO", thread_number=None):
        """Log a message to the Upload YouTube log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_platform_yt, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_captions(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Upload Captions log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_platform_gh, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_rumble(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Upload Rumble log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_platform_rm, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_bitchute(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Upload BitChute log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_platform_bc, level, thread_number=thread_number
        )

    @classmethod
    def log_upload_odysee(cls, message, level=LogLevels.Info, thread_number=None):
        """Log a message to the Upload Odysee log."""
        cls._initialize_log_db()
        cls.log_message(
            message, cls.table_upload_platform_od, level, thread_number=thread_number
        )

    @classmethod
    def log_thread_diagnostic(cls, message, log_type=None):
        """Log a diagnostic message for thread operations with console output.

        Args:
            message: The diagnostic message
            log_type: Optional log type to also log to database
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        import sys

        console_msg = f"[{timestamp}] DIAG: {message}"
        try:
            print(console_msg, file=sys.stderr, flush=True)
        except Exception:
            pass

        # Also log to database if specified
        if log_type:
            try:
                cls.log_message(message, log_type, thread_number=0)
            except Exception:
                pass

    @classmethod
    def flush_logs(cls):
        """Wait for all queued log messages to be written before returning."""
        if cls._log_queue is None:
            return

        # Start the logger thread if not already started
        if cls._logger_thread is None or not cls._logger_thread.is_alive():
            cls._start_logger_thread()

        # Get initial queue size for diagnostics
        try:
            initial_size = cls._log_queue.qsize()
        except:
            initial_size = 0

        # Wait for the queue to be empty - with timeout to prevent hanging
        try:
            cls._log_queue.join()
        except Exception:
            pass

        # Give logger thread multiple moments to process final messages
        for attempt in range(5):
            time.sleep(0.1)
            # Check if queue is truly empty
            try:
                if cls._log_queue.empty():
                    break
            except Exception:
                break

    @classmethod
    def shutdown_logging(cls):
        """Shutdown the logging thread gracefully and integrate with lifecycle manager."""
        if cls._log_queue is None:
            return

        try:
            remaining = cls._log_queue.qsize()
        except:
            remaining = 0

        if remaining > 0:
            pass

        # Drain the queue completely before stopping
        max_drain_attempts = 10
        drain_attempt = 0
        while drain_attempt < max_drain_attempts:
            try:
                if cls._log_queue.empty():
                    break
                cls._log_queue.join()
                time.sleep(0.2)
            except Exception:
                break
            drain_attempt += 1

        # Send sentinel value to stop thread
        try:
            cls._log_queue.put_nowait(None)
        except Exception as e:
            print(f"[SHUTDOWN_LOGGING] Failed to send sentinel: {e}", flush=True)

        # Wait for thread to stop - with longer timeout
        cls._logger_thread_stop = True
        if cls._logger_thread and cls._logger_thread.is_alive():
            cls._logger_thread.join(timeout=5.0)
            if cls._logger_thread.is_alive():
                print(
                    "[SHUTDOWN_LOGGING] WARNING: Logger thread did not stop after 5s",
                    flush=True,
                )

        # Unregister atexit handler to avoid double shutdown
        try:
            atexit.unregister(cls.shutdown_logging)
        except Exception:
            pass

        # Register with lifecycle manager for coordinated shutdown
        try:
            from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

            if cls._db:
                AsyncioLifecycleManager.register_shutdown_handler(cls.shutdown_logging)
        except Exception:
            pass
