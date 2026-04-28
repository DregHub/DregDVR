import asyncio
import sys
import traceback
from utils.logging_utils import LogManager,LogLevels


class YTDLPVersionManager:
    """
    Manages switching between stable and nightly versions of yt-dlp.
    On startup, the stable version is used by default.
    """

    _current_version = "stable"  # Default to stable on startup

    @classmethod
    async def switch_stable_dlp(cls):
        """
        Install or upgrade to the stable version of yt-dlp.
        """
        try:
            LogManager.log_core("Switching to stable yt-dlp...", LogLevels.Info)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--root-user-action=ignore",
                "-U",
                "yt-dlp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            output = output.decode()
            LogManager.log_core(output, LogLevels.Info)
            if process.returncode == 0:
                cls._current_version = "stable"
                LogManager.log_core("Successfully switched to stable yt-dlp.", LogLevels.Info)
                return True
            else:
                LogManager.log_core(
                    f"Failed to switch to stable yt-dlp. Return code: {process.returncode}", LogLevels.Error
                )
                return False
        except Exception as e:
            LogManager.log_core(
                f"Failed to switch to stable yt-dlp: {e}\n{traceback.format_exc()}", LogLevels.Error
            )
            return False

    @classmethod
    async def switch_nightly_dlp(cls):
        """
        Install or upgrade to the nightly version of yt-dlp.
        """
        try:
            LogManager.log_core("Switching to nightly yt-dlp...", LogLevels.Info)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--root-user-action=ignore",
                "-U",
                "--pre",
                "yt-dlp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            output = output.decode()
            LogManager.log_core(output, LogLevels.Info)
            if process.returncode == 0:
                cls._current_version = "nightly"
                LogManager.log_core("Successfully switched to nightly yt-dlp.", LogLevels.Info)
                return True
            else:
                LogManager.log_core(
                    f"Failed to switch to nightly yt-dlp. Return code: {process.returncode}", LogLevels.Error
                )
                return False
        except Exception as e:
            LogManager.log_core(
                f"Failed to switch to nightly yt-dlp: {e}\n{traceback.format_exc()}", LogLevels.Error
            )
            return False

    @classmethod
    def get_current_version(cls):
        """
        Get the currently set yt-dlp version (stable or nightly).
        """
        return cls._current_version
