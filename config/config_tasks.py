"""
Database-backed Tasks Configuration
Replaces the INI file-based config_tasks.py functionality
"""


class DVR_Tasks:
    """DVR tasks configuration using SQLite database."""

    _current_instance = None
    _db = None

    @classmethod
    async def set_instance(cls, instance_name: str):
        """Set the current instance by name."""
        from db.dvr_db import DVRDB
        from utils.file_utils import FileManager

        if cls._db is None:
            cls._db = await DVRDB.get_global()

        cls._current_instance = FileManager.gen_safe_filename(instance_name)

    @classmethod
    def get_current_instance(cls):
        """Get the current instance name."""
        return cls._current_instance

    @classmethod
    async def _get_db(cls):
        """Get database instance."""
        if cls._db is None:
            from db.dvr_db import DVRDB

            cls._db = await DVRDB.get_global()
        return cls._db

    @classmethod
    async def _get_instance_name(cls):
        """Get current instance name from database."""
        if not cls._current_instance:
            return None

        db = await cls._get_db()
        instances = await db.get_all_instances()
        for inst in instances:
            from utils.file_utils import FileManager

            if (
                FileManager.gen_safe_filename(inst["instance_name"])
                == cls._current_instance
            ):
                return inst["instance_name"]
        return None

    @classmethod
    async def get_dependency_package_update(cls):
        """Get dependency package update flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return True
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("dependency_package_update", True) if tasks else True)

    @classmethod
    async def get_livestream_download(cls):
        """Get livestream download flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return True
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("livestream_download", True) if tasks else True)

    @classmethod
    async def get_livestream_recovery_download(cls):
        """Get livestream recovery download flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return True
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("livestream_recovery_download", True) if tasks else True)

    @classmethod
    async def get_comments_download(cls):
        """Get comments download flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("comments_download", False) if tasks else False)

    @classmethod
    async def get_comments_republish(cls):
        """Get comments republish flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("comments_republish", False) if tasks else False)

    @classmethod
    async def get_captions_download(cls):
        """Get captions download flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("captions_download", False) if tasks else False)

    @classmethod
    async def get_captions_upload(cls):
        """Get captions upload flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("captions_upload", False) if tasks else False)

    @classmethod
    async def get_posted_videos_download(cls):
        """Get posted videos download flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("posted_videos_download", False) if tasks else False)

    @classmethod
    async def get_posted_notices_download(cls):
        """Get posted notices download flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("posted_notices_download", False) if tasks else False)

    @classmethod
    async def get_livestream_upload(cls):
        """Get livestream upload flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("livestream_upload", False) if tasks else False)

    @classmethod
    async def get_posted_videos_upload(cls):
        """Get posted videos upload flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("posted_videos_upload", False) if tasks else False)

    @classmethod
    async def get_update_playlist(cls):
        """Get update YouTube source playlist flag."""
        instance_name = await cls._get_instance_name()
        if not instance_name:
            return False
        db = await cls._get_db()
        tasks = await db.get_tasks(instance_name)
        return bool(tasks.get("update_playlist", False) if tasks else False)
