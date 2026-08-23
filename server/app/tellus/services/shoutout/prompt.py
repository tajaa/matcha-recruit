"""Prompt construction kept separate from scanning mechanics for provider replacement."""

_PLATFORM_DOMAINS = {
    "instagram": "instagram.com",
    "tiktok": "tiktok.com",
    "youtube": "youtube.com or youtu.be",
    "facebook": "facebook.com or fb.com",
    "x": "x.com or twitter.com",
}


def build_prompt(
    *, brand_name: str, handles: list[dict], brand_terms: list[str], exclude_terms: list[str] | None = None,
    city: str | None, state: str | None, lookback_days: int, focus: str = "all", max_results: int | None = None,
) -> str:
    handle_text = ", ".join(f"{h['platform']}: @{h['handle']}" for h in handles) or "none"
    terms = ", ".join(brand_terms) or brand_name
    exclusions = ", ".join(exclude_terms or []) or "none"
    place = ", ".join(value for value in (city, state) if value) or "unspecified"
    if focus == "manual_handle":
        target = handles[0] if handles else {"platform": "social", "handle": "unknown"}
        domain = _PLATFORM_DOMAINS.get(target["platform"], target["platform"])
        return (
            f"Use web search to find public {target['platform']} posts by people other than @{target['handle']} "
            f"that visibly mention, tag, or discuss @{target['handle']}. Search for public post, reel, video, or "
            f"comment URLs on the official {domain} domain; do not return posts authored by @{target['handle']}. "
            f"Do not use aggregators, profile pages, hashtag pages, search pages, analytics pages, or articles. "
            f"Prefer posts from the last {lookback_days} days. "
            f"{f'Return no more than {max_results} results. ' if max_results is not None else ''}"
            "Each returned candidate must use an exact public post URL found by web search. "
            "Do not construct URLs from handles, titles, snippets, or IDs. Omit unsupported candidates. "
            "First return this JSON object: "
            '{"mentions":[{"platform":"instagram|tiktok|youtube|facebook|x","url":"https URL","author_handle":"optional",'
            '"excerpt":"short exact excerpt","matched_terms":["terms actually visible"],"confidence":0-100,"corroborated":true|false}]}. '
            "Then add a Sources: line with an OpenAI web-search citation for the exact public post URL of every mention. "
            f"{f'Continue searching until {max_results} independently sourced posts are found or no more are available. ' if max_results is not None else ''}"
            "Never invent URLs."
        )
    if focus == "handles":
        search_instruction = "Prioritize posts authored by accounts other than the brand that match the listed brand handles."
    elif focus == "terms":
        search_instruction = "Prioritize public posts whose text visibly contains the listed brand terms."
    else:
        search_instruction = "Search both the listed handles and the listed brand terms."
    return (
        "Use web search to find public posts by people other than the brand itself who positively mention this business. "
        f"{search_instruction} Business: {brand_name}. Brand handles: {handle_text}. Search terms: {terms}. "
        f"Exclude terms: {exclusions}. Location: {place}. "
        f"Prefer posts from the last {lookback_days} days. "
        f"{f'Return no more than {max_results} results. ' if max_results is not None else ''}"
        "Each returned candidate must use an exact public post URL found by web search. "
        "Do not construct URLs from handles, titles, snippets, or IDs. Omit unsupported candidates. "
        "First return this JSON object: "
        '{"mentions":[{"platform":"instagram|tiktok|youtube|facebook|x","url":"https URL","author_handle":"optional",'
        '"excerpt":"short exact excerpt","matched_terms":["terms actually visible"],"confidence":0-100,"corroborated":true|false}]}. '
        "Then add a Sources: line with an OpenAI web-search citation for the exact public post URL of every mention. "
        "Never return the brand's own posts or invent URLs."
    )
