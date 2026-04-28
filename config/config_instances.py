"""
Database-backed Instances Configuration
Replaces the INI file-based config_instances.py functionality
"""

class DVR_Instances:
    """Configuration class for managing multiple DVR instances using SQLite database."""

    _db = None

    @classmethod
    async def _get_db(cls):
        """Get database instance."""
        if cls._db is None:
            from  db.dvr_db import DVRDB
            cls._db = await DVRDB.get_global()
        return cls._db

    @classmethod
    async def get_all_instances(cls):
        """Get all DVR instances from the database."""
        try:
            db = await cls._get_db()
            instances = await db.get_all_instances()

            # Convert to expected format
            result = []
            for inst in instances:
                result.append(
                    {
                        "instance_name": inst["instance_name"],
                        "dvr_data_in_other_instance": bool(
                            inst["dvr_data_in_other_instance"]
                        ),
                        "dvr_data_other_instance_name": inst.get(
                            "dvr_data_other_instance_name"
                        )
                        or "",
                    }
                )

            return result
        except Exception as e:
            logger.error(f"Error getting instances: {e}")
            return []

    @classmethod
    async def get_instance_config(cls, instance_name):
        """Get configuration for a specific instance by name."""
        try:
            db = await cls._get_db()
            instances = await db.get_all_instances()

            for inst in instances:
                if inst["instance_name"] == instance_name:
                    return {
                        "instance_name": inst["instance_name"],
                        "dvr_data_in_other_instance": bool(
                            inst["dvr_data_in_other_instance"]
                        ),
                        "dvr_data_other_instance_name": inst.get(
                            "dvr_data_other_instance_name"
                        )
                        or "",
                    }

            return None
        except Exception as e:
            logger.error(f"Error getting instance config for {instance_name}: {e}")
            return None
