"""Strict URL identity and web-search corroboration helpers."""
import hashlib
from dataclasses import dataclass
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

_POST_PATH_RULES: dict[str, tuple[str, ...]] = {
    "instagram": ("p", "reel", "reels", "tv"),
    "tiktok": ("video", "t", "v", "photo"),
    "youtube": ("watch", "shorts", "live", "v"),
    "facebook": ("posts", "reel", "videos", "photo", "photos", "permalink.php", "share", "watch", "story.php"),
    "x": ("status",),
}

_EXCLUDED_SEGMENTS = {"explore", "tags", "hashtag", "search", "directory"}

_TERMINAL_KEYWORDS = {"permalink.php", "story.php"}


def is_post_url(platform: str, raw_url: str) -> bool:
    """True only for a single public post/video permalink, not a profile, tab, or index page."""
    rules = _POST_PATH_RULES.get(platform)
    if rules is None:
        return False
    parsed = urlsplit(raw_url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if any(segment.lower() in _EXCLUDED_SEGMENTS for segment in segments):
        return False
    if platform == "youtube" and host == "youtu.be":
        return len(segments) >= 1
    if platform == "youtube" and any(segment == "watch" for segment in segments):
        return bool(dict(parse_qsl(parsed.query)).get("v"))
    lowered = [segment.lower() for segment in segments]
    for index, segment in enumerate(lowered):
        if segment not in rules:
            continue
        if segment in _TERMINAL_KEYWORDS:
            return True
        if index + 1 < len(lowered) and lowered[index + 1]:
            return True
    return False


def instagram_shortcode(raw_url: str) -> str | None:
    """Return the shortcode from /p/<code>, /reel/<code>, /reels/<code>, /tv/<code>,
    including the /<user>/p/<code> form. None for any non-post URL."""
    if not is_post_url("instagram", raw_url):
        return None
    segments = [segment for segment in urlsplit(raw_url.strip()).path.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment in ("p", "reel", "reels", "tv") and index + 1 < len(segments):
            return segments[index + 1]
    return None


@dataclass(frozen=True)
class CorroborationResult:
    accepted: list[dict]
    invalid_url: int
    source_mismatch: int


def corroborated_candidates(candidates: list[dict], grounding_uris: list[str]) -> CorroborationResult:
    """Retain only model candidates whose URL is represented by this response's grounding."""
    grounded: dict[str, str] = {}
    for uri in grounding_uris:
        for platform in _PLATFORMS:
            try:
                grounded.setdefault(url_fingerprint(platform, uri), uri)
            except LoyaltyError:
                continue
    accepted, invalid_url, source_mismatch = [], 0, 0
    for candidate in candidates:
        platform = candidate.get("platform")
        url = candidate.get("url")
        if platform not in _PLATFORMS or not isinstance(url, str):
            invalid_url += 1
            continue
        try:
            fingerprint = url_fingerprint(platform, url)
        except LoyaltyError:
            invalid_url += 1
            continue
        if fingerprint not in grounded:
            source_mismatch += 1
            continue
        accepted.append({
            **candidate,
            "canonical_url": canonicalize_social_url(platform, url),
            "url_fingerprint": fingerprint,
            "grounding_uri": grounded[fingerprint],
        })
    return CorroborationResult(accepted, invalid_url, source_mismatch)
