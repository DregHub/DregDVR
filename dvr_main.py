import asyncio
import traceback
from utils.logging_utils import LogManager, LogLevels
from config.config_settings import DVR_Config
from config.config_tasks import DVR_Tasks
from config.config_instances import DVR_Instances
from utils.file_utils import FileManager
import logging

logger = logging.getLogger(__name__)


class DVRMain:
    def add_task_if_enabled(self, tasks, enabled, coro_func, disabled_message):
        if enabled == True:
            tasks.append(coro_func())
        else:
            LogManager.log_core(disabled_message, LogLevels.Info)

    async def _get_task_configs(self):
        """Return the task configuration list with enabled flags and their coroutine functions."""
        livestream_download_enabled = await DVR_Tasks.get_livestream_download()
        livestream_recovery_download_enabled = (
            await DVR_Tasks.get_livestream_recovery_download()
        )
        captions_download_enabled = await DVR_Tasks.get_captions_download()
        captions_upload_enabled = await DVR_Tasks.get_captions_upload()
        comments_republish_enabled = await DVR_Tasks.get_comments_republish()
        posted_videos_download_enabled = await DVR_Tasks.get_posted_videos_download()
        posted_notices_download_enabled = await DVR_Tasks.get_posted_notices_download()
        livestream_upload_enabled = await DVR_Tasks.get_livestream_upload()
        posted_videos_upload_enabled = await DVR_Tasks.get_posted_videos_upload()
        update_playlist_enabled = await DVR_Tasks.get_update_playlist()

        # Import all task modules
        from downloader.livestreams import LivestreamDownloader
        from downloader.recovery import RecoveryDownloader
        from downloader.videos import VideoDownloader
        from downloader.captions import CaptionsDownloader
        from downloader.posts import CommunityDownloader
        from uploader.videos import VideoUploader
        from uploader.captions import CaptionsUploader
        from downloader.comments import LiveCommentsDownloader
        from utils.playlist_manager import PlaylistManager

        return [
            (
                livestream_download_enabled,
                LivestreamDownloader.download_livestreams,
                "Livestream Download is disabled in Tasks Table. Skipping...",
            ),
            (
                livestream_recovery_download_enabled,
                RecoveryDownloader.monitor_recoveryqueue,
                "Livestream Recovery Download is disabled in Tasks Table. Skipping...",
            ),
            (
                comments_republish_enabled,
                LiveCommentsDownloader.republish_comments,
                "Comments Republish is disabled in Tasks Table. Skipping...",
            ),
            (
                posted_videos_download_enabled,
                VideoDownloader.download_videos,
                "Posted Video Download is disabled in Tasks Table. Skipping...",
            ),
            (
                captions_download_enabled,
                CaptionsDownloader.download_captions,
                "Caption Download is disabled in Tasks Table. Skipping...",
            ),
            (
                captions_upload_enabled,
                CaptionsUploader.upload_captions,
                "Caption Upload is disabled in Tasks Table. Skipping...",
            ),
            (
                posted_notices_download_enabled,
                CommunityDownloader.monitor_channel,
                "Posted Community Message Download is disabled in Tasks Table. Skipping...",
            ),
            (
                livestream_upload_enabled,
                VideoUploader.upload_livestreams,
                "Livestream Upload is disabled in Tasks Table. Skipping...",
            ),
            (
                posted_videos_upload_enabled,
                VideoUploader.upload_posted_videos,
                "Posted Video Upload is disabled in Tasks Table. Skipping...",
            ),
            (
                update_playlist_enabled,
                PlaylistManager.update_channel_playlist,
                "Update YouTube Source Playlist is disabled in Tasks Table. Skipping...",
            ),
        ]

    async def run_instance(self, instance_name: str):
        """Run a single instance by name."""
        safe_instance_name = FileManager.gen_safe_filename(instance_name)

        # Set instance context
        DVR_Config.set_instance(safe_instance_name)
        await DVR_Tasks.set_instance(safe_instance_name)

        LogManager.log_core(
            f"Starting single instance: {instance_name}", LogLevels.Info
        )

        # Get task configs and build tasks list
        task_configs = await self._get_task_configs()
        tasks = []
        for enabled, coro_func, msg in task_configs:
            self.add_task_if_enabled(tasks, enabled, coro_func, msg)

        if tasks:
            LogManager.log_core(
                f"Starting tasks for instance: {instance_name}", LogLevels.Info
            )
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                LogManager.log_core(
                    f"Error during instance task execution: {e} {traceback.format_exc()}",
                    LogLevels.Error,
                )
            return True
        else:
            LogManager.log_core(
                f"All Tasks are disabled for instance {instance_name}. Skipping...",
                LogLevels.Info,
            )
            return False

    async def run_dvr(self):
        # Initialize logging database schema before any logging operations
        await LogManager._ensure_database_schema()

        # Get all instances
        instances = await DVR_Instances.get_all_instances()
        if not instances:
            print("Create a DVR Instance in the Streamlit Webui to start!")
            return False

        # Set temporary instance context using the first instance so startup checks use instance-specific configs
        first_instance_name = instances[0]["instance_name"]
        first_safe_name = FileManager.gen_safe_filename(first_instance_name)
        DVR_Config.set_instance(first_safe_name)
        await DVR_Tasks.set_instance(first_safe_name)

        # Create task coroutines for each instance
        all_instance_tasks = []

        for instance_config in instances:
            instance_name = instance_config["instance_name"]
            safe_instance_name = FileManager.gen_safe_filename(instance_name)

            # Set instance context
            DVR_Config.set_instance(safe_instance_name)
            await DVR_Tasks.set_instance(safe_instance_name)

            LogManager.log_core(
                f"Setting up tasks for instance: {instance_name}", LogLevels.Info
            )

            # Get task configs and build tasks list
            task_configs = await self._get_task_configs()
            tasks = []
            for enabled, coro_func, msg in task_configs:
                self.add_task_if_enabled(tasks, enabled, coro_func, msg)

            if tasks:
                LogManager.log_core(
                    f"Starting tasks for instance: {instance_name} (4k recording mode enabled!)",
                    LogLevels.Info,
                )
                all_instance_tasks.extend(tasks)
            else:
                LogManager.log_core(
                    f"All Tasks are disabled for instance {instance_name}. Skipping...",
                    LogLevels.Info,
                )

        if not all_instance_tasks:
            LogManager.log_core(
                "All Tasks are disabled across all instances. Skipping DVR task execution and leaving Streamlit available for configuration.",
                LogLevels.Info,
            )
            return False
        else:
            LogManager.log_core(
                f"Starting Dregg's DVR with {len(instances)} instance(s)... Am i 4k recording? Yes im 4k recording!",
                LogLevels.Info,
            )
            try:
                await asyncio.gather(*all_instance_tasks, return_exceptions=True)
            except Exception as e:
                LogManager.log_core(
                    f"Error during DVR task execution: {e} {traceback.format_exc()}",
                    LogLevels.Error,
                )
            return True


if __name__ == "__main__":
    async def run_dvr_with_loop_registration():
        from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager

        # Register the event loop with lifecycle manager for logging
        loop = asyncio.get_running_loop()
        try:
            AsyncioLifecycleManager.register_loop(loop, loop_name="dvr_main_loop")
            logger.info("Successfully registered event loop with lifecycle manager")
        except Exception as e:
            logger.error(f"Failed to register event loop: {e}")
            raise

        dvr = DVRMain()
        result = await dvr.run_dvr()
        if not result:
            logger.error("DVR initialization failed.")
        return result

    result = asyncio.run(run_dvr_with_loop_registration())
