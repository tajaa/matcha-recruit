"""One-time Gmail OAuth2 setup — run on the host (not in Docker).

Usage:
    1. Create a Google Cloud project and enable the Gmail API
    2. Create an OAuth2 "Desktop app" credential
    3. Download the JSON and save it as workspace/credentials.json
    4. Run: python -m agent.gmail_auth
    5. Complete the browser consent flow
    6. workspace/token.json is created — the agent can now read Gmail
"""

import json
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    workspace = Path(__file__).parent / "workspace"
    creds_path = workspace / "credentials.json"
    token_path = workspace / "token.json"

    if not creds_path.exists():
        print(
            "credentials.json not found.\n\n"
            "1. Go to https://console.cloud.google.com/apis/credentials\n"
            "2. Create an OAuth 2.0 Client ID (type: Desktop app)\n"
            "3. Download the JSON and save it as:\n"
            f"   {creds_path}\n"
        )
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing dependency: pip install google-auth-oauthlib")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    token_path.write_text(json.dumps(token_data, indent=2))

    print(f"\nToken saved to {token_path}")
    print("\nNext steps:")
    print("  1. Enable gmail in HEARTBEAT.md: - [x] email_inbox")
    print("  2. Set AGENT_GMAIL_ENABLED=true in your environment")
    print("  3. Run the agent: ./run.sh or python -m agent.cli")


if __name__ == "__main__":
    main()
