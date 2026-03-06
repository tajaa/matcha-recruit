"""Sandbox enforcement for the autonomous agent.

Wraps all I/O (network, filesystem, AI) with whitelist/jail checks.
Any violation raises SandboxViolation.
"""

import html
import json
import logging
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class SandboxViolation(Exception):
    """Raised when an operation violates sandbox constraints."""


class SandboxedFetcher:
    """HTTP fetcher that only allows whitelisted URL patterns."""

    def __init__(self, allowed_urls: list[str]):
        # Store parsed origins/prefixes for matching
        self._allowed: list[str] = list(allowed_urls)

    def _is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        for pattern in self._allowed:
            pattern_parsed = urlparse(pattern)
            # Match scheme + host, and ensure the URL path starts with the pattern path
            if (parsed.scheme == pattern_parsed.scheme
                    and parsed.hostname == pattern_parsed.hostname
                    and parsed.path.startswith(pattern_parsed.path)):
                return True
        return False

    async def fetch(self, url: str, timeout: float = 30.0) -> str:
        if not self._is_allowed(url):
            logger.warning(f"BLOCKED fetch: {url}")
            raise SandboxViolation(f"URL not in whitelist: {url}")

        logger.info(f"Fetching: {url}")
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.text


class SandboxedFS:
    """Filesystem wrapper jailed to a workspace root directory."""

    def __init__(self, workspace_root: str | Path):
        self._root = Path(workspace_root).resolve()
        # Ensure workspace dirs exist
        for subdir in ("inbox", "processed", "output"):
            (self._root / subdir).mkdir(parents=True, exist_ok=True)

    def _resolve_safe(self, relative_path: str) -> Path:
        """Resolve a path and ensure it's within the workspace root."""
        resolved = (self._root / relative_path).resolve()
        # Resolve symlinks and reject anything outside root
        if not str(resolved).startswith(str(self._root)):
            logger.warning(f"BLOCKED path traversal: {relative_path} -> {resolved}")
            raise SandboxViolation(
                f"Path escapes workspace: {relative_path} (resolved to {resolved})"
            )
        return resolved

    def read(self, relative_path: str) -> str:
        path = self._resolve_safe(relative_path)
        logger.info(f"Reading: {path}")
        return path.read_text()

    def write(self, relative_path: str, content: str) -> Path:
        path = self._resolve_safe(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Writing: {path}")
        path.write_text(content)
        return path

    def move(self, src_relative: str, dst_relative: str) -> Path:
        src = self._resolve_safe(src_relative)
        dst = self._resolve_safe(dst_relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Moving: {src} -> {dst}")
        shutil.move(str(src), str(dst))
        return dst

    def list_dir(self, relative_path: str) -> list[str]:
        path = self._resolve_safe(relative_path)
        if not path.is_dir():
            return []
        return [f.name for f in path.iterdir() if f.is_file()]

    @property
    def root(self) -> Path:
        return self._root


class SandboxedGemini:
    """Thin wrapper around Gemini that logs prompts/responses."""

    def __init__(self, model: str, api_key: str | None = None):
        from google import genai
        self._model = model
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise SandboxViolation("No GEMINI_API_KEY configured")
        self._client = genai.Client(api_key=key)

    async def generate(self, prompt: str) -> str:
        import asyncio
        logger.info(f"Gemini prompt ({len(prompt)} chars) -> model={self._model}")

        # google-genai's generate_content is sync, run in thread
        def _call():
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            return resp.text

        result = await asyncio.to_thread(_call)
        logger.info(f"Gemini response ({len(result)} chars)")
        return result


class SandboxedGmail:
    """Read-only Gmail client using OAuth2 tokens.

    Only allows GET requests to the Gmail API. Token refresh is handled
    manually via httpx POST to oauth2.googleapis.com.
    """

    GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
    TOKEN_URI = "https://oauth2.googleapis.com/token"

    def __init__(self, workspace_root: str | Path):
        self._workspace = Path(workspace_root)
        self._token_path = self._workspace / "token.json"
        self._token_data: dict | None = None
        if self._token_path.exists():
            self._token_data = json.loads(self._token_path.read_text())

    @property
    def is_configured(self) -> bool:
        return self._token_data is not None and "refresh_token" in self._token_data

    async def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if not self._token_data:
            raise SandboxViolation("Gmail token.json not found")

        # Try existing token first — if it fails we'll refresh
        token = self._token_data.get("token")
        if token:
            # Test the token with a lightweight request
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.GMAIL_API_BASE}/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    return token

        # Refresh the token
        logger.info("Refreshing Gmail access token")
        refresh_token = self._token_data.get("refresh_token")
        client_id = self._token_data.get("client_id")
        client_secret = self._token_data.get("client_secret")

        if not all([refresh_token, client_id, client_secret]):
            raise SandboxViolation("Incomplete token.json — re-run gmail_auth")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URI,
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
        logger.info("Gmail token refreshed and saved")
        return self._token_data["token"]

    async def _gmail_get(self, path: str, params: dict | None = None) -> dict:
        """Make a GET request to the Gmail API."""
        url = f"{self.GMAIL_API_BASE}{path}"

        # Validate URL stays within Gmail API
        parsed = urlparse(url)
        if parsed.hostname != "gmail.googleapis.com" or not parsed.path.startswith("/gmail/v1"):
            raise SandboxViolation(f"Gmail URL outside allowed scope: {url}")

        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_unread(self, max_results: int = 25, label_ids: list[str] | None = None) -> list[dict]:
        """Fetch unread message stubs (id + threadId)."""
        params = {
            "maxResults": max_results,
            "q": "is:unread",
        }
        if label_ids:
            params["labelIds"] = ",".join(label_ids)

        data = await self._gmail_get("/users/me/messages", params=params)
        return data.get("messages", [])

    async def get_message(self, msg_id: str) -> dict:
        """Fetch a single message and extract headers + body text."""
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

    def _extract_body(self, payload: dict) -> str:
        """Walk MIME parts, prefer text/plain, fall back to stripped HTML."""
        import base64

        # Single-part message
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        # Multipart — walk parts
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
                # Recurse into nested multipart
                nested = self._extract_body(part)
                if nested:
                    return nested

        if plain_text:
            return plain_text
        if html_text:
            return self._strip_html(html_text)

        return "(no readable body)"

    @staticmethod
    def _strip_html(raw_html: str) -> str:
        """Crude HTML tag stripping for fallback body extraction."""
        text = re.sub(r"<style[^>]*>.*?</style>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text


class Sandbox:
    """Aggregates all sandboxed resources."""

    def __init__(self, config):
        # Build full URL whitelist from feeds + extra patterns
        all_urls = []
        for feed in config.rss_feeds:
            all_urls.append(feed["url"])
        all_urls.extend(config.allowed_url_patterns)

        # Add Gmail API URLs when enabled
        if config.gmail_enabled:
            all_urls.append("https://gmail.googleapis.com/gmail/v1/")
            all_urls.append("https://oauth2.googleapis.com/token")

        self.fetcher = SandboxedFetcher(all_urls)
        self.fs = SandboxedFS(config.workspace_root)
        self.gemini = SandboxedGemini(config.gemini_model)

        # Gmail — only initialize if enabled and token exists
        if config.gmail_enabled:
            gmail = SandboxedGmail(config.workspace_root)
            self.gmail = gmail if gmail.is_configured else None
        else:
            self.gmail = None
