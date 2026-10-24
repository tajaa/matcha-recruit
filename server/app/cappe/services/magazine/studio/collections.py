"""Portable page designs, without site-owned photos or reader access settings.

The document schema is also the collection format. Pictures become empty
frames, so reuse across the account's sites never copies private library
references or prevents a source picture being deleted. Curated graphics are
global and remain available even when hidden in the bank.
"""
import json
from typing import Any, Mapping, Optional

from .identity import resolve_item, resolved_threads
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
    if doc.get("identity") is not None:
        # A collection goes into other stories, whose identities lack these
        # styles and swatches: keep how it looks, not what it named. (The
        # Studio makes parent frames the pages' own before it sends them.)
        identity = doc["identity"]
        doc = normalize_doc({
            **{k: v for k, v in doc.items() if k != "identity"},
            "pages": [{"id": p["id"]} for p in doc["pages"]],
            "threads": [{"id": t["id"], "frames": t["frames"], "paras": t["paras"]} for t in resolved_threads(doc)],
            "items": [{k: v for k, v in resolve_item(i, identity).items() if k not in ("fill_swatch", "stroke_swatch")}
                      for i in doc["items"]],
        }, bank)
    if len(json.dumps(doc, separators=(",", ":"))) > MAX_COLLECTION_BYTES:
        raise DocError("A collection is too big to save. Use fewer pages or less text.")
    return doc
