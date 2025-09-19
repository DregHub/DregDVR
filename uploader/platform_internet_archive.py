import os
import traceback
from datetime import datetime
from utils.logging_utils import LogManager
from utils.subprocess_utils import run_subprocess
from config_settings import DVR_Config
from config_accounts import Account_Config

IA_LastSessionTime = None


def write_netrc(email, password):
    """Write credentials to the .netrc/_netrc file for IA CLI authentication."""
    # Windows uses '_netrc', others use '.netrc'
    netrc_filename = "_netrc" if os.name == "nt" else ".netrc"
    netrc_path = os.path.join(os.path.expanduser("~"), netrc_filename)
    machine = "archive.org"
    content = f"machine {machine}\n  login {email}\n  password {password}\n"
    with open(netrc_path, "w") as f:
        f.write(content)
    try:
        os.chmod(netrc_path, 0o600)
    except Exception as e:
        LogManager.log_upload_ia("IA Login error. {e}\n{traceback.format_exc()}")


async def login_ia_session(email, password):
    global IA_LastSessionTime
    current_time = datetime.now()

    if (
        IA_LastSessionTime
        and (current_time - IA_LastSessionTime).total_seconds() < 86400
    ):
        LogManager.log_upload_ia("Login attempt skipped. Already logged in within the last 24 hours.")
        return

    try:
        write_netrc(email, password)
        LogManager.log_upload_ia("Internet Archive session established successfully (via .netrc/_netrc).")
        IA_LastSessionTime = current_time
    except Exception as e:
        LogManager.log_upload_ia(f"Failed to establish Internet Archive session: {e}\n{traceback.format_exc()}")


async def upload_to_ia(filepath, filename):
    """Upload a video file to Internet Archive."""
    try:
        IA_ItemID = Account_Config.get_ia_itemid()
        IA_Email = Account_Config.get_ia_email()
        IA_Password = Account_Config.get_ia_password()
        await login_ia_session(IA_Email, IA_Password)
        LogManager.log_upload_ia(f"Attempting archive of file: {filepath} to InternetArchive")

        command = [
            "ia",
            "upload",
            f"{IA_ItemID}",
            f'"{filepath}"',
            "--retries",
            "10",
            f"--metadata='title:{filename},file:{filename}'",
        ]

        await run_subprocess(
            command,
            LogManager.UPLOAD_IA_LOG_FILE,
            "IA archive command failed",
            "Exception in IA",
        )

        LogManager.log_upload_ia(f"Completed archive of file: {filepath} to InternetArchive")
    except Exception as e:
        LogManager.log_upload_ia(f"Failed to archive {filepath} to InternetArchive {e}\n{traceback.format_exc()}")
