"""What each platform's downloadable file looks like.

TikTok and YouTube can't be posted to through their APIs yet (their app
audits are pending), so the owner downloads a file cut for each and uploads
it by hand. Instagram gets one too, for posting from the phone.

All three vertical apps take the same 1080x1920 H.264 file, and their screen
furniture (Instagram's caption block, TikTok's description and right-hand
buttons, YouTube Shorts' title) all sits in the bottom third and the right
edge. One caption box that clears all of them (`VERTICAL_BOX`) means the
three vertical files are the same file, so an export is at most two encodes:
the vertical one, and a 1920x1080 one when YouTube gets a clearly landscape
clip as a regular video.

A cut is named by its `Recipe.key` (`1080x1920-180`, `…-captions`), which is
also how the export row records what is done, so a restarted worker skips
what's already stored. Nothing here touches the network or the database.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..common import slugify
from . import render

EXPORT_PLATFORMS = ("instagram", "tiktok", "youtube")
LABELS = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube"}
# YouTube Shorts and Instagram's usual upload top out at three minutes; TikTok
# takes longer, but one length for all keeps every encode inside one task.
MAX_EXPORT_SECONDS = 180
# 6 Mbps for three minutes plus sound stays under this, so `-fs` never
# truncates a good file (a truncated one would fail `check_output`).
EXPORT_MAX_BYTES = 240 * 1024 * 1024
EXPORT_ENCODE_TIMEOUT = 480
# Debian's fonts-dejavu-core (server/Dockerfile). Passed to libass only when
# it is there; elsewhere fontconfig finds a substitute.
FONTS_DIR = "/usr/share/fonts/truetype/dejavu"
FONT = "DejaVu Sans"


@dataclass(frozen=True)
class CaptionBox:
    """Where the words sit, in the frame's own pixels (ASS PlayRes). The
    block is anchored bottom-centre `margin_v` up from the bottom."""
    font_size: int
    margin_v: int
    margin_h: int
    outline: int
    shadow: int
    max_chars: int
    max_words: int = 4


# 1080x1920: the block's bottom edge at y=1400, clear of Instagram's bottom
# 420 px, TikTok's description (from about y=1450) and its button column
# (x past 940), and the Shorts title block. 140 px each side leaves 800 px —
# about 18 characters of DejaVu Sans Bold at 72 px.
VERTICAL_BOX = CaptionBox(font_size=72, margin_v=520, margin_h=140, outline=4, shadow=2, max_chars=18)
# 1920x1080 for a regular YouTube video: lower, smaller, a little wider.
LANDSCAPE_BOX = CaptionBox(font_size=56, margin_v=90, margin_h=200, outline=3, shadow=2, max_chars=24)

_KEY = re.compile(r"(\d+)x(\d+)-(\d+)(-captions)?")


@dataclass(frozen=True)
class Recipe:
    spec: render.RenderSpec
    captions: bool
    max_seconds: int = MAX_EXPORT_SECONDS

    @property
    def key(self) -> str:
        return f"{self.spec.width}x{self.spec.height}-{self.max_seconds}{'-captions' if self.captions else ''}"

    @property
    def box(self) -> CaptionBox:
        return VERTICAL_BOX if self.spec.height > self.spec.width else LANDSCAPE_BOX

    @classmethod
    def from_key(cls, key: str) -> "Recipe":
        m = _KEY.fullmatch(key or "")
        if not m:
            raise ValueError(f"Not a recipe: {key!r}")
        size = (int(m.group(1)), int(m.group(2)))
        spec = next((s for s in (render.VERTICAL, render.LANDSCAPE) if (s.width, s.height) == size), None)
        if spec is None:
            raise ValueError(f"Not a recipe: {key!r}")
        return cls(spec=spec, captions=bool(m.group(4)), max_seconds=int(m.group(3)))


def spec_for(platform: str, facts: render.VideoFacts) -> render.RenderSpec:
    """YouTube takes a clearly landscape clip as a regular 16:9 video;
    everything else is vertical."""
    if platform == "youtube" and facts.aspect >= render.LANDSCAPE_ASPECT:
        return render.LANDSCAPE
    return render.VERTICAL


def targets_for(platforms: list[str], facts: render.VideoFacts, *, captions: bool) -> dict[str, str]:
    """`{platform: recipe key}` — several platforms share a key."""
    return {p: Recipe(spec_for(p, facts), captions).key for p in platforms if p in EXPORT_PLATFORMS}


def reusable_render(recipe: Recipe, asset: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The cut the asset already has for posting, when it is exactly this
    file: no captions and a clip short enough that the 90 s trim didn't
    bite. Marked `shared` so deleting the export leaves it alone."""
    if recipe.captions or asset.get("status") != "ready":
        return None
    if int(asset.get("duration_ms") or 0) > render.MAX_SECONDS * 1000:
        return None
    stored = (asset.get("renders") or {}).get(recipe.spec.name) or {}
    if not stored.get("url"):
        return None
    return {"url": stored["url"], "key": stored.get("key"), "width": recipe.spec.width,
            "height": recipe.spec.height, "duration_ms": stored.get("duration_ms"), "bytes": stored.get("bytes"),
            "trimmed": False, "shared": True}


def download_name(site_name: Optional[str], filename: Optional[str], target: str, ext: str) -> str:
    """`po-coffee-oat-latte-tiktok.mp4` — what the browser saves it as."""
    stem = os.path.splitext(filename or "")[0]
    parts = [slugify(site_name or "")]
    if stem:
        parts.append(slugify(stem))
    return f"{'-'.join(parts)[:80].strip('-')}-{target}{ext}"


__all__ = [
    "EXPORT_PLATFORMS", "LABELS", "MAX_EXPORT_SECONDS", "EXPORT_MAX_BYTES", "EXPORT_ENCODE_TIMEOUT", "FONTS_DIR",
    "FONT", "CaptionBox", "VERTICAL_BOX", "LANDSCAPE_BOX", "Recipe", "spec_for", "targets_for", "reusable_render",
    "download_name",
]
