import traceback
from datetime import datetime
from utils.logging_utils import LogManager
from config_accounts import Account_Config
import internetarchive as ia

# Global session variables
_ia_session = None
_ia_authenticated = False

async def login_ia_session(email, password, user_agent):
    """Authenticate with Internet Archive using the Python API."""
    global _ia_session, _ia_authenticated
    
    try:
        # Check if already logged in
        if _ia_authenticated and _ia_session is not None:
            LogManager.log_upload_ia("Already authenticated with Internet Archive. Skipping login.")
            return

        if not email or not password:
            raise ValueError("Email and password must be provided via accounts config.")
        
        LogManager.log_upload_ia("Attempting to authenticate with Internet Archive...")
        ia.configure(email, password)
        # Verify authentication was successful
        try:
            _ia_session = ia.ArchiveSession()
            _ia_session.headers.update({'User-Agent': user_agent})
            _ia_authenticated = True
            LogManager.log_upload_ia("Authentication successful. User Agent set for session.")
        except Exception as verify_error:
            _ia_authenticated = False
            _ia_session = None
            raise ValueError(f"Authentication succeeded but session verification failed: {verify_error}")
            
    except Exception as e:
        LogManager.log_upload_ia(f"ERROR: Failed to establish Internet Archive session: {e}\n{traceback.format_exc()}")
        _ia_authenticated = False
        _ia_session = None
        raise


async def upload_to_ia(filepath, filename):
    """Upload a video file to Internet Archive using the Python API."""
    global _ia_session, _ia_authenticated
    
    try:
        LogManager.log_upload_ia(f"Starting upload process for: {filepath}")
        
        # Retrieve credentials
        try:
            IA_ItemID = Account_Config.get_ia_itemid()
            IA_Email = Account_Config.get_ia_email()
            IA_Password = Account_Config.get_ia_password()
            IA_UserAgent = Account_Config.get_ia_user_agent()
            
            if not IA_ItemID or not IA_Email or not IA_Password or not IA_UserAgent:
                raise ValueError("Internet Archive credentials, User Agent, or Item ID missing in config")
            
            LogManager.log_upload_ia(f"Retrieved Internet Archive credentials for item: {IA_ItemID}")
        except Exception as e:
            LogManager.log_upload_ia(f"ERROR: Failed to retrieve Internet Archive credentials: {e}")
            raise

        # Establish session only if not already authenticated
        if not _ia_authenticated:
            try:
                await login_ia_session(IA_Email, IA_Password, IA_UserAgent)
                LogManager.log_upload_ia("Internet Archive session established")
            except Exception as e:
                LogManager.log_upload_ia(f"ERROR: Failed to establish Internet Archive session: {e}")
                raise
        else:
            LogManager.log_upload_ia("Using existing Internet Archive session")

        # Get the Internet Archive item using the stored session
        try:
            LogManager.log_upload_ia(f"Attempting to retrieve Internet Archive item: {IA_ItemID}")
            item = _ia_session.get_item(IA_ItemID)
            
            if item is None:
                raise ValueError(f"Item {IA_ItemID} not found or could not be retrieved")
            
            LogManager.log_upload_ia(f"Retrieved Internet Archive item: {IA_ItemID}")
        except Exception as e:
            LogManager.log_upload_ia(f"ERROR: Failed to retrieve Internet Archive item {IA_ItemID}: {e}\n{traceback.format_exc()}")
            raise

        # Upload the file
        try:
            LogManager.log_upload_ia(f"Uploading file to Internet Archive: {filepath} as {filename}")
            
            response = item.upload_file(
                filepath,
                metadata={
                    'title': filename,
                    'file': filename
                },
                retries=10
            )
            
            # Check if upload response indicates success
            if response is not None:
                LogManager.log_upload_ia(f"File uploaded to Internet Archive: {filepath}")
            else:
                raise ValueError("Upload returned no response - operation may have failed")
                
        except Exception as e:
            LogManager.log_upload_ia(f"ERROR: Failed to upload file to Internet Archive: {filepath} - {e}\n{traceback.format_exc()}")
            raise
            
        LogManager.log_upload_ia(f"Completed archive of file: {filepath} to Internet Archive")
        
    except Exception as e:
        LogManager.log_upload_ia(f"ERROR: Upload process failed for {filepath}: {e}\n{traceback.format_exc()}")
        raise
