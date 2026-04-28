"""
Base class for async database managers using aiosqlite.
Provides common connection management, lifecycle registration, and database utilities.
"""

import asyncio
import logging
from typing import Optional
import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Base class for async database managers providing common connection management."""

    def __init__(self, db_path: str = None):
        """Initialize base database manager.

        Args:
            db_path: Path to the database file. If None, subclasses should set it.
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._is_connected = False
        self._is_disconnecting = False
        self._lifecycle_registered = False
        self._db_name = self.__class__.__name__

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create database connection.

        Returns:
            aiosqlite.Connection: The database connection

        Raises:
            RuntimeError: If connection is being closed or has been closed
        """
        if (
            self._is_disconnecting
            or not self._is_connected
            and self._connection is not None
        ):
            raise RuntimeError(
                "Database connection is being closed or has been closed."
            )

        if self._connection is None:
            if self.db_path is None:
                raise RuntimeError(
                    "Database path not set. Set db_path before connecting."
                )

            self._connection = await aiosqlite.connect(self.db_path, timeout=30.0)
            self._connection.row_factory = aiosqlite.Row
            self._is_connected = True

            # Register with lifecycle manager for coordinated shutdown
            # (only if a running loop exists)
            if not self._lifecycle_registered:
                try:
                    from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

                    loop = asyncio.get_running_loop()
                    AsyncioLifecycleManager.register_database(
                        self, loop, db_name=f"{self._db_name}({self.db_path})"
                    )
                    self._lifecycle_registered = True
                except RuntimeError:
                    # No running loop yet - registration will be skipped for now
                    # This can happen during early initialization before the event loop is created
                    pass
                except Exception as e:
                    logger.warning(
                        f"Failed to register {self._db_name} with lifecycle manager: {e}"
                    )

        return self._connection

    async def close(self):
        """Close database connection with worker thread synchronization."""
        if self._is_disconnecting or not self._is_connected:
            return

        self._is_disconnecting = True

        try:
            if self._connection:
                try:
                    await self._connection.close()
                    logger.debug(
                        f"Closed {self._db_name} connection for {self.db_path}"
                    )
                except Exception as e:
                    logger.warning(f"Error closing {self._db_name} connection: {e}")

                # Wait briefly for worker thread to finish
                try:
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

                self._connection = None
                self._is_connected = False
        finally:
            self._is_disconnecting = False

    def _sanitize_identifier(self, value: str) -> str:
        """Sanitize a string for use as a SQLite identifier.

        Args:
            value: The string to sanitize

        Returns:
            str: A sanitized identifier safe for use in SQL

        Raises:
            ValueError: If value is not a string
        """
        if not isinstance(value, str):
            raise ValueError("Identifier must be a string")
        # Remove/escape special characters
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in value)
        if not sanitized or sanitized[0].isdigit():
            sanitized = "_" + sanitized
        return sanitized

    async def _execute_query(
        self,
        query: str,
        params: tuple = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ):
        """Execute a query with optional fetching.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_one: If True, fetch one row
            fetch_all: If True, fetch all rows

        Returns:
            Result of the query (None, row, or list of rows)
        """
        conn = await self._get_connection()
        cursor = await conn.execute(query, params or ())

        if fetch_one:
            row = await cursor.fetchone()
            await cursor.close()
            return row
        elif fetch_all:
            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        else:
            await cursor.close()
            return None

    async def _execute_update(self, query: str, params: tuple = None) -> bool:
        """Execute an update/insert/delete query.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            bool: True if successful
        """
        conn = await self._get_connection()
        await conn.execute(query, params or ())
        await conn.commit()
        return True
