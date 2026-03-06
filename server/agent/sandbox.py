"""Sandbox enforcement for the autonomous agent.

Wraps all I/O (network, filesystem, AI) with whitelist/jail checks.
Any violation raises SandboxViolation.
"""

import logging
import os
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


class Sandbox:
    """Aggregates all sandboxed resources."""

    def __init__(self, config):
        # Build full URL whitelist from feeds + extra patterns
        all_urls = []
        for feed in config.rss_feeds:
            all_urls.append(feed["url"])
        all_urls.extend(config.allowed_url_patterns)

        self.fetcher = SandboxedFetcher(all_urls)
        self.fs = SandboxedFS(config.workspace_root)
        self.gemini = SandboxedGemini(config.gemini_model)
