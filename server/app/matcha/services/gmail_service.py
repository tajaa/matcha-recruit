"""Gmail service for matcha-work agent features.

Adapted from agent/sandbox.py:SandboxedGmail. Uses OAuth2 tokens to
fetch, draft, and send emails via the Gmail API.
"""

import base64
import html
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
TOKEN_URI = "https://oauth2.googleapis.com/token"

# Default to the agent workspace token if no override
DEFAULT_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "agent", "workspace", "token.json"
)


class GmailService:
    """Gmail client using OAuth2 tokens — fetch, draft, send emails."""

    def __init__(self, token_path: str | None = None):
        self._token_path = Path(token_path or os.getenv("GMAIL_TOKEN_PATH", DEFAULT_TOKEN_PATH))
        self._token_data: dict | None = None
        self._send_timestamps: list[float] = []
        if self._token_path.exists():
            try:
                self._token_data = json.loads(self._token_path.read_text())
            except Exception:
                logger.warning("Failed to read Gmail token.json at %s", self._token_path)

    @property
    def is_configured(self) -> bool:
        return self._token_data is not None and "refresh_token" in self._token_data

    async def get_status(self) -> dict:
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
            raise ValueError("Gmail token.json not found")

        token = self._token_data.get("token")
        if token:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GMAIL_API_BASE}/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    return token

        logger.info("Refreshing Gmail access token")
        refresh_token = self._token_data.get("refresh_token")
        client_id = self._token_data.get("client_id")
        client_secret = self._token_data.get("client_secret")

        if not all([refresh_token, client_id, client_secret]):
            raise ValueError("Incomplete token.json — re-run OAuth flow")

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
        self._token_path.write_text(json.dumps(self._token_data, indent=2))
        self._token_path.chmod(0o600)
        return self._token_data["token"]

    async def _gmail_get(self, path: str, params=None) -> dict:
        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMAIL_API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def _gmail_post(self, path: str, body: dict) -> dict:
        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GMAIL_API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_unread(self, max_results: int = 25) -> list[dict]:
        data = await self._gmail_get("/users/me/messages", params=[
            ("maxResults", str(max_results)),
            ("q", "is:unread"),
        ])
        stubs = data.get("messages", [])
        emails = []
        for stub in stubs:
            try:
                email = await self.get_message(stub["id"])
                emails.append(email)
            except Exception as e:
                logger.warning("Failed to fetch message %s: %s", stub["id"], e)
        return emails

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

        data = await self._gmail_post("/users/me/drafts", draft_body)
        logger.info("Draft created: %s", data.get("id"))
        return data

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
        logger.info("Email sent to %s: %s", to, data.get("id"))
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
                if nested:
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


# Singleton
_gmail_service: GmailService | None = None


def get_gmail_service() -> GmailService:
    global _gmail_service
    if _gmail_service is None:
        _gmail_service = GmailService()
    return _gmail_service
