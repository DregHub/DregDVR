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
from config import Config


async def upload_to_youtube(filepath, filename):
    """Upload a video file to YouTube."""
    media_upload = None
    try:
        LogManager.log_upload_yt(f"Attempting upload of file: {filepath} to YouTube")
        AuthDirName = Config.get_value("Directories", "Auth_Dir")
        AuthDir = os.path.join(Config.ProjRoot_Dir, AuthDirName)

        YT_ClientSecretFile = os.path.join(AuthDir, "YT-client_secret.json")
        YT_CredentialsFile = os.path.join(AuthDir, "YT-oauth2.json")

        storage = Storage(YT_CredentialsFile)
        credentials = storage.get()

        flow = flow_from_clientsecrets(
            YT_ClientSecretFile,
            scope="https://www.googleapis.com/auth/youtube.upload",
            message="Missing client secrets file"
        )

        if credentials is None or credentials.invalid:
            args = argparser.parse_args([])
            args.noauth_local_webserver = True
            credentials = run_flow(flow, storage, args)

        youtube = build("youtube", "v3", http=credentials.authorize(httplib2.Http()))
        LogManager.log_upload_yt("YoutubeAPI Initialized Successfully")

        Short_Meta_Description = MetaDataManager.read_value("ShortDescription", LogManager.UPLOAD_YT_LOG_FILE)
        CSV_Keywords = MetaDataManager.read_value("CSVTags", LogManager.UPLOAD_YT_LOG_FILE)
        Title = filename.replace(".mp4", "")
        LogManager.log_upload_yt(f"Uploading {Title} to YouTube...")

        media_upload = MediaFileUpload(filepath, chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": Title,
                    "description": Short_Meta_Description,
                    "tags": CSV_Keywords.split(",") if CSV_Keywords else [],
                    "categoryId": "22",
                },
                "status": {"privacyStatus": "public"},
            },
            media_body=media_upload,
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, request.execute)
        if response:
            LogManager.log_upload_yt(f"Successfully uploaded {Title} to YouTube: {response['id']}")
            if media_upload and hasattr(media_upload, '_fd') and media_upload._fd:
                from contextlib import suppress
                with suppress(Exception):
                    media_upload._fd.close()
            return True
        else:
            LogManager.log_upload_yt(f"Upload failed for {Title}")
            return False
    except Exception as e:
        LogManager.log_upload_yt(f"Exception in upload_to_youtube: {e}\n{traceback.format_exc()}")
        return False
    finally:
        # Ensure file handle is closed if present
        if media_upload and hasattr(media_upload, '_fd') and media_upload._fd:
            from contextlib import suppress
            with suppress(Exception):
                media_upload._fd.close()
