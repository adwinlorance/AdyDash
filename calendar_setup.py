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
        except Exception as e:
            logger.error(f"Error loading credentials from environment: {str(e)}")
    
    # If environment variables didn't work, try local files
    if not creds and os.path.exists('token.pickle'):
        try:
            logger.info("Loading credentials from local token.pickle")
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            logger.error(f"Error loading local token.pickle: {str(e)}")
    
    # If there are no (valid) credentials available, try to refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials")
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error refreshing credentials: {str(e)}")
                return None
        else:
            # Try to get credentials from environment variable
            credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
            if credentials_json:
                try:
                    logger.info("Creating flow from environment credentials")
                    credentials_data = json.loads(credentials_json)
                    flow = InstalledAppFlow.from_client_config(
                        credentials_data, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error creating flow from environment credentials: {str(e)}")
                    return None
            elif os.path.exists('credentials.json'):
                try:
                    logger.info("Creating flow from local credentials.json")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error creating flow from local credentials: {str(e)}")
                    return None
            else:
                logger.error("No credentials available (neither in environment nor local files)")
                return None
        
        # If we got valid credentials, save them to environment if possible
        if creds:
            try:
                token_pickle_data = pickle.dumps(creds)
                token_pickle_b64 = base64.b64encode(token_pickle_data).decode('utf-8')
                logger.info("Generated new token pickle data")
                # Log the new token data (you'll need to add this to your environment variables)
                logger.info("New token data generated. Update your environment variables with:")
                logger.info(f"GOOGLE_TOKEN_PICKLE={token_pickle_b64}")
            except Exception as e:
                logger.error(f"Error saving credentials: {str(e)}")

    return creds 