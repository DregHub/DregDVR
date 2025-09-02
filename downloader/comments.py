import os
import traceback
import asyncio
from datetime import datetime
from chat_downloader import ChatDownloader
from config import Config
from utils.logging_utils import LogManager
from utils.index_utils import IndexManager
from downloader.livestreams import LivestreamDownloader


class LiveCommentsDownloader:
    youtube_source = Config.get_youtube_source()
    DownloadFilePrefix = Config.get_live_downloadprefix()
    DownloadTimeStampFormat = Config.get_download_timestamp_format()
    Live_Comments_Dir = Config.get_live_comments_dir()
    _download_lock = asyncio.Lock()

    @classmethod
    async def download_comments(cls):
        async with cls._download_lock:
            while True:
                try:
                    CurrentIndex = IndexManager.find_new_live_index(LogManager.DOWNLOAD_LIVE_LOG_FILE)
                    YT_Handle = LivestreamDownloader.extract_username(cls.youtube_source)
                    LogManager.log_download_comments(f"Starting Live Comment Monitor for {YT_Handle}")
                    CurrentTime = datetime.now().strftime("%d-%m-%Y %I-%M%p")
                    LiveChat_FileName = f"{CurrentIndex} {cls.DownloadFilePrefix} {CurrentTime}.txt"
                    LiveChat_File = os.path.join(cls.Live_Comments_Dir, LiveChat_FileName)
                    yturl = str(cls.youtube_source)
                    os.makedirs(cls.Live_Comments_Dir, exist_ok=True)

                    # Run the blocking chat download in a thread
                    def collect_comments():
                        try:
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
                            except Exception as chat_exc:
                                LogManager.log_download_comments(f"Exception initializing chat: {chat_exc}\n{traceback.format_exc()}")

                        except Exception as chat_exc:
                            # Silently ignore "this channel has no videos of the requested type"
                            if "this channel has no videos of the requested type" in str(chat_exc).lower():
                                return
                            else:
                                LogManager.log_download_comments(f"Exception in collect_comments: {chat_exc}\n{traceback.format_exc()}")

                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, collect_comments)

                    await asyncio.sleep(30)
                except Exception as e:
                    if "channel has no videos of the requested type" in str(e).lower():
                        await asyncio.sleep(30)
                        continue
                    else:
                        LogManager.log_download_comments(f"Exception in download_comments:  {e}\n{traceback.format_exc()}")
                        await asyncio.sleep(30)
