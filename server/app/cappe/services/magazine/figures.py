"""A picture on a story page: responsive sizes, and the credit printed under it.

The credit always comes from the library row (`cappe_assets.credit_line`),
never from the story, so it can't be left off: an AI picture always reads "AI
illustration", an archive picture its license line, an upload whatever the
owner wrote. When a picture we must credit under CC BY/BY-SA is cropped to fill
a cover, the credit says so (the licenses ask for changes to be indicated).
"""
from __future__ import annotations

from html import escape
from typing import Optional

from ..render.sanitize import _safe_href, _safe_image

AI_CREDIT = "AI illustration"

# How wide a picture is drawn, for the browser to choose a size from srcset.
SIZES = {
    "column": "(min-width: 760px) 680px, 100vw",
    "wide": "(min-width: 1140px) 1080px, 100vw",
    "full": "100vw",
    "half": "(min-width: 760px) 50vw, 100vw",
    "third": "(min-width: 760px) 33vw, 100vw",
    "card": "(min-width: 900px) 30vw, (min-width: 600px) 45vw, 100vw",
}


def credit_text(asset: dict, *, cropped: bool = False) -> str:
    if asset.get("ai_generated"):
        return AI_CREDIT
    text = (asset.get("credit_line") or "").strip()
    if text and cropped and asset.get("license") in ("by", "by-sa"):
        text += " (cropped)"
    return text


def credit_html(asset: dict, *, cropped: bool = False) -> str:
    text = credit_text(asset, cropped=cropped)
    if not text:
        return ""
    source = _safe_href(asset.get("source_url")) if asset.get("source_url") else "#"
    inner = escape(text)
    if source != "#" and not asset.get("ai_generated"):
        inner = f'<a href="{escape(source, quote=True)}" rel="nofollow noopener" target="_blank">{inner}</a>'
    cls = "mz-credit mz-credit--ai" if asset.get("ai_generated") else "mz-credit"
    return f'<span class="{cls}">{inner}</span>'


def _variants(asset: dict) -> list[tuple[int, str]]:
    webp = (asset.get("variants") or {}).get("webp") or []
    out = []
    for v in webp:
        url = _safe_image(v.get("url")) if isinstance(v, dict) else None
        if url and isinstance(v.get("w"), int):
            out.append((v["w"], url))
    return sorted(out)


def img_html(asset: dict, *, size: str = "column", eager: bool = False, cls: str = "",
             style: str = "") -> str:
    """The `<img>` for a library picture, or "" when its URL isn't safe."""
    src = _safe_image(asset.get("url"))
    if not src:
        return ""
    variants = _variants(asset)
    attrs = [f'src="{escape(src, quote=True)}"', f'alt="{escape(asset.get("alt") or "", quote=True)}"']
    if variants:
        srcset = ", ".join(f"{escape(url, quote=True)} {w}w" for w, url in variants)
        attrs.append(f'srcset="{srcset}"')
        attrs.append(f'sizes="{SIZES.get(size, SIZES["column"])}"')
    if asset.get("width") and asset.get("height"):
        attrs.append(f'width="{int(asset["width"])}" height="{int(asset["height"])}"')
    attrs.append('fetchpriority="high"' if eager else 'loading="lazy" decoding="async"')
    if cls:
        attrs.append(f'class="{cls}"')
    if style:
        attrs.append(f'style="{escape(style, quote=True)}"')
    return f"<img {' '.join(attrs)} />"


def figure_html(asset: Optional[dict], *, caption: str = "", size: str = "column", eager: bool = False,
                cls: str = "mz-fig", style: str = "") -> str:
    """A picture with its caption and credit, or "" for an empty slot."""
    if not asset:
        return ""
    img = img_html(asset, size=size, eager=eager)
    if not img:
        return ""
    caption = (caption or asset.get("caption") or "").strip()
    credit = credit_html(asset)
    figcaption = ""
    if caption or credit:
        cap = f'<span class="mz-cap">{escape(caption)}</span>' if caption else ""
        figcaption = f"<figcaption>{cap}{credit}</figcaption>"
    style_attr = f' style="{escape(style, quote=True)}"' if style else ""
    return f'<figure class="{cls}"{style_attr}>{img}{figcaption}</figure>'


def share_image(asset: Optional[dict]) -> Optional[str]:
    """The picture for a link preview or an email: the share JPEG if stored."""
    if not asset:
        return None
    share = (asset.get("variants") or {}).get("share")
    return (_safe_image(share.get("url")) if isinstance(share, dict) else None) or _safe_image(asset.get("url"))


def card_image(asset: Optional[dict], *, width: int = 960) -> Optional[dict]:
    """A picture for a card outside a magazine page (the reader's dashboard):
    the smallest stored size at least `width` wide, else the largest, with its
    alt text and credit."""
    if not asset:
        return None
    sizes = _variants(asset)
    url = next((u for w, u in sizes if w >= width), sizes[-1][1] if sizes else None) or share_image(asset)
    if not url:
        return None
    return {"url": url, "alt": asset.get("alt") or "", "credit": credit_text(asset)}
