"""
Database-backed Account Configuration
Replaces the INI file-based account_config.py functionality
"""


class Account_Config:
    """Account configuration using SQLite database."""

    _current_instance = None
    _db = None

    @classmethod
    async def set_instance(cls, instance_name: str):
        """Set the current instance by name."""
        from db.dvr_db import DVRDB
        from utils.file_utils import FileManager

        if cls._db is None:
            cls._db = await DVRDB.get_global()

        # Find instance by name
        instances = await cls._db.get_all_instances()
        for inst in instances:
            if FileManager.gen_safe_filename(inst["instance_name"]) == instance_name:
                cls._current_instance = inst["instance_name"]
                return

    @classmethod
    def get_current_instance(cls):
        """Get the current instance ID."""
        return cls._current_instance

    @classmethod
    async def _get_db(cls):
        """Get database instance."""
        if cls._db is None:
            from db.dvr_db import DVRDB

            cls._db = await DVRDB.get_global()
        return cls._db

    @classmethod
    def build_youtube_url(cls, channel_name: str, add_live: bool = False) -> str:
        """Build a full YouTube URL from a channel name."""
        if not channel_name:
            return ""

        # If it's already a URL, return it
        if channel_name.startswith("http"):
            url = channel_name
        else:
            # Handle @handle format
            if not channel_name.startswith("@"):
                channel_name = "@" + channel_name
            url = f"https://www.youtube.com/{channel_name}"

        if add_live:
            url += "/live"

        return url

    @classmethod
    def extract_channel_handle(cls, channel_name: str) -> str:
        """Extract the @handle from a channel name or URL."""
        if not channel_name:
            return ""

        # If it's already a handle
        if channel_name.startswith("@"):
            return channel_name

        # If it's a URL, extract the handle
        if "youtube.com/" in channel_name:
            parts = channel_name.split("youtube.com/")
            if len(parts) > 1:
                return parts[1].strip("/")

        return channel_name

    # File naming
    @classmethod
    async def get_live_downloadprefix(cls):
        """Get live download prefix."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("live_downloadprefix") or "" if account else ""

    @classmethod
    async def get_posted_downloadprefix(cls):
        """Get posted videos download prefix."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("posted_downloadprefix") or "" if account else ""

    # Internet Archive
    @classmethod
    async def get_ia_itemid(cls):
        """Get Internet Archive item ID."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("ia_itemid") or "" if account else ""

    @classmethod
    async def get_ia_user_agent(cls):
        """Get Internet Archive user agent."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("ia_user_agent") or "" if account else ""

    @classmethod
    async def get_ia_email(cls):
        """Get Internet Archive email."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("ia_email") or "" if account else ""

    @classmethod
    async def get_ia_password(cls):
        """Get Internet Archive password."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("ia_password") or "" if account else ""

    # GitHub
    @classmethod
    async def get_github_token(cls):
        """Get GitHub personal access token."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("github_token") or "" if account else ""

    @classmethod
    async def get_github_repo_owner(cls):
        """Get GitHub repository owner."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("github_repo_owner") or "" if account else ""

    @classmethod
    async def get_github_repo_name(cls):
        """Get GitHub repository name."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("github_repo_name") or "" if account else ""

    @classmethod
    async def get_github_captions_path(cls):
        """Get GitHub captions path."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("github_captions_path") or "" if account else ""

    # Rumble
    @classmethod
    async def get_rumble_email(cls):
        """Get Rumble email."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("rumble_email") or "" if account else ""

    @classmethod
    async def get_rumble_password(cls):
        """Get Rumble password."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("rumble_password") or "" if account else ""

    @classmethod
    async def get_rumble_primary_category(cls):
        """Get Rumble primary category."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("rumble_primary_category") or "" if account else ""

    @classmethod
    async def get_rumble_secondary_category(cls):
        """Get Rumble secondary category."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("rumble_secondary_category") or "" if account else ""

    # BitChute
    @classmethod
    async def get_bitchute_email(cls):
        """Get BitChute email."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("bitchute_email") or "" if account else ""

    @classmethod
    async def get_bitchute_password(cls):
        """Get BitChute password."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("bitchute_password") or "" if account else ""

    # Odysee
    @classmethod
    async def get_odysee_email(cls):
        """Get Odysee email."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("odysee_email") or "" if account else ""

    @classmethod
    async def get_odysee_password(cls):
        """Get Odysee password."""
        if not cls._current_instance:
            return ""
        db = await cls._get_db()
        account = await db.get_account(cls._current_instance)
        return account.get("odysee_password") or "" if account else ""
