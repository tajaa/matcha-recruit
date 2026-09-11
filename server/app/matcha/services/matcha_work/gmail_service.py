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
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from pathlib import Path
from typing import Optional
from uuid import UUID

import httpx

from ....core.services.secret_crypto import encrypt_secret, decrypt_secret
from ....database import get_connection

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
TOKEN_URI = "https://oauth2.googleapis.com/token"
TOKEN_CACHE_TTL = 300  # 5 min

# Google OAuth client credentials path
GOOGLE_OAUTH_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_OAUTH_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agent", "workspace", "credentials.json"),
)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

# A newsletter is ~100 KB of HTML. Past this the reader shows the text body.
BODY_HTML_MAX_CHARS = 1_000_000

_HTML_DROP_RE = re.compile(r"<(style|script|head)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE)
_HTML_BREAK_RE = re.compile(
    r"<\s*(br|/p|/div|/tr|/li|/h[1-6]|/table|/blockquote|/header|/footer|/section|/article)\b[^>]*>",
    re.IGNORECASE,
)


def _html_to_text(markup: str) -> str:
    """Readable text from an HTML-only message. Block ends become line
    breaks so paragraphs survive; every other tag is dropped."""
    text = _HTML_DROP_RE.sub("", markup)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = _HTML_BREAK_RE.sub("\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _decode_header(value: str | None) -> str:
    """RFC 2047 encoded-words (`=?UTF-8?B?…?=`) as readable text. Gmail
    returns header values verbatim, so a non-ASCII sender name or subject
    arrives encoded. A value that won't decode is returned as it came."""
    if not value or "=?" not in value:
        return value or ""
    try:
        return str(make_header(decode_header(value)))
    except (HeaderParseError, LookupError, UnicodeDecodeError, ValueError):
        return value


# (limit, window seconds, label) — per user, however many requests or workers.
SEND_RATE_LIMITS = ((5, 60, "5 emails per minute"), (50, 3600, "50 emails per hour"))


class GmailSendRateLimited(RuntimeError):
    """The per-user send ceiling tripped. Nothing was sent."""


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

    async def _gmail_delete(self, path: str) -> None:
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{GMAIL_API_BASE}{path}", headers=headers, timeout=30.0)
            resp.raise_for_status()

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
                # No HTML: the list stays light; the reader fetches the one
                # message it opens.
                return await self.get_message(stub["id"])
            except Exception as e:
                logger.warning("Failed to fetch message %s: %s", stub["id"], e)
                return None

        results = await _aio.gather(*[_fetch_one(s) for s in stubs])
        return [r for r in results if r is not None]

    async def get_message(self, msg_id: str, *, include_html: bool = False) -> dict:
        """One message. `include_html` adds the raw HTML part (`body_html`)
        for the reader. Nothing else needs it, and building it for a list of
        newsletters is megabytes of strings thrown straight away."""
        data = await self._gmail_get(f"/users/me/messages/{msg_id}", params={"format": "full"})
        payload = data.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        markup = self._find_part(payload, "text/html") if include_html else None
        message = {
            "id": msg_id,
            # Gmail's own thread id (for threadId on a reply) and the RFC 5322
            # Message-ID header (for In-Reply-To/References). They are different
            # identifiers; conflating them was the old reply_to_id bug.
            "thread_id": data.get("threadId"),
            "message_id_header": headers.get("message-id"),
            "subject": _decode_header(headers.get("subject", "(no subject)")),
            "from": _decode_header(headers.get("from", "unknown")),
            "date": headers.get("date", ""),
            # Gmail's own preview line, entity-escaped the way it arrives.
            "snippet": html.unescape(data.get("snippet") or ""),
            "body": self._extract_body(payload, markup),
            "is_unread": "UNREAD" in (data.get("labelIds") or []),
            "attachments": self._extract_attachments(payload),
        }
        if include_html:
            # The reader renders this (sandboxed); past the cap it falls back
            # to `body`. Never sent to the model or into a card snapshot.
            message["body_html"] = markup if markup and len(markup) <= BODY_HTML_MAX_CHARS else None
        return message

    async def get_attachment(self, msg_id: str, attachment_id: str) -> bytes:
        data = await self._gmail_get(
            f"/users/me/messages/{msg_id}/attachments/{attachment_id}"
        )
        encoded = data.get("data") or ""
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))

    async def mark_read(self, msg_id: str) -> dict:
        return await self._gmail_post(
            f"/users/me/messages/{msg_id}/modify", {"removeLabelIds": ["UNREAD"]}
        )

    def _build_raw(self, to: str, subject: str, body: str, in_reply_to: str | None) -> str:
        """RFC 822 message, base64url-encoded the way Gmail's `raw` field wants.

        `in_reply_to` is the ORIGINAL message's `Message-ID` header value (angle
        brackets included), never Gmail's hex message id — that one only goes in
        the API-level `threadId`.
        """
        for field_name, value in [("to", to), ("subject", subject)]:
            if "\r" in value or "\n" in value:
                raise ValueError(f"Email {field_name} contains newline characters")
        if in_reply_to and ("\r" in in_reply_to or "\n" in in_reply_to):
            raise ValueError("Email in_reply_to contains newline characters")

        lines = [f"To: {to}", f"Subject: {subject}", "Content-Type: text/plain; charset=utf-8"]
        if in_reply_to:
            lines += [f"In-Reply-To: {in_reply_to}", f"References: {in_reply_to}"]
        lines += ["", body]
        return base64.urlsafe_b64encode("\r\n".join(lines).encode()).decode()

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: str | None = None,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> dict:
        """Save a Gmail draft. `thread_id` keeps it in the conversation;
        `in_reply_to` threads it for other mail clients. `reply_to_id` is the
        legacy positional form (a Gmail message id used as the thread id — only
        correct for a thread's first message); it no longer writes a bogus
        In-Reply-To header."""
        raw = self._build_raw(to, subject, body, in_reply_to)
        draft_body: dict = {"message": {"raw": raw}}
        thread = thread_id or reply_to_id
        if thread:
            draft_body["message"]["threadId"] = thread
        return await self._gmail_post("/users/me/drafts", draft_body)

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_id: str | None = None,
        *,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> dict:
        """Send now. Same threading contract as create_draft."""
        # Validate first, so a refused header doesn't spend the allowance.
        raw = self._build_raw(to, subject, body, in_reply_to)
        await self._check_send_rate()
        send_body: dict = {"raw": raw}
        thread = thread_id or reply_to_id
        if thread:
            send_body["threadId"] = thread
        return await self._gmail_post("/users/me/messages/send", send_body)

    async def delete_draft(self, draft_id: str) -> None:
        """Remove a saved draft (gmail.compose covers drafts.delete). Used after
        an AI draft's edited version is sent, so it doesn't linger in Drafts."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", draft_id or ""):
            raise ValueError("Invalid draft id")
        await self._gmail_delete(f"/users/me/drafts/{draft_id}")

    async def _check_send_rate(self) -> None:
        """Per-USER ceiling in the shared rate-limit store (Redis; in-process
        when Redis is down). It used to be a list on the instance, but every
        route builds a fresh GmailService, so the list never held more than
        the one send in flight and the ceiling could not trip."""
        from fastapi import HTTPException

        from ....core.services.redis_cache import check_rate_limit

        for limit, window, label in SEND_RATE_LIMITS:
            try:
                await check_rate_limit(str(self.user_id), f"gmail_send_{window}s", limit, window)
            except HTTPException as exc:
                raise GmailSendRateLimited(f"Send rate limit: max {label}") from exc

    def _part_text(self, part: dict) -> str | None:
        """One MIME part's body, decoded with the charset its Content-Type
        declares. Not every sender writes UTF-8; an unknown charset falls back
        to it rather than failing the whole message."""
        data = (part.get("body") or {}).get("data")
        if not data:
            return None
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        charset = "utf-8"
        for header in part.get("headers") or []:
            if (header.get("name") or "").lower() == "content-type":
                found = re.search(r'charset="?([\w.:-]+)"?', header.get("value") or "", re.IGNORECASE)
                if found:
                    charset = found.group(1)
        try:
            return raw.decode(charset, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")

    def _find_part(self, part: dict, mime: str) -> str | None:
        """The first `mime` body in a depth-first walk of this message's own
        multipart tree. A part with a filename is an attachment (a notes.txt,
        a saved .html), and a `message/rfc822` part is a forwarded or attached
        email; neither is ever this message's body, so the walk descends only
        through `multipart/*` containers."""
        mime_type = part.get("mimeType") or ""
        if mime_type == mime and not part.get("filename"):
            text = self._part_text(part)
            if text:
                return text
        if mime_type and not mime_type.startswith("multipart/"):
            return None
        for child in part.get("parts") or []:
            found = self._find_part(child, mime)
            if found:
                return found
        return None

    def _extract_body(self, payload: dict, markup: str | None = None) -> str:
        """Plain text: what the AI actions and a card's snapshot read. The
        HTML-only case is converted with its paragraphs kept. Pass `markup`
        when the caller already decoded the HTML part, so it isn't decoded
        twice."""
        plain = self._find_part(payload, "text/plain")
        if plain and plain.strip():
            return plain
        if markup is None:
            markup = self._find_part(payload, "text/html")
        if markup:
            return _html_to_text(markup)
        return "(no readable body)"

    def _extract_attachments(self, payload: dict) -> list[dict]:
        attachments = []
        for part in payload.get("parts", []):
            body = part.get("body") or {}
            filename = part.get("filename")
            if filename and body.get("attachmentId"):
                attachments.append({
                    "filename": filename[:255],
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "attachment_id": body["attachmentId"],
                })
            attachments.extend(self._extract_attachments(part))
        return attachments


class GmailMailboxService(GmailService):
    """Gmail client for the platform POS intake inbox.

    Unlike the per-user service, this token is configured at the platform
    level and is never loaded from a tenant or employee row.
    """

    def __init__(self):
        super().__init__(UUID(int=0))
        from app.config import get_settings
        settings = get_settings()
        self._token_data = {
            "token": None,
            "refresh_token": settings.pos_intake_gmail_refresh_token,
            "client_id": settings.pos_intake_gmail_client_id,
            "client_secret": settings.pos_intake_gmail_client_secret,
            "scopes": GMAIL_SCOPES,
        }
        self._loaded = True

    async def load_token(self):
        return None

    async def save_token(self, token_data: dict):
        self._token_data = token_data
        self._loaded = True
