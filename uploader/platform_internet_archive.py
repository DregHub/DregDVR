import traceback
import asyncio
from datetime import datetime
from utils.logging_utils import LogManager
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


async def login_ia_session(email, password, user_agent, log_file=None):
    """Authenticate with Internet Archive using the Python API."""
    global _ia_session, _ia_authenticated

    try:
        # Check if already logged in
        if _ia_authenticated and _ia_session is not None:
            LogManager.log_message(
                "Already authenticated with Internet Archive. Skipping login.",
                log_file
            )
            return

        if not email or not password:
            raise ValueError("Email and password must be provided via accounts config.")

        LogManager.log_message("Attempting to authenticate with Internet Archive...", log_file)

        try:
            ia.configure(email, password)
        except Exception as config_error:
            _ia_authenticated = False
            _ia_session = None
            LogManager.log_message(
                f"ERROR: ia.configure failed: {config_error}\n email: {email} \n password: {password}  \n {traceback.format_exc()}",
                log_file
            )
            return
        # Verify authentication was successful
        try:
            _ia_session = ia.ArchiveSession()
            _ia_session.headers.update({"User-Agent": user_agent})
            _ia_authenticated = True
            LogManager.log_message(
                "Authentication successful. User Agent set for session.",
                log_file
            )
        except Exception as verify_error:
            _ia_authenticated = False
            _ia_session = None
            raise ValueError(
                f"Authentication succeeded but session verification failed: {verify_error}"
            )

    except Exception as e:
        LogManager.log_message(
            f"ERROR: Failed to establish Internet Archive session: {e}\n{traceback.format_exc()}",
            log_file
        )
        _ia_authenticated = False
        _ia_session = None
        raise


async def upload_to_ia(filepath, filename, title, log_file=None, thread_number=None, uniqueid=None):
    """Upload a video file to Internet Archive using the Python API."""
    global _ia_session, _ia_authenticated

    if thread_number is None:
        thread_number = 1
    try:
        thread_lock = _get_ia_lock(thread_number)
        async with thread_lock:
            LogManager.log_message(f"Starting upload process for: {filepath}", log_file)

            # Retrieve credentials
            try:
                IA_ItemID = Account_Config.get_ia_itemid()
                IA_Email = Account_Config.get_ia_email()
                IA_Password = Account_Config.get_ia_password()
                IA_UserAgent = Account_Config.get_ia_user_agent()

                if not IA_ItemID or not IA_Email or not IA_Password or not IA_UserAgent:
                    LogManager.log_message(
                        "Internet Archive credentials, User Agent, or Item ID missing in config",
                        log_file
                    )
                    return False, "Internet Archive credentials, User Agent, or Item ID missing in config"

                LogManager.log_message(
                    f"Retrieved Internet Archive credentials for item: {IA_ItemID}",
                    log_file
                )
            except Exception as e:
                LogManager.log_message(
                    f"ERROR: Failed to retrieve Internet Archive credentials: {e}",
                    log_file
                )
                return False, f"Failed to retrieve Internet Archive credentials: {e}"

            # Establish session only if not already authenticated
            if not _ia_authenticated:
                try:
                    await login_ia_session(IA_Email, IA_Password, IA_UserAgent, log_file)
                    LogManager.log_message("Internet Archive session established", log_file)
                except Exception as e:
                    LogManager.log_message(
                        f"ERROR: Failed to establish Internet Archive session: {e}",
                        log_file
                    )
                    raise
            else:
                LogManager.log_message("Using existing Internet Archive session", log_file)

            # Get the Internet Archive item using the stored session
            try:
                LogManager.log_message(
                    f"Attempting to retrieve Internet Archive item: {IA_ItemID}",
                    log_file
                )
                item = _ia_session.get_item(IA_ItemID)

                if item is None:
                    raise ValueError(
                        f"Item {IA_ItemID} not found or could not be retrieved"
                    )

                LogManager.log_message(f"Retrieved Internet Archive item: {IA_ItemID}", log_file)
            except Exception as e:
                LogManager.log_message(
                    f"ERROR: Failed to retrieve Internet Archive item {IA_ItemID}: {e}\n{traceback.format_exc()}",
                    log_file
                )
                raise

            # Upload the file
            try:
                LogManager.log_message(
                    f"Uploading file to Internet Archive: {filepath} as {filename}",
                    log_file
                )

                response = item.upload_file(
                    filepath, metadata={"title": filename, "file": filename}, retries=10
                )

                # Check if upload response indicates success
                if response is not None:
                    LogManager.log_message(
                        f"File uploaded to Internet Archive: {filepath}",
                        log_file
                    )
                else:
                    raise ValueError(
                        "Upload returned no response - operation may have failed"
                    )

            except Exception as e:
                LogManager.log_message(
                    f"ERROR: Failed to upload file to Internet Archive: {filepath} - {e}\n{traceback.format_exc()}",
                    log_file
                )
                return False, f"Failed to upload file to Internet Archive: {filepath} - {e}"

            LogManager.log_message(
                f"Completed archive of file: {filepath} to Internet Archive",
                log_file
            )
            return True, None

    except Exception as e:
        LogManager.log_message(
            f"ERROR: Upload process failed for {filepath}: {e}\n{traceback.format_exc()}",
            log_file
        )
        return False, str(e)
