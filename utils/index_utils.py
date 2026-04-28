import traceback
from utils.logging_utils import LogManager, LogLevels


class IndexManager:
    """Manages live and posted video indices using a database-backed approach."""

    @classmethod
    async def _ensure_instance_exists(cls, instance_name, db):
        """Ensure the instance exists in the index table, creating it if necessary."""
        try:
            # Check if instance exists
            conn = await db._get_connection()
            cursor = await conn.execute(
                'SELECT instance_name FROM "index" WHERE instance_name = ?',
                (instance_name,),
            )
            existing = await cursor.fetchone()
            await cursor.close()

            if not existing:
                # Create new entry with default indices
                await conn.execute(
                    'INSERT INTO "index" (instance_name, live_index, posted_index) VALUES (?, 0, 0)',
                    (instance_name,),
                )
                await conn.commit()
                LogManager.log_core(
                    f"Created new index entry for instance: {instance_name}",
                    LogLevels.Info,
                )
        except Exception as e:
            LogManager.log_core(
                f"Failed to ensure instance exists: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def get_current_live_index(cls, instance_name):
        """
        Get the current live index for the specified instance.

        Args:
            instance_name: The name of the instance

        Returns:
            int: The current live index value
        """
        try:
            from db.dvr_db import DVRDB

            db = await DVRDB.get_global()
            await cls._ensure_instance_exists(instance_name, db)

            conn = await db._get_connection()
            cursor = await conn.execute(
                'SELECT live_index FROM "index" WHERE instance_name = ?',
                (instance_name,),
            )
            result = await cursor.fetchone()
            await cursor.close()

            if result:
                return result[0]
            return 0
        except Exception as e:
            LogManager.log_core(
                f"Failed to get current live index: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def get_current_posted_index(cls, instance_name):
        """
        Get the current posted index for the specified instance.

        Args:
            instance_name: The name of the instance

        Returns:
            int: The current posted index value
        """
        try:
            from db.dvr_db import DVRDB

            db = await DVRDB.get_global()
            await cls._ensure_instance_exists(instance_name, db)

            conn = await db._get_connection()
            cursor = await conn.execute(
                'SELECT posted_index FROM "index" WHERE instance_name = ?',
                (instance_name,),
            )
            result = await cursor.fetchone()
            await cursor.close()

            if result:
                return result[0]
            return 0
        except Exception as e:
            LogManager.log_core(
                f"Failed to get current posted index: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def increment_current_live_index(cls, instance_name):
        """
        Increment the live index for the specified instance.

        Args:
            instance_name: The name of the instance

        Returns:
            int: The new live index value after incrementing
        """
        try:
            from db.dvr_db import DVRDB

            db = await DVRDB.get_global()
            await cls._ensure_instance_exists(instance_name, db)

            # Increment and update in a single operation
            conn = await db._get_connection()
            await conn.execute(
                'UPDATE "index" SET live_index = live_index + 1, updated_at = CURRENT_TIMESTAMP WHERE instance_name = ?',
                (instance_name,),
            )
            await conn.commit()

            # Return the new value
            new_index = await cls.get_current_live_index(instance_name)
            return new_index
        except Exception as e:
            LogManager.log_core(
                f"Failed to increment live index: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise

    @classmethod
    async def increment_current_posted_index(cls, instance_name):
        """
        Increment the posted index for the specified instance.

        Args:
            instance_name: The name of the instance

        Returns:
            int: The new posted index value after incrementing
        """
        try:
            from db.dvr_db import DVRDB

            db = await DVRDB.get_global()
            await cls._ensure_instance_exists(instance_name, db)

            # Increment and update in a single operation
            conn = await db._get_connection()
            await conn.execute(
                'UPDATE "index" SET posted_index = posted_index + 1, updated_at = CURRENT_TIMESTAMP WHERE instance_name = ?',
                (instance_name,),
            )
            await conn.commit()

            # Return the new value
            new_index = await cls.get_current_posted_index(instance_name)
            return new_index
        except Exception as e:
            LogManager.log_core(
                f"Failed to increment posted index: {e}\n{traceback.format_exc()}",
                LogLevels.Error,
            )
            raise
