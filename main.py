import os
import traceback
import asyncio
import json
from utils.logging_utils import LogManager
from config import Config
from utils.dependency_utils import DependencyManager


async def main():
    try:
        dirs_to_create = json.loads(Config.get_value("Directories", "dirs_to_create"))
        for dir in dirs_to_create:
            os.makedirs(dir, exist_ok=True)

        if os.name == "nt":
            # Windows
            LogManager.log_core("Skipping Dependency Package Update as os = Windows")
        else:
            await DependencyManager.instal_apk_packages()
            await DependencyManager.update_apk_repositories()
            await DependencyManager.update_ia()
            await DependencyManager.update_ytdlp()
            pip_dependencies = json.loads(Config.get_value("Maintenance", "required_dependencies"))
            for dependency in pip_dependencies:
                await DependencyManager.install_pip_dependency(dependency)
            LogManager.log_core("All required dependencies installed/updated successfully.")
        ContainerMaintenance = Config.get_value("Maintenance", "container_maintenance_inf_loop")
        if ContainerMaintenance.lower() == "true":
            LogManager.log_core("Container Maintenance Mode is ON")
            LogManager.log_core("Script Will Loop Forever...")
            # Infinite loop incase we need to access the containers shell
            while True:
                await asyncio.sleep(600000)

        else:
            LogManager.log_core("Starting Dregg's DVR... Am i 4k wecording? Yes im 4k wecording!")

            disable_live_download = Config.get_value("Maintenance", "disable_live_download").lower()
            disable_posted_download = Config.get_value("Maintenance", "disable_posted_download").lower()
            disable_posted_notices_download = Config.get_value("Maintenance", "disable_posted_notices_download").lower()
            disable_live_upload = Config.get_value("Maintenance", "disable_live_upload").lower()
            disable_posted_upload = Config.get_value("Maintenance", "disable_posted_upload").lower()
            disable_live_recovery_download = Config.get_value("Maintenance", "disable_live_recovery_download").lower()

            tasks = []
            if disable_live_download != "true":
                from downloader.livestreams import LivestreamDownloader
                tasks.append(LivestreamDownloader.download_livestreams())
            else:
                LogManager.log_core("Live Download is disabled in INI Maintenance Section. Skipping...")

            if disable_live_recovery_download != "true":
                from downloader.recovery import RecoveryDownloader
                tasks.append(RecoveryDownloader.monitor_recoveryqueue())
            else:
                LogManager.log_core("Live Recovery Download is disabled in INI Maintenance Section. Skipping...")

            if disable_posted_download != "true":
                from downloader.videos import VideoDownloader
                tasks.append(VideoDownloader.download_videos())
            else:
                LogManager.log_core("Posted Download is disabled in INI Maintenance Section. Skipping...")

            if disable_posted_notices_download != "true":
                from downloader.posts import CommunityDownloader
                tasks.append(CommunityDownloader.monitor_channel())
            else:
                LogManager.log_core("Posted Community Message Download is disabled in INI Maintenance Section. Skipping...")

            if disable_live_upload != "true":
                from uploader.livestreams import LiveStreamUploader
                tasks.append(LiveStreamUploader.upload_live_videos())
            else:
                LogManager.log_core("Live Upload is disabled in INI Maintenance Section. Skipping...")

            if disable_posted_upload != "true":
                from uploader.videos import VideoUploader
                tasks.append(VideoUploader.upload_videos())
            else:
                LogManager.log_core("Posted Upload is disabled in INI Maintenance Section. Skipping...")


            if not tasks:
                LogManager.log_core("All Tasks are disabled in INI Maintenance Section. Exiting...")
            else:
                await asyncio.gather(*tasks)

    except Exception as e:
        LogManager.log_core(f"Exception in main:  {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(main())
