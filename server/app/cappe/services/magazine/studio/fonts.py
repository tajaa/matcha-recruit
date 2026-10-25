"""The Studio's own faces: the catalog (`magazine/fonts.FONTS`) built as
static, Latin-subset files with the same vertical metrics in every table, so
every browser puts a baseline where the Studio measured it.

`server/scripts/build_magazine_fonts.py` builds them from google/fonts at a
pinned commit (the build is deterministic, so every environment has the same
bytes) and writes `fonts_manifest.json`, committed here. Each face is served
by its sha256 at `/api/cappe/public/fonts/<sha>.ttf` (`routes/public/
fonts.py`), immutable, from our own origin: the Studio measures those bytes
(HarfBuzz) and shows them (`FontFace`), and a reader's page loads them under
the same name, `f-<sha>`.

A face the manifest lacks (a catalog face not built yet) is set by name from
Google Fonts instead; its lines may then sit a little off what the Studio
showed.
"""
from __future__ import annotations

import json
import math
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

MANIFEST = Path(__file__).resolve().parent / "fonts_manifest.json"
FONT_URL = "/api/cappe/public/fonts/{sha}.ttf"
_SHA = re.compile(r"^[0-9a-f]{64}$")


@lru_cache(maxsize=1)
def manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    faces = [f for f in data.get("faces") or [] if isinstance(f, dict) and _SHA.match(str(f.get("sha", "")))]
    return {"version": data.get("version") or "", "faces": faces}


@lru_cache(maxsize=1)
def _index() -> tuple[dict, dict]:
    by_style = {(f["family"], int(f["weight"]), bool(f["italic"])): f for f in manifest()["faces"]}
    by_sha = {f["sha"]: f for f in manifest()["faces"]}
    return by_style, by_sha


def face(family_name: str, weight: int, italic: bool) -> Optional[dict]:
    """A built face, else (while a document is shown) one of its own fonts."""
    key = (family_name, int(weight), bool(italic))
    found = _index()[0].get(key)
    if found is None and isinstance(family_name, str) and family_name.startswith("u-"):
        found = (_showing.get() or {}).get(key)
    return found


def by_sha(sha: str) -> Optional[dict]:
    return _index()[1].get(sha) if isinstance(sha, str) else None


def family(sha: str) -> str:
    """The name a face is loaded under: its own, never a font's real name."""
    return f"f-{sha[:16]}"


def url(sha: str) -> str:
    return FONT_URL.format(sha=sha)


# ── a magazine's own fonts ───────────────────────────────────────────────────
#
# A run names one by its key, `u-` and 16 hex digits (`custom_fonts.py`), never
# a font's real name. While a document is checked (`schema.normalize_doc`) the
# site's faces are in scope (`checking`): a key the site has gets its nearest
# weight, one it doesn't falls back to the default font, as an unknown catalog
# font does. A stored document carries the faces it names (`doc.faces`), so
# rendering it puts those in scope (`showing`) and trusts its keys.

CUSTOM = re.compile(r"^u-[0-9a-f]{16}$")
_checking: ContextVar[Optional[Mapping[str, list]]] = ContextVar("studio_custom_faces", default=None)
_showing: ContextVar[Optional[dict]] = ContextVar("studio_doc_faces", default=None)


@contextmanager
def checking(faces: Optional[Mapping[str, list]]) -> Iterator[None]:
    """`faces`: the site's own fonts the document names, {key: [face, ...]}."""
    token = _checking.set(faces or {})
    try:
        yield
    finally:
        _checking.reset(token)


def checking_faces() -> Optional[Mapping[str, list]]:
    return _checking.get()


@contextmanager
def showing(doc: Optional[dict]) -> Iterator[None]:
    faces = [f for f in (doc or {}).get("faces") or [] if isinstance(f, dict)]
    token = _showing.set({(f["family"], int(f["weight"]), bool(f["italic"])): f for f in faces})
    try:
        yield
    finally:
        _showing.reset(token)


def custom_face(family_key: Any, weight: Any, italic: Any) -> Optional[tuple[str, int, bool]]:
    """A custom font's (key, weight, italic) as stored, or None when it isn't
    one (or, while checking, the site doesn't have it)."""
    if not isinstance(family_key, str) or not CUSTOM.match(family_key):
        return None
    want = float(weight) if isinstance(weight, (int, float)) and not isinstance(weight, bool) and math.isfinite(weight) else 400.0
    scope = _checking.get()
    if scope is None:
        return family_key, int(max(100, min(900, math.floor(want / 100 + 0.5) * 100))), bool(italic)
    faces = scope.get(family_key) or []
    if not faces:
        return None
    # The style asked for when the family has it, else the other (an
    # italic-only family sets upright text in italic); ties go to the
    # heavier, as nearest_weight.
    style = [f for f in faces if bool(f["italic"]) == bool(italic)] or faces
    wt = min((int(f["weight"]) for f in style), key=lambda x: (abs(x - want), -x))
    return family_key, wt, bool(style[0]["italic"])
