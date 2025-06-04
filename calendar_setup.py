from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle
import logging
import json
import base64

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def refresh_credentials():
    """Refresh the Google Calendar credentials"""
    try:
        # Get credentials from environment
        token_pickle_b64 = os.getenv('GOOGLE_TOKEN_PICKLE')
        creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        
        if not token_pickle_b64 or not creds_json:
            logger.error("Missing required environment variables for token refresh")
            return False
            
        try:
            # Load credentials from environment
            token_pickle_data = base64.b64decode(token_pickle_b64)
            creds = pickle.loads(token_pickle_data)
            
            # Load client config
            client_config = json.loads(creds_json)
            
            if creds and creds.expired and creds.refresh_token:
                logger.info("Attempting to refresh expired credentials")
                creds.refresh(Request())
                
                # Save refreshed credentials back to environment
                new_token_pickle = base64.b64encode(pickle.dumps(creds)).decode('utf-8')
                os.environ['GOOGLE_TOKEN_PICKLE'] = new_token_pickle
                logger.info("Successfully refreshed and saved new credentials")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error refreshing credentials: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Error in refresh_credentials: {str(e)}")
        return False

def get_calendar_credentials():
    """Gets valid user credentials from storage or from environment variables."""
    creds = None
    
    # Try to get credentials from environment variables first
    token_pickle_b64 = os.getenv('GOOGLE_TOKEN_PICKLE')
    if token_pickle_b64:
        try:
            logger.info("Found token pickle in environment variables")
            token_pickle_data = base64.b64decode(token_pickle_b64)
            creds = pickle.loads(token_pickle_data)
            
            # If credentials are expired, try to refresh them
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired credentials")
                if refresh_credentials():
                    # Reload the refreshed credentials
                    token_pickle_b64 = os.getenv('GOOGLE_TOKEN_PICKLE')
                    token_pickle_data = base64.b64decode(token_pickle_b64)
                    creds = pickle.loads(token_pickle_data)
                else:
                    logger.error("Failed to refresh credentials")
                    return None
            
        except Exception as e:
            logger.error(f"Error loading credentials from environment: {str(e)}")
            return None
    
    return creds 