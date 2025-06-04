from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import pickle
import base64
import os

# If modifying these scopes, delete the token.pickle file.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def setup_calendar_credentials():
    """Set up Google Calendar credentials using local OAuth flow."""
    try:
        # Check if credentials.json exists
        if not os.path.exists('credentials.json'):
            print("Error: credentials.json not found!")
            print("Please download your OAuth 2.0 credentials from Google Cloud Console")
            print("and save them as 'credentials.json' in this directory.")
            return False

        # Create the flow using client secrets file
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        
        # Run the local server flow
        print("\nOpening browser for Google OAuth authentication...")
        creds = flow.run_local_server(port=0)

        # Save the credentials to token.pickle
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
        print("\nCredentials saved successfully!")

        # Now convert both files to base64 for Azure
        # Convert credentials.json
        with open('credentials.json', 'r') as f:
            creds_json = f.read()
        creds_b64 = base64.b64encode(creds_json.encode('utf-8')).decode('utf-8')
        
        # Convert token.pickle
        with open('token.pickle', 'rb') as f:
            token_data = f.read()
        token_b64 = base64.b64encode(token_data).decode('utf-8')

        print("\n=== Azure App Service Configuration Values ===")
        print("\nGOOGLE_CREDENTIALS_JSON:")
        print(creds_b64)
        print("\nGOOGLE_TOKEN_PICKLE:")
        print(token_b64)
        print("\nPlease copy these values to your Azure App Service Configuration")
        return True

    except Exception as e:
        print(f"Error setting up credentials: {str(e)}")
        return False

if __name__ == "__main__":
    print("Setting up Google Calendar credentials...")
    setup_calendar_credentials() 