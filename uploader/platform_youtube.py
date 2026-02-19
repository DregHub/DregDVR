import shutil
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
from config_settings import DVR_Config
from config_accounts import Account_Config


async def upload_to_youtube(filepath, filename):
    """Upload a video file to YouTube."""
    media_upload = None
    try:
        LogManager.log_upload_yt(f"Attempting upload of file: {filepath} to YouTube")
        YT_ClientSecretFile = DVR_Config.get_yt_client_secret_file()
        YT_CredentialsFile = DVR_Config.get_yt_credentials_file()
        YT_PrivacyMode = DVR_Config.get_yt_upload_visibility()
        YT_Catagory = DVR_Config.get_yt_upload_catagory()
        storage = Storage(YT_CredentialsFile)
        credentials = storage.get()

        flow = flow_from_clientsecrets(
            YT_ClientSecretFile,
            scope="https://www.googleapis.com/auth/youtube.upload",
            message="Missing client secrets file"
        )

        if credentials is None or getattr(credentials, "invalid", False):
            args = argparser.parse_args([])
            args.noauth_local_webserver = True
            credentials = run_flow(flow, storage, args)

        # Derive a clean title from the provided filename (handle both basename and name-without-ext)
        Title = os.path.splitext(os.path.basename(filename))[0]

        # Build the API client using authorized HTTP
        youtube = build("youtube", "v3", http=credentials.authorize(httplib2.Http()))
        LogManager.log_upload_yt("YoutubeAPI Initialized Successfully")

        Short_Meta_Description = MetaDataManager.read_value("ShortDescription", LogManager.UPLOAD_YT_LOG_FILE)
        CSV_Keywords = MetaDataManager.read_value("CSVTags", LogManager.UPLOAD_YT_LOG_FILE)
        LogManager.log_upload_yt(f"Uploading {Title} to YouTube...")

        # Prepare tags, trimming whitespace and ignoring empty strings
        tags = []
        if CSV_Keywords:
            tags = [t.strip() for t in CSV_Keywords.split(",") if t.strip()]

        media_upload = MediaFileUpload(filepath, chunksize=-1, resumable=True)
        request_body = {
            "snippet": {
                "title": Title,
                "description": Short_Meta_Description,
                "tags": tags,
                "categoryId": str(YT_Catagory),
            },
            "status": {"privacyStatus": str(YT_PrivacyMode)},
        }
        LogManager.log_upload_yt(request_body)
        request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media_upload)
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, request.execute)
        if response:
            LogManager.log_upload_yt(f"Successfully uploaded {Title} to YouTube: {response.get('id')}")
            return True
        else:
            LogManager.log_upload_yt(f"Upload failed for {Title}")
            return False
    except Exception as e:
        LogManager.log_upload_yt(f"Exception in upload_to_youtube: {e}\n{traceback.format_exc()}")
        return False
    finally:
        # Ensure file handle is closed if present
        if media_upload and hasattr(media_upload, "_fd") and media_upload._fd:
            from contextlib import suppress
            with suppress(Exception):
                media_upload._fd.close()
