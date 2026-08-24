"""Search query construction kept separate from scanning mechanics for provider replacement."""
from dataclasses import dataclass

_PLATFORM_SITE_FILTERS = {
    "instagram": "site:instagram.com",
    "tiktok": "site:tiktok.com",
    "youtube": "(site:youtube.com OR site:youtu.be)",
    "facebook": "(site:facebook.com OR site:fb.com)",
    "x": "(site:x.com OR site:twitter.com)",
}

_ALL_PLATFORMS_FILTER = "(" + " OR ".join(_PLATFORM_SITE_FILTERS.values()) + ")"

_DEFAULT_NUM_RESULTS = 20


@dataclass(frozen=True)
class SearchQuery:
    q: str
    match_terms: list[str]
    num: int


def build_query(
    *, brand_name: str, handles: list[dict], brand_terms: list[str], exclude_terms: list[str] | None = None,
    city: str | None, state: str | None, lookback_days: int, focus: str = "all", max_results: int | None = None,
) -> SearchQuery:
    del lookback_days  # Google has no reliable freshness filter for social platforms; kept for interface parity.
    terms = brand_terms or [brand_name]
    exclusions = exclude_terms or []
    num = max_results if max_results is not None else _DEFAULT_NUM_RESULTS

    if focus == "manual_handle":
        target = handles[0] if handles else {"platform": "social", "handle": "unknown"}
        handle = target["handle"]
        site_filter = _PLATFORM_SITE_FILTERS.get(target["platform"], "")
        parts = [part for part in (site_filter, f'"@{handle}"', f"-inurl:/{handle}") if part]
        return SearchQuery(q=" ".join(parts), match_terms=[handle, *terms], num=num)

    handle_terms = [f'"@{h["handle"]}"' for h in handles]
    term_terms = [f'"{term}"' for term in terms]
    if focus == "handles":
        text_terms = handle_terms or [f'"{brand_name}"']
    elif focus == "terms":
        text_terms = term_terms
    else:
        text_terms = handle_terms + term_terms

    place = " ".join(value for value in (city, state) if value)
    parts = [_ALL_PLATFORMS_FILTER, "(" + " OR ".join(text_terms) + ")"]
    if place:
        parts.append(place)
    parts.extend(f'-"{term}"' for term in exclusions)
    match_terms = [*(h["handle"] for h in handles), *terms]
    return SearchQuery(q=" ".join(parts), match_terms=match_terms, num=num)
