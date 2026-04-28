"""
Native async LoggingDatabaseManager using aiosqlite for non-blocking database access.
Handles all logging database operations.
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Optional, List, Dict
from db.common_db import DatabaseManager

logger = logging.getLogger(__name__)


class LogDB(DatabaseManager):
    """Async logging database manager providing non-blocking SQLite access via aiosqlite."""

    # Global singleton instance
    _global_instance = None

    # Log level constants
    LOG_LEVEL_DEBUG = "DEBUG"
    LOG_LEVEL_INFO = "INFO"
    LOG_LEVEL_WARNING = "WARNING"
    LOG_LEVEL_ERROR = "ERROR"
    LOG_LEVELS = [LOG_LEVEL_DEBUG, LOG_LEVEL_INFO, LOG_LEVEL_WARNING, LOG_LEVEL_ERROR]

    LOG_TABLES = {
        "core": "log_core",
        "download_live": "log_download_live",
        "download_posted": "log_download_posted",
        "download_live_recovery": "log_download_live_recovery",
        "download_captions": "log_download_captions",
        "download_comments": "log_download_comments",
        "download_posted_notices": "log_download_posted_notices",
        "playlist_update": "log_playlist_update",
        "upload_live": "log_upload_live",
        "upload_posted": "log_upload_posted",
        "upload_captions": "log_upload_captions",
        "upload_ia": "log_upload_ia",
        "upload_yt": "log_upload_yt",
        "upload_rumble": "log_upload_rumble",
        "upload_bitchute": "log_upload_bitchute",
        "upload_odysee": "log_upload_odysee",
    }

    def __init__(self, db_dir: str = None):
        """Initialize async logging database manager."""
        if db_dir is None:
            from utils.file_utils import FileManager

            db_dir = FileManager.get_dvr_runtime_dir()

        db_path = str(Path(db_dir) / "DVR_Logs.db")
        super().__init__(db_path)

        self.db_dir = db_dir
        self.is_fresh = False
        self._schema_initialized = False
        logger.debug(f"LogDB initialized with db_path: {self.db_path}")

    @classmethod
    async def get_global(cls):
        """Get or create the global LogDB instance.

        This class method ensures only one logging database manager exists and is reused
        across all modules, preventing database lock conflicts.

        Returns:
            LogDB: The global singleton logging database manager instance
        """
        if cls._global_instance is None:
            cls._global_instance = cls()
            await cls._global_instance.initialize_database()

        return cls._global_instance

    @classmethod
    def get_global_sync(cls):
        """Get the global logging database instance (without initialization).

        WARNING: Only use this after async initialization is complete.
        For normal use, await get_global() instead.

        Returns:
            LogDB: The global singleton instance or None if not yet initialized
        """
        return cls._global_instance

    def is_initialized(self) -> bool:
        """Check if the database schema has been initialized."""
        return self._schema_initialized

    # _get_connection and close methods are now inherited from DatabaseManager

    def get_table_name(self, log_type: str) -> Optional[str]:
        """Get table name for log type."""
        return self.LOG_TABLES.get(log_type)

    def _validate_level(self, level: str) -> str:
        """Validate log level."""
        level = level.upper() if level else "INFO"
        if level not in self.LOG_LEVELS:
            level = "INFO"
        return level

    async def initialize_database(self):
        """Initialize logging database schema."""
        try:
            conn = await self._get_connection()
            for log_type, table_name in self.LOG_TABLES.items():
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT DEFAULT 'INFO',
                        message TEXT,
                        thread_number INTEGER,
                        is_aggregation INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

            await conn.commit()
            self.is_fresh = True
            self._schema_initialized = True

            # Attempt deferred registration with lifecycle manager now that schema is initialized
            # (in case initialization was skipped earlier due to no running loop)
            if not self._lifecycle_registered:
                try:
                    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

                    loop = asyncio.get_running_loop()
                    AsyncioLifecycleManager.register_database(
                        self, loop, db_name=f"DVR_Logs({self.db_path})"
                    )
                    self._lifecycle_registered = True
                except RuntimeError:
                    # Still no running loop - this shouldn't happen if called from async context
                    print(
                        f"[DB_INIT] Warning: still no running loop for deferred registration",
                        flush=True,
                    )
                except Exception as e:
                    print(
                        f"[DB_INIT] Warning: deferred registration failed - {e}",
                        flush=True,
                    )

        except Exception as e:
            print(
                f"[DB_INIT_ERROR] Failed to initialize logging database: {e}",
                flush=True,
            )
            import traceback

            print(f"[DB_INIT_ERROR] Traceback: {traceback.format_exc()}", flush=True)
            raise

    async def log_message(
        self,
        log_type: str,
        message: str,
        level: str = "INFO",
        thread_number: int = None,
        is_aggregation: bool = False,
    ) -> bool:
        """Log a message."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                logger.warning(f"Unknown log type: {log_type}")
                return False

            level = self._validate_level(level)

            await conn.execute(
                f"""INSERT INTO {table_name} (level, message, thread_number, is_aggregation)
                   VALUES (?, ?, ?, ?)""",
                (level, message, thread_number, 1 if is_aggregation else 0),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log message: {e}")
            return False

    async def get_logs(
        self,
        log_type: str,
        level: str = None,
        thread_number: int = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Get logs with optional filtering."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return []

            query = f"SELECT * FROM {table_name} WHERE 1=1"
            params = []

            if level:
                level = self._validate_level(level)
                query += " AND level = ?"
                params.append(level)

            if thread_number is not None:
                query += " AND thread_number = ?"
                params.append(thread_number)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return []

    async def get_log_count(self, log_type: str) -> int:
        """Get total log count for a type."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return 0

            cursor = await conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to get log count: {e}")
            return 0

    async def clear_logs(self, log_type: str) -> bool:
        """Clear logs for a specific type."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return False

            await conn.execute(f"DELETE FROM {table_name}")
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to clear logs: {e}")
            return False

    async def clear_all_logs(self) -> bool:
        """Clear all logs."""
        try:
            conn = await self._get_connection()
            for table_name in self.LOG_TABLES.values():
                await conn.execute(f"DELETE FROM {table_name}")
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to clear all logs: {e}")
            return False

    async def search_logs(
        self, log_type: str, search_term: str, limit: int = 100
    ) -> List[Dict]:
        """Search logs by message content."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return []

            cursor = await conn.execute(
                f"""SELECT * FROM {table_name} 
                   WHERE message LIKE ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (f"%{search_term}%", limit),
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to search logs: {e}")
            return []

    async def export_logs(self, log_type: str, file_path: str) -> bool:
        """Export logs to JSON file."""
        try:
            logs = await self.get_logs(log_type, limit=10000)
            with open(file_path, "w") as f:
                json.dump(logs, f, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Failed to export logs: {e}")
            return False

    # ===== Logs_* table methods (with aggregation support) =====

    async def log_aggregated_message(
        self,
        log_type: str,
        message: str,
        level: str = "INFO",
        thread_number: int = None,
        aggregation_count: int = 1,
    ) -> bool:
        """Log a message to the log table with aggregation support."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                logger.warning(f"Unknown log type: {log_type}")
                return False

            level = self._validate_level(level)

            await conn.execute(
                f"""INSERT INTO {table_name}
                   (message, level, thread_number, is_aggregation)
                   VALUES (?, ?, ?, ?)""",
                (message, level, thread_number, 1),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log aggregated message: {e}")
            return False

    async def get_aggregated_logs(
        self,
        log_type: str,
        level: str = None,
        thread_number: int = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Get aggregated logs with optional filtering."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return []

            query = f"SELECT * FROM {table_name} WHERE 1=1"
            params = []

            if level:
                level = self._validate_level(level)
                query += " AND level = ?"
                params.append(level)

            if thread_number is not None:
                query += " AND thread_number = ?"
                params.append(thread_number)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to get aggregated logs: {e}")
            return []

    async def get_aggregated_log_count(self, log_type: str) -> int:
        """Get total aggregated log count for a type."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return 0

            cursor = await conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to get aggregated log count: {e}")
            return 0

    async def clear_aggregated_logs(self, log_type: str) -> bool:
        """Clear aggregated logs for a specific type."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return False

            await conn.execute(f"DELETE FROM {table_name}")
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to clear aggregated logs: {e}")
            return False

    async def search_aggregated_logs(
        self, log_type: str, search_term: str, limit: int = 100
    ) -> List[Dict]:
        """Search aggregated logs by message content."""
        try:
            conn = await self._get_connection()
            table_name = self.get_table_name(log_type)
            if not table_name:
                return []

            cursor = await conn.execute(
                f"""SELECT * FROM {table_name}
                   WHERE message LIKE ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (f"%{search_term}%", limit),
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to search aggregated logs: {e}")
            return []
