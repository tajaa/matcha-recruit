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
    "final_pay": {
        "search_guidance": "Search state labor department for final paycheck timing after resignation/termination and PTO/vacation payout rules.",
        "preferred_source_types": [".gov", "state wage and hour division"],
    },
    "minor_work_permit": {
        "search_guidance": "Search state labor or education agencies for youth employment permits, age restrictions, and hour limits.",
        "preferred_source_types": [".gov", "state labor standards"],
    },
    "scheduling_reporting": {
        "search_guidance": "Search state/city labor agencies for predictive scheduling, fair workweek, reporting-time pay, and spread-of-hours rules.",
        "preferred_source_types": [".gov", "city labor standards office"],
    },
    "leave": {
        "search_guidance": "Search state labor department for paid family/medical leave programs, state disability insurance, pregnancy disability leave.",
        "preferred_source_types": [".gov", "state labor department", "state EDD/ESD"],
    },
    "workplace_safety": {
        "search_guidance": "Check federal OSHA via osha.gov, then state OSHA plans. Look for state-specific safety training and reporting requirements.",
        "preferred_source_types": [".gov", "osha.gov", "state OSHA"],
    },
    "workers_comp": {
        "search_guidance": "Check state workers' compensation board/commission. Look for mandatory coverage thresholds and exemptions.",
        "preferred_source_types": [".gov", "state workers comp board"],
    },
    "anti_discrimination": {
        "search_guidance": "Check state civil rights commission/human rights agency. Look for protected classes beyond federal, training mandates, and pay equity laws.",
        "preferred_source_types": [".gov", "state civil rights commission", "state human rights"],
    },
    "hipaa_privacy": {
        "search_guidance": "Check HHS.gov and SAMHSA for HIPAA Privacy/Security Rules, HITECH breach notification, and 42 CFR Part 2 substance use disorder record rules. Search state attorney general and state health agencies for state health privacy laws exceeding HIPAA.",
        "preferred_source_types": [".gov", "hhs.gov", "state attorney general"],
    },
    "billing_integrity": {
        "search_guidance": "Check OIG.hhs.gov for Anti-Kickback Statute and False Claims Act guidance. Search CMS.gov for Medicare/Medicaid billing requirements and Stark Law. Check DOL/EBSA, CMS, and state insurance regulators for MHPAEA mental health parity enforcement.",
        "preferred_source_types": [".gov", "oig.hhs.gov", "cms.gov"],
    },
    "clinical_safety": {
        "search_guidance": "Check CMS.gov for Conditions of Participation. Search OSHA for bloodborne pathogens (29 CFR 1910.1030). Check EPA and state environmental agencies for medical waste disposal rules. Check Joint Commission standards and state health department for infection control and patient safety.",
        "preferred_source_types": [".gov", "cms.gov", "osha.gov", "jointcommission.org"],
    },
    "healthcare_workforce": {
        "search_guidance": "Check state medical/nursing board for credentialing and scope of practice. Search OIG exclusion list (LEIE). Check state mandatory reporter laws.",
        "preferred_source_types": [".gov", "state medical board", "oig.hhs.gov"],
    },
    "corporate_integrity": {
        "search_guidance": "Check OIG.hhs.gov for compliance program guidance and corporate integrity agreements. Search for state whistleblower/qui tam protections.",
        "preferred_source_types": [".gov", "oig.hhs.gov", "state attorney general"],
    },
    "research_consent": {
        "search_guidance": "Check HHS.gov OHRP for IRB oversight and Common Rule. Search FDA.gov for investigational regs and 21 CFR Part 11. Check state informed consent laws.",
        "preferred_source_types": [".gov", "hhs.gov", "fda.gov"],
    },
    "state_licensing": {
        "search_guidance": "Check state health department for facility licensure requirements, plant/accessibility standards, and post-Dobbs provider/facility abortion rules. Search state medical/nursing boards for provider licensing. Check state telehealth practice laws.",
        "preferred_source_types": [".gov", "state health department", "state medical board"],
    },
    "emergency_preparedness": {
        "search_guidance": "Check CMS.gov for EMTALA requirements and emergency preparedness rule. Search CMS/state health department survey guidance for NFPA fire and life safety adoption. Search state health department for emergency management requirements.",
        "preferred_source_types": [".gov", "cms.gov", "state health department"],
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
