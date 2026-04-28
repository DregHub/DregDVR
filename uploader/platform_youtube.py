import traceback
import httplib2
import os
import asyncio
from oauth2client.tools import argparser
from oauth2client.tools import run_flow
from oauth2client.file import Storage
from oauth2client.client import flow_from_clientsecrets
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from utils.logging_utils import LogManager
from utils.meta_utils import MetaDataManager
from config.config_settings import DVR_Config

# Thread-specific upload locks to allow concurrent uploads across different threads
_yt_upload_locks = {}  # {thread_number: asyncio.Lock()}


def _get_yt_lock(thread_number=None):
    """Get or create a lock for a specific thread."""
    if thread_number is None:
        thread_number = 1

    if thread_number not in _yt_upload_locks:
        _yt_upload_locks[thread_number] = asyncio.Lock()

    return _yt_upload_locks[thread_number]


async def upload_to_youtube(
    filepath, filename, title, log_table=None, thread_number=None, unique_id=None
):
    """Upload a video file to YouTube."""
    media_upload = None
    if thread_number is None:
        thread_number = 1
    try:
        thread_lock = _get_yt_lock(thread_number)
        async with thread_lock:
            LogManager.log_upload_yt(
                f"Attempting upload of file: {filepath} to YouTube"
            )
            YT_ClientSecretFile = DVR_Config.get_yt_client_secret_file()
            YT_CredentialsFile = DVR_Config.get_yt_credentials_file()
            YT_PrivacyMode = DVR_Config.get_upload_visibility()
            YT_Catagory = DVR_Config.get_upload_category()
            storage = Storage(YT_CredentialsFile)
            credentials = storage.get()

            flow = flow_from_clientsecrets(
                YT_ClientSecretFile,
                scope="https://www.googleapis.com/auth/youtube.upload",
                message="Missing client secrets file",
            )

            if credentials is None or getattr(credentials, "invalid", False):
                args = argparser.parse_args([])
                args.noauth_local_webserver = True
                credentials = run_flow(flow, storage, args)

            # Derive a clean title from the provided filename (handle both basename and name-without-ext)
            Title = title if title else os.path.splitext(os.path.basename(filename))[0]

            # Build the API client using authorized HTTP
            youtube = build(
                "youtube", "v3", http=credentials.authorize(httplib2.Http())
            )
            LogManager.log_upload_yt("YoutubeAPI Initialized Successfully")

            description = MetaDataManager.read_value(
                "Description",
                "_Youtube",
                log_table or LogManager.table_upload_platform_yt,
            )
            CSV_Keywords = MetaDataManager.read_value(
                "Tags", "_Youtube", log_table or LogManager.table_upload_platform_yt
            )
            LogManager.log_upload_yt(f"Uploading {Title} to YouTube...")

            # Prepare tags, trimming whitespace and ignoring empty strings
            tags = []
            if CSV_Keywords:
                tags = [t.strip() for t in CSV_Keywords.split(",") if t.strip()]

            media_upload = MediaFileUpload(filepath, chunksize=-1, resumable=True)
            request_body = {
                "snippet": {
                    "title": Title,
                    "description": description,
                    "tags": tags,
                    "categoryId": str(YT_Catagory),
                },
                "status": {"privacyStatus": str(YT_PrivacyMode)},
            }
            # LogManager.log_upload_yt(request_body)
            request = youtube.videos().insert(
                part="snippet,status", body=request_body, media_body=media_upload
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, request.execute)
            if response:
                LogManager.log_upload_yt(
                    f"Successfully uploaded {Title} to YouTube: {response.get('id')}"
                )
                return True, None
            else:
                LogManager.log_upload_yt(f"Upload failed for {Title}")
                return False, "Upload failed"
    except Exception as e:
        LogManager.log_upload_yt(
            f"Exception in upload_to_youtube: {e}\n{traceback.format_exc()}"
        )
        return False, str(e)
    finally:
        # Ensure file handle is closed if present
        if media_upload and hasattr(media_upload, "_fd") and media_upload._fd:
            from contextlib import suppress

            with suppress(Exception):
                media_upload._fd.close()
