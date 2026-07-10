"""Fetch and store the full statute/regulation text for authority items.

The registry stored citation + heading + source_url only; compliance means being
able to read the obligation. This fetches the body text from official sources and
stores it on ``authority_index_items`` (migration ``statbody01``).

Two fetch strategies, dispatched by source (``fetcher_for``):
  * **ecfr** — one call to the eCFR versioner **full-text XML** endpoint per
    (title, part), then match each item by its citation. Efficient: one request
    covers a whole part's sections.
  * **html** — a generic best-effort fetch of the item's ``source_url`` (CA
    leginfo, dir.ca.gov, uscode/cornell, …), with bs4 main-content extraction.
    This is what makes "future states plug in" work — any .gov HTML page is
    fetchable without new code.

Pure extractors (``extract_ecfr_bodies``, ``extract_html_text``, ``_norm_citation``)
are fixture-tested with no network. Never invents text: an unfetchable item is
reported skipped/failed, never filled.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; MatchaCompliance/1.0; +https://hey-matcha.com)"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_ECFR_FULL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?part={part}"


# ── pure helpers ─────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Collapse whitespace; trim. The reading text, not layout."""
    return re.sub(r"[ \t]*\n[ \t\n]*", "\n", re.sub(r"[ \t]+", " ", text or "")).strip()


def _norm_citation(c: str) -> str:
    """eCFR full-XML metadata cites subparts as '29 CFR Part 1904 Subpart A' while
    our items store '29 CFR 1904 Subpart A' — drop 'Part ' ONLY in the
    'NN CFR Part NNNN' prefix (anchored, so unrelated 'Part' tokens in appendix
    citations can't collapse two citations onto one key). Sections match as-is."""
    return re.sub(r"(\bCFR )Part\s+", r"\1", (c or "").strip())


def _citation_of(el, _html) -> Optional[str]:
    hm = el.get("hierarchy_metadata")
    if not hm:
        return None
    m = re.search(r'"citation"\s*:\s*"([^"]+)"', _html.unescape(hm))
    return m.group(1) if m else None


def _own_text(el, _html) -> str:
    """Text of an element EXCLUDING descendants that carry their own citation.

    A subpart (DIV6) contains its sections (DIV8), each an item in its own right;
    without this, the subpart body would duplicate every section's text (2x the
    part, hundreds of KB). This yields each node's *own* obligation text only."""
    parts: List[str] = []

    def walk(node, is_root: bool):
        if not is_root and _citation_of(node, _html):
            return  # captured as its own item
        if node.text:
            parts.append(node.text)
        for ch in node:
            walk(ch, False)
            if ch.tail:
                parts.append(ch.tail)

    walk(el, True)
    return _clean(" ".join(parts))


def extract_ecfr_bodies(xml: bytes | str) -> Dict[str, str]:
    """Parse eCFR full-text XML → {normalized citation: body text}.

    Every DIV node carries a ``hierarchy_metadata`` attribute whose ``citation``
    identifies it; the node's *own* text (not its sub-items) is its body.
    """
    import html as _html

    from lxml import etree

    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    root = etree.fromstring(xml)
    out: Dict[str, str] = {}
    for el in root.iter():
        raw = _citation_of(el, _html)
        if not raw:
            continue
        text = _own_text(el, _html)
        if len(text) < 40:
            # A subpart usually has no prose of its own (just its heading) —
            # a 17-char "body" would open an empty reader. Fall back to the
            # full subtree so reading a subpart reads its sections.
            text = _clean(" ".join(el.itertext()))
        if text:
            out[_norm_citation(raw)] = text
    return out


def extract_html_text(html: str) -> str:
    """Best-effort readable text from a source page (bs4). Strips chrome; prefers
    a known/main content container, falls back to the body."""
    import warnings

    from bs4 import BeautifulSoup
    try:
        from bs4 import XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    except Exception:
        pass

    soup = BeautifulSoup(html or "", "lxml")
    # NB: do NOT strip <form> — JSF/XHTML .gov pages (CA leginfo) wrap the law
    # text inside a form, so decomposing it nukes the content.
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "svg"]):
        tag.decompose()
    node = None
    # Known content containers (CA leginfo id=codeLawSectionNoHead / single_law_section;
    # eCFR renderer; Cornell), then generic mains.
    for sel in ("#codeLawSectionNoHead", "#single_law_section", "#manylawsections",
                "#content_main", "#displayCodeSection",
                "main", "article", "#content", ".content", "#main-content"):
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) >= 40:
            break
        node = None
    node = node or soup.body or soup
    return _clean(node.get_text("\n"))


