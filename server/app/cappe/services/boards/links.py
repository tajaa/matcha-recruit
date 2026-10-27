"""A pasted link's preview: a title, a line about it and a picture.

The page is fetched through the SSRF-guarded fetcher (`core.services.safe_fetch`,
every hop a public address, the body capped) with no database connection
held. Only the `<head>`'s metadata is read: Open Graph, the Twitter card and
`<title>`. The picture it names is downloaded the same way and kept as a
private thumbnail, so the board never hotlinks someone else's image (the
dashboard's CSP wouldn't load it anyway).

A link straight to a picture is that picture (`LinkPreview.image_bytes` with
`direct=True`): the route pins it as a photo, the address kept as its source.

Any failure leaves a plain card named by the link's host. A preview is a
nicety, never a reason to refuse the pin.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlsplit

from ....core.services.safe_fetch import fetch_public
from .. import media
from . import files
from .limits import LINK_DESCRIPTION_MAX, LINK_TITLE_MAX, SITE_NAME_MAX, URL_MAX

logger = logging.getLogger(__name__)

MAX_PAGE_BYTES = 768 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
PAGE_ACCEPT = "text/html,application/xhtml+xml;q=0.9,image/*;q=0.8,*/*;q=0.5"
IMAGE_ACCEPT = "image/webp,image/*,*/*;q=0.8"
TIMEOUT = 12.0
_CHARSET = re.compile(rb"""charset\s*=\s*["']?([A-Za-z0-9_\-:.]+)""", re.IGNORECASE)


class BadLink(ValueError):
    """Not an address we will fetch."""


@dataclass
class LinkPreview:
    url: str
    title: str
    description: Optional[str] = None
    site_name: Optional[str] = None
    image_bytes: Optional[bytes] = None
    image_mime: Optional[str] = None
    direct: bool = False


def normalize_url(raw: str) -> str:
    """An http(s) address from what was pasted ("example.com/a" is https)."""
    text = (raw or "").strip()
    if not text or len(text) > URL_MAX or any(c.isspace() for c in text):
        raise BadLink("Paste a web address, like https://example.com.")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or "." not in parts.hostname:
        raise BadLink("Paste a web address, like https://example.com.")
    if parts.username or parts.password:
        raise BadLink("That address has a password in it. Paste it without one.")
    return text


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or url).lower()
    return host[4:] if host.startswith("www.") else host


def _clip(text: Optional[str], limit: int) -> Optional[str]:
    text = " ".join((text or "").split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class _Head(HTMLParser):
    """Reads the metadata tags of a page's head and stops at its body."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag == "body":
            self.done = True
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = {k.lower(): (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or "").strip().lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self._in_title and not self.done and len(self.title) < 1000:
            self.title += data


def parse_head(html: str, base_url: str) -> dict:
    """Title, description, site name and picture address from a page's head."""
    parser = _Head()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — html.parser on hostile markup: keep what was read
        pass
    m = parser.meta
    image = m.get("og:image:secure_url") or m.get("og:image") or m.get("og:image:url") or m.get("twitter:image")
    image_url = urljoin(base_url, image.strip()) if image and image.strip() else None
    if image_url and urlsplit(image_url).scheme not in ("http", "https"):
        image_url = None
    return {
        "title": _clip(m.get("og:title") or m.get("twitter:title") or parser.title, LINK_TITLE_MAX),
        "description": _clip(m.get("og:description") or m.get("twitter:description") or m.get("description"),
                             LINK_DESCRIPTION_MAX),
        "site_name": _clip(m.get("og:site_name"), SITE_NAME_MAX),
        "image_url": image_url,
    }


def _decode(body: bytes) -> str:
    """The page's text in the charset its head declares, else UTF-8."""
    declared = _CHARSET.search(body[:4096])
    if declared:
        try:
            return body.decode(declared.group(1).decode("ascii"), errors="replace")
        except LookupError:
            pass
    return body.decode("utf-8", errors="replace")


async def _picture(url: str) -> tuple[Optional[bytes], Optional[str]]:
    try:
        got = await fetch_public(url, max_bytes=MAX_IMAGE_BYTES, accept=IMAGE_ACCEPT, total_timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — unsafe host, network error, timeout
        logger.info("board link picture %s: %s", host_of(url), exc)
        return None, None
    if got.status != 200 or got.truncated or not got.content_type.startswith("image/"):
        return None, None
    return got.body, got.content_type


async def fetch_preview(url: str) -> LinkPreview:
    """What a card for `url` shows. Never raises for the page's sake."""
    plain = LinkPreview(url=url, title=host_of(url))
    try:
        page = await fetch_public(url, max_bytes=MAX_PAGE_BYTES, accept=PAGE_ACCEPT, total_timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 — unsafe host, network error, timeout
        logger.info("board link %s: %s", host_of(url), exc)
        return plain
    if page.status >= 400:
        return plain
    if page.content_type in files.IMAGE_TYPES:
        if page.truncated:
            return plain
        return LinkPreview(url=url, title=host_of(url), image_bytes=page.body, image_mime=page.content_type,
                           direct=True)
    if "html" not in page.content_type:
        return plain
    head = parse_head(_decode(page.body), page.final_url or url)
    preview = LinkPreview(url=url, title=head["title"] or host_of(url), description=head["description"],
                          site_name=head["site_name"] or host_of(page.final_url or url))
    if head["image_url"]:
        data, _mime = await _picture(head["image_url"])
        if data:
            try:
                preview.image_bytes = await asyncio.to_thread(files.thumbnail, data)
                preview.image_mime = "image/webp"
            except media.ImageRejected:
                pass
    return preview
