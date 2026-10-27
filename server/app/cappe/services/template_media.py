"""Bundled example photography shared by storefront and Studio previews.

These are presentation assets, never catalog rows or magazine-library assets.
Only the versioned allowlist can be served by the public template-media route.
"""
from pathlib import Path

_ROOT = Path(__file__).parent / "site_templates" / "assets"
SAMPLE_ASSETS = {f"{name}-v1.webp": _ROOT / f"{name}-v1.webp"
                 for name in ("vessel", "tote", "lamp", "editorial-fashion", "editorial-art", "editorial-coast", "editorial-detail")}
