"""Dynamic search strategy selection for compliance research (Phase 2.2).

This module provides category-specific search guidance and preferred domains
to improve first-attempt accuracy in compliance research by steering Gemini
toward authoritative sources.
"""
from typing import List, Optional


CATEGORY_SEARCH_STRATEGIES = {
    "minimum_wage": {
        "search_guidance": "Prioritize official .gov sources. Check state Department of Labor/Industrial Relations.",
        "preferred_source_types": [".gov", "state labor department"],
    },
    "overtime": {
        "search_guidance": "Check federal FLSA rules via dol.gov, then state-specific exemptions.",
        "preferred_source_types": [".gov", "federal DOL"],
    },
    "sick_leave": {
        "search_guidance": "Search state labor department for paid sick leave laws. Check local ordinances.",
        "preferred_source_types": [".gov", "state DOL"],
    },
    "meal_breaks": {
        "search_guidance": "Check state wage and hour division. Many states defer to federal (no requirement).",
        "preferred_source_types": [".gov", "state labor standards"],
    },
    "pay_frequency": {
        "search_guidance": "Search state labor department for payday laws. Usually state-level only.",
        "preferred_source_types": [".gov", "state labor department"],
    },
}

# States with well-structured government data portals
STATES_WITH_STRUCTURED_DATA = {
    "CA": {
        "domain": "dir.ca.gov",
        "categories": ["minimum_wage", "sick_leave", "meal_breaks", "overtime"],
    },
    "NY": {
        "domain": "labor.ny.gov",
        "categories": ["minimum_wage", "sick_leave", "overtime"],
    },
    "WA": {
        "domain": "lni.wa.gov",
        "categories": ["minimum_wage", "sick_leave", "meal_breaks", "overtime"],
    },
    "CO": {
        "domain": "cdle.colorado.gov",
        "categories": ["minimum_wage", "sick_leave", "overtime"],
    },
    "OR": {
        "domain": "oregon.gov/boli",
        "categories": ["minimum_wage", "sick_leave", "meal_breaks"],
    },
    "NJ": {
        "domain": "nj.gov/labor",
        "categories": ["minimum_wage", "sick_leave"],
    },
    "MA": {
        "domain": "mass.gov/ago",
        "categories": ["minimum_wage", "sick_leave"],
    },
    "IL": {
        "domain": "labor.illinois.gov",
        "categories": ["minimum_wage", "sick_leave"],
    },
    "AZ": {
        "domain": "azica.gov",
        "categories": ["minimum_wage", "sick_leave"],
    },
    "TX": {
        "domain": "twc.texas.gov",
        "categories": ["minimum_wage", "pay_frequency"],
    },
}


def get_search_guidance_for_categories(categories: Optional[List[str]] = None) -> str:
    """Build search guidance text for specified categories.

    Args:
        categories: List of category names. If None, includes all categories.

    Returns:
        Formatted string with search guidance for the prompt.
    """
    if categories is None:
        categories = list(CATEGORY_SEARCH_STRATEGIES.keys())

    lines = []
    for cat in categories:
        strategy = CATEGORY_SEARCH_STRATEGIES.get(cat)
        if strategy:
            guidance = strategy["search_guidance"]
            lines.append(f"- {cat}: {guidance}")

    if not lines:
        return ""

    return "\n".join(lines)


def get_preferred_domains(state: str, categories: Optional[List[str]] = None) -> List[str]:
    """Get preferred government domains for a state and categories.

    Args:
        state: Two-letter state code (e.g., "CA").
        categories: Optional list of categories to filter by.

    Returns:
        List of preferred domain strings.
    """
    domains = []

    # Always include federal DOL
    domains.append("dol.gov")

    # Add state-specific domain if we have structured data info
    state_info = STATES_WITH_STRUCTURED_DATA.get(state.upper())
    if state_info:
        # If categories specified, only include if state covers those categories
        if categories is None or any(cat in state_info["categories"] for cat in categories):
            domains.append(state_info["domain"])

    return domains


def build_search_strategy_prompt(
    state: str,
    categories: Optional[List[str]] = None,
) -> str:
    """Build the complete search strategy section for research prompts.

    Args:
        state: Two-letter state code.
        categories: Optional list of categories being researched.

    Returns:
        Formatted prompt section with search strategy guidance.
    """
    guidance = get_search_guidance_for_categories(categories)
    preferred = get_preferred_domains(state, categories)

    if not guidance and not preferred:
        return ""

    lines = ["\nSEARCH STRATEGY GUIDANCE:"]

    if guidance:
        lines.append("Category-specific tips:")
        lines.append(guidance)

    if preferred:
        lines.append(f"\nPreferred domains for {state}:")
        for domain in preferred:
            lines.append(f"- {domain}")

    return "\n".join(lines)
