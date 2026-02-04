"""
Source registry configuration for Tier 1 structured data sources.

These are authoritative sources that provide machine-readable compliance data
(CSV, HTML tables) that can be parsed directly without LLM interpretation.
"""

# Mapping of US state names to 2-letter codes
STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

# Reverse mapping
CODE_TO_STATE = {v: k.title() for k, v in STATE_CODES.items()}


SOURCE_REGISTRY = {
    "berkeley_minwage_csv": {
        "source_name": "UC Berkeley Labor Center",
        "source_url": "https://laborcenter.berkeley.edu/wp-content/uploads/2024/01/Local-Minimum-Wage-Ordinances-Inventory-2024.csv",
        "source_type": "csv",
        "domain": "laborcenter.berkeley.edu",
        "categories": ["minimum_wage"],
        "coverage_scope": "city_county",
        "coverage_states": None,  # All states with local ordinances
        "fetch_interval_hours": 168,  # Weekly
        "parser_config": {
            "encoding": "utf-8",
            "skip_rows": 0,
            "columns": {
                "jurisdiction": "Jurisdiction",
                "state": "State",
                "current_wage": "Current Minimum Wage",
                "effective_date": "Effective Date",
                "next_wage": "Scheduled Increase",
                "next_date": "Next Increase Date",
                "notes": "Notes",
            },
        },
    },
    "epi_minwage_tracker": {
        "source_name": "Economic Policy Institute",
        "source_url": "https://www.epi.org/minimum-wage-tracker/",
        "source_type": "html_table",
        "domain": "epi.org",
        "categories": ["minimum_wage"],
        "coverage_scope": "state",
        "coverage_states": None,  # All 50 states + DC
        "fetch_interval_hours": 168,
        "parser_config": {
            "table_selector": "table.mw-tracker-table",
            "rate_type": "general",
            "columns": {
                "state": 0,
                "current_wage": 1,
                "effective_date": 2,
                "next_wage": 3,
                "next_date": 4,
            },
        },
    },
    "dol_whd_tipped": {
        "source_name": "US DOL Wage and Hour Division - Tipped",
        "source_url": "https://www.dol.gov/agencies/whd/state/minimum-wage/tipped",
        "source_type": "html_table",
        "domain": "dol.gov",
        "categories": ["minimum_wage"],
        "coverage_scope": "state",
        "coverage_states": None,
        "fetch_interval_hours": 168,
        "parser_config": {
            "table_selector": "table",
            "rate_type": "tipped",
            "columns": {
                "state": 0,
                "cash_wage": 1,
                "tip_credit": 2,
                "total": 3,
            },
        },
    },
    "ncsl_minwage_chart": {
        "source_name": "NCSL State Minimum Wage Chart",
        "source_url": "https://www.ncsl.org/labor-and-employment/state-minimum-wages",
        "source_type": "html_table",
        "domain": "ncsl.org",
        "categories": ["minimum_wage"],
        "coverage_scope": "state",
        "coverage_states": None,
        "fetch_interval_hours": 168,
        "parser_config": {
            "table_selector": "table.state-table",
            "rate_type": "general",
            "columns": {
                "state": 0,
                "current_wage": 1,
                "future_changes": 2,
            },
        },
    },
}


def get_source_for_jurisdiction(
    state: str,
    city: str | None = None,
    county: str | None = None,
    category: str = "minimum_wage",
) -> list[str]:
    """
    Return list of source_keys that may have data for this jurisdiction.

    Priority order:
    1. City/county sources (Berkeley) if city/county provided
    2. State-level sources (EPI, DOL, NCSL)
    """
    sources = []

    # Check city/county sources first
    if city or county:
        for key, src in SOURCE_REGISTRY.items():
            if src["coverage_scope"] == "city_county" and category in src["categories"]:
                sources.append(key)

    # Then state-level sources
    for key, src in SOURCE_REGISTRY.items():
        if src["coverage_scope"] == "state" and category in src["categories"]:
            sources.append(key)

    return sources
