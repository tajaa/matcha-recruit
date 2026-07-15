"""Frozen source-page snapshots for compliance requirements (migration jrver01).

A URL is not evidence — government pages change and die. When a requirement
becomes tenant-visible (approve) or gets a codified statute citation (codify),
we fetch the cited page and store its extracted text + a content hash, so a
later dispute can show "here is the page as it read on that date".

Best-effort by contract: a fetch failure records the http_status (or 0) and
never raises into the caller's write. Deduped per requirement by content hash —
a re-verify of an unchanged page stores nothing new.
"""
import logging
from typing import Optional

import httpx

from .scope_registry.body_fetch import extract_html_text, _hash

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_HEADERS = {"User-Agent": "MatchaComplianceBot/1.0 (+compliance evidence capture)"}


async def snapshot_source(
    conn,
    requirement_id,
    url: Optional[str],
    context: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[str]:
    """Fetch ``url`` and store a snapshot row for ``requirement_id``.

    ``context`` is the event tag ('approve' | 'codify' | 'research' | 'verify').
    Returns the snapshot's outcome ('stored' | 'duplicate' | 'skipped' | 'failed')
    for logging; never raises. Pass a shared ``client`` when snapshotting many
    rows in one pass to reuse the connection pool.
    """
    if not url or not url.strip():
        return "skipped"
    url = url.strip()

    text: Optional[str] = None
    status = 0
    owns_client = client is None
    try:
        client = client or httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True)
        try:
            resp = await client.get(url)
            status = resp.status_code
            if resp.status_code == 200 and resp.content:
                ctype = resp.headers.get("content-type", "")
                if "html" in ctype or "text" in ctype or not ctype:
                    text = extract_html_text(resp.text) or None
        finally:
            if owns_client:
                await client.aclose()
    except Exception as exc:  # network/timeout/parse — record the miss, don't block
        logger.warning("snapshot_source: fetch failed for %s (%s): %s", url, context, exc)

    content_hash = _hash(text) if text else None

    try:
        # ON CONFLICT on the partial unique (requirement_id, content_hash) — same
        # page content is stored once. A failed fetch (hash NULL) always inserts,
        # so misses are still auditable, but they don't dedupe against each other.
        row = await conn.fetchrow(
            """
            INSERT INTO requirement_source_snapshots
                (requirement_id, source_url, content_text, content_hash, http_status, context)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (requirement_id, content_hash) WHERE content_hash IS NOT NULL
            DO NOTHING
            RETURNING id
            """,
            requirement_id, url, text, content_hash, status, context,
        )
        return "stored" if row else "duplicate"
    except Exception as exc:
        logger.warning("snapshot_source: insert failed for %s: %s", requirement_id, exc)
        return "failed"
