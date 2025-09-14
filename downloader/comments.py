import os
import traceback
import asyncio
from datetime import datetime
from chat_downloader import ChatDownloader
from config import Config
from utils.logging_utils import LogManager
from utils.index_utils import IndexManager
from downloader.livestreams import LivestreamDownloader

# Import specific chat_downloader errors
try:
    from chat_downloader.errors import NoChatReplay, VideoUnavailable
except ImportError:
    NoChatReplay = VideoUnavailable = Exception  # fallback if not available


class LiveCommentsDownloader:
    DownloadFilePrefix = Config.get_live_downloadprefix()
    DownloadTimeStampFormat = Config.get_download_timestamp_format()
    Live_Comments_Dir = Config.get_live_comments_dir()
    _download_lock = asyncio.Lock()

    @classmethod
    async def download_comments(cls, youtube_video):
        async with cls._download_lock:
            try:
                CurrentIndex = IndexManager.find_new_live_index(LogManager.DOWNLOAD_LIVE_LOG_FILE)
                yturl = str("https://www.youtube.com/watch?v=" + youtube_video)
                LogManager.log_download_comments(f"Starting Live Comment Monitor for {yturl}")
                CurrentTime = datetime.now().strftime("%d-%m-%Y %I-%M%p")
                LiveChat_FileName = f"{CurrentIndex} {cls.DownloadFilePrefix} {CurrentTime}.txt"
                LiveChat_File = os.path.join(cls.Live_Comments_Dir, LiveChat_FileName)
                os.makedirs(cls.Live_Comments_Dir, exist_ok=True)

                # Run the blocking chat download in a thread
                def collect_comments():
                    try:
                        chat = ChatDownloader().get_chat(yturl)
                        if chat is not None:
                            try:
                                for message in chat:
                                    try:
                                        formatted_message = chat.format(message)
                                        if formatted_message:  # Only write non-empty messages
                                            with open(LiveChat_File, "a", encoding="utf-8") as f:
                                                f.write(formatted_message + "\n")
                                    except Exception as msg_exc:
                                        LogManager.log_download_comments(f"Exception formatting/writing message: {msg_exc}\n{traceback.format_exc()}")
                            except PermissionError as perm_exc:
                                LogManager.log_download_comments(f"Ignored PermissionError during chat iteration: {perm_exc}\n{traceback.format_exc()}")
                            except Exception as iter_exc:
                                # Silently ignore "this channel has no videos of the requested type"
                                if "this channel has no videos of the requested type" in str(iter_exc).lower():
                                    return
                                else:
                                    LogManager.log_download_comments(f"Unexpected error during chat iteration: {iter_exc}\n{traceback.format_exc()}")
                        else:
                            LogManager.log_download_comments(f"ChatDownloader.get_chat returned None for url: {yturl}")
                    except NoChatReplay as ncr_exc:
                        LogManager.log_download_comments(f"No chat replay available for this video: {ncr_exc}")
                        return
                    except VideoUnavailable as vu_exc:
                        LogManager.log_download_comments(f"Video unavailable: {vu_exc}")
                        return
                    except Exception as chat_exc:
                        LogManager.log_download_comments(f"Exception initializing chat: {chat_exc}\n{traceback.format_exc()}")

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, collect_comments)

                await asyncio.sleep(30)
            except Exception as e:
                if "channel has no videos of the requested type" in str(e).lower():
                    return
                else:
                    LogManager.log_download_comments(f"Exception in download_comments:  {e}\n{traceback.format_exc()}")
                    await asyncio.sleep(30)
