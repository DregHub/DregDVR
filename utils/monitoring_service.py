"""
Monitoring Service Module
Tracks real-time download and upload progress from DLPEvents and log files.
Stores monitoring data in active_downloads and active_uploads database tables.
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service for monitoring active downloads and uploads in real-time."""

    def __init__(self, config_db_path: str = None):
        """Initialize monitoring service.

        Args:
            config_db_path: Path to DVR_Main.db
        """
        if config_db_path is None:
            root_dir = os.getcwd()
            runtime_dir = os.path.join(root_dir, "_DVR_Runtime")
            config_db_path = os.path.join(runtime_dir, "DVR_Main.db")

        self.config_db_path = config_db_path
        self.logs_dir = os.path.join(os.path.dirname(config_db_path), "logs")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.config_db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def initialize_monitoring_tables(self):
        """Create monitoring tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Active downloads table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS active_downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instance_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT DEFAULT 'downloading',
                    downloaded_bytes INTEGER DEFAULT 0,
                    total_bytes INTEGER,
                    download_speed REAL DEFAULT 0.0,
                    eta_seconds INTEGER,
                    progress_percentage REAL DEFAULT 0.0,
                    attempts INTEGER DEFAULT 1,
                    error_message TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE,
                    UNIQUE(instance_id, filename)
                )
            """
            )

            # Active uploads table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS active_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instance_id INTEGER NOT NULL,
                    video_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    progress_percentage REAL DEFAULT 0.0,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_time TIMESTAMP,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE,
                    UNIQUE(instance_id, video_id, platform)
                )
            """
            )

            # Add indices for efficient filtering
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_active_downloads_instance_id 
                ON active_downloads(instance_id)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_active_downloads_status 
                ON active_downloads(status)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_active_uploads_instance_id 
                ON active_uploads(instance_id)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_active_uploads_status 
                ON active_uploads(status)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_active_uploads_platform 
                ON active_uploads(platform)
            """
            )

            conn.commit()
            logger.info("Monitoring tables initialized")

    def update_download_progress(
        self,
        instance_id: int,
        filename: str,
        downloaded_bytes: int = 0,
        total_bytes: int = None,
        download_speed: float = 0.0,
        eta_seconds: int = None,
        status: str = "downloading",
        attempts: int = 1,
        error_message: str = None,
    ) -> bool:
        """Update or create download progress entry.

        Args:
            instance_id: Instance ID
            filename: Download filename
            downloaded_bytes: Bytes downloaded so far
            total_bytes: Total file bytes (if known)
            download_speed: Current download speed in bytes/sec
            eta_seconds: Estimated seconds remaining
            status: Current status (downloading, completed, failed, paused)
            attempts: Number of download attempts
            error_message: Error message if failed

        Returns:
            True if successfully updated/created
        """
        try:
            # Calculate progress percentage
            progress_percentage = 0.0
            if total_bytes and total_bytes > 0:
                progress_percentage = (downloaded_bytes / total_bytes) * 100

            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if entry exists
                cursor.execute(
                    """
                    SELECT id FROM active_downloads 
                    WHERE instance_id = ? AND filename = ?
                """,
                    (instance_id, filename),
                )

                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE active_downloads SET 
                        downloaded_bytes = ?, total_bytes = ?, download_speed = ?,
                        eta_seconds = ?, progress_percentage = ?, status = ?,
                        attempts = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE instance_id = ? AND filename = ?
                    """,
                        (
                            downloaded_bytes,
                            total_bytes,
                            download_speed,
                            eta_seconds,
                            progress_percentage,
                            status,
                            attempts,
                            error_message,
                            instance_id,
                            filename,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO active_downloads 
                        (instance_id, filename, downloaded_bytes, total_bytes, download_speed,
                         eta_seconds, progress_percentage, status, attempts, error_message)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            instance_id,
                            filename,
                            downloaded_bytes,
                            total_bytes,
                            download_speed,
                            eta_seconds,
                            progress_percentage,
                            status,
                            attempts,
                            error_message,
                        ),
                    )

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error updating download progress: {e}")
            return False

    def mark_download_complete(self, instance_id: int, filename: str) -> bool:
        """Mark a download as completed.

        Args:
            instance_id: Instance ID
            filename: Download filename

        Returns:
            True if successfully updated
        """
        return self.update_download_progress(
            instance_id=instance_id,
            filename=filename,
            status="completed",
            progress_percentage=100.0,
        )

    def mark_download_failed(
        self,
        instance_id: int,
        filename: str,
        error_message: str = None,
        retry_count: int = 0,
    ) -> bool:
        """Mark a download as failed.

        Args:
            instance_id: Instance ID
            filename: Download filename
            error_message: Error description
            retry_count: Number of retries attempted

        Returns:
            True if successfully updated
        """
        return self.update_download_progress(
            instance_id=instance_id,
            filename=filename,
            status="failed",
            error_message=error_message,
            attempts=retry_count,
        )

    def remove_download(self, instance_id: int, filename: str) -> bool:
        """Remove a download entry from monitoring (cleanup completed/canceled downloads).

        Args:
            instance_id: Instance ID
            filename: Download filename

        Returns:
            True if successfully removed
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM active_downloads 
                    WHERE instance_id = ? AND filename = ?
                """,
                    (instance_id, filename),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing download: {e}")
            return False

    def get_active_downloads(
        self, instance_id: int = None, status: str = None
    ) -> List[Dict]:
        """Get active downloads.

        Args:
            instance_id: Optional filter by instance ID
            status: Optional filter by status

        Returns:
            List of active download entries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM active_downloads WHERE 1=1"
                params = []

                if instance_id is not None:
                    query += " AND instance_id = ?"
                    params.append(instance_id)

                if status is not None:
                    query += " AND status = ?"
                    params.append(status)

                query += " ORDER BY updated_at DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error retrieving active downloads: {e}")
            return []

    def update_upload_status(
        self,
        instance_id: int,
        video_id: str,
        platform: str,
        status: str = "pending",
        progress_percentage: float = 0.0,
        error_message: str = None,
        retry_count: int = 0,
        next_retry_time: datetime = None,
    ) -> bool:
        """Update or create upload status entry.

        Args:
            instance_id: Instance ID
            video_id: Video identifier
            platform: Upload platform (youtube, rumble, bitchute, odysee, ia, github)
            status: Current status (pending, uploading, completed, failed, retrying)
            progress_percentage: Upload progress 0-100
            error_message: Error message if failed
            retry_count: Number of retries attempted
            next_retry_time: Time for next retry attempt

        Returns:
            True if successfully updated/created
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if entry exists
                cursor.execute(
                    """
                    SELECT id FROM active_uploads 
                    WHERE instance_id = ? AND video_id = ? AND platform = ?
                """,
                    (instance_id, video_id, platform),
                )

                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE active_uploads SET 
                        status = ?, progress_percentage = ?, error_message = ?,
                        retry_count = ?, next_retry_time = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE instance_id = ? AND video_id = ? AND platform = ?
                    """,
                        (
                            status,
                            progress_percentage,
                            error_message,
                            retry_count,
                            next_retry_time,
                            instance_id,
                            video_id,
                            platform,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO active_uploads 
                        (instance_id, video_id, platform, status, progress_percentage, 
                         error_message, retry_count, next_retry_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            instance_id,
                            video_id,
                            platform,
                            status,
                            progress_percentage,
                            error_message,
                            retry_count,
                            next_retry_time,
                        ),
                    )

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error updating upload status: {e}")
            return False

    def mark_upload_complete(
        self, instance_id: int, video_id: str, platform: str
    ) -> bool:
        """Mark an upload as completed.

        Args:
            instance_id: Instance ID
            video_id: Video identifier
            platform: Upload platform

        Returns:
            True if successfully updated
        """
        return self.update_upload_status(
            instance_id=instance_id,
            video_id=video_id,
            platform=platform,
            status="completed",
            progress_percentage=100.0,
        )

    def remove_upload(self, instance_id: int, video_id: str, platform: str) -> bool:
        """Remove an upload entry from monitoring.

        Args:
            instance_id: Instance ID
            video_id: Video identifier
            platform: Upload platform

        Returns:
            True if successfully removed
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM active_uploads 
                    WHERE instance_id = ? AND video_id = ? AND platform = ?
                """,
                    (instance_id, video_id, platform),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing upload: {e}")
            return False

    def get_active_uploads(
        self, instance_id: int = None, platform: str = None, status: str = None
    ) -> List[Dict]:
        """Get active uploads.

        Args:
            instance_id: Optional filter by instance ID
            platform: Optional filter by platform
            status: Optional filter by status

        Returns:
            List of active upload entries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM active_uploads WHERE 1=1"
                params = []

                if instance_id is not None:
                    query += " AND instance_id = ?"
                    params.append(instance_id)

                if platform is not None:
                    query += " AND platform = ?"
                    params.append(platform)

                if status is not None:
                    query += " AND status = ?"
                    params.append(status)

                query += " ORDER BY updated_at DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error retrieving active uploads: {e}")
            return []

    def get_operation_stats(self, instance_id: int = None) -> Dict[str, Any]:
        """Get statistics about active operations.

        Args:
            instance_id: Optional filter by instance ID

        Returns:
            Dictionary with operation statistics
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                stats = {
                    "total_downloads": 0,
                    "completed_downloads": 0,
                    "failed_downloads": 0,
                    "total_uploads": 0,
                    "completed_uploads": 0,
                    "failed_uploads": 0,
                    "total_download_speed": 0.0,
                    "average_download_progress": 0.0,
                }

                # Download stats
                where = ""
                if instance_id is not None:
                    where = f" WHERE instance_id = {instance_id}"

                cursor.execute(f"SELECT COUNT(*) FROM active_downloads{where}")
                stats["total_downloads"] = cursor.fetchone()[0] or 0

                cursor.execute(
                    f"SELECT COUNT(*) FROM active_downloads WHERE status = 'completed'{' AND instance_id = ' + str(instance_id) if instance_id else ''}"
                )
                stats["completed_downloads"] = cursor.fetchone()[0] or 0

                cursor.execute(
                    f"SELECT COUNT(*) FROM active_downloads WHERE status = 'failed'{' AND instance_id = ' + str(instance_id) if instance_id else ''}"
                )
                stats["failed_downloads"] = cursor.fetchone()[0] or 0

                # Upload stats
                cursor.execute(f"SELECT COUNT(*) FROM active_uploads{where}")
                stats["total_uploads"] = cursor.fetchone()[0] or 0

                cursor.execute(
                    f"SELECT COUNT(*) FROM active_uploads WHERE status = 'completed'{' AND instance_id = ' + str(instance_id) if instance_id else ''}"
                )
                stats["completed_uploads"] = cursor.fetchone()[0] or 0

                cursor.execute(
                    f"SELECT COUNT(*) FROM active_uploads WHERE status = 'failed'{' AND instance_id = ' + str(instance_id) if instance_id else ''}"
                )
                stats["failed_uploads"] = cursor.fetchone()[0] or 0

                # Average speeds and progress
                cursor.execute(
                    f"SELECT AVG(download_speed), AVG(progress_percentage) FROM active_downloads WHERE status = 'downloading'{' AND instance_id = ' + str(instance_id) if instance_id else ''}"
                )
                result = cursor.fetchone()
                if result and result[0]:
                    stats["total_download_speed"] = float(result[0])
                if result and result[1]:
                    stats["average_download_progress"] = float(result[1])

                return stats

        except Exception as e:
            logger.error(f"Error calculating operation stats: {e}")
            return {}

    def cleanup_old_operations(self, max_age_hours: int = 24) -> int:
        """Clean up old completed/failed operations from database.

        Args:
            max_age_hours: Remove operations older than this many hours

        Returns:
            Number of records deleted
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Delete old downloads
                cursor.execute(
                    """
                    DELETE FROM active_downloads 
                    WHERE (status = 'completed' OR status = 'failed') 
                    AND updated_at < ?
                """,
                    (cutoff_time,),
                )
                downloads_deleted = cursor.rowcount

                # Delete old uploads
                cursor.execute(
                    """
                    DELETE FROM active_uploads 
                    WHERE (status = 'completed' OR status = 'failed') 
                    AND updated_at < ?
                """,
                    (cutoff_time,),
                )
                uploads_deleted = cursor.rowcount

                conn.commit()

                total_deleted = downloads_deleted + uploads_deleted
                logger.info(f"Cleaned up {total_deleted} old monitoring records")
                return total_deleted

        except Exception as e:
            logger.error(f"Error cleaning up old operations: {e}")
            return 0
