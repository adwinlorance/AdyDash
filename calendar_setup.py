from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle
import logging
import json
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

# If modifying these scopes, delete both the local token.pickle and the environment variable
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_local_token_path():
    """Get the path to the local token file"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token.pickle')

def get_local_credentials_path():
    """Get the path to the local credentials file"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')

def get_credentials_from_env():
    """Get credentials from environment variables"""
    try:
        token_pickle_b64 = os.getenv('GOOGLE_TOKEN_PICKLE')
        if not token_pickle_b64:
            logger.error("GOOGLE_TOKEN_PICKLE environment variable not found")
            return None

        token_pickle_data = base64.b64decode(token_pickle_b64)
        creds = pickle.loads(token_pickle_data)
        logger.info("Successfully loaded credentials from environment")
        return creds
    except Exception as e:
        logger.error(f"Error loading credentials from environment: {str(e)}")
        return None

def save_credentials_to_env(creds):
    """Save credentials back to environment variable"""
    try:
        token_pickle = base64.b64encode(pickle.dumps(creds)).decode('utf-8')
        os.environ['GOOGLE_TOKEN_PICKLE'] = token_pickle
        logger.info("Successfully saved credentials to environment")
        return True
    except Exception as e:
        logger.error(f"Error saving credentials to environment: {str(e)}")
        return False

def save_credentials_locally(creds):
    """Save credentials to a local file"""
    try:
        with open(get_local_token_path(), 'wb') as token:
            pickle.dump(creds, token)
        logger.info("Successfully saved credentials locally")
        return True
    except Exception as e:
        logger.error(f"Error saving credentials locally: {str(e)}")
        return False

def refresh_credentials():
    """Refresh the Google Calendar credentials"""
    try:
        creds = get_credentials_from_env()
        if not creds:
            logger.error("No credentials found in environment to refresh")
            return False

        if not creds.expired:
            logger.info("Credentials are still valid, no refresh needed")
            return True

        if not creds.refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            logger.info("Attempting to refresh expired credentials")
            creds.refresh(Request())
            return save_credentials_to_env(creds)
        except Exception as e:
            logger.error(f"Error during credential refresh: {str(e)}")
            return False

    except Exception as e:
        logger.error(f"Error in refresh_credentials: {str(e)}")
        return False

def get_calendar_credentials():
    """Gets valid user credentials from environment variables."""
    try:
        # Get credentials from environment
        creds = get_credentials_from_env()
        if not creds:
            logger.error("Could not load credentials from environment")
            return None

        # Check if credentials need refresh
        if creds.expired and creds.refresh_token:
            logger.info("Credentials expired, attempting refresh")
            if not refresh_credentials():
                logger.error("Failed to refresh credentials")
                return None
            # Get the refreshed credentials
            creds = get_credentials_from_env()

        if not creds or not creds.valid:
            logger.error("No valid credentials available")
            return None

        return creds

    except Exception as e:
        logger.error(f"Error in get_calendar_credentials: {str(e)}")
        return None 