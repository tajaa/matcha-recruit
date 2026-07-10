"""Pure helpers behind runtime-extensible industry specialties. No DB, no network."""
import pytest

from app.core.services.industry_specialties import (
    _FALLBACK_DOMAIN,
    default_domain,
    industry_tag,
    label_from_slug,
    slugify,
)


@pytest.mark.parametrize("raw,expected", [
    ("Ophthalmology", "ophthalmology"),
    ("  Sleep Medicine  ", "sleep_medicine"),
    ("Primary Care", "primary_care"),
    ("Ear, Nose & Throat", "ear_nose_throat"),
    ("OB/GYN", "ob_gyn"),
    ("cardiology", "cardiology"),
    ("Behavioral   Health", "behavioral_health"),
])
def test_slugify(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "---"])
def test_slugify_yields_empty_for_junk(raw):
    """The endpoint rejects an empty slug rather than creating `healthcare:`."""
    assert slugify(raw) == ""


def test_slugify_is_idempotent():
    once = slugify("Behavioral Health")
    assert slugify(once) == once


def test_label_from_slug_round_trips_the_migration_seed():
    """The migration seeds labels with SQL `initcap(replace(slug,'_',' '))`."""
    assert label_from_slug("behavioral_health") == "Behavioral Health"
    assert label_from_slug("oncology") == "Oncology"
    assert label_from_slug("managed_care") == "Managed Care"


def test_label_from_slug_ignores_empty_segments():
    assert label_from_slug("a__b") == "A B"
    assert label_from_slug("") == ""


def test_industry_tag_shape_matches_compliance_categories():
    """Tags must be `parent:slug` — that is what the matrix's specialty match splits on."""
    assert industry_tag("healthcare", "ophthalmology") == "healthcare:ophthalmology"
    assert industry_tag("manufacturing", "quality") == "manufacturing:quality"


@pytest.mark.parametrize("parent,expected", [
    ("healthcare", "healthcare"),
    ("biotech", "life_sciences"),
    ("manufacturing", "manufacturing"),
])
def test_default_domain_maps_known_industries(parent, expected):
    assert default_domain(parent) == expected


def test_default_domain_falls_back_for_unknown_industry():
    """`category_domain_enum` is closed; an unmapped parent must still insert."""
    assert default_domain("retail") == _FALLBACK_DOMAIN


def test_every_default_domain_is_a_real_enum_value():
    """A domain not in `category_domain_enum` would blow up the INSERT at runtime."""
    valid = {
        "labor", "privacy", "clinical", "billing", "licensing", "safety",
        "reporting", "emergency", "corporate_integrity", "life_sciences",
        "healthcare", "manufacturing", "quality",
    }
    for parent in ("healthcare", "biotech", "manufacturing", "retail", "unknown"):
        assert default_domain(parent) in valid


# ── column-limit guards ───────────────────────────────────────────────────────

def test_column_limits_match_the_live_schema():
    """These mirror `compliance_categories`. If a migration widens a column,
    widen the constant — do not let the INSERT discover it at runtime."""
    from app.core.services.industry_specialties import (
        MAX_CATEGORY_SLUG, MAX_GROUP, MAX_INDUSTRY_TAG,
    )
    assert (MAX_CATEGORY_SLUG, MAX_GROUP, MAX_INDUSTRY_TAG) == (60, 30, 60)


def test_real_gemini_slug_fits_but_only_just():
    """Observed on the live ophthalmology derivation: 57 of 60 characters.
    The margin is what the guard exists for."""
    from app.core.services.industry_specialties import MAX_CATEGORY_SLUG

    observed = "clinical_laboratory_improvement_amendments_waived_testing"
    assert len(observed) == 57
    assert len(observed) <= MAX_CATEGORY_SLUG


def test_industry_tag_stays_within_its_column_for_a_long_specialty():
    from app.core.services.industry_specialties import MAX_GROUP, MAX_INDUSTRY_TAG

    slug = slugify("Pediatric Interventional Cardiology")  # 34 chars — over MAX_GROUP
    assert len(slug) > MAX_GROUP
    assert len(industry_tag("healthcare", slug)) <= MAX_INDUSTRY_TAG
    # The group column is the binding constraint, and `confirm` raises on it.


# ── discover-tag normalization ────────────────────────────────────────────────

def test_rewrite_tag_replaces_the_raw_discover_tag():
    """`discover_specialization_categories` derives its tag with
    `.lower().replace(' ', '_')`, which keeps punctuation: "OB/GYN" →
    `healthcare:ob/gyn`. Confirm writes `healthcare:ob_gyn`. The stored
    research_context embeds the tag as a literal instruction for future research
    passes — left unrewritten, requirements would be tagged with a tag no
    specialty or category matches, permanently invisible to the filter."""
    from app.core.services.industry_specialties import rewrite_tag

    ctx = "…Tag each requirement with 'applicable_industries': ['healthcare:ob/gyn']."
    out = rewrite_tag(ctx, "healthcare:ob/gyn", "healthcare:ob_gyn")
    assert "healthcare:ob_gyn" in out
    assert "ob/gyn" not in out


def test_rewrite_tag_noop_when_tags_agree_or_inputs_empty():
    from app.core.services.industry_specialties import rewrite_tag

    ctx = "tag ['healthcare:oncology']"
    assert rewrite_tag(ctx, "healthcare:oncology", "healthcare:oncology") == ctx
    assert rewrite_tag("", "a", "b") == ""
    assert rewrite_tag(ctx, "", "b") == ctx


def test_underlying_tag_diverges_exactly_when_name_has_punctuation():
    """Documents the divergence discover() exists to normalize."""
    for name, diverges in [("Sleep Medicine", False), ("OB/GYN", True), ("Ear, Nose & Throat", True)]:
        underlying = "healthcare:" + name.lower().replace(" ", "_")
        normalized = industry_tag("healthcare", slugify(name))
        assert (underlying != normalized) is diverges, name


# ── proposed-category key validation ─────────────────────────────────────────

def test_proposed_category_key_must_be_slug_shaped():
    """The key becomes `compliance_categories.slug` verbatim; an uppercase or
    spaced key would create a category downstream comparisons never match."""
    import pydantic

    from app.core.routes.admin import ProposedCategory

    ProposedCategory(key="laser_safety_compliance")  # valid
    for bad in ("Laser Safety", "LASER_SAFETY", "laser-safety", "_leading", "a", "x" * 61):
        with pytest.raises(pydantic.ValidationError):
            ProposedCategory(key=bad)
