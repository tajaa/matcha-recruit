"""Prompt construction kept separate from scanning mechanics for provider replacement."""


def build_prompt(
    *, brand_name: str, handles: list[dict], brand_terms: list[str], exclude_terms: list[str] | None = None,
    city: str | None, state: str | None, lookback_days: int, focus: str = "all",
) -> str:
    handle_text = ", ".join(f"{h['platform']}: @{h['handle']}" for h in handles) or "none"
    terms = ", ".join(brand_terms) or brand_name
    exclusions = ", ".join(exclude_terms or []) or "none"
    place = ", ".join(value for value in (city, state) if value) or "unspecified"
    if focus == "handles":
        search_instruction = "Prioritize posts authored by accounts other than the brand that match the listed brand handles."
    elif focus == "terms":
        search_instruction = "Prioritize public posts whose text visibly contains the listed brand terms."
    else:
        search_instruction = "Search both the listed handles and the listed brand terms."
    return (
        "Use Google Search to find public posts by people other than the brand itself who positively mention this business. "
        f"{search_instruction} Business: {brand_name}. Brand handles: {handle_text}. Search terms: {terms}. "
        f"Exclude terms: {exclusions}. Location: {place}. "
        f"Prefer posts from the last {lookback_days} days. Return strict JSON only: "
        '{"mentions":[{"platform":"instagram|tiktok|youtube|facebook|x","url":"https URL","author_handle":"optional",'
        '"excerpt":"short exact excerpt","matched_terms":["terms actually visible"],"confidence":0-100,"corroborated":true|false}]}. '
        "Never return the brand's own posts or invent URLs."
    )
