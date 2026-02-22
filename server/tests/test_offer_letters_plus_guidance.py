import asyncio
from app.matcha.models.offer_letter import OfferGuidanceRequest
from app.matcha.routes.offer_letters import (
    _normalize_city,
    get_offer_package_recommendation,
)


def test_offer_guidance_city_alias_normalization():
    assert _normalize_city("nyc") == "New York City"
    assert _normalize_city("salt lake city") == "Salt Lake City"


def test_offer_guidance_recommendation_returns_expected_ranges():
    payload = OfferGuidanceRequest(
        role_title="Senior Software Engineer",
        city="San Francisco",
        state="CA",
        years_experience=8,
        employment_type="Full-Time Exempt",
    )

    result = asyncio.run(
        get_offer_package_recommendation(
            payload=payload,
        )
    )

    assert result.salary_low > 0
    assert result.salary_low < result.salary_mid < result.salary_high
    assert result.bonus_target_pct_low >= 8
    assert result.bonus_target_pct_high >= result.bonus_target_pct_low
    assert result.normalized_city == "San Francisco"
    assert result.confidence >= 0.8
    assert result.rationale
