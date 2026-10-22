"""Which cut of a video each network gets — pure, so it is tested without a
database or a network.

A post's media names a video by `asset_id`; at publish time the item is
swapped for the cut that network takes:
  * Instagram → a Reel, from the vertical cut;
  * Facebook → a Reel from the vertical cut, or, when the clip is landscape
    (it then has a landscape cut), a regular Page video from that.
Photos pass through unchanged.
"""
from __future__ import annotations

from typing import Any

from .providers.base import ProviderError


def video_cut(platform: str, renders: dict[str, Any]) -> tuple[str, str]:
    """(format, render name) for a video on this network."""
    if platform == "facebook" and renders.get("landscape"):
        return "video", "landscape"
    return "reel", "vertical"


def media_for(platform: str, media: list[dict[str, Any]], assets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The post's media as this network receives it. Raises ProviderError
    when a video isn't ready: retryable while it is still being prepared."""
    out: list[dict[str, Any]] = []
    for item in media:
        if (item.get("kind") or "image") != "video":
            out.append(item)
            continue
        asset = assets.get(str(item.get("asset_id") or ""))
        if asset is None or asset.get("status") in ("failed", "deleted"):
            raise ProviderError((asset or {}).get("error") or "The video for this post is gone — upload it again",
                                retryable=False)
        if asset.get("status") != "ready":
            raise ProviderError("The video is still being prepared", retryable=True)
        fmt, name = video_cut(platform, asset.get("renders") or {})
        render = (asset.get("renders") or {}).get(name) or {}
        if not render.get("url"):
            raise ProviderError("The video for this post wasn't prepared — upload it again", retryable=False)
        frames = asset.get("frames") or []
        cover = frames[len(frames) // 2] if frames else {}
        out.append({**item, "url": render["url"], "format": fmt,
                    "duration_ms": render.get("duration_ms") or asset.get("duration_ms"),
                    # The middle poster frame doubles as the Reel's cover.
                    "thumb_offset_ms": cover.get("t_ms") if isinstance(cover, dict) else None})
    return out


__all__ = ["video_cut", "media_for"]
