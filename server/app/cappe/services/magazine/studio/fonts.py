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
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

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
    return _index()[0].get((family_name, int(weight), bool(italic)))


def by_sha(sha: str) -> Optional[dict]:
    return _index()[1].get(sha) if isinstance(sha, str) else None


def family(sha: str) -> str:
    """The name a face is loaded under: its own, never a font's real name."""
    return f"f-{sha[:16]}"


def url(sha: str) -> str:
    return FONT_URL.format(sha=sha)
