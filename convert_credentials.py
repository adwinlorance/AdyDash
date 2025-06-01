import base64
import json
import os

def convert_credentials():
    # Convert token.pickle to base64
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            token_pickle_data = f.read()
            token_b64 = base64.b64encode(token_pickle_data).decode('utf-8')
            print("\n=== GOOGLE_TOKEN_PICKLE ===")
            print(token_b64)
    else:
        print("token.pickle not found!")

    # Convert credentials.json to string
    if os.path.exists('credentials.json'):
        with open('credentials.json', 'r') as f:
            creds_data = json.load(f)
            creds_str = json.dumps(creds_data)
            print("\n=== GOOGLE_CREDENTIALS_JSON ===")
            print(creds_str)
    else:
        print("credentials.json not found!")

if __name__ == '__main__':
    print("Converting Google credentials to Azure App Service format...")
    convert_credentials() 