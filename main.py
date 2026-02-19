import os
import traceback
import asyncio
import json
import logging
from utils.logging_utils import LogManager
from config_settings import DVR_Config
from config_tasks import DVR_Tasks
from utils.dependency_utils import DependencyManager


def create_required_dirs():
    """
    Create project, runtime and data profile directories and their subdirectories
    as defined in the configuration.
    """
    DVR_Config._init_parser()
    root = os.getcwd()

    runtime_profiledir_name = json.loads(DVR_Config.get_value("Directories", "runtime_dir"))
    data_profiledir_name = json.loads(DVR_Config.get_value("Directories", "data_dir"))
    runtime_profiledir = os.path.join(root, runtime_profiledir_name)
    data_profiledir = os.path.join(root, data_profiledir_name)
        
    runtime_subdirs_to_create = json.loads(DVR_Config.get_value("Directories", "runtime_subdirs_to_create"))
    data_subdirs_to_create = json.loads(DVR_Config.get_value("Directories", "data_subdirs_to_create"))

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


async def main():
    try:
        logging.error(f"Starting Dregg DVR")
        # Ensure required project/runtime/data directories exist
        create_required_dirs()
        
        dependency_package_update = DVR_Tasks.get_dependency_package_update()

        if dependency_package_update == "true":
            if os.name == "nt":
                # Windows
                LogManager.log_core("Skipping Dependency Package Update as os = Windows")
            else:
                apk_dependencies = DVR_Config.get_required_apk_dependencies()
                for dependency in apk_dependencies:
                    await DependencyManager.install_apk_dependency(dependency)

                pip_dependencies = DVR_Config.get_required_py_dependencies()
                for dependency in pip_dependencies:
                    await DependencyManager.install_pip_dependency(dependency)

                await DependencyManager.update_ytdlp()
                    
                LogManager.log_core("All required dependencies installed/updated successfully.")
        else:
            LogManager.log_core("Skipping Dependency Package Update as dependency_package_update = false in dvr_tasks.ini")
                


       
        ContainerMaintenance = DVR_Tasks.get_container_maintenance_inf_loop()
        if ContainerMaintenance.lower() == "true":
            LogManager.log_core("Container Maintenance Mode is ON")
            LogManager.log_core("Script Will Loop Forever...")
            # Infinite loop incase we need to access the containers shell
            while True:
                await asyncio.sleep(600000)

        else:
            LogManager.log_core("Starting Dregg's DVR... Am i 4k wecording? Yes im 4k wecording!")
            livestream_download = DVR_Tasks.get_livestream_download()
            livestream_recovery_download = DVR_Tasks.get_livestream_recovery_download()
            captions_download = DVR_Tasks.get_captions_download()
            posted_videos_download = DVR_Tasks.get_posted_videos_download()
            posted_notices_download = DVR_Tasks.get_posted_notices_download()
            livestream_upload = DVR_Tasks.get_livestream_upload()
            posted_videos_upload = DVR_Tasks.get_posted_videos_upload()
            
            tasks = []
            if livestream_download == "true":
                from downloader.livestreams import LivestreamDownloader
                tasks.append(LivestreamDownloader.download_livestreams())
            else:
                LogManager.log_core("Livestream Download is disabled in INI Tasks. Skipping...")

            if livestream_recovery_download == "true":
                from downloader.recovery import RecoveryDownloader
                tasks.append(RecoveryDownloader.monitor_recoveryqueue())
            else:
                LogManager.log_core("Livestream Recovery Download is disabled in INI Tasks. Skipping...")

            if posted_videos_download == "true":
                from downloader.videos import VideoDownloader
                tasks.append(VideoDownloader.download_videos())
            else:
                LogManager.log_core("Posted Video Download is disabled in INI Tasks. Skipping...")

            if captions_download == "true":
                from downloader.captions import CaptionsDownloader
                tasks.append(CaptionsDownloader.monitor_channel())
            else:
                LogManager.log_core("Caption Download is disabled in INI Tasks. Skipping...")


            if posted_notices_download == "true":
                from downloader.posts import CommunityDownloader
                tasks.append(CommunityDownloader.monitor_channel())
            else:
                LogManager.log_core("Posted Community Message Download is disabled in INI Tasks. Skipping...")

            if livestream_upload == "true":
                from uploader.livestreams import LiveStreamUploader
                tasks.append(LiveStreamUploader.upload_live_videos())
            else:
                LogManager.log_core("Livestream Upload is disabled in INI Tasks. Skipping...")

            if posted_videos_upload == "true":
                from uploader.videos import VideoUploader
                tasks.append(VideoUploader.upload_videos())
            else:
                LogManager.log_core("Posted Video Upload is disabled in INI Tasks. Skipping...")


            if not tasks:
                LogManager.log_core("All Tasks are disabled in INI Tasks. Exiting...")
            else:
                await asyncio.gather(*tasks)

    except Exception as e:
        LogManager.log_core(f"Exception in main:  {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    asyncio.run(main())
