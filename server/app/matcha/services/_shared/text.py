"""Shared text formatting helpers. Leaf module: imports nothing from services/."""
import re


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


def _slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "x"
