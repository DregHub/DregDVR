import os
import logging
from config.config_instances import DVR_Instances

logger = logging.getLogger(__name__)


class InstanceManager:
    """Manage DVR instances - all runtime files stored in /_DVR_Runtime at filesystem root."""

    @staticmethod
    def get_runtime_base_dir():
        """Get the base runtime directory at filesystem root.

        Returns:
            str: Path to /_DVR_Runtime
        """
        return "/_DVR_Runtime"

    @staticmethod
    async def get_instances():
        """Retrieve all configured instances from database.

        Returns:
            list: List of instance configurations
        """
        try:
            return await DVR_Instances.get_all_instances()
        except Exception as e:
            logger.error(f"Error retrieving instances: {e}")
            return []

    @staticmethod
    def ensure_instance_dirs():
        """Ensure runtime directories exist at filesystem root."""
        runtime_dir = InstanceManager.get_runtime_base_dir()

        directories = [
            runtime_dir,
            os.path.join(runtime_dir, "UI_Assets"),
            os.path.join(runtime_dir, "UI_Assets", "Thumbnails"),
            os.path.join(runtime_dir, "PlayWright"),
            os.path.join(runtime_dir, "Auth", "Download", "Upload"),
        ]

        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                logger.error(f"Error creating directory {directory}: {e}")
                raise

    @staticmethod
    def validate_instances():
        """Validate that at least one instance is configured.

        Returns:
            bool: True if instances exist, False otherwise
        """
        instances = InstanceManager.get_instances()
        if not instances:
            logger.warning(
                "No instances found in database. You must have at least 1 for operation."
            )
            return False
        return True

    @staticmethod
    def get_instance_ui_assets_dir():
        """Get the UI assets directory (logos, favicons, thumbnails).

        Returns:
            str: Path to UI assets directory
        """
        return os.path.join(InstanceManager.get_runtime_base_dir(), "_UI_Assets")

    @staticmethod
    def get_instance_thumbnails_dir():
        """Get the thumbnails directory.

        Returns:
            str: Path to thumbnails directory
        """
        return os.path.join(InstanceManager.get_instance_ui_assets_dir(), "thumbnails")

    @staticmethod
    async def initialize_instances():
        """Initialize all instances: ensure directories and validate configuration.

        Returns:
            list: List of initialized instance configurations, or empty list if none exist
        """
        try:
            # Ensure all required runtime directories exist
            InstanceManager.ensure_instance_dirs()

            # Get all instances from database
            instances = await InstanceManager.get_instances()

            if instances:
                logger.info(f"Initialized {len(instances)} DVR instance(s)")

            return instances
        except Exception as e:
            logger.error(f"Error initializing instances: {e}")
            return []
