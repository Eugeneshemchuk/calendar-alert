"""
Run this ONCE, locally, to generate a Google OAuth refresh token for the
calendar-alert script. It opens a browser for you to authorize access,
then prints a refresh token to paste into your GitHub repo secrets.

Setup before running:
1. Go to https://console.cloud.google.com/apis/credentials
2. Create an OAuth 2.0 Client ID, type "Desktop app"
3. Download the credentials JSON, save it here as client_secret.json
4. pip install google-auth-oauthlib
5. python get_refresh_token.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n--- Save these as GitHub repo secrets ---")
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("------------------------------------------")
    print("\nDelete client_secret.json after this — it's no longer needed.")


if __name__ == "__main__":
    main()
