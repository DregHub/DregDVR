import os
import traceback
import asyncio
import json
import logging
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from config.config_tasks import DVR_Tasks
from utils.dependency_utils import DependencyManager


def create_required_dirs():
    """
    Create project, runtime and data profile directories and their subdirectories
    as defined in the configuration.
    """
    DVR_Config._init_parser()
    root = os.getcwd()
    DVR_Config.Project_Root_Dir = os.path.dirname(os.path.abspath(__file__))
    runtime_profiledir_name = json.loads(
        DVR_Config.get_value("Directories", "runtime_dir")
    )
    data_profiledir_name = json.loads(DVR_Config.get_value("Directories", "data_dir"))
    runtime_profiledir = os.path.join(root, runtime_profiledir_name)
    data_profiledir = os.path.join(root, data_profiledir_name)

    runtime_subdirs_to_create = json.loads(
        DVR_Config.get_value("Directories", "runtime_subdirs_to_create")
    )
    data_subdirs_to_create = json.loads(
        DVR_Config.get_value("Directories", "data_subdirs_to_create")
    )

    for sub in runtime_subdirs_to_create:
        newdir = os.path.join(runtime_profiledir, sub)
        # Cant use log manager yet as the dirs may not exist log to container shell instead
        logging.info(f"making new runtime profile subdirectory: {newdir}")
        os.makedirs(newdir, exist_ok=True)

    for sub in data_subdirs_to_create:
        newdir = os.path.join(data_profiledir, sub)
        logging.info(f"making new dvr data subdirectory: {newdir}")
        os.makedirs(newdir, exist_ok=True)

    logging.info("Created required directories successfully.")


async def handle_dependency_updates():
    dependency_package_update_enabled = DVR_Tasks.get_dependency_package_update()

    if dependency_package_update_enabled == True:
        if os.name == "nt":
            # Windows
            LogManager.log_core("Skipping Dependency Package Update as os = Windows")
        else:
            apt_dependencies = DVR_Config.get_required_apt_dependencies()
            for dependency in apt_dependencies:
                await DependencyManager.install_apt_dependency(dependency)

            pip_dependencies = DVR_Config.get_required_py_dependencies()
            for dependency in pip_dependencies:
                await DependencyManager.install_pip_dependency(dependency)

            await DependencyManager.update_ytdlp()

            LogManager.log_core(
                "All required dependencies installed/updated successfully."
            )
    else:
        LogManager.log_core(
            "Skipping Dependency Package Update as dependency_package_update = false in dvr_tasks.ini"
        )


async def handle_container_maintenance():
    ContainerMaintenance = DVR_Tasks.get_container_maintenance_inf_loop()
    if ContainerMaintenance == True:
        LogManager.log_core("Container Maintenance Mode is ON")
        LogManager.log_core("Script Will Loop Forever...")
        # Infinite loop incase we need to access the containers shell
        while True:
            await asyncio.sleep(600000)


def add_task_if_enabled(tasks, enabled, coro_func, disabled_message):
    if enabled == True:
        tasks.append(coro_func())
    else:
        LogManager.log_core(disabled_message)


async def main():
    try:
        logging.info("Starting Dregg DVR")
        # Ensure required project/runtime/data directories exist
        create_required_dirs()

        await handle_dependency_updates()

        await handle_container_maintenance()

        livestream_download_enabled = DVR_Tasks.get_livestream_download()
        livestream_recovery_download_enabled = DVR_Tasks.get_livestream_recovery_download()
        captions_download_enabled = DVR_Tasks.get_captions_download()
        captions_upload_enabled = DVR_Tasks.get_captions_upload()
        #currently download comments is scheduled by the live download dlp events
        #comments_download_enabled = DVR_Tasks.get_comments_download()
        comments_republish_enabled = DVR_Tasks.get_comments_republish()
        posted_videos_download_enabled = DVR_Tasks.get_posted_videos_download()
        posted_notices_download_enabled = DVR_Tasks.get_posted_notices_download()
        livestream_upload_enabled = DVR_Tasks.get_livestream_upload()
        posted_videos_upload_enabled = DVR_Tasks.get_posted_videos_upload()
        update_yt_source_playlist = DVR_Tasks.get_update_yt_source_playlist()
        update_caption_source_playlist = DVR_Tasks.get_update_caption_source_playlist()

        # Import all task modules
        from downloader.livestreams import LivestreamDownloader
        from downloader.recovery import RecoveryDownloader
        from downloader.videos import VideoDownloader
        from downloader.captions import CaptionsDownloader
        from downloader.posts import CommunityDownloader
        from uploader.videos import VideoUploader
        from uploader.captions import CaptionsUploader
        from downloader.comments import LiveCommentsDownloader
        from downloader.videos import VideosPlaylistManager
        from downloader.captions import CaptionsPlaylistManager

        tasks = []
        task_configs = [
            (
                livestream_download_enabled,
                LivestreamDownloader.download_livestreams,
                "Livestream Download is disabled in INI Tasks. Skipping...",
            ),
            (
                livestream_recovery_download_enabled,
                RecoveryDownloader.monitor_recoveryqueue,
                "Livestream Recovery Download is disabled in INI Tasks. Skipping...",
            ),
            (
                comments_republish_enabled,
                LiveCommentsDownloader.republish_comments,
                "Comments Republish is disabled in INI Tasks. Skipping...",
            ),
            (
                posted_videos_download_enabled,
                VideoDownloader.download_videos,
                "Posted Video Download is disabled in INI Tasks. Skipping...",
            ),
            (
                captions_download_enabled,
                CaptionsDownloader.download_captions,
                "Caption Download is disabled in INI Tasks. Skipping...",
            ),
            (
                captions_upload_enabled,
                CaptionsUploader.upload_captions,
                "Caption Upload is disabled in INI Tasks. Skipping...",
            ),
            (
                posted_notices_download_enabled,
                CommunityDownloader.monitor_channel,
                "Posted Community Message Download is disabled in INI Tasks. Skipping...",
            ),
            (
                livestream_upload_enabled,
                VideoUploader.upload_livestreams,
                "Livestream Upload is disabled in INI Tasks. Skipping...",
            ),
            (
                posted_videos_upload_enabled,
                VideoUploader.upload_posted_videos,
                "Posted Video Upload is disabled in INI Tasks. Skipping...",
            ),
            (
                update_yt_source_playlist,
                VideosPlaylistManager.run_playlist_update_task,
                "Update YouTube Source Playlist is disabled in INI Tasks. Skipping...",
            ),
            (
                update_caption_source_playlist,
                CaptionsPlaylistManager.run_playlist_update_task,
                "Update Caption Source Playlist is disabled in INI Tasks. Skipping...",
            ),
        ]

        for enabled, coro_func, msg in task_configs:
            add_task_if_enabled(tasks, enabled, coro_func, msg)

        if not tasks:
            LogManager.log_core("All Tasks are disabled in INI Tasks. Exiting...")
        else:
            LogManager.log_core(
                "Starting Dregg's DVR... Am i 4k wecording? Yes im 4k wecording!"
            )
            await asyncio.gather(*tasks)

    except Exception as e:
        LogManager.log_core(f"Exception in main:  {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(main())
