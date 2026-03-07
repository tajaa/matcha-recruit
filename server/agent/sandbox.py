"""Sandbox enforcement for the autonomous agent.

Wraps all I/O (network, filesystem, AI) with whitelist/jail checks.
Any violation raises SandboxViolation.
"""

import atexit
import html
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import time
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


class SandboxedLocal:
    """Local LLM via llama-server (OpenAI-compatible API).

    Two modes:
    - Local: starts llama-server as a subprocess (for dev)
    - Remote: connects to an external llama-server URL (for Docker/EC2)
    """

    def __init__(self, model_path: str | None = None, port: int = 8999, base_url: str | None = None):
        self._process: subprocess.Popen | None = None

        if base_url:
            # Remote mode — connect to an already-running llama-server
            self._base_url = base_url.rstrip("/")
            logger.info(f"Connecting to remote llama-server at {self._base_url}")
            self._wait_for_server()
        else:
            # Local mode — start our own llama-server subprocess
            self._base_url = f"http://127.0.0.1:{port}"
            self._start_server(model_path, port)

    def _start_server(self, model_path: str, port: int):
        """Start llama-server in the background."""
        llama_server = shutil.which("llama-server")
        if not llama_server:
            raise SandboxViolation("llama-server not found in PATH")

        logger.info(f"Starting llama-server on port {port} with {Path(model_path).name}")
        self._process = subprocess.Popen(
            [
                llama_server,
                "-m", model_path,
                "--port", str(port),
                "--ctx-size", "4096",
                "--n-gpu-layers", "99",
                "--log-disable",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        atexit.register(self.stop)
        self._wait_for_server()

    def _wait_for_server(self):
        """Wait for llama-server to become ready."""
        for _ in range(30):
            try:
                resp = httpx.get(f"{self._base_url}/health", timeout=1.0)
                if resp.status_code == 200:
                    logger.info("llama-server ready")
                    return
            except httpx.ConnectError:
                pass
            time.sleep(0.5)

        self.stop()
        raise SandboxViolation(f"llama-server not ready at {self._base_url} within 15 seconds")

    def stop(self):
        if self._process and self._process.poll() is None:
            logger.info("Stopping llama-server")
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    async def generate(self, prompt: str) -> str:
        """Generate a completion via the OpenAI-compatible /v1/chat/completions endpoint."""
        import asyncio

        logger.info(f"Local model prompt ({len(prompt)} chars)")

        def _call():
            resp = httpx.post(
                f"{self._base_url}/v1/chat/completions",
                json={
                    "model": "local",
                    "messages": [{"role": "user", "content": f"/no_think\n{prompt}"}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            # Strip any <think>...</think> blocks from Qwen3.5 reasoning
            text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
            return text.strip()

        result = await asyncio.to_thread(_call)
        logger.info(f"Local model response ({len(result)} chars)")
        return result


class SandboxedGmail:
    """Gmail client using OAuth2 tokens (read + draft, no send).

    Scopes: gmail.readonly + gmail.compose. Token refresh is handled
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
        self._token_path.chmod(0o600)
        logger.info("Gmail token refreshed and saved")
        return self._token_data["token"]

    async def _gmail_get(self, path: str, params: dict | list[tuple[str, str]] | None = None) -> dict:
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

    async def _gmail_post(self, path: str, body: dict) -> dict:
        """Make a POST request to the Gmail API (drafts only)."""
        url = f"{self.GMAIL_API_BASE}{path}"

        parsed = urlparse(url)
        if parsed.hostname != "gmail.googleapis.com" or not parsed.path.startswith("/gmail/v1"):
            raise SandboxViolation(f"Gmail URL outside allowed scope: {url}")

        # Only allow draft creation — block send endpoints
        if "/send" in path:
            raise SandboxViolation("Sending emails is not allowed")

        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def create_draft(self, to: str, subject: str, body: str, reply_to_id: str | None = None) -> dict:
        """Create a draft email. Does NOT send — it sits in Drafts until you send manually."""
        import base64

        # Validate email fields against header injection
        for field_name, value in [("to", to), ("subject", subject)]:
            if "\r" in value or "\n" in value:
                raise SandboxViolation(f"Email {field_name} contains newline characters (header injection attempt)")

        # Basic email format validation for 'to' field
        # Accept both bare "user@example.com" and RFC822 "Name <user@example.com>"
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', to) and \
           not re.match(r'^.+\s*<[^@\s]+@[^@\s]+\.[^@\s]+>$', to):
            raise SandboxViolation(f"Invalid email address format: {to}")

        lines = [
            f"To: {to}",
            f"Subject: {subject}",
            "Content-Type: text/plain; charset=utf-8",
        ]
        if reply_to_id:
            lines.append(f"In-Reply-To: {reply_to_id}")
            lines.append(f"References: {reply_to_id}")

        lines.append("")
        lines.append(body)

        raw = base64.urlsafe_b64encode("\r\n".join(lines).encode()).decode()

        draft_body = {"message": {"raw": raw}}
        if reply_to_id:
            draft_body["message"]["threadId"] = reply_to_id

        data = await self._gmail_post("/users/me/drafts", draft_body)
        logger.info(f"Draft created: {data.get('id')}")
        return data

    async def list_labels(self) -> list[dict]:
        """List all Gmail labels (system + custom)."""
        data = await self._gmail_get("/users/me/labels")
        labels = []
        for label in data.get("labels", []):
            labels.append({
                "id": label["id"],
                "name": label.get("name", label["id"]),
                "type": label.get("type", "user"),
            })
        return labels

    async def fetch_unread(self, max_results: int = 25, label_ids: list[str] | None = None) -> list[dict]:
        """Fetch unread message stubs (id + threadId)."""
        # Gmail API requires labelIds as repeated query params, not comma-joined
        params: list[tuple[str, str]] = [
            ("maxResults", str(max_results)),
            ("q", "is:unread"),
        ]
        if label_ids:
            for label in label_ids:
                params.append(("labelIds", label))

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


class SandboxedCalendar:
    """Google Calendar client — creates events using the same OAuth token as Gmail.

    Scope: calendar.events (create/edit own events, cannot delete calendars).
    """

    CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(self, gmail: SandboxedGmail):
        self._gmail = gmail

    async def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
    ) -> dict:
        """Create a calendar event. start/end are ISO 8601 datetime strings."""
        url = f"{self.CALENDAR_API_BASE}/calendars/primary/events"

        parsed = urlparse(url)
        if parsed.hostname != "www.googleapis.com" or not parsed.path.startswith("/calendar/v3"):
            raise SandboxViolation(f"Calendar URL outside allowed scope: {url}")

        body: dict = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        if location:
            body["location"] = location

        token = await self._gmail._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info(f"Calendar event created: {data.get('htmlLink')}")
        return data


class Sandbox:
    """Aggregates all sandboxed resources."""

    def __init__(self, config):
        # Build full URL whitelist from feeds + extra patterns
        all_urls = []
        for feed in config.rss_feeds:
            all_urls.append(feed["url"])
        all_urls.extend(config.allowed_url_patterns)

        # Add Gmail + Calendar API URLs when enabled
        if config.gmail_enabled:
            all_urls.append("https://gmail.googleapis.com/gmail/v1/")
            all_urls.append("https://oauth2.googleapis.com/token")
            all_urls.append("https://www.googleapis.com/calendar/v3/")

        self.fetcher = SandboxedFetcher(all_urls)
        self.fs = SandboxedFS(config.workspace_root)

        # Gemini — optional if a local model is available
        self.gemini: SandboxedGemini | None = None
        if os.getenv("GEMINI_API_KEY"):
            self.gemini = SandboxedGemini(config.gemini_model)

        # Local model — connect to remote llama-server or start local subprocess
        self.local: SandboxedLocal | None = None
        if config.local_model_url:
            try:
                self.local = SandboxedLocal(base_url=config.local_model_url)
            except SandboxViolation as e:
                logger.warning(f"Remote local model unavailable: {e}")
        elif config.local_model_path and Path(config.local_model_path).is_file():
            try:
                self.local = SandboxedLocal(config.local_model_path, config.local_model_port)
            except SandboxViolation as e:
                logger.warning(f"Local model unavailable: {e}")

        # Default LLM: local if available, else gemini. Override with force_gemini().
        self.llm = self.local or self.gemini
        if self.llm is None:
            raise SandboxViolation("No LLM configured — set GEMINI_API_KEY or AGENT_LOCAL_MODEL_URL")

        # Gmail — only initialize if enabled and token exists
        if config.gmail_enabled:
            gmail = SandboxedGmail(config.workspace_root)
            self.gmail = gmail if gmail.is_configured else None
        else:
            self.gmail = None

        # Calendar — shares Gmail's OAuth token
        self.calendar: SandboxedCalendar | None = None
        if self.gmail is not None:
            self.calendar = SandboxedCalendar(self.gmail)
