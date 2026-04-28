"""
UI Database Helpers
Provides query functions for the Streamlit UI layer.
Handles all database access for instances, tasks, playlists, captions, comments, posts, and logs.
"""

import sqlite3
import logging
import asyncio
from typing import Optional, Dict, List, Any
from db.dvr_db import DVRDB
from db.log_db import LogDB

logger = logging.getLogger(__name__)


class UIDBHelpers:
    """Helper class providing database queries for UI components."""

    _db = None
    _log_db = None
    _initialized = False

    @classmethod
    def _run_async(cls, coro):
        """Helper to run async code from sync context."""
        try:
            # Try to get the running loop (Streamlit might have one)
            loop = asyncio.get_running_loop()
            # If we're in an async context, we can't use run_until_complete
            # Use run_coroutine_threadsafe to run the coroutine in the existing loop
            import concurrent.futures

            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        except RuntimeError:
            # No running loop, create a new one and register it
            async def run_with_registration():
                from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

                loop = asyncio.get_running_loop()
                try:
                    AsyncioLifecycleManager.register_loop(
                        loop, loop_name="ui_db_helpers"
                    )
                except Exception as e:
                    logger.warning(f"Failed to register UI event loop: {e}")
                return await coro

            return asyncio.run(run_with_registration())

    @classmethod
    def ensure_initialized(cls):
        """Ensure database is initialized before use."""
        if not cls._initialized:
            cls._db = cls._run_async(DVRDB.get_global())
            cls._log_db = cls._run_async(LogDB.get_global())
            cls._initialized = True

    @classmethod
    def get_db(cls):
        """Get database manager instance, initializing if needed."""
        cls.ensure_initialized()
        return cls._db

    @classmethod
    def _get_instance_id(cls, channel_id: str) -> Optional[int]:
        """Get instance ID from channel_id.

        Args:
            channel_id: Channel ID (PRIMARY KEY)

        Returns:
            Instance ID or None if not found
        """
        try:
            db = cls.get_db()
            instance = cls._run_async(db.get_instance(channel_id))
            if instance and "id" in dict(instance):
                return dict(instance)["id"]
            return None
        except Exception as e:
            logger.error(f"Error getting instance ID for {channel_id}: {e}")
            return None

    # ==================== Instance Operations ====================

    @classmethod
    def get_all_instances(cls) -> List[Dict[str, Any]]:
        """Get all instances with their basic info.

        Returns:
            List of instance dicts with channel_id, instance_name, channel_name (if set), created_at
        """
        try:
            db = cls.get_db()
            instances = cls._run_async(db.get_all_instances())
            result = []
            for inst in instances:
                inst_dict = dict(inst)
                # Get account info to fetch channel_name (yt_source)
                account = cls._run_async(db.get_account(inst_dict["instance_name"]))
                if account:
                    inst_dict["channel_name"] = account.get("yt_source")
                else:
                    inst_dict["channel_name"] = None
                result.append(inst_dict)
            return result
        except Exception as e:
            logger.error(f"Error getting all instances: {e}")
            return []

    @classmethod
    def get_instance_by_name(cls, instance_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific instance with full details.

        Args:
            instance_name: Instance name

        Returns:
            Instance dict with all details or None
        """
        try:
            db = cls.get_db()
            instance = cls._run_async(db.get_instance_by_name(instance_name))
            if instance:
                instance_dict = dict(instance)
                # Get account info to fetch channel_name
                account = cls._run_async(db.get_account(instance_name))
                if account:
                    instance_dict["channel_name"] = account.get("yt_source")
                else:
                    instance_dict["channel_name"] = None

                # Get uploaders configuration
                uploaders = cls._run_async(db.get_uploaders(instance_name))
                if uploaders:
                    instance_dict["uploaders"] = uploaders

                return instance_dict
            return None
        except Exception as e:
            logger.error(f"Error getting instance {instance_name}: {e}")
            return None

    # ==================== Task Operations ====================

    @classmethod
    def get_tasks_for_instance(cls, instance_name: str) -> Optional[Dict[str, Any]]:
        """Get task status for an instance.

        Args:
            instance_name: Instance name (PRIMARY KEY)

        Returns:
            Dict with all task statuses or None
        """
        try:
            db = cls.get_db()
            tasks = cls._run_async(db.get_tasks(instance_name))
            return tasks
        except Exception as e:
            logger.error(f"Error getting tasks for instance {instance_name}: {e}")
            return None

    @classmethod
    def update_instance_channel_name(
        cls, instance_name: str, channel_name: str
    ) -> bool:
        """Update instance channel name in accounts table.

        Args:
            instance_name: Instance name (PRIMARY KEY)
            channel_name: Channel name (e.g., '@channelname')

        Returns:
            True if successful, False otherwise
        """
        try:
            db = cls.get_db()
            cls._run_async(db.update_account(instance_name, yt_source=channel_name))
            return True
        except Exception as e:
            logger.error(
                f"Error updating channel name for instance {instance_name}: {e}"
            )
            return False

    @classmethod
    def update_instance_source_platform(
        cls, instance_name: str, source_platform: str
    ) -> bool:
        """Update source platform for an instance.

        Args:
            instance_name: Instance name (PRIMARY KEY)
            source_platform: Source platform (e.g., 'YouTube.com/@', 'Twitch.com/@')

        Returns:
            True if successful, False otherwise
        """
        try:
            db = cls.get_db()
            cls._run_async(
                db.update_instance(instance_name, source_platform=source_platform)
            )
            return True
        except Exception as e:
            logger.error(
                f"Error updating source platform for instance {instance_name}: {e}"
            )
            return False

    @classmethod
    def update_instance_tasks(
        cls, instance_name: str, task_updates: Dict[str, bool]
    ) -> bool:
        """Update task status for an instance.

        Args:
            instance_name: Instance name (PRIMARY KEY)
            task_updates: Dict mapping task names to boolean values

        Returns:
            True if successful, False otherwise
        """
        try:
            db = cls.get_db()
            cls._run_async(db.update_tasks(instance_name, **task_updates))
            return True
        except Exception as e:
            logger.error(f"Error updating tasks for instance {instance_name}: {e}")
            return False

    @classmethod
    def update_instance_upload_platforms(
        cls, instance_name: str, upload_platforms: List[str]
    ) -> bool:
        """Update upload platforms for an instance in the uploaders table.

        Args:
            instance_name: Instance name (PRIMARY KEY)
            upload_platforms: List of platform names (e.g., ['YouTube', 'Rumble', 'Odysee'])

        Returns:
            True if successful, False otherwise
        """
        try:
            db = cls.get_db()

            # Map platform names to database column names
            platform_mapping = {
                "YouTube": "upload_to_youtube",
                "Internet Archive": "upload_to_ia",
                "Rumble": "upload_to_rumble",
                "BitChute": "upload_to_bitchute",
                "Odysee": "upload_to_odysee",
                "GitHub": "upload_to_github",
            }

            # Build update dict - set all platforms to False first, then True for selected ones
            update_dict = {db_col: False for db_col in platform_mapping.values()}
            for platform in upload_platforms:
                if platform in platform_mapping:
                    update_dict[platform_mapping[platform]] = True
                else:
                    logger.warning(f"Unknown platform: {platform}")

            # Update the uploaders table
            cls._run_async(db.update_uploaders(instance_name, **update_dict))
            return True
        except Exception as e:
            logger.error(
                f"Error updating upload platforms for instance {instance_name}: {e}"
            )
            return False

    # ==================== Playlist Operations ====================

    @classmethod
    def get_playlist_items(
        cls,
        instance_name: str,
        limit: int = 100,
        offset: int = 0,
        search_query: str = None,
        status_filter: str = None,
    ) -> List[Dict[str, Any]]:
        """Get playlist items (videos/livestreams) for an instance with filtering (merged from download and upload tables).

        Args:
            instance_name: Instance name
            limit: Max items to return
            offset: Pagination offset
            search_query: Optional search term to filter by title or URL
            status_filter: Optional status filter (e.g., 'downloaded', 'not_downloaded', 'uploaded', 'not_uploaded')

        Returns:
            List of playlist items
        """
        try:
            db = cls.get_db()

            # Get all download entries for the instance across all channels
            all_download_entries = cls._run_async(
                db.get_all_instance_playlist_entries(instance_name)
            )

            # Get all upload entries for the instance across all channels
            all_upload_entries = []
            try:
                # Find all upload tables
                conn = cls._run_async(db._get_connection())
                cursor = cls._run_async(
                    conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                        (f"playlist_upload_%",),
                    )
                )
                upload_tables = cls._run_async(cursor.fetchall())
                cls._run_async(cursor.close())

                for table_row in upload_tables:
                    table_name = table_row[0]
                    cursor = cls._run_async(conn.execute(f"SELECT * FROM {table_name}"))
                    upload_rows = cls._run_async(cursor.fetchall())
                    cls._run_async(cursor.close())
                    all_upload_entries.extend(
                        [dict(row) for row in upload_rows] if upload_rows else []
                    )
            except Exception as e:
                logger.warning(f"Error getting upload entries: {e}")

            # Create a dictionary of upload entries by URL for easy lookup
            upload_dict = {entry.get("url"): entry for entry in all_upload_entries}

            # Merge download and upload entries
            all_entries = []
            for download_entry in all_download_entries:
                merged_entry = dict(download_entry)
                url = merged_entry.get("url")

                # Merge with upload data if available
                if url in upload_dict:
                    upload_entry = upload_dict[url]
                    merged_entry.update(
                        {
                            "uploaded_video_all_hosts": upload_entry.get(
                                "uploaded_video_all_hosts"
                            ),
                            "uploaded_video_ia": upload_entry.get("uploaded_video_ia"),
                            "uploaded_video_yt": upload_entry.get("uploaded_video_yt"),
                            "uploaded_video_rm": upload_entry.get("uploaded_video_rm"),
                            "uploaded_video_bc": upload_entry.get("uploaded_video_bc"),
                            "uploaded_video_od": upload_entry.get("uploaded_video_od"),
                            "uploaded_caption": upload_entry.get("uploaded_caption"),
                            "upload_error_bc": upload_entry.get("upload_error_bc"),
                            "upload_error_ia": upload_entry.get("upload_error_ia"),
                            "upload_error_yt": upload_entry.get("upload_error_yt"),
                            "upload_error_rm": upload_entry.get("upload_error_rm"),
                            "upload_error_od": upload_entry.get("upload_error_od"),
                        }
                    )

                all_entries.append(merged_entry)

            # Apply search filter
            if search_query:
                search_lower = search_query.lower()
                all_entries = [
                    entry
                    for entry in all_entries
                    if (
                        entry.get("title", "").lower().find(search_lower) != -1
                        or entry.get("url", "").lower().find(search_lower) != -1
                    )
                ]

            # Apply status filter
            if status_filter == "downloaded":
                all_entries = [
                    e for e in all_entries if bool(e.get("downloaded_video", False))
                ]
            elif status_filter == "not_downloaded":
                all_entries = [
                    e for e in all_entries if not bool(e.get("downloaded_video", False))
                ]
            elif status_filter == "uploaded":
                all_entries = [
                    e
                    for e in all_entries
                    if bool(e.get("uploaded_video_all_hosts", False))
                ]
            elif status_filter == "not_uploaded":
                all_entries = [
                    e
                    for e in all_entries
                    if not bool(e.get("uploaded_video_all_hosts", False))
                ]
            elif status_filter == "live":
                all_entries = [e for e in all_entries if bool(e.get("was_live", False))]
            elif status_filter == "not_live":
                all_entries = [
                    e for e in all_entries if not bool(e.get("was_live", False))
                ]

            # Apply pagination
            paginated = all_entries[offset : offset + limit]

            return paginated
        except Exception as e:
            logger.error(
                f"Error getting playlist items for instance {instance_name}: {e}"
            )
            return []

    @classmethod
    def get_playlist_count(
        cls, instance_name: str, search_query: str = None, status_filter: str = None
    ) -> int:
        """Get total count of playlist items for an instance with optional filters (merged from download and upload tables).

        Args:
            instance_name: Instance name
            search_query: Optional search term to filter by title or URL
            status_filter: Optional status filter

        Returns:
            Count of items
        """
        try:
            db = cls.get_db()

            # Get all download entries for the instance across all channels
            all_download_entries = cls._run_async(
                db.get_all_instance_playlist_entries(instance_name)
            )

            # Get all upload entries for the instance across all channels
            all_upload_entries = []
            try:
                # Find all upload tables
                conn = cls._run_async(db._get_connection())
                cursor = cls._run_async(
                    conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                        (f"playlist_upload_%",),
                    )
                )
                upload_tables = cls._run_async(cursor.fetchall())
                cls._run_async(cursor.close())

                for table_row in upload_tables:
                    table_name = table_row[0]
                    cursor = cls._run_async(conn.execute(f"SELECT * FROM {table_name}"))
                    upload_rows = cls._run_async(cursor.fetchall())
                    cls._run_async(cursor.close())
                    all_upload_entries.extend(
                        [dict(row) for row in upload_rows] if upload_rows else []
                    )
            except Exception as e:
                logger.warning(f"Error getting upload entries: {e}")

            # Create a dictionary of upload entries by URL for easy lookup
            upload_dict = {entry.get("url"): entry for entry in all_upload_entries}

            # Merge download and upload entries
            all_entries = []
            for download_entry in all_download_entries:
                merged_entry = dict(download_entry)
                url = merged_entry.get("url")

                # Merge with upload data if available
                if url in upload_dict:
                    upload_entry = upload_dict[url]
                    merged_entry.update(
                        {
                            "uploaded_video_all_hosts": upload_entry.get(
                                "uploaded_video_all_hosts"
                            ),
                            "uploaded_video_ia": upload_entry.get("uploaded_video_ia"),
                            "uploaded_video_yt": upload_entry.get("uploaded_video_yt"),
                            "uploaded_video_rm": upload_entry.get("uploaded_video_rm"),
                            "uploaded_video_bc": upload_entry.get("uploaded_video_bc"),
                            "uploaded_video_od": upload_entry.get("uploaded_video_od"),
                            "uploaded_caption": upload_entry.get("uploaded_caption"),
                            "upload_error_bc": upload_entry.get("upload_error_bc"),
                            "upload_error_ia": upload_entry.get("upload_error_ia"),
                            "upload_error_yt": upload_entry.get("upload_error_yt"),
                            "upload_error_rm": upload_entry.get("upload_error_rm"),
                            "upload_error_od": upload_entry.get("upload_error_od"),
                        }
                    )

                all_entries.append(merged_entry)

            # Apply search filter
            if search_query:
                search_lower = search_query.lower()
                all_entries = [
                    entry
                    for entry in all_entries
                    if (
                        entry.get("title", "").lower().find(search_lower) != -1
                        or entry.get("url", "").lower().find(search_lower) != -1
                    )
                ]

            # Apply status filter
            if status_filter == "downloaded":
                all_entries = [
                    e for e in all_entries if bool(e.get("downloaded_video", False))
                ]
            elif status_filter == "not_downloaded":
                all_entries = [
                    e for e in all_entries if not bool(e.get("downloaded_video", False))
                ]
            elif status_filter == "uploaded":
                all_entries = [
                    e
                    for e in all_entries
                    if bool(e.get("uploaded_video_all_hosts", False))
                ]
            elif status_filter == "not_uploaded":
                all_entries = [
                    e
                    for e in all_entries
                    if not bool(e.get("uploaded_video_all_hosts", False))
                ]
            elif status_filter == "live":
                all_entries = [e for e in all_entries if bool(e.get("was_live", False))]
            elif status_filter == "not_live":
                all_entries = [
                    e for e in all_entries if not bool(e.get("was_live", False))
                ]

            return len(all_entries)
        except Exception as e:
            logger.error(f"Error getting playlist count: {e}")
            return 0

    # ==================== Captions Operations ====================

    @classmethod
    def get_videos_with_captions(cls, instance_name: str) -> List[Dict[str, Any]]:
        """Get videos that have captions downloaded.

        Args:
            instance_name: Instance name

        Returns:
            List of videos with captions
        """
        try:
            instance_id = cls._get_instance_id(instance_name)
            if not instance_id:
                return []

            db = cls.get_db()
            # Get all playlist entries for this instance with captions
            all_entries = cls._run_async(
                db.get_all_instance_playlist_entries(instance_name)
            )
            videos_with_captions = [
                e for e in all_entries if bool(e.get("downloaded_caption", False))
            ]

            # Fetch caption counts from captions table
            result = []
            with db.get_connection() as conn:
                cursor = conn.cursor()
                for video in videos_with_captions:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as caption_count
                        FROM captions
                        WHERE instance_id = ? AND video_id = ?
                        """,
                        (instance_id, video.get("unique_id")),
                    )
                    row = cursor.fetchone()
                    caption_count = row[0] if row else 0

                    result.append(
                        {
                            "video_id": video.get("unique_id"),
                            "title": video.get("title"),
                            "datetime": video.get("datetime"),
                            "caption_count": caption_count,
                        }
                    )

            return sorted(result, key=lambda x: x["datetime"], reverse=True)
        except Exception as e:
            logger.error(f"Error getting videos with captions: {e}")
            return []

    @classmethod
    def get_captions_for_video(
        cls, instance_name: str, video_id: str
    ) -> List[Dict[str, Any]]:
        """Get all captions for a specific video.

        Args:
            instance_name: Instance name
            video_id: Video ID

        Returns:
            List of captions
        """
        try:
            instance_id = cls._get_instance_id(instance_name)
            if not instance_id:
                return []

            db = cls.get_db()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 
                        id,
                        language,
                        caption_data,
                        downloaded_at,
                        created_at
                    FROM captions
                    WHERE instance_id = ? AND video_id = ?
                    ORDER BY language
                """,
                    (instance_id, video_id),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting captions for video {video_id}: {e}")
            return []

    # ==================== Comments Operations ====================

    @classmethod
    def get_videos_with_comments(cls, instance_name: str) -> List[Dict[str, Any]]:
        """Get videos that have comments downloaded.

        Args:
            instance_name: Instance name

        Returns:
            List of videos with comments
        """
        try:
            instance_id = cls._get_instance_id(instance_name)
            if not instance_id:
                return []

            db = cls.get_db()

            # Get all download tables for this instance
            db_manager = DVRDB()
            instance_safe = db_manager._sanitize_identifier(instance_name)

            with db.get_connection() as conn:
                cursor = conn.cursor()

                # Find all download tables for this instance
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                    (f"playlist_download_{instance_safe}_%",),
                )
                tables = cursor.fetchall()

                all_videos = []
                for table_row in tables:
                    table_name = table_row[0]
                    cursor.execute(
                        f"""
                        SELECT DISTINCT
                            instance_name,
                            unique_id as video_id,
                            title,
                            datetime
                        FROM {table_name}
                        WHERE instance_name = ?
                        """,
                        (instance_name,),
                    )
                    videos = cursor.fetchall()
                    all_videos.extend([dict(row) for row in videos])

                # Get comments for this instance
                cursor.execute(
                    "SELECT video_id, COUNT(*) as comment_count FROM comments WHERE instance_id = ? GROUP BY video_id",
                    (instance_id,),
                )
                comments = cursor.fetchall()
                comment_dict = {row[0]: row[1] for row in comments}

                # Join videos with comments
                result = []
                for video in all_videos:
                    video_id = video.get("video_id")
                    if video_id in comment_dict:
                        video["comment_count"] = comment_dict[video_id]
                        result.append(video)

                # Sort by datetime
                result.sort(key=lambda x: x.get("datetime", ""), reverse=True)

                return result
        except Exception as e:
            logger.error(f"Error getting videos with comments: {e}")
            return []

    @classmethod
    def get_comments_for_video(
        cls, instance_name: str, video_id: str
    ) -> List[Dict[str, Any]]:
        """Get all comments for a specific video.

        Args:
            instance_name: Instance name
            video_id: Video ID

        Returns:
            List of comments
        """
        try:
            instance_id = cls._get_instance_id(instance_name)
            if not instance_id:
                return []

            db = cls.get_db()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        id,
                        comment_data,
                        author,
                        likes,
                        replies,
                        downloaded_at,
                        created_at
                    FROM comments
                    WHERE instance_id = ? AND video_id = ?
                    ORDER BY created_at DESC
                """,
                    (instance_id, video_id),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting comments for video {video_id}: {e}")
            return []

    # ==================== Posts Operations ====================

    @classmethod
    def get_posts(
        cls, instance_name: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get posts for an instance.

        Args:
            instance_name: Instance name
            limit: Max items to return
            offset: Pagination offset

        Returns:
            List of posts
        """
        try:
            instance_id = cls._get_instance_id(instance_name)
            if not instance_id:
                return []

            db = cls.get_db()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        id,
                        title,
                        html_content,
                        text_content,
                        metadata,
                        comment_count,
                        created_at,
                        updated_at
                    FROM posts
                    WHERE instance_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """,
                    (instance_id, limit, offset),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting posts for instance {instance_name}: {e}")
            return []

    @classmethod
    def get_post_by_id(cls, post_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific post.

        Args:
            post_id: Post ID

        Returns:
            Post dict or None
        """
        try:
            db = cls.get_db()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        id,
                        title,
                        html_content,
                        text_content,
                        metadata,
                        comment_count,
                        created_at,
                        updated_at
                    FROM posts
                    WHERE id = ?
                """,
                    (post_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting post {post_id}: {e}")
            return None

    # ==================== Logs Operations ====================

    @classmethod
    def get_instance_logs(
        cls,
        log_type: str = "core",
        level: str = None,
        thread_number: int = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get logs for an instance.

        Args:
            log_type: Type of log (core, download_live, download_captions, upload_yt, etc.)
            level: Optional level filter (DEBUG, INFO, WARNING, ERROR)
            thread_number: Optional thread number filter
            limit: Max items to return
            offset: Pagination offset

        Returns:
            List of log entries
        """
        try:
            cls.ensure_initialized()
            logs = cls._run_async(
                cls._log_db.get_logs(
                    log_type=log_type,
                    level=level,
                    thread_number=thread_number,
                    limit=limit,
                    offset=offset,
                )
            )
            return logs
        except Exception as e:
            logger.error(f"Error getting logs for type {log_type}: {e}")
            return []

    @classmethod
    def get_thread_numbers(cls, log_type: str = "core") -> List[int]:
        """Get available thread numbers for a specific log type.

        Args:
            log_type: Type of log to get thread numbers from

        Returns:
            List of unique thread numbers (sorted)
        """
        try:
            cls.ensure_initialized()
            table_name = cls._log_db.get_table_name(log_type)
            if not table_name:
                return []

            # Get logs and extract unique thread numbers
            logs = cls._run_async(cls._log_db.get_logs(log_type=log_type, limit=1000))

            thread_numbers = set()
            for log in logs:
                thread_num = log.get("thread_number")
                if thread_num is not None:
                    thread_numbers.add(thread_num)

            return sorted(list(thread_numbers))
        except Exception as e:
            logger.error(f"Error getting thread numbers for log type {log_type}: {e}")
            return []

    @classmethod
    def get_log_types(cls) -> List[str]:
        """Get available log types.

        Returns:
            List of log type names
        """
        return [
            "core",
            "download_live",
            "download_live_recovery",
            "download_captions",
            "download_comments",
            "download_posted",
            "download_posted_notices",
            "channel_playlist",
            "upload_posted",
            "upload_live",
            "upload_ia",
            "upload_yt",
            "upload_rumble",
            "upload_bitchute",
            "upload_odysee",
            "upload_captions",
        ]
