from app.core.services import compliance_service as cs


def test_base_title_strips_city_county_variants():
    assert cs._base_title(
        "City of West Hollywood Minimum Wage",
        "West Hollywood",
    ) == "Minimum Wage"

    assert cs._base_title(
        "Los Angeles County Minimum Wage",
        "Los Angeles",
    ) == "Minimum Wage"

    assert cs._base_title(
        "West Hollywood Minimum Wage",
        "City of West Hollywood",
    ) == "Minimum Wage"


def test_filter_by_jurisdiction_priority_prefers_local():
    requirements = [
        {
            "category": "minimum_wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
            "current_value": "$16.90",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "City of West Hollywood Minimum Wage",
            "current_value": "$20.25",
        },
        {
            "category": "overtime",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Overtime",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    assert "City of West Hollywood Minimum Wage" in titles
    assert "California Minimum Wage" not in titles
    assert "California Overtime" in titles


def test_category_normalization_groups_titles():
    requirements = [
        {
            "category": "Minimum Wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "county",
            "jurisdiction_name": "Los Angeles",
            "title": "Los Angeles County Minimum Wage",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    assert "Los Angeles County Minimum Wage" in titles
    assert "California Minimum Wage" not in titles


def test_minimum_wage_keeps_special_categories_and_general():
    requirements = [
        {
            "category": "minimum_wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Minimum Wage",
            "current_value": "$16.90",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "West Hollywood Minimum Wage",
            "current_value": "$20.25",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "West Hollywood Hotel Worker Minimum Wage",
            "current_value": "$19.61",
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "state",
            "jurisdiction_name": "California",
            "title": "California Hotel Worker Minimum Wage",
            "current_value": "$18.00",
        },
    ]

    filtered = cs._filter_by_jurisdiction_priority(requirements)
    titles = {req["title"] for req in filtered}

    assert "West Hollywood Minimum Wage" in titles
    assert "California Minimum Wage" not in titles
    assert "West Hollywood Hotel Worker Minimum Wage" in titles
    assert "California Hotel Worker Minimum Wage" not in titles


def test_normalize_value_text_handles_wording_only_changes():
    assert cs._normalize_value_text("$16.90 / hour") == cs._normalize_value_text(
        "$16.90 per hour"
    )
    assert cs._normalize_value_text("biweekly", "pay_frequency") == cs._normalize_value_text(
        "every two weeks", "pay_frequency"
    )
    assert cs._normalize_value_text("twice a month", "pay_frequency") == cs._normalize_value_text(
        "semimonthly", "pay_frequency"
    )
    assert cs._normalize_value_text(
        "semi-monthly or at least twice a month", "pay_frequency"
    ) == cs._normalize_value_text("semimonthly", "pay_frequency")
    assert cs._normalize_value_text(
        "At least twice per month", "pay_frequency"
    ) == cs._normalize_value_text("Semi-monthly", "pay_frequency")
    assert cs._normalize_value_text(
        "$16.90", "minimum_wage"
    ) == cs._normalize_value_text("$16.90/hr", "minimum_wage")

