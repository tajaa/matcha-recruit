"""Prompt construction kept separate from scanning mechanics for provider replacement."""


def build_prompt(*, brand_name: str, handles: list[dict], brand_terms: list[str], city: str | None, state: str | None, lookback_days: int) -> str:
    handle_text = ", ".join(f"{h['platform']}: @{h['handle']}" for h in handles) or "none"
    terms = ", ".join(brand_terms) or brand_name
    place = ", ".join(value for value in (city, state) if value) or "unspecified"
    return (
        "Use Google Search to find public posts by people other than the brand itself who positively mention this business. "
        f"Business: {brand_name}. Brand handles: {handle_text}. Search terms: {terms}. Location: {place}. "
        f"Prefer posts from the last {lookback_days} days. Return strict JSON only: "
        '{"mentions":[{"platform":"instagram|tiktok|youtube|facebook|x","url":"https URL","author_handle":"optional",'
        '"excerpt":"short exact excerpt","matched_terms":["terms actually visible"],"confidence":0-100,"corroborated":true|false}]}. '
        "Never return the brand's own posts or invent URLs."
    )
