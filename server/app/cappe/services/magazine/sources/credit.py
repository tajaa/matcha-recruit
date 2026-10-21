"""The credit line printed under an imported picture.

Creative Commons asks for the title, the author, the source and the license
(TASL), which the line gives in that order; the figure links it to the page we
found the picture on. Public-domain and CC0 works need no credit, but a
magazine credits them anyway: it is good practice and readers expect it.
"""
from __future__ import annotations

from .base import StockResult, clean

_CC = {"by": "CC BY", "by-sa": "CC BY-SA"}


def credit_line(r: StockResult) -> str:
    creator = clean(r.creator, 160)
    title = clean(r.title, 160)
    provider = clean(r.provider_label, 80)
    if r.source == "nasa":
        return clean(f"NASA/{creator}" if creator and not creator.upper().startswith("NASA") else creator or "NASA", 500)
    if r.license in _CC:
        who = f"“{title}” by {creator}" if title and creator else (f"Photo: {creator}" if creator else f"“{title}”")
        version = f" {r.license_version}" if r.license_version else ""
        return clean(f"{who} / {_CC[r.license]}{version} via {provider}", 500)
    note = "public domain" if r.license == "pdm" else "CC0"
    if r.source == "openverse":
        who = f"Photo: {creator}" if creator else (f"“{title}”" if title else "Photo")
        return clean(f"{who} / {note} via {provider}", 500)
    # A museum's work: the artist, then the museum.
    return clean(f"{creator} / {provider} ({note})" if creator else f"{provider} ({note})", 500)
