import asyncio
import sys
import os
import traceback
import aiohttp
import aiofiles
import tarfile
import tempfile
import shutil
from utils.logging_utils import LogManager
from config_settings import DVR_Config


class DependencyManager:
    bin_dir = DVR_Config.get_bin_dir()

    @classmethod
    async def install_pip_dependency(cls, package_name):
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--root-user-action=ignore", package_name,
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
    async def update_apk_repositories(cls):
        """
        Replace 'dl-cdn.alpinelinux.org/alpine' with
        'mirror1.hs-esslingen.de/pub/Mirrors/alpine' in /etc/apk/repositories.
        Log the contents of /etc/apk/repositories before and after modification.
        """
        old = "dl-cdn.alpinelinux.org/alpine"
        new = "mirror1.hs-esslingen.de/pub/Mirrors/alpine"
        repo_file = "/etc/apk/repositories"

        try:
            # Log the contents before modification
            async with aiofiles.open(repo_file, "r") as file:
                before_lines = await file.readlines()

            changed = False
            new_lines = []
            for line in before_lines:
                if old in line:
                    new_lines.append(line.replace(old, new))
                    changed = True
                else:
                    new_lines.append(line)

            if changed:
                async with aiofiles.open(repo_file, "w") as file:
                    await file.writelines(new_lines)
                proc = await asyncio.create_subprocess_exec(
                    "apk", "update",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )
                await proc.communicate()
                LogManager.log_core("APK repositories updated to Esslingen University of Applied Sciences mirror.")
            else:
                LogManager.log_core(
                    "No changes made to APK repositories (already using Esslingen mirror or custom repos).")

            # Log the contents after modification
            async with aiofiles.open(repo_file, "r") as file:
                after_lines = await file.readlines()
            LogManager.log_core("Contents of /etc/apk/repositories AFTER modification:\n" + "".join(after_lines))
        except Exception as e:
            LogManager.log_core(f"An error occurred: {e}")

    @classmethod
    async def instal_apk_packages(cls):
        """
        Ensure build dependencies, python3 and py3-pip are installed via apk, and wheel is installed via pip.
        """
        try:
            # Install build dependencies first
            process_build = await asyncio.create_subprocess_exec(
                "apk", "add", "--no-cache", "gcc", "musl-dev", "python3-dev", "libffi-dev", "ffmpeg",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output_build, _ = await process_build.communicate()
            output_build = output_build.decode()
            LogManager.log_core("apk add build dependencies output:\n" + output_build)
            if process_build.returncode != 0:
                LogManager.log_core(f"Failed to install build dependencies. Return code: {process_build.returncode}")
                return

            # Install python3 and py3-pip using apk
            process_apk = await asyncio.create_subprocess_exec(
                "apk", "add", "--update-cache", "python3", "py3-pip",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            output_apk, _ = await process_apk.communicate()
            output_apk = output_apk.decode()
            LogManager.log_core("apk add output:\n" + output_apk)
            if process_apk.returncode != 0:
                LogManager.log_core(f"Failed to install python3/py3-pip. Return code: {process_apk.returncode}")
                return

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
    async def update_ia(cls):
        """Install and update the latest ia tool from archive.org."""
        try:
            ia_url = "https://archive.org/download/ia-pex/ia"
            ia_path = os.path.join(cls.bin_dir, "ia")
            async with aiohttp.ClientSession() as session:
                async with session.get(ia_url) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(ia_path, mode='wb') as f:
                            await f.write(await resp.read())
                        os.chmod(ia_path, 0o755)  # Make the file executable
                        LogManager.log_core("Downloaded and updated the ia tool.")
                    else:
                        LogManager.log_core(f"Failed to download IA tool: HTTP {resp.status}")
        except Exception as e:
            LogManager.log_core(f"Failed to update IA tool: {e}\n{traceback.format_exc()}")

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