_USC_RE = re.compile(r"(\d+)\s+U\.?\s*S\.?\s*C\.?\s+§?\s*([\w.\-]+)")
_GOVINFO_LINK = "https://www.govinfo.gov/link/uscode/{title}/{section}"


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF (govinfo U.S. Code granule)."""
    import fitz  # pymupdf

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return _clean("\n".join(page.get_text() for page in doc))


async def _fetch_uscode_body(client, citation: str):
    """Official U.S. Code text via govinfo (NOT Cornell — ToS). The link service
    resolves title/section to the official PDF granule; extract its text.
    Returns (text, pdf_url) or None.

    Known limitation: govinfo granules are page-based, so the text can open with
    the tail of the neighboring section (e.g. §213's first page carries the end
    of §212). That's the official artifact — deliberately not trimmed, since a
    slicing heuristic risks cutting real notes."""
    m = _USC_RE.search(citation or "")
    if not m:
        return None
    title, section = m.group(1), m.group(2)
    r = await client.get(_GOVINFO_LINK.format(title=title, section=section))
    r.raise_for_status()
    final = str(r.url)
    # A successful resolution lands on the official PDF granule; a soft-404
    # lands on an error/node URL. Guard on both the URL and the content type.
    if not final.lower().endswith(".pdf") or "pdf" not in r.headers.get("content-type", "").lower():
        return None
    text = _pdf_text(r.content)
    return (text, final) if text and len(text) >= 40 else None


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ── async fetch/store ────────────────────────────────────────────────────────

async def _store_body(conn, item_id, body_text: str, source_url: str) -> str:
    """Upsert one item's body. Returns 'fetched' | 'unchanged'."""
    h = _hash(body_text)
    existing = await conn.fetchval(
        "SELECT body_hash FROM authority_index_items WHERE id = $1", item_id
    )
    if existing == h:
        return "unchanged"
    await conn.execute(
        """
        UPDATE authority_index_items
        SET body_text = $2, body_source_url = $3, body_fetched_at = NOW(), body_hash = $4
        WHERE id = $1
        """,
        item_id, body_text, source_url, h,
    )
    return "fetched"


async def _fetch_ecfr_index(conn, index_row, items, client) -> Dict[str, Any]:
    """One full-text XML call for the part, then match items by citation."""
    from app.core.services.government_apis.ecfr import _fetch_title_dates

    slug = index_row["slug"]  # ecfr-<title>-<part>
    m = re.match(r"ecfr-(\d+)-(\d+)$", slug)
    if not m:
        return {"fetched": 0, "unchanged": 0, "failed": len(items),
                "warnings": [f"{slug}: not an ecfr title-part slug"]}
    title, part = int(m.group(1)), int(m.group(2))
    dates = await _fetch_title_dates(client)
    date = dates.get(title)
    if not date:
        return {"fetched": 0, "unchanged": 0, "failed": len(items),
                "warnings": [f"{slug}: no eCFR issue date for title {title}"]}

    url = _ECFR_FULL.format(date=date, title=title, part=part)
    resp = await client.get(url)
    resp.raise_for_status()
    bodies = extract_ecfr_bodies(resp.content)

    fetched = unchanged = 0
    warnings: List[str] = []
    for it in items:
        text = bodies.get(_norm_citation(it["citation"]))
        if not text:
            warnings.append(f"{it['citation']}: no matching text in eCFR XML")
            continue
        status = await _store_body(conn, it["id"], text, url)
        fetched += status == "fetched"
        unchanged += status == "unchanged"
    return {"fetched": fetched, "unchanged": unchanged,
            "failed": 0, "warnings": warnings}


async def _fetch_html_index(conn, index_row, items, client) -> Dict[str, Any]:
    """Per-item fetch: a U.S. Code citation goes to the official govinfo source;
    anything else is a best-effort HTML extract off its source_url."""
    fetched = unchanged = failed = 0
    warnings: List[str] = []
    for it in items:
        try:
            # U.S. Code → govinfo (official), regardless of the stored (Cornell) link.
            usc = await _fetch_uscode_body(client, it["citation"])
            if usc:
                text, src = usc
            else:
                url = it.get("source_url")
                if not url or not str(url).startswith("http"):
                    warnings.append(f"{it['citation']}: no http source_url")
                    continue
                resp = await client.get(url)
                resp.raise_for_status()
                text, src = extract_html_text(resp.text), url
            if not text or len(text) < 40:
                warnings.append(f"{it['citation']}: empty/too-short extract")
                failed += 1
                continue
            status = await _store_body(conn, it["id"], text, src)
            fetched += status == "fetched"
            unchanged += status == "unchanged"
        except Exception as exc:
            warnings.append(f"{it['citation']}: {exc}")
            failed += 1
        await asyncio.sleep(0.3)  # good citizen
    return {"fetched": fetched, "unchanged": unchanged, "failed": failed, "warnings": warnings}


async def fetch_bodies_for_index(conn, slug: str) -> Dict[str, Any]:
    """Fetch statute bodies for one authority index. Idempotent (hash-skips
    unchanged). eCFR indexes fetch as one batch XML; others go per-item
    (U.S. Code → govinfo, else generic HTML). Never invents text."""
    index_row = await conn.fetchrow(
        "SELECT id, slug, source_type FROM authority_indexes WHERE slug = $1", slug
    )
    if index_row is None:
        raise ValueError(f"unknown authority index: {slug!r}")
    items = [
        dict(r) for r in await conn.fetch(
            "SELECT id, citation, source_url FROM authority_index_items "
            "WHERE authority_index_id = $1 ORDER BY citation",
            index_row["id"],
        )
    ]
    if not items:
        return {"slug": slug, "fetched": 0, "unchanged": 0, "failed": 0, "warnings": []}

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": _UA},
                                 follow_redirects=True) as client:
        if index_row["source_type"] == "ecfr":
            res = await _fetch_ecfr_index(conn, index_row, items, client)
        else:
            res = await _fetch_html_index(conn, index_row, items, client)
    return {"slug": slug, **res}
