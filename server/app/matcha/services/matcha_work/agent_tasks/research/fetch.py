"""Loading a page for a research task's model: the page's facts, plus its links.

The same SSRF-guarded load and the same page facts as agent cards'
`fetch_page` (`agent_card/agent.py`), plus the page's links to other pages of
its own site (`page_extract.page_links`). A listing or results page is how a
model finds each listing's own page; without its links it can only cite what
a search engine happened to return. A link printed on a page this run loaded
counts as seen, so a candidate may cite it.
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.matcha.services.matcha_work.agent_card.page_extract import extract_page, page_links, page_urls

logger = logging.getLogger(__name__)

PAGE_BYTES = 2 * 1024 * 1024
FETCH_SECONDS = 25.0
MAX_OUTPUT_CHARS = 14_000


def _read(html: bytes, url: str) -> dict:
    page = extract_page(html, url)
    page["links"] = page_links(html, url)
    return page


async def fetch_page(url: str, *, fetch=fetch_public) -> tuple[dict, set[str]]:
    """(tool output, the URLs it vouches for)."""
    try:
        fetched = await fetch(url, max_bytes=PAGE_BYTES, accept="text/html,application/xhtml+xml",
                              total_timeout=FETCH_SECONDS)
    except UnsafeURL as exc:
        return {"error": f"Refused: {exc}"}, set()
    except Exception as exc:
        return {"error": f"Could not load the page: {type(exc).__name__}"}, set()
    if fetched.status >= 400:
        return {"error": f"The site answered HTTP {fetched.status}", "url": fetched.final_url}, set()
    if "html" not in fetched.content_type and "xml" not in fetched.content_type:
        return {"error": f"Not an HTML page ({fetched.content_type or 'unknown type'})"}, set()
    try:
        page = await asyncio.to_thread(_read, fetched.body, fetched.final_url)
    except Exception:
        logger.info("research page extraction failed for %s", url[:200], exc_info=True)
        return {"error": "Could not read that page's structure. Try another source."}, set()
    urls = page_urls(page) | {fetched.url} | {link["url"] for link in page["links"]}
    over = len(json.dumps(page, default=str)) - MAX_OUTPUT_CHARS
    if over > 0:
        page["text"] = page["text"][: max(0, len(page["text"]) - over)]
        page["text_truncated"] = True
    return page, urls
