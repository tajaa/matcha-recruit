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
        },
        {
            "category": "minimum_wage",
            "jurisdiction_level": "city",
            "jurisdiction_name": "West Hollywood",
            "title": "City of West Hollywood Minimum Wage",
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


