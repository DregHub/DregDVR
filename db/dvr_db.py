"""
Native DVRDB using aiosqlite for non-blocking database access.
Handles all core DVR configuration: instances, accounts, settings, tasks, uploaders, credentials, and playlists.
"""

import logging
import traceback
from utils.logging_utils import LogManager, LogLevels
from pathlib import Path
from typing import Optional, Dict, List, Any
from contextlib import asynccontextmanager
from db.common_db import DatabaseManager


logger = logging.getLogger(__name__)


class DVRDB(DatabaseManager):
    """
    Async database manager providing non-blocking SQLite access via aiosqlite.
    Manages instances, accounts, settings, tasks, uploaders, credentials, and playlists.
    """

    # Global singleton instance
    _global_instance = None

    def __init__(self, db_path: str = None):
        # Set database path
        if db_path is None:
            from utils.file_utils import FileManager

            db_dir = FileManager.get_dvr_runtime_dir()
            db_path = str(Path(db_dir) / "DVR_Main.db")

        super().__init__(db_path)
        self.is_fresh = False

    @classmethod
    async def get_global(cls):
        """Get or create the global DVRDB instance.

        This class method ensures only one database manager exists and is reused
        across all modules, preventing database lock conflicts.

        Returns:
            DVRDB: The global singleton database manager instance
        """
        if cls._global_instance is None:
            cls._global_instance = cls()
            await cls._global_instance.initialize_database()

        return cls._global_instance

    @classmethod
    def get_global_sync(cls):
        """Get the global database instance (without initialization).

        WARNING: Only use this after async initialization is complete.
        For normal use, await get_global() instead.

        Returns:
            DVRDB: The global singleton instance or None if not yet initialized
        """
        return cls._global_instance

    async def connect(self, db_path: str = None):
        """Initialize database connection (legacy method - use _get_connection instead)."""
        # Use provided path or fall back to instance path
        if db_path is not None:
            self.db_path = db_path

        return await self._get_connection()

    async def disconnect(self):
        """Properly close connection before event loop closes.

        Waits briefly for aiosqlite worker threads to finish before returning.
        """
        await self.close()

    @asynccontextmanager
    async def connection(self, db_path: str = None):
        """Context manager for safe connection lifecycle"""
        try:
            db = await self.connect(db_path)
            yield db
        finally:
            await self.disconnect()

    # _sanitize_identifier is now inherited from DatabaseManager

    @classmethod
    def get_playlist_download_table_name(cls, channel_name: str) -> str:
        """Get playlist download table name using channel name only."""
        channel_safe = cls._sanitize_identifier_static(channel_name)
        return f"playlist_download_{channel_safe}"

    @classmethod
    def get_playlist_upload_table_name(cls, channel_name: str) -> str:
        """Get playlist upload table name using channel name only."""
        channel_safe = cls._sanitize_identifier_static(channel_name)
        return f"playlist_upload_{channel_safe}"

    @staticmethod
    def _sanitize_identifier_static(value: str) -> str:
        """Static method to sanitize a string for use as a SQLite identifier."""
        if not isinstance(value, str):
            raise ValueError("Identifier must be a string")
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in value)
        # Remove leading underscores that might have been added from sanitization
        sanitized = sanitized.lstrip("_")
        return sanitized

    async def initialize_database(self):
        """Initialize database schema."""
        try:
            conn = await self._get_connection()

            # Create core tables
            await conn.executescript(
                """
            -- Instances table
            CREATE TABLE IF NOT EXISTS instances (
                channel_id TEXT NOT NULL,
                instance_name TEXT NOT NULL,
                channel_name TEXT,
                source_platform TEXT NOT NULL,
                dvr_data_in_other_instance BOOLEAN DEFAULT 0,
                dvr_data_other_instance_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id)
            );

            -- Accounts table (instance-scoped)
            CREATE TABLE IF NOT EXISTS accounts (
                instance_name TEXT NOT NULL,
                yt_source TEXT,
                live_downloadprefix TEXT,
                posted_downloadprefix TEXT,
                ia_itemid TEXT,
                ia_user_agent TEXT,
                ia_email TEXT,
                ia_password TEXT,
                github_token TEXT,
                github_repo_owner TEXT,
                github_repo_name TEXT,
                github_captions_path TEXT,
                rumble_email TEXT,
                rumble_password TEXT,
                rumble_primary_category TEXT,
                rumble_secondary_category TEXT,
                bitchute_email TEXT,
                bitchute_password TEXT,
                odysee_email TEXT,
                odysee_password TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Index table (instance-scoped)
            CREATE TABLE IF NOT EXISTS "index" (
                instance_name TEXT NOT NULL,
                live_index INTEGER NOT NULL,
                posted_index INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Global settings table
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT NOT NULL,
                download_timestamp_format TEXT DEFAULT '%(timestamp>%d-%m-%Y %I-%M%p)s',
                dlp_verbose_downloads BOOLEAN DEFAULT 1,
                dlp_keep_fragments_downloads BOOLEAN DEFAULT 0,
                dlp_max_download_retries INTEGER DEFAULT 10,
                dlp_max_fragment_retries INTEGER DEFAULT 10,
                dlp_js_runtime TEXT DEFAULT 'deno',
                dlp_truncate_title_after_x_chars INTEGER DEFAULT 60,
                dlp_subtitle_use_srtfix BOOLEAN DEFAULT 1,
                dlp_getinfo_timeout_seconds INTEGER DEFAULT 800,
                dlp_stall_timeout_seconds INTEGER DEFAULT 800,
                dlp_buffer_first_attempt_errors BOOLEAN DEFAULT 1,
                session_video_recording BOOLEAN DEFAULT 0,
                session_error_html_dump BOOLEAN DEFAULT 0,
                video_download_max_threads INTEGER DEFAULT 2,
                caption_download_max_threads INTEGER DEFAULT 2,
                caption_upload_max_threads INTEGER DEFAULT 2,
                video_upload_max_threads INTEGER DEFAULT 2,
                playlist_processing_max_threads INTEGER DEFAULT 6,
                yt_cookies_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (key)
            );

            -- Instance settings table
            CREATE TABLE IF NOT EXISTS instance_settings (
                instance_name TEXT NOT NULL,
                upload_visibility TEXT DEFAULT 'Public',
                upload_category TEXT DEFAULT '22',
                yt_client_secret_content TEXT,
                yt_oauth2_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Tasks table (instance-scoped)
            CREATE TABLE IF NOT EXISTS tasks (
                instance_name TEXT NOT NULL,
                dependency_package_update BOOLEAN DEFAULT 1,
                livestream_download BOOLEAN DEFAULT 1,
                livestream_recovery_download BOOLEAN DEFAULT 1,
                comments_download BOOLEAN DEFAULT 0,
                comments_republish BOOLEAN DEFAULT 0,
                captions_download BOOLEAN DEFAULT 0,
                captions_upload BOOLEAN DEFAULT 0,
                posted_videos_download BOOLEAN DEFAULT 0,
                posted_notices_download BOOLEAN DEFAULT 0,
                livestream_upload BOOLEAN DEFAULT 0,
                posted_videos_upload BOOLEAN DEFAULT 0,
                update_playlist BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Uploaders table (instance-scoped)
            CREATE TABLE IF NOT EXISTS uploaders (
                instance_name TEXT NOT NULL,
                upload_to_youtube BOOLEAN DEFAULT 0,
                upload_to_ia BOOLEAN DEFAULT 0,
                upload_to_rumble BOOLEAN DEFAULT 0,
                upload_to_bitchute BOOLEAN DEFAULT 0,
                upload_to_odysee BOOLEAN DEFAULT 0,
                upload_to_github BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Metadata table (instance + platform)
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                content_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT,
                description TEXT,
                channel_id TEXT,
                channel_name TEXT,
                upload_date TIMESTAMP,
                duration INTEGER,
                view_count INTEGER,
                like_count INTEGER,
                comment_count INTEGER,
                thumbnail_url TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, content_id, platform)
            );

            -- Credentials table
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                credential_type TEXT NOT NULL,
                value TEXT NOT NULL,
                is_encrypted BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, platform, credential_type)
            );

            -- Active downloads table
            CREATE TABLE IF NOT EXISTS active_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
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
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, filename)
            );

            -- Active uploads table
            CREATE TABLE IF NOT EXISTS active_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                video_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                progress_percentage REAL DEFAULT 0.0,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_time TIMESTAMP,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, video_id, platform)
            );

            -- Captions table
            CREATE TABLE IF NOT EXISTS captions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                video_id TEXT NOT NULL,
                language TEXT NOT NULL,
                caption_data TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, video_id, language)
            );

            -- Channel metadata table
            CREATE TABLE IF NOT EXISTS channel_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_url TEXT,
                description TEXT,
                subscriber_count INTEGER,
                view_count INTEGER,
                video_count INTEGER,
                thumbnail_url TEXT,
                banner_url TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(channel_id)
            );

            -- Comments table
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                video_id TEXT NOT NULL,
                comment_data TEXT,
                author TEXT,
                likes INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, video_id)
            );

            -- Config status table
            CREATE TABLE IF NOT EXISTS config_status (
                key TEXT NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (key)
            );
 
            -- Metadata cache table
            CREATE TABLE IF NOT EXISTS metadata_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                content_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                cache_value TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, content_id, platform, cache_key)
            );

            -- Playlists table
            CREATE TABLE IF NOT EXISTS playlists (
                channel_id TEXT NOT NULL,
                instance_name TEXT NOT NULL,
                download_playlist_name TEXT,
                upload_playlist_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Posts table
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                title TEXT NOT NULL,
                html_content TEXT,
                text_content TEXT,
                metadata TEXT,
                comment_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Sessions table
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                session_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                session_data TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(session_id)
            );

            -- Thumbnails table
            CREATE TABLE IF NOT EXISTS thumbnails (
                instance_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instance_name),
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION
            );

            -- Tokens table
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                token_type TEXT NOT NULL,
                token_value TEXT NOT NULL,
                expires_at TIMESTAMP,
                refresh_token TEXT,
                is_valid BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, platform, token_type)
            );

            -- Upload metadata table
            CREATE TABLE IF NOT EXISTS upload_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                description TEXT,
                tags TEXT,
                thumbnail_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instance_name) REFERENCES instances(channel_id) ON DELETE CASCADE ON UPDATE NO ACTION,
                UNIQUE(instance_name, platform)
            );
            """
            )
            await conn.commit()
            self.is_fresh = True

        except Exception as e:
            LogManager.log_core(
                f"[DB_MAIN_INIT_ERROR] Failed to initialize database: {e} {traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    async def is_configured(self) -> bool:
        """Check if database is configured."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT value FROM config_status WHERE key = 'configured'"
            )
            row = await cursor.fetchone()
            await cursor.close()
            return row and row[0] == "true"
        except Exception:
            return False

    async def set_configured(self, configured: bool = True):
        """Set configured flag."""
        try:
            conn = await self._get_connection()
            await conn.execute(
                "INSERT OR REPLACE INTO config_status (key, value) VALUES (?, ?)",
                ("configured", "true" if configured else "false"),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to set configured flag: {e}")
            raise

    # ===== Instance operations =====
    async def add_instance(
        self,
        channel_id: str,
        instance_name: str,
        channel_name: str = None,
        source_platform: str = None,
        dvr_data_in_other_instance: bool = False,
        dvr_data_other_instance_name: str = None,
    ) -> str:
        """Add a new instance."""
        try:
            conn = await self._get_connection()
            await conn.execute(
                """INSERT INTO instances
                   (channel_id, instance_name, channel_name, source_platform,
                    dvr_data_in_other_instance, dvr_data_other_instance_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    channel_id,
                    instance_name,
                    channel_name,
                    source_platform,
                    1 if dvr_data_in_other_instance else 0,
                    dvr_data_other_instance_name,
                ),
            )
            await conn.commit()
            return channel_id
        except Exception as e:
            logger.error(f"Failed to add instance {channel_id}: {e}")
            raise

    async def get_all_instances(self) -> List[Dict]:
        """Get all instances."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute("SELECT * FROM instances")
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to get instances: {e}")
            return []

    async def get_instance(self, channel_id: str) -> Optional[Dict]:
        """Get instance by channel_id."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM instances WHERE channel_id = ?",
                (channel_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get instance {channel_id}: {e}")
            return None

    async def get_instance_by_name(self, instance_name: str) -> Optional[Dict]:
        """Get instance by instance_name."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM instances WHERE instance_name = ?",
                (instance_name,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get instance by name {instance_name}: {e}")
            return None

    async def update_instance(self, channel_id: str, **kwargs):
        """Update instance."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "instance_name",
                "channel_name",
                "source_platform",
                "dvr_data_in_other_instance",
                "dvr_data_other_instance_name",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [channel_id]

            await conn.execute(
                f"UPDATE instances SET {set_clause} WHERE channel_id = ?",
                values,
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update instance {channel_id}: {e}")
            raise

    async def delete_instance(self, channel_id: str):
        """Delete instance."""
        try:
            conn = await self._get_connection()
            await conn.execute(
                "DELETE FROM instances WHERE channel_id = ?",
                (channel_id,),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to delete instance {channel_id}: {e}")
            raise

    # ===== Account operations =====
    async def get_account(self, instance_name: str) -> Optional[Dict]:
        """Get account for instance."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM accounts WHERE instance_name = ?",
                (instance_name,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get account for {instance_name}: {e}")
            return None

    async def update_account(self, instance_name: str, **kwargs):
        """Update account."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "yt_source",
                "live_downloadprefix",
                "posted_downloadprefix",
                "ia_itemid",
                "ia_user_agent",
                "ia_email",
                "ia_password",
                "github_token",
                "github_repo_owner",
                "github_repo_name",
                "github_captions_path",
                "rumble_email",
                "rumble_password",
                "rumble_primary_category",
                "rumble_secondary_category",
                "bitchute_email",
                "bitchute_password",
                "odysee_email",
                "odysee_password",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            # Get existing account or create new
            existing = await self.get_account(instance_name)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [instance_name]
                await conn.execute(
                    f"UPDATE accounts SET {set_clause} WHERE instance_name = ?",
                    values,
                )
            else:
                # Create new account entry
                columns = ["instance_name"] + list(updates.keys())
                placeholders = ["?"] * len(columns)
                values = [instance_name] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO accounts ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update account for {instance_name}: {e}")
            raise

    # ===== Settings operations =====
    async def get_instance_settings(self, instance_name: str) -> Optional[Dict]:
        """Get instance-scoped settings."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM instance_settings WHERE instance_name = ?",
                (instance_name,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"Failed to get instance settings for {instance_name}: {e}")
            return {}

    async def get_global_settings(self) -> Optional[Dict]:
        """Get global settings."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM global_settings WHERE key = 'default'"
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"Failed to get global settings: {e}")
            return {}

    async def get_settings(self, instance_name: str) -> Optional[Dict]:
        """Get merged settings (global + instance-specific)."""
        global_settings = await self.get_global_settings()
        instance_settings = await self.get_instance_settings(instance_name)
        merged = {**global_settings, **instance_settings}
        return merged

    async def update_instance_settings(self, instance_name: str, **kwargs):
        """Update instance settings."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "upload_visibility",
                "upload_category",
                "yt_client_secret_content",
                "yt_oauth2_content",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            existing = await self.get_instance_settings(instance_name)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [instance_name]
                await conn.execute(
                    f"UPDATE instance_settings SET {set_clause} WHERE instance_name = ?",
                    values,
                )
            else:
                # Create new instance settings entry
                columns = ["instance_name"] + list(updates.keys())
                placeholders = ["?"] * len(columns)
                values = [instance_name] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO instance_settings ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update instance settings: {e}")
            raise

    async def update_global_settings(self, **kwargs):
        """Update global settings."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "download_timestamp_format",
                "dlp_verbose_downloads",
                "dlp_keep_fragments_downloads",
                "dlp_max_download_retries",
                "dlp_max_fragment_retries",
                "dlp_js_runtime",
                "dlp_truncate_title_after_x_chars",
                "dlp_subtitle_use_srtfix",
                "dlp_getinfo_timeout_seconds",
                "dlp_stall_timeout_seconds",
                "dlp_buffer_first_attempt_errors",
                "session_video_recording",
                "session_error_html_dump",
                "video_download_max_threads",
                "caption_download_max_threads",
                "caption_upload_max_threads",
                "video_upload_max_threads",
                "playlist_processing_max_threads",
                "yt_cookies_content",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            existing = await self.get_global_settings()
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + ["default"]
                await conn.execute(
                    f"UPDATE global_settings SET {set_clause} WHERE key = ?",
                    values,
                )
            else:
                # Create new global settings entry
                columns = ["key"] + list(updates.keys())
                placeholders = ["?"] * len(columns)
                values = ["default"] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO global_settings ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update global settings: {e}")
            raise

    async def update_settings(self, instance_name: str, **kwargs):
        """Update settings (convenience method)."""
        await self.update_instance_settings(instance_name, **kwargs)

    # ===== YouTube credentials =====
    async def get_yt_cookies_content(self) -> Optional[str]:
        """Get YouTube cookies from global settings."""
        try:
            settings = await self.get_global_settings()
            return settings.get("yt_cookies_content")
        except Exception as e:
            logger.error(f"Failed to get YouTube cookies: {e}")
            return None

    async def set_yt_cookies_content(self, content: str):
        """Set YouTube cookies in global settings."""
        try:
            await self.update_global_settings(yt_cookies_content=content)
        except Exception as e:
            logger.error(f"Failed to set YouTube cookies: {e}")
            raise

    async def get_yt_client_secret_content(self, instance_name: str) -> Optional[str]:
        """Get YouTube client secret for instance from instance settings."""
        try:
            settings = await self.get_instance_settings(instance_name)
            return settings.get("yt_client_secret_content")
        except Exception as e:
            logger.error(f"Failed to get YT client secret for {instance_name}: {e}")
            return None

    async def set_yt_client_secret_content(self, instance_name: str, content: str):
        """Set YouTube client secret for instance in instance settings."""
        try:
            await self.update_instance_settings(
                instance_name, yt_client_secret_content=content
            )
        except Exception as e:
            logger.error(f"Failed to set YT client secret for {instance_name}: {e}")
            raise

    async def get_yt_oauth2_content(self, instance_name: str) -> Optional[str]:
        """Get YouTube OAuth2 token for instance from instance settings."""
        try:
            settings = await self.get_instance_settings(instance_name)
            return settings.get("yt_oauth2_content")
        except Exception as e:
            logger.error(f"Failed to get YT OAuth2 for {instance_name}: {e}")
            return None

    async def set_yt_oauth2_content(self, instance_name: str, content: str):
        """Set YouTube OAuth2 token for instance in instance settings."""
        try:
            await self.update_instance_settings(
                instance_name, yt_oauth2_content=content
            )
        except Exception as e:
            logger.error(f"Failed to set YT OAuth2 for {instance_name}: {e}")
            raise

    # ===== Tasks operations =====
    async def get_tasks(self, instance_name: str) -> Optional[Dict]:
        """Get tasks for instance."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM tasks WHERE instance_name = ?",
                (instance_name,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"Failed to get tasks for {instance_name}: {e}")
            return {}

    async def update_tasks(self, instance_name: str, **kwargs):
        """Update tasks."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "dependency_package_update",
                "livestream_download",
                "livestream_recovery_download",
                "comments_download",
                "comments_republish",
                "captions_download",
                "captions_upload",
                "posted_videos_download",
                "posted_notices_download",
                "livestream_upload",
                "posted_videos_upload",
                "update_playlist",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            existing = await self.get_tasks(instance_name)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [instance_name]
                await conn.execute(
                    f"UPDATE tasks SET {set_clause} WHERE instance_name = ?",
                    values,
                )
            else:
                # Create new tasks entry
                columns = ["instance_name"] + list(updates.keys())
                placeholders = ["?"] * len(columns)
                values = [instance_name] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO tasks ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update tasks for {instance_name}: {e}")
            raise

    # ===== Uploaders operations =====
    async def get_uploaders(self, instance_name: str) -> Optional[Dict]:
        """Get uploaders for instance."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM uploaders WHERE instance_name = ?",
                (instance_name,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"Failed to get uploaders for {instance_name}: {e}")
            return {}

    async def update_uploaders(self, instance_name: str, **kwargs):
        """Update uploaders."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "upload_to_youtube",
                "upload_to_ia",
                "upload_to_rumble",
                "upload_to_bitchute",
                "upload_to_odysee",
                "upload_to_github",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            existing = await self.get_uploaders(instance_name)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [instance_name]
                await conn.execute(
                    f"UPDATE uploaders SET {set_clause} WHERE instance_name = ?",
                    values,
                )
            else:
                # Create new uploaders entry
                columns = ["instance_name"] + list(updates.keys())
                placeholders = ["?"] * len(columns)
                values = [instance_name] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO uploaders ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update uploaders for {instance_name}: {e}")
            raise

    # ===== Metadata operations =====
    async def get_metadata(
        self, instance_name: str, content_id: str, platform: str
    ) -> Optional[Dict]:
        """Get metadata for instance + content_id + platform."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM metadata WHERE instance_name = ? AND content_id = ? AND platform = ?",
                (instance_name, content_id, platform),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(
                f"Failed to get metadata for {instance_name}/{content_id}/{platform}: {e}"
            )
            return {}

    async def update_metadata(
        self, instance_name: str, content_id: str, platform: str, **kwargs
    ):
        """Update metadata."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "content_type",
                "title",
                "description",
                "channel_id",
                "channel_name",
                "upload_date",
                "duration",
                "view_count",
                "like_count",
                "comment_count",
                "thumbnail_url",
                "metadata_json",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            existing = await self.get_metadata(instance_name, content_id, platform)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [instance_name, content_id, platform]
                await conn.execute(
                    f"UPDATE metadata SET {set_clause} WHERE instance_name = ? AND content_id = ? AND platform = ?",
                    values,
                )
            else:
                # Create new metadata entry
                columns = ["instance_name", "content_id", "platform"] + list(
                    updates.keys()
                )
                placeholders = ["?"] * len(columns)
                values = [instance_name, content_id, platform] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO metadata ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(
                f"Failed to update metadata for {instance_name}/{content_id}/{platform}: {e}"
            )
            raise

    # ===== Credentials operations =====
    async def get_credential(
        self, instance_name: str, platform: str, credential_type: str
    ) -> Optional[Dict]:
        """Get credential."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """SELECT * FROM credentials 
                   WHERE instance_name = ? AND platform = ? AND credential_type = ?""",
                (instance_name, platform, credential_type),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get credential: {e}")
            return None

    async def add_credential(
        self,
        instance_name: str,
        platform: str,
        credential_type: str,
        value: str,
        is_encrypted: bool = False,
    ):
        """Add or update credential."""
        try:
            conn = await self._get_connection()
            await conn.execute(
                """INSERT OR REPLACE INTO credentials
                   (instance_name, platform, credential_type, value, is_encrypted)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    instance_name,
                    platform,
                    credential_type,
                    value,
                    1 if is_encrypted else 0,
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to add credential: {e}")
            raise

    async def get_playlist_entry(
        self, instance_name: str, channel_source: str, url: str
    ) -> Optional[Dict]:
        """Get playlist entry from download table."""
        try:
            conn = await self._get_connection()
            # Check if channel_source is already a full table name
            if channel_source.startswith("playlist_download_"):
                table_name = channel_source
            else:
                table_name = self.get_playlist_download_table_name(channel_source)

            cursor = await conn.execute(
                f"SELECT * FROM {table_name} WHERE instance_name = ? AND url = ?",
                (instance_name, url),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get playlist entry: {e}")
            return None

    async def get_playlist_upload_entry(
        self, instance_name: str, channel_source: str, url: str
    ) -> Optional[Dict]:
        """Get playlist entry from upload table."""
        try:
            conn = await self._get_connection()
            # Check if channel_source is already a full table name
            if channel_source.startswith("playlist_upload_"):
                table_name = channel_source
            else:
                table_name = self.get_playlist_upload_table_name(channel_source)

            cursor = await conn.execute(
                f"SELECT * FROM {table_name} WHERE instance_name = ? AND url = ?",
                (instance_name, url),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get playlist upload entry: {e}")
            return None

    async def add_or_update_playlist_entry(
        self,
        instance_name: str,
        channel_source: str,
        url: str,
        **kwargs,
    ):
        """Add or update playlist entry across download and upload tables."""
        try:
            conn = await self._get_connection()
            # Check if channel_source is already a full table name
            if channel_source.startswith("playlist_download_"):
                download_table_name = channel_source
            else:
                download_table_name = self.get_playlist_download_table_name(channel_source)

            if channel_source.startswith("playlist_upload_"):
                upload_table_name = channel_source
            else:
                upload_table_name = self.get_playlist_upload_table_name(channel_source)

            # Define fields for each table
            download_fields = {
                "instance_name",
                "unique_id",
                "file_path",
                "title",
                "datetime",
                "isshort",
                "live_status",
                "was_live",
                "live_download_stage",
                "captions_download_started",
                "recovery_download_started",
                "has_captions",
                "downloaded_video",
                "downloaded_caption",
                "video_download_attempts",
                "caption_download_attempts",
            }

            upload_fields = {
                "instance_name",
                "unique_id",
                "uploaded_video_all_hosts",
                "uploaded_video_ia",
                "uploaded_video_yt",
                "uploaded_video_rm",
                "uploaded_video_bc",
                "uploaded_video_od",
                "uploaded_caption",
                "upload_error_bc",
                "upload_error_ia",
                "upload_error_yt",
                "upload_error_rm",
                "upload_error_od",
            }

            # Split updates into download and upload
            download_updates = {k: v for k, v in kwargs.items() if k in download_fields}
            upload_updates = {k: v for k, v in kwargs.items() if k in upload_fields}

            # Handle download table
            existing_download = await self.get_playlist_entry(
                instance_name, channel_source, url
            )
            if download_updates:
                # Ensure instance_name and unique_id are included
                download_updates["instance_name"] = instance_name
                if "unique_id" not in download_updates:
                    download_updates["unique_id"] = url

                if existing_download:
                    set_clause = ", ".join(f"{k} = ?" for k in download_updates.keys())
                    values = list(download_updates.values()) + [url]
                    await conn.execute(
                        f"UPDATE {download_table_name} SET {set_clause} WHERE url = ?",
                        values,
                    )
                else:
                    # Create new entry
                    columns = ["url"] + list(download_updates.keys())
                    placeholders = ["?"] * len(columns)
                    values = [url] + list(download_updates.values())
                    await conn.execute(
                        f"INSERT INTO {download_table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                        values,
                    )

            # Handle upload table
            existing_upload = await self.get_playlist_upload_entry(
                instance_name, channel_source, url
            )
            if upload_updates:
                # Ensure instance_name and unique_id are included
                upload_updates["instance_name"] = instance_name
                if "unique_id" not in upload_updates:
                    upload_updates["unique_id"] = url

                if existing_upload:
                    set_clause = ", ".join(f"{k} = ?" for k in upload_updates.keys())
                    values = list(upload_updates.values()) + [url]
                    await conn.execute(
                        f"UPDATE {upload_table_name} SET {set_clause} WHERE url = ?",
                        values,
                    )
                else:
                    # Create new entry
                    columns = ["url"] + list(upload_updates.keys())
                    placeholders = ["?"] * len(columns)
                    values = [url] + list(upload_updates.values())
                    await conn.execute(
                        f"INSERT INTO {upload_table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                        values,
                    )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to add/update playlist entry: {e}")
            raise

    async def get_all_instance_playlist_entries(self, instance_name: str) -> List[Dict]:
        """Get all playlist entries for an instance across all channels (download table only)."""
        try:
            conn = await self._get_connection()

            # Find all download tables for this instance
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                (f"playlist_download_%",),
            )
            tables = await cursor.fetchall()
            await cursor.close()

            all_entries = []
            for table_row in tables:
                table_name = table_row[0]
                cursor = await conn.execute(
                    f"SELECT * FROM {table_name} WHERE instance_name = ?",
                    (instance_name,),
                )
                rows = await cursor.fetchall()
                await cursor.close()
                all_entries.extend([dict(row) for row in rows] if rows else [])

            return all_entries
        except Exception as e:
            logger.error(f"Failed to get all playlist entries: {e}")
            return []

    async def get_channel_playlist_entries_where(
        self,
        instance_name: str,
        channel_source: str,
        live_status: str = None,
        live_download_stage: str = None,
        downloaded_video: int = None,
    ) -> List[Dict]:
        """Get playlist entries for a channel with optional filters (download table only).

        Args:
            instance_name: Instance name to filter by
            channel_source: Channel source to filter by (can be either channel name or full table name)
            live_status: Optional filter for live_status (e.g., 'is_live', 'was_live')
            live_download_stage: Optional filter for live_download_stage (e.g., 'Started', 'Completed')
            downloaded_video: Optional filter for downloaded_video (0 or 1)

        Returns:
            List of matching playlist entries
        """
        try:
            conn = await self._get_connection()
            # Check if channel_source is already a full table name
            if channel_source.startswith("playlist_download_"):
                table_name = channel_source
            else:
                table_name = self.get_playlist_download_table_name(channel_source)

            # Build WHERE clause dynamically
            conditions = ["instance_name = ?"]
            params = [instance_name]

            if live_status is not None:
                conditions.append("live_status = ?")
                params.append(live_status)

            if live_download_stage is not None:
                conditions.append("live_download_stage = ?")
                params.append(live_download_stage)

            if downloaded_video is not None:
                conditions.append("downloaded_video = ?")
                params.append(downloaded_video)

            where_clause = " AND ".join(conditions)

            cursor = await conn.execute(
                f"SELECT * FROM {table_name} WHERE {where_clause}",
                params,
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to get channel playlist entries with filters: {e}")
            return []

    # ===== Channel Playlist Table Operations =====

    def get_playlist_table_name(self, instance_name: str, channel_source: str) -> str:
        """Get playlist download table name for a channel."""
        return self.get_playlist_download_table_name(channel_source)

    async def ensure_playlist_table_exists(
        self, instance_name: str, channel_source: str
    ):
        """Ensure separate download and upload playlist tables exist for a channel."""
        # Check if channel_source is already a full table name
        if channel_source.startswith("playlist_download_"):
            download_table_name = channel_source
        else:
            download_table_name = self.get_playlist_download_table_name(channel_source)

        if channel_source.startswith("playlist_upload_"):
            upload_table_name = channel_source
        else:
            upload_table_name = self.get_playlist_upload_table_name(channel_source)

        conn = await self._get_connection()

        try:
            # Create download table
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {download_table_name} (
                    instance_name TEXT NOT NULL,
                    unique_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    file_path TEXT,
                    title TEXT,
                    datetime TEXT,
                    is_short INTEGER DEFAULT 0,
                    live_status TEXT,
                    was_live INTEGER DEFAULT 0,
                    live_download_stage TEXT,
                    captions_download_started INTEGER DEFAULT 0,
                    recovery_download_started INTEGER DEFAULT 0,
                    has_captions INTEGER DEFAULT 0,
                    downloaded_video INTEGER DEFAULT 0,
                    downloaded_caption INTEGER DEFAULT 0,
                    video_download_attempts INTEGER DEFAULT 0,
                    caption_download_attempts INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (instance_name, unique_id)
                )
                """
            )

            # Create indexes for download table
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{download_table_name}_url ON {download_table_name}(url)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{download_table_name}_downloaded_video ON {download_table_name}(downloaded_video)
                """
            )

            # Create upload table
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {upload_table_name} (
                    instance_name TEXT NOT NULL,
                    unique_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    uploaded_video_all_hosts INTEGER DEFAULT 0,
                    uploaded_video_ia INTEGER DEFAULT 0,
                    uploaded_video_yt INTEGER DEFAULT 0,
                    uploaded_video_rm INTEGER DEFAULT 0,
                    uploaded_video_bc INTEGER DEFAULT 0,
                    uploaded_video_od INTEGER DEFAULT 0,
                    uploaded_caption INTEGER DEFAULT 0,
                    upload_error_bc TEXT,
                    upload_error_ia TEXT,
                    upload_error_yt TEXT,
                    upload_error_rm TEXT,
                    upload_error_od TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (instance_name, unique_id)
                )
                """
            )

            # Create indexes for upload table
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{upload_table_name}_url ON {upload_table_name}(url)
                """
            )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to create playlist tables for {channel_source}: {e}")
            raise

    async def get_channel_playlist_entries(
        self, instance_name: str, channel_source: str
    ) -> List[Dict]:
        """Get all playlist entries for a channel (download table only)."""
        # Check if channel_source is already a full table name
        if channel_source.startswith("playlist_download_"):
            table_name = channel_source
        else:
            table_name = self.get_playlist_table_name(instance_name, channel_source)

        conn = await self._get_connection()

        try:
            cursor = await conn.execute(
                f"SELECT * FROM {table_name} WHERE instance_name = ?", (instance_name,)
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to get channel playlist entries: {e}")
            return []

    async def add_or_update_channel_playlist_entry(
        self, instance_name: str, channel_source: str, entry: Dict
    ) -> bool:
        """Add or update a playlist entry (download table only)."""
        # Check if channel_source is already a full table name
        if channel_source.startswith("playlist_download_"):
            table_name = channel_source
        else:
            table_name = self.get_playlist_table_name(instance_name, channel_source)

        conn = await self._get_connection()

        try:
            # Ensure instance_name and unique_id are in the entry
            entry["instance_name"] = instance_name
            if "unique_id" not in entry:
                entry["unique_id"] = entry.get("url")

            # Check if entry exists by unique_id
            cursor = await conn.execute(
                f"SELECT url FROM {table_name} WHERE instance_name = ? AND unique_id = ?",
                (instance_name, entry.get("unique_id")),
            )
            existing = await cursor.fetchone()
            await cursor.close()

            if existing:
                # Update existing entry
                set_clause = ", ".join(
                    [
                        f"{k} = ?"
                        for k in entry.keys()
                        if k not in ["url", "instance_name", "unique_id"]
                    ]
                )
                values = [
                    v
                    for k, v in entry.items()
                    if k not in ["url", "instance_name", "unique_id"]
                ] + [instance_name, entry.get("unique_id")]
                await conn.execute(
                    f"UPDATE {table_name} SET {set_clause} WHERE instance_name = ? AND unique_id = ?",
                    values,
                )
            else:
                # Insert new entry
                columns = list(entry.keys())
                placeholders = ["?"] * len(columns)
                await conn.execute(
                    f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    list(entry.values()),
                )

            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add/update playlist entry: {e}")
            return False

    async def get_channel_playlist_entry_by_url(
        self, instance_name: str, channel_source: str, url: str
    ) -> Optional[Dict]:
        """Get a playlist entry by URL (download table only)."""
        # Check if channel_source is already a full table name
        if channel_source.startswith("playlist_download_"):
            table_name = channel_source
        else:
            table_name = self.get_playlist_table_name(instance_name, channel_source)

        conn = await self._get_connection()

        try:
            cursor = await conn.execute(
                f"SELECT * FROM {table_name} WHERE instance_name = ? AND url = ?",
                (instance_name, url),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get playlist entry by URL: {e}")
            return None

    async def update_channel_playlist_entry_field(
        self, instance_name: str, channel_source: str, url: str, field: str, value: Any
    ) -> bool:
        """Update a specific field in a playlist entry (download table only)."""
        # Check if channel_source is already a full table name
        if channel_source.startswith("playlist_download_"):
            table_name = channel_source
        else:
            table_name = self.get_playlist_table_name(instance_name, channel_source)

        conn = await self._get_connection()

        try:
            cursor = await conn.execute(
                f"UPDATE {table_name} SET {field} = ? WHERE instance_name = ? AND url = ?",
                (value, instance_name, url),
            )
            await conn.commit()
            await cursor.close()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update playlist entry field: {e}")
            return False

    # ===== Playlists Table Operations =====

    async def get_playlists(self, channel_id: str, instance_name: str) -> Optional[Dict]:
        """Get playlists for an instance."""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                "SELECT * FROM playlists WHERE channel_id = ? AND instance_name = ?",
                (channel_id, instance_name),
            )
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"Failed to get playlists for {instance_name}: {e}")
            return {}

    async def update_playlists(self, channel_id: str, instance_name: str, **kwargs):
        """Update playlists for an instance."""
        try:
            conn = await self._get_connection()
            allowed_fields = {
                "download_playlist_name",
                "upload_playlist_name",
            }
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
            if not updates:
                return

            existing = await self.get_playlists(channel_id, instance_name)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [channel_id, instance_name]
                await conn.execute(
                    f"UPDATE playlists SET {set_clause} WHERE channel_id = ? AND instance_name = ?",
                    values,
                )
            else:
                # Create new playlists entry
                columns = ["channel_id", "instance_name"] + list(updates.keys())
                placeholders = ["?"] * len(columns)
                values = [channel_id, instance_name] + list(updates.values())
                await conn.execute(
                    f"INSERT INTO playlists ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                    values,
                )

            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update playlists for {instance_name}: {e}")
            raise

    async def create_initial_index_entry(self, instance_name: str, live_index: int = 1, posted_index: int = 1):
        """Create initial index entry for a new instance.

        Args:
            instance_name: The instance name to create the index entry for
            live_index: Initial live index value (default: 1)
            posted_index: Initial posted index value (default: 1)
        """
        try:
            conn = await self._get_connection()
            await conn.execute(
                """INSERT OR REPLACE INTO "index"
                   (instance_name, live_index, posted_index)
                   VALUES (?, ?, ?)""",
                (instance_name, live_index, posted_index),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to create initial index entry for {instance_name}: {e}")
            raise

    async def get_current_download_playlist(self, instance_name: str) -> Optional[str]:
        """Get the current download playlist name for an instance.

        Args:
            instance_name: The instance name to get the download playlist for

        Returns:
            The download_playlist_name or None if not found
        """
        try:
            instance = await self.get_instance_by_name(instance_name)
            if not instance:
                return None

            channel_id = instance.get("channel_id")
            if not channel_id:
                return None

            playlists = await self.get_playlists(channel_id, instance_name)
            return playlists.get("download_playlist_name")
        except Exception as e:
            logger.error(f"Failed to get current download playlist for {instance_name}: {e}")
            return None

    async def get_current_upload_playlist(self, instance_name: str) -> Optional[str]:
        """Get the current upload playlist name for an instance.

        Args:
            instance_name: The instance name to get the upload playlist for

        Returns:
            The upload_playlist_name or None if not found
        """
        try:
            instance = await self.get_instance_by_name(instance_name)
            if not instance:
                return None

            channel_id = instance.get("channel_id")
            if not channel_id:
                return None

            playlists = await self.get_playlists(channel_id, instance_name)
            return playlists.get("upload_playlist_name")
        except Exception as e:
            logger.error(f"Failed to get current upload playlist for {instance_name}: {e}")
            return None
