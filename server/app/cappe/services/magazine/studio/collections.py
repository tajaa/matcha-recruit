"""Portable page designs, without site-owned photos or reader access settings.

The document schema is also the collection format. Pictures become empty
frames, so reuse across the account's sites never copies private library
references or prevents a source picture being deleted. Curated graphics are
global and remain available even when hidden in the bank.
"""
import json
from typing import Any, Mapping, Optional

from .schema import DocError, normalize_doc

MAX_COLLECTIONS = 50
MAX_COLLECTION_PAGES = 32
MAX_COLLECTION_BYTES = 1_000_000


def collection_doc(raw: dict[str, Any], bank: Optional[Mapping[str, dict]] = None) -> dict:
    if len(json.dumps(raw, ensure_ascii=True, separators=(",", ":"))) > MAX_COLLECTION_BYTES:
        raise DocError("A collection is too big to save. Use fewer pages or less text.")
    if isinstance(raw.get("pages"), list) and len(raw["pages"]) > MAX_COLLECTION_PAGES:
        raise DocError(f"A collection holds at most {MAX_COLLECTION_PAGES} pages.")
    portable = {**raw, "paywall_page": None}
    if isinstance(raw.get("items"), list):
        portable["items"] = [
            {**i, "asset_id": None, "caption": ""} if isinstance(i, dict) and i.get("kind") == "image" else i
            for i in raw["items"]
        ]
    if isinstance(raw.get("threads"), list):
        portable["threads"] = [{k: v for k, v in t.items() if k != "comp"} if isinstance(t, dict) else t
                               for t in raw["threads"]]
    try:
        doc = normalize_doc(portable, bank)
    except (TypeError, OverflowError) as exc:
        raise DocError("This collection has malformed page data. Check its frames and text, then try again.") from exc
    if len(json.dumps(doc, separators=(",", ":"))) > MAX_COLLECTION_BYTES:
        raise DocError("A collection is too big to save. Use fewer pages or less text.")
    return doc
