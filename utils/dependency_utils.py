import asyncio
import sys
import traceback
from utils.logging_utils import LogManager

class DependencyManager:

    @classmethod
    async def install_apk_dependency(cls, package_name):
        try:
            process_apk = await asyncio.create_subprocess_exec(
                "apk", "add", "--update-cache", package_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output_apk, _ = await process_apk.communicate()
            output_apk = output_apk.decode()
            LogManager.log_core("apk add output:\n" + output_apk)
            if process_apk.returncode != 0:
                LogManager.log_core(f"Failed to install {package_name}. Return code: {process_apk.returncode}")
                return False
            else:
                LogManager.log_core(f"{package_name} installed successfully. Return code: {process_apk.returncode}")
                return True
        except Exception as e:
            LogManager.log_core(f"Failed to install {package_name}:  {e}\n{traceback.format_exc()}")
            return False
 
    @classmethod
    async def install_pip_dependency(cls, package_name):
        try:
            # Ensure pip itself is up-to-date before installing the requested package
            process_upgrade = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--upgrade", "--root-user-action=ignore", "pip",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output_upgrade, _ = await process_upgrade.communicate()
            output_upgrade = output_upgrade.decode()
            LogManager.log_core("pip upgrade output:\n" + output_upgrade)
            if process_upgrade.returncode != 0:
                LogManager.log_core(f"Failed to upgrade pip. Return code: {process_upgrade.returncode}")

            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--upgrade", "--root-user-action=ignore", package_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output, _ = await process.communicate()
            output = output.decode()
            LogManager.log_core(output)
            if process.returncode == 0:
                LogManager.log_core(f"{package_name} installed/updated successfully.")
            else:
                LogManager.log_core(f"Failed to install {package_name}. Return code: {process.returncode}")
        except Exception as e:
            LogManager.log_core(f"Failed to install {package_name}:  {e}\n{traceback.format_exc()}")

    @classmethod
    async def install_apk_packages(cls):
        """
        Ensure build dependencies, python3 and py3-pip are installed via apk, and wheel is installed via pip.
        """
        try:
            # Install wheel using pip
            process_pip = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--root-user-action=ignore", "--upgrade", "wheel",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output_pip, _ = await process_pip.communicate()
            output_pip = output_pip.decode()
            LogManager.log_core("pip install wheel output:\n" + output_pip)
            if process_pip.returncode != 0:
                LogManager.log_core(f"Failed to install wheel. Return code: {process_pip.returncode}")
        except Exception as e:
            LogManager.log_core(f"Failed to ensure python3, pip, and wheel: {e}\n{traceback.format_exc()}")

    @classmethod
    async def update_ytdlp(cls):
        """Install or update yt-dlp using pip."""
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--root-user-action=ignore", "-U", "--pre", 'yt-dlp[default]',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output, _ = await process.communicate()
            output = output.decode()
            LogManager.log_core(output)
            if process.returncode == 0:
                LogManager.log_core("yt-dlp installed/updated successfully.")
            else:
                LogManager.log_core(f"Failed to install yt-dlp. Return code: {process.returncode}")
        except Exception as e:
            LogManager.log_core(f"Failed to install yt-dlp:  {e}\n{traceback.format_exc()}")
