import os
import traceback
import asyncio
import json
from utils.logging_utils import LogManager
from config_settings import DVR_Config
from config_tasks import DVR_Tasks
from utils.dependency_utils import DependencyManager


async def main():
    try:
        ProjRoot_Dir = ProjRoot_Dir = os.path.dirname(os.path.abspath(__file__))
        print(f"Project Root Directory: {ProjRoot_Dir}")
        os.makedirs(ProjRoot_Dir, exist_ok=True)
        root_dirs_to_create = json.loads(DVR_Config.get_value("Directories", "root_dirs_to_create"))
        dvr_subdirs_to_create = json.loads(DVR_Config.get_value("Directories", "dvr_subdirs_to_create"))
        for dir in root_dirs_to_create:
            newdir = os.path.join(ProjRoot_Dir, dir)
            print(f"making new root subdirectory: {newdir}")
            os.makedirs(newdir, exist_ok=True)
        for dir in dvr_subdirs_to_create:
            newdir = os.path.join(DVR_Config.get_download_root(), dir)
            print(f"making new dvr subdirectory: {newdir}")
            os.makedirs(newdir, exist_ok=True)
        print("Created required directories successfully.")
            
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

            await DependencyManager.update_ia()
            await DependencyManager.update_ytdlp()
                
            LogManager.log_core("All required dependencies installed/updated successfully.")
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
