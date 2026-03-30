"""Per-user Gmail service for matcha-work agent features.

Each user connects their own Gmail via OAuth. Tokens are stored
encrypted in the users.gmail_token JSONB column.
"""

import base64
import html
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional
from uuid import UUID

import httpx

from ...core.services.secret_crypto import encrypt_secret, decrypt_secret
from ...database import get_connection

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
TOKEN_URI = "https://oauth2.googleapis.com/token"
TOKEN_CACHE_TTL = 300  # 5 min

# Google OAuth client credentials path
GOOGLE_OAUTH_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_OAUTH_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "agent", "workspace", "credentials.json"),
)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def get_oauth_credentials() -> dict | None:
    """Load Google OAuth client credentials from credentials.json."""
    path = Path(GOOGLE_OAUTH_CREDENTIALS_PATH)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        # credentials.json has either "web" or "installed" key
        return data.get("web") or data.get("installed") or data
    except Exception:
        return None


class GmailService:
    """Per-user Gmail client. Loads/saves encrypted tokens from the database."""

    def __init__(self, user_id: UUID):
        self.user_id = user_id
        self._token_data: dict | None = None
        self._loaded = False
        self._send_timestamps: list[float] = []
        self._token_validated_at: float = 0

    async def load_token(self):
        """Load and decrypt token from users.gmail_token."""
        if self._loaded:
            return
        async with get_connection() as conn:
            row = await conn.fetchrow("SELECT gmail_token FROM users WHERE id=$1", self.user_id)
        if row and row["gmail_token"]:
            raw = row["gmail_token"] if isinstance(row["gmail_token"], dict) else json.loads(row["gmail_token"])
            try:
                self._token_data = {
                    "token": decrypt_secret(raw.get("token")) if raw.get("token") else None,
                    "refresh_token": decrypt_secret(raw["refresh_token"]),
                    "client_id": raw["client_id"],
                    "client_secret": decrypt_secret(raw["client_secret"]),
                    "scopes": raw.get("scopes", []),
                }
            except Exception:
                logger.warning("Failed to decrypt Gmail token for user %s", self.user_id)
                self._token_data = None
        self._loaded = True

    async def save_token(self, token_data: dict):
        """Encrypt and save token to DB."""
        self._token_data = token_data
        encrypted = {
            "token": encrypt_secret(token_data.get("token")),
            "refresh_token": encrypt_secret(token_data["refresh_token"]),
            "client_id": token_data["client_id"],
            "client_secret": encrypt_secret(token_data["client_secret"]),
            "scopes": token_data.get("scopes", []),
        }
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE users SET gmail_token=$1 WHERE id=$2",
                json.dumps(encrypted), self.user_id,
            )
        self._loaded = True

    @property
    def is_configured(self) -> bool:
        return self._token_data is not None and bool(self._token_data.get("refresh_token"))

    async def get_status(self) -> dict:
        await self.load_token()
        if not self.is_configured:
            return {"connected": False, "email": None}
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GMAIL_API_BASE}/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    return {"connected": True, "email": resp.json().get("emailAddress")}
            return {"connected": True, "email": None}
        except Exception:
            return {"connected": False, "email": None}

    async def _get_access_token(self) -> str:
        if not self._token_data:
            raise ValueError("Gmail not connected")

        token = self._token_data.get("token")

        if token and (time.time() - self._token_validated_at) < TOKEN_CACHE_TTL:
            return token

        if token:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GMAIL_API_BASE}/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    self._token_validated_at = time.time()
                    return token

        logger.info("Refreshing Gmail access token for user %s", self.user_id)
        refresh_token = self._token_data.get("refresh_token")
        client_id = self._token_data.get("client_id")
        client_secret = self._token_data.get("client_secret")

        if not all([refresh_token, client_id, client_secret]):
            raise ValueError("Incomplete Gmail token — reconnect your email")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URI,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            new_tokens = resp.json()

        self._token_data["token"] = new_tokens["access_token"]
        self._token_validated_at = time.time()
        # Persist refreshed token to DB
        await self.save_token(self._token_data)
        return self._token_data["token"]

    async def _get_headers(self) -> dict:
        token = await self._get_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _gmail_get(self, path: str, params=None) -> dict:
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{GMAIL_API_BASE}{path}", headers=headers, params=params, timeout=30.0)
            resp.raise_for_status()
            return resp.json()

    async def _gmail_post(self, path: str, body: dict) -> dict:
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{GMAIL_API_BASE}{path}", headers=headers, json=body, timeout=30.0)
            resp.raise_for_status()
            return resp.json()

    async def fetch_unread(self, max_results: int = 25) -> list[dict]:
        import asyncio as _aio
        await self.load_token()
        data = await self._gmail_get("/users/me/messages", params=[
            ("maxResults", str(max_results)),
            ("q", "is:unread"),
        ])
        stubs = data.get("messages", [])

        async def _fetch_one(stub: dict) -> dict | None:
            try:
                return await self.get_message(stub["id"])
            except Exception as e:
                logger.warning("Failed to fetch message %s: %s", stub["id"], e)
                return None

        results = await _aio.gather(*[_fetch_one(s) for s in stubs])
        return [r for r in results if r is not None]

    async def get_message(self, msg_id: str) -> dict:
        data = await self._gmail_get(f"/users/me/messages/{msg_id}", params={"format": "full"})
        headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}
        body = self._extract_body(data.get("payload", {}))
        return {
            "id": msg_id,
            "subject": headers.get("subject", "(no subject)"),
            "from": headers.get("from", "unknown"),
            "date": headers.get("date", ""),
            "body": body,
        }

    async def create_draft(self, to: str, subject: str, body: str, reply_to_id: str | None = None) -> dict:
        for field_name, value in [("to", to), ("subject", subject)]:
            if "\r" in value or "\n" in value:
                raise ValueError(f"Email {field_name} contains newline characters")

        lines = [f"To: {to}", f"Subject: {subject}", "Content-Type: text/plain; charset=utf-8"]
        if reply_to_id:
            lines += [f"In-Reply-To: {reply_to_id}", f"References: {reply_to_id}"]
        lines += ["", body]

        raw = base64.urlsafe_b64encode("\r\n".join(lines).encode()).decode()
        draft_body: dict = {"message": {"raw": raw}}
        if reply_to_id:
            draft_body["message"]["threadId"] = reply_to_id

        return await self._gmail_post("/users/me/drafts", draft_body)

    async def send_email(self, to: str, subject: str, body: str, reply_to_id: str | None = None) -> dict:
        self._check_send_rate()

        for field_name, value in [("to", to), ("subject", subject)]:
            if "\r" in value or "\n" in value:
                raise ValueError(f"Email {field_name} contains newline characters")

        lines = [f"To: {to}", f"Subject: {subject}", "Content-Type: text/plain; charset=utf-8"]
        if reply_to_id:
            lines += [f"In-Reply-To: {reply_to_id}", f"References: {reply_to_id}"]
        lines += ["", body]

        raw = base64.urlsafe_b64encode("\r\n".join(lines).encode()).decode()
        send_body: dict = {"raw": raw}
        if reply_to_id:
            send_body["threadId"] = reply_to_id

        data = await self._gmail_post("/users/me/messages/send", send_body)
        self._send_timestamps.append(time.time())
        return data

    def _check_send_rate(self):
        now = time.time()
        self._send_timestamps = [t for t in self._send_timestamps if now - t < 3600]
        if len([t for t in self._send_timestamps if now - t < 60]) >= 5:
            raise ValueError("Send rate limit: max 5 emails per minute")
        if len(self._send_timestamps) >= 50:
            raise ValueError("Send rate limit: max 50 emails per hour")

    def _extract_body(self, payload: dict) -> str:
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        parts = payload.get("parts", [])
        plain_text = None
        html_text = None

        for part in parts:
            mime = part.get("mimeType", "")
            body_data = part.get("body", {}).get("data")
            if mime == "text/plain" and body_data:
                plain_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            elif mime == "text/html" and body_data:
                html_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            elif mime.startswith("multipart/"):
                nested = self._extract_body(part)
                if nested and nested != "(no readable body)":
                    return nested

        if plain_text:
            return plain_text
        if html_text:
            text = re.sub(r"<style[^>]*>.*?</style>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = html.unescape(text)
            return re.sub(r"\s+", " ", text).strip()

        return "(no readable body)"
