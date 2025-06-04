import base64
import json
import pickle
from google.oauth2.credentials import Credentials
import os

def convert_credentials_to_base64():
    """Convert credentials.json to base64 string"""
    try:
        # Read credentials.json
        with open('credentials.json', 'r') as f:
            creds_json = f.read()
        
        # Convert to base64
        creds_b64 = base64.b64encode(creds_json.encode('utf-8')).decode('utf-8')
        
        print("\nGOOGLE_CREDENTIALS_JSON:")
        print(creds_b64)
        
    except FileNotFoundError:
        print("credentials.json not found in current directory")
    except Exception as e:
        print(f"Error converting credentials: {str(e)}")

def convert_token_to_base64():
    """Convert token.pickle to base64 string"""
    try:
        # Read token.pickle
        with open('token.pickle', 'rb') as f:
            token_data = f.read()
        
        # Convert to base64
        token_b64 = base64.b64encode(token_data).decode('utf-8')
        
        print("\nGOOGLE_TOKEN_PICKLE:")
        print(token_b64)
        
    except FileNotFoundError:
        print("token.pickle not found in current directory")
    except Exception as e:
        print(f"Error converting token: {str(e)}")

if __name__ == "__main__":
    print("Converting Google Calendar credentials to base64 format...")
    convert_credentials_to_base64()
    convert_token_to_base64()
    print("\nCopy these values to your Azure App Service Configuration") 