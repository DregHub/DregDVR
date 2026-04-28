import traceback
import asyncio
from utils.logging_utils import LogManager, LogLevels
from config.config_settings import DVR_Config
from config.config_accounts import Account_Config
import internetarchive as ia

# Global session variables
_ia_session = None
_ia_authenticated = False
# Thread-specific upload locks to allow concurrent uploads across different threads
_ia_upload_locks = {}  # {thread_number: asyncio.Lock()}


def _get_ia_lock(thread_number=None):
    """Get or create a lock for a specific thread."""
    if thread_number is None:
        thread_number = 1

    if thread_number not in _ia_upload_locks:
        _ia_upload_locks[thread_number] = asyncio.Lock()

    return _ia_upload_locks[thread_number]


async def login_ia_session(email, password, user_agent, log_table=None):
    """Authenticate with Internet Archive using the Python API."""
    global _ia_session, _ia_authenticated

    try:
        # Check if already logged in
        if _ia_authenticated and _ia_session is not None:
            LogManager.log_upload_ia(
                "Already authenticated with Internet Archive. Skipping login.",
                LogLevels.Debug,
            )
            return

        if not email or not password:
            raise ValueError("Email and password must be provided via accounts config.")

        LogManager.log_upload_ia(
            "Attempting to authenticate with Internet Archive...", LogLevels.Info
        )

        try:
            ia.configure(email, password)
        except Exception as config_error:
            _ia_authenticated = False
            _ia_session = None
            LogManager.log_upload_ia(
                f"ERROR: ia.configure failed: {config_error}\n email: {email} \n password: {password}  \n {traceback.format_exc()}",
                LogLevels.Error,
            )
            return
        # Verify authentication was successful
        try:
            _ia_session = ia.ArchiveSession()
            _ia_session.headers.update({"User-Agent": user_agent})
            _ia_authenticated = True
            LogManager.log_upload_ia(
                "Authentication successful. User Agent set for session.", LogLevels.Info
            )
        except Exception as verify_error:
            _ia_authenticated = False
            _ia_session = None
            raise ValueError(
                f"Authentication succeeded but session verification failed: {verify_error}",
                LogLevels.Error,
            )

    except Exception as e:
        LogManager.log_upload_ia(
            f"ERROR: Failed to establish Internet Archive session: {e}\n{traceback.format_exc()}",
            LogLevels.Error,
        )
        _ia_authenticated = False
        _ia_session = None
        raise


async def upload_to_ia(
    filepath, filename, title, log_table=None, thread_number=None, unique_id=None
):
    """Upload a video file to Internet Archive using the Python API."""
    global _ia_session, _ia_authenticated

    if thread_number is None:
        thread_number = 1
    try:
        thread_lock = _get_ia_lock(thread_number)
        async with thread_lock:
            LogManager.log_upload_ia(f"Starting upload process for: {filepath}")

            # Retrieve credentials
            try:
                IA_ItemID = await Account_Config.get_ia_itemid()
                IA_Email = await Account_Config.get_ia_email()
                IA_Password = await Account_Config.get_ia_password()
                IA_UserAgent = await Account_Config.get_ia_user_agent()

                if not IA_ItemID or not IA_Email or not IA_Password or not IA_UserAgent:
                    LogManager.log_upload_ia(
                        "Internet Archive credentials, User Agent, or Item ID missing in config",
                        LogLevels.Info,
                    )
                    return (
                        False,
                        "Internet Archive credentials, User Agent, or Item ID missing in config",
                    )

                LogManager.log_upload_ia(
                    f"Retrieved Internet Archive credentials for item: {IA_ItemID}",
                    LogLevels.Info,
                )
            except Exception as e:
                LogManager.log_upload_ia(
                    f"ERROR: Failed to retrieve Internet Archive credentials: {e}",
                    LogLevels.Error,
                )
                return False, f"Failed to retrieve Internet Archive credentials: {e}"

            # Establish session only if not already authenticated
            if not _ia_authenticated:
                try:
                    await login_ia_session(
                        IA_Email, IA_Password, IA_UserAgent, log_table
                    )
                    LogManager.log_upload_ia(
                        "Internet Archive session established", LogLevels.info
                    )
                except Exception as e:
                    LogManager.log_upload_ia(
                        f"ERROR: Failed to establish Internet Archive session: {e}",
                        LogLevels.Error,
                    )
                    raise
            else:
                LogManager.log_upload_ia("Using existing Internet Archive session")

            # Get the Internet Archive item using the stored session
            try:
                LogManager.log_upload_ia(
                    f"Attempting to retrieve Internet Archive item: {IA_ItemID}",
                    LogLevels.Info,
                )
                item = _ia_session.get_item(IA_ItemID)

                if item is None:
                    raise ValueError(
                        f"Item {IA_ItemID} not found or could not be retrieved"
                    )

                LogManager.log_upload_ia(
                    f"Retrieved Internet Archive item: {IA_ItemID}", LogLevels.Info
                )
            except Exception as e:
                LogManager.log_upload_ia(
                    f"ERROR: Failed to retrieve Internet Archive item {IA_ItemID}: {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )
                raise

            # Upload the file
            try:
                LogManager.log_upload_ia(
                    f"Uploading file to Internet Archive: {filepath} as {filename}",
                    LogLevels.Info,
                )

                response = item.upload_file(
                    filepath, metadata={"title": filename, "file": filename}, retries=10
                )

                # Check if upload response indicates success
                if response is not None:
                    LogManager.log_upload_ia(
                        f"File uploaded to Internet Archive: {filepath}", LogLevels.info
                    )
                else:
                    raise ValueError(
                        "Upload returned no response - operation may have failed"
                    )

            except Exception as e:
                LogManager.log_upload_ia(
                    f"ERROR: Failed to upload file to Internet Archive: {filepath} - {e}\n{traceback.format_exc()}",
                    LogLevels.Error,
                )
                return (
                    False,
                    f"Failed to upload file to Internet Archive: {filepath} - {e}",
                )

            LogManager.log_upload_ia(
                f"Completed archive of file: {filepath} to Internet Archive",
                LogLevels.Info,
            )
            return True, None

    except Exception as e:
        LogManager.log_upload_ia(
            f"ERROR: Upload process failed for {filepath}: {e}\n{traceback.format_exc()}",
            LogLevels.Error,
        )
        return False, str(e)
