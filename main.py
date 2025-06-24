import os
import traceback
import asyncio
from utils.logging_utils import LogManager
from config import Config
from utils.dependency_utils import DependencyManager


async def main():
    try:
        if os.name == "nt":
            # Windows
            LogManager.log_core("Skipping Dependence Package Update as os = Windows")
            pass
        else:
            LogManager.log_core("Updating Dependency Packages... This may take some time...")

            await DependencyManager.ensure_python_and_pip()
            await DependencyManager.install_pip_dependency("aiohttp")
            await DependencyManager.install_pip_dependency("aiofiles")
            await DependencyManager.install_pip_dependency("asyncio")
            await DependencyManager.install_pip_dependency("configparser")
            await DependencyManager.install_pip_dependency("oauth2client")
            await DependencyManager.install_pip_dependency("google-api-python-client")
            await DependencyManager.install_pip_dependency("chat-downloader")
            await DependencyManager.update_apk_repositories()
            await DependencyManager.update_ia()
            await DependencyManager.update_ytdlp()

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
            disable_comment_download = Config.get_value("Maintenance", "disable_comment_download").lower()
            disable_posted_download = Config.get_value("Maintenance", "disable_posted_download").lower()
            disable_live_upload = Config.get_value("Maintenance", "disable_live_upload").lower()
            disable_posted_upload = Config.get_value("Maintenance", "disable_posted_upload").lower()

            tasks = []
            if disable_live_download != "true":
                from downloader.livestreams import LivestreamDownloader
                tasks.append(LivestreamDownloader.download_livestreams())
            else:
                LogManager.log_core("Live Download is disabled in INI Maintenance Section. Skipping...")
            if disable_posted_download != "true":
                from downloader.videos import VideoDownloader
                tasks.append(VideoDownloader.download_videos())
            else:
                LogManager.log_core("Posted Download is disabled in INI Maintenance Section. Skipping...")
            if disable_comment_download != "true":
                from downloader.comments import LiveCommentsDownloader
                tasks.append(LiveCommentsDownloader.download_comments())
            else:
                LogManager.log_core("Comment Download is disabled in INI Maintenance Section. Skipping...")
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
