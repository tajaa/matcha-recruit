"""Google Drive import for Matcha Drive — per-user, read-only.

A person connects their own Google account (`drive.readonly`), pastes a
Google Doc / Drive file link, and Matcha stores a SNAPSHOT of it in Matcha
Drive. Review never depends on later Google access.

Invariants:
  - The pasted URL is never fetched. Only a file id is parsed out of it
    (`parse_file_id`) and only googleapis.com is called, so a link cannot
    steer a server-side request anywhere else.
  - `users.gdrive_token` holds encrypted access/refresh tokens, expiry and
    the Google account email. The OAuth client secret is read from the shared
    credentials file at use time, never copied into user rows.
  - Google-native files are exported (Docs -> DOCX, Sheets -> XLSX,
    Slides -> PDF); anything else is downloaded as-is. 25 MB cap either way,
    enforced while streaming.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx

from app.core.services.secret_crypto import decrypt_secret, encrypt_secret
from app.database import get_connection

from .drive_service import MAX_FILE_BYTES

logger = logging.getLogger(__name__)

GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
OAUTH_STATE_PREFIX = "gdrive_oauth_state"
CALLBACK_PATH = "/api/matcha-work/drive/google/callback"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,100}$")
_PATH_ID_RE = re.compile(r"/(?:d|folders)/([A-Za-z0-9_-]{10,100})(?:[/?#]|$)")
_GOOGLE_HOSTS = {"docs.google.com", "drive.google.com"}

# Google-native mime -> (export mime, extension)
_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx",
    ),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


class GoogleDriveError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def parse_file_id(url: str) -> Optional[str]:
    """File id from a docs.google.com / drive.google.com link, else None. Pure."""
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "").lower() not in _GOOGLE_HOSTS:
        return None
    if "/folders/" in parsed.path:
        return None  # a folder, not a file
    match = _PATH_ID_RE.search(parsed.path)
    if match:
        return match.group(1)
    candidate = (parse_qs(parsed.query).get("id") or [None])[0]
    return candidate if candidate and _ID_RE.fullmatch(candidate) else None


def export_plan(mime_type: str) -> tuple[Optional[str], str]:
    """(export mime or None for a plain download, extension to ensure). Pure.
    Raises for Google-native types there is no useful export for."""
    if mime_type in _EXPORTS:
        return _EXPORTS[mime_type]
    if mime_type.startswith("application/vnd.google-apps."):
        raise GoogleDriveError(400, "That kind of Google file can't be imported. Use a Doc, Sheet, Slides deck, or an uploaded file.")
    return None, ""


def ensure_extension(name: str, ext: str) -> str:
    name = (name or "Untitled").strip() or "Untitled"
    return name if not ext or name.lower().endswith(ext) else f"{name}{ext}"


@dataclass(frozen=True)
class GoogleFile:
    file_id: str
    name: str
    mime_type: str
    data: bytes


def _client_credentials() -> dict:
    from app.matcha.services.matcha_work.gmail_service import get_oauth_credentials

    creds = get_oauth_credentials()
    if not creds or not creds.get("client_id") or not creds.get("client_secret"):
        raise GoogleDriveError(500, "Google sign-in isn't configured on the server.")
    return creds


class GoogleDriveService:
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        self._token: Optional[dict] = None
        self._loaded = False

    async def load_token(self) -> Optional[dict]:
        if self._loaded:
            return self._token
        async with get_connection() as conn:
            raw = await conn.fetchval("SELECT gdrive_token FROM users WHERE id = $1", self.user_id)
        self._loaded = True
        if not raw:
            return None
        data = raw if isinstance(raw, dict) else json.loads(raw)
        try:
            self._token = {
                "access_token": decrypt_secret(data["access_token"]) if data.get("access_token") else None,
                "refresh_token": decrypt_secret(data["refresh_token"]),
                "expires_at": float(data.get("expires_at") or 0),
                "email": data.get("email"),
            }
        except Exception:
            logger.warning("[gdrive] could not decrypt token for user %s", self.user_id)
            self._token = None
        return self._token

    async def save_token(self, token: dict) -> None:
        stored = {
            "access_token": encrypt_secret(token["access_token"]) if token.get("access_token") else None,
            "refresh_token": encrypt_secret(token["refresh_token"]),
            "expires_at": token.get("expires_at") or 0,
            "email": token.get("email"),
            "scopes": GDRIVE_SCOPES,
        }
        async with get_connection() as conn:
            await conn.execute("UPDATE users SET gdrive_token = $1 WHERE id = $2", json.dumps(stored), self.user_id)
        self._token = dict(token)
        self._loaded = True

    async def disconnect(self) -> None:
        async with get_connection() as conn:
            await conn.execute("UPDATE users SET gdrive_token = NULL WHERE id = $1", self.user_id)
        self._token = None
        self._loaded = True

    async def get_status(self) -> dict:
        token = await self.load_token()
        return {"connected": bool(token and token.get("refresh_token")), "email": (token or {}).get("email")}

    async def exchange_code(self, code: str, redirect_uri: str) -> None:
        """Callback half: trade the authorization code, record the account
        email, persist. Google omits refresh_token on a re-consent it already
        has one for; `prompt=consent` on connect makes that rare, and keeping
        the previous refresh token covers it."""
        creds = _client_credentials()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URI, data={
                "code": code, "client_id": creds["client_id"], "client_secret": creds["client_secret"],
                "redirect_uri": redirect_uri, "grant_type": "authorization_code",
            })
            if resp.status_code != 200:
                logger.error("[gdrive] token exchange failed: %s", resp.text[:300])
                raise GoogleDriveError(400, "Google didn't accept the sign-in. Please try again.")
            tokens = resp.json()
            about = await client.get(
                f"{DRIVE_API}/about", params={"fields": "user(emailAddress)"},
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
        email = about.json().get("user", {}).get("emailAddress") if about.status_code == 200 else None
        previous = await self.load_token()
        refresh = tokens.get("refresh_token") or (previous or {}).get("refresh_token")
        if not refresh:
            raise GoogleDriveError(400, "Google didn't grant offline access. Disconnect Matcha in your Google account settings and connect again.")
        await self.save_token({
            "access_token": tokens["access_token"],
            "refresh_token": refresh,
            "expires_at": time.time() + float(tokens.get("expires_in") or 3600),
            "email": email,
        })

    async def _access_token(self) -> str:
        token = await self.load_token()
        if not token or not token.get("refresh_token"):
            raise GoogleDriveError(409, "Connect your Google account first.")
        if token.get("access_token") and token.get("expires_at", 0) > time.time() + 60:
            return token["access_token"]
        creds = _client_credentials()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URI, data={
                "grant_type": "refresh_token", "refresh_token": token["refresh_token"],
                "client_id": creds["client_id"], "client_secret": creds["client_secret"],
            })
        if resp.status_code != 200:
            logger.warning("[gdrive] refresh failed for user %s: %s", self.user_id, resp.text[:200])
            raise GoogleDriveError(409, "Your Google connection expired. Connect your Google account again.")
        fresh = resp.json()
        await self.save_token({
            **token,
            "access_token": fresh["access_token"],
            "expires_at": time.time() + float(fresh.get("expires_in") or 3600),
        })
        return fresh["access_token"]

    async def fetch_file(self, file_id: str) -> GoogleFile:
        if not _ID_RE.fullmatch(file_id or ""):
            raise GoogleDriveError(400, "That doesn't look like a Google Drive file link.")
        headers = {"Authorization": f"Bearer {await self._access_token()}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            meta = await client.get(
                f"{DRIVE_API}/files/{file_id}",
                params={"fields": "id,name,mimeType,size", "supportsAllDrives": "true"},
                headers=headers,
            )
            if meta.status_code in (403, 404):
                raise GoogleDriveError(404, "Google says that file doesn't exist or your account can't open it.")
            if meta.status_code != 200:
                raise GoogleDriveError(502, "Google Drive didn't respond. Try again in a moment.")
            info = meta.json()
            mime = info.get("mimeType") or "application/octet-stream"
            export_mime, ext = export_plan(mime)
            if export_mime is None and int(info.get("size") or 0) > MAX_FILE_BYTES:
                raise GoogleDriveError(413, "That file is over 25 MB.")
            if export_mime:
                url, params = f"{DRIVE_API}/files/{file_id}/export", {"mimeType": export_mime}
            else:
                url, params = f"{DRIVE_API}/files/{file_id}", {"alt": "media", "supportsAllDrives": "true"}
            data = await _read_capped(client, url, params, headers)
        return GoogleFile(
            file_id=file_id,
            name=ensure_extension(info.get("name") or "Untitled", ext),
            mime_type=export_mime or mime,
            data=data,
        )


async def _read_capped(client: httpx.AsyncClient, url: str, params: dict, headers: dict) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async with client.stream("GET", url, params=params, headers=headers) as resp:
        if resp.status_code != 200:
            raise GoogleDriveError(502, "Google Drive couldn't send that file. Try again in a moment.")
        async for chunk in resp.aiter_bytes():
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise GoogleDriveError(413, "That file is over 25 MB.")
            chunks.append(chunk)
    return b"".join(chunks)
