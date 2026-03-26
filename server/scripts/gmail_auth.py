#!/usr/bin/env python3
"""Gmail OAuth2 token generator — two-step process.

Step 1: Run with no arguments to get the authorization URL.
        Send this URL to the person who owns the Gmail account.
        They sign in, click Allow, and send you the code from the redirect URL.

Step 2: Run with the code to exchange it for a token.json.
        Then upload token.json to EC2.

Usage:
    python scripts/gmail_auth.py                    # Step 1: prints the auth URL
    python scripts/gmail_auth.py "PASTE_CODE_HERE"  # Step 2: exchanges code for token
"""
import json
import sys
from urllib.parse import urlencode

import os

# From environment or .env — never hardcode secrets
CLIENT_ID = os.environ.get("GMAIL_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GMAIL_OAUTH_CLIENT_SECRET", "")
if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Set GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET env vars")
    sys.exit(1)
REDIRECT_URI = "http://localhost"
SCOPES = "https://www.googleapis.com/auth/gmail.send"


def step1_get_auth_url():
    params = urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
    url = f"https://accounts.google.com/o/oauth2/auth?{params}"

    print("\n" + "=" * 60)
    print("STEP 1: Send this link to the person who owns the Gmail account")
    print("=" * 60)
    print(f"\n{url}\n")
    print("Tell them:")
    print("  1. Click the link above")
    print("  2. Sign in with support@hey-matcha.com")
    print("  3. Click 'Allow' when Google asks for permission")
    print("  4. The page will redirect to a blank page (that's normal)")
    print("  5. Copy the ENTIRE URL from the browser address bar")
    print("     It will look like: http://localhost/?code=4/0AXXXXXX...&scope=...")
    print("  6. Send that URL (or just the code= part) back to you")
    print()
    print("Once you have the code, run:")
    print('  python scripts/gmail_auth.py "THE_CODE_HERE"')
    print()


def step2_exchange_code(code: str):
    # Clean up the code — they might paste the full URL
    if "code=" in code:
        code = code.split("code=")[1].split("&")[0]

    import urllib.request
    import urllib.parse

    data = urllib.parse.urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nERROR: Google returned {e.code}")
        print(body)
        print("\nCommon issues:")
        print("  - Code expired (they take ~10 minutes, get a new one)")
        print("  - Code already used (each code works once)")
        print("  - Wrong account signed in")
        sys.exit(1)

    # Build token.json in the format EmailService expects
    token = {
        "refresh_token": result["refresh_token"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    output_path = "gmail_token.json"
    with open(output_path, "w") as f:
        json.dump(token, f, indent=2)

    print("\n" + "=" * 60)
    print("SUCCESS — token saved to gmail_token.json")
    print("=" * 60)
    print(f"\nRefresh token: {result['refresh_token'][:20]}...")
    print(f"Saved to: {output_path}")
    print()
    print("Now upload it to EC2:")
    print("  scp -i roonMT-arm.pem gmail_token.json ec2-user@54.177.107.107:/home/ec2-user/matcha/credentials/gmail_token.json")
    print()
    print("Then restart the container:")
    print("  ssh -i roonMT-arm.pem ec2-user@54.177.107.107 'cd /home/ec2-user/matcha && docker compose up -d'")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        step2_exchange_code(sys.argv[1])
    else:
        step1_get_auth_url()
