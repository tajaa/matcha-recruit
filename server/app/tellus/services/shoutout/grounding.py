"""Strict URL identity and Google-grounding corroboration helpers."""
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..loyalty_service import LoyaltyError, canonicalize_social_url


def url_fingerprint(platform: str, raw_url: str) -> str:
    """Collapse known equivalent social post forms more aggressively than display URLs."""
    canonical = canonicalize_social_url(platform, raw_url)
    parsed = urlsplit(canonical)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/") or "/"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if platform == "x":
        host = "x.com"
    elif platform == "youtube":
        host = "youtube.com"
        if host == "youtube.com" and parsed.hostname == "youtu.be":
            path, query = "/watch", {"v": path.strip("/")}
        query = {key: value for key, value in query.items() if key in {"v", "list"}}
    elif platform == "instagram":
        query = {key: value for key, value in query.items() if key == "img_index"}
    key = urlunsplit(("https", host, path, urlencode(sorted(query.items())), ""))
    return hashlib.sha256(key.encode()).hexdigest()


_PLATFORMS = {"instagram", "tiktok", "youtube", "facebook", "x"}


def corroborated_candidates(candidates: list[dict], grounding_uris: list[str]) -> tuple[list[dict], int]:
    """Retain only model candidates whose URL is represented by this response's grounding."""
    grounded: dict[str, str] = {}
    for uri in grounding_uris:
        for platform in _PLATFORMS:
            try:
                grounded.setdefault(url_fingerprint(platform, uri), uri)
            except LoyaltyError:
                continue
    accepted, rejected = [], 0
    for candidate in candidates:
        platform = candidate.get("platform")
        url = candidate.get("url")
        if platform not in _PLATFORMS or not isinstance(url, str):
            rejected += 1
            continue
        try:
            fingerprint = url_fingerprint(platform, url)
        except LoyaltyError:
            rejected += 1
            continue
        if fingerprint not in grounded:
            rejected += 1
            continue
        accepted.append({
            **candidate,
            "canonical_url": canonicalize_social_url(platform, url),
            "url_fingerprint": fingerprint,
            "grounding_uri": grounded[fingerprint],
        })
    return accepted, rejected
