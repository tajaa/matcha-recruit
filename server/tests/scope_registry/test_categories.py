"""Canonical business-category taxonomy. No DB, no network.

Pins the three commit-2 guarantees of SCOPE_REGISTRY_PLAN.md:
  * category ancestry and NAICS resolution (621111 → ophthalmology chain;
    493110 → warehousing, NOT manufacturing)
  * alias round-trip for all seven legacy vocabularies
  * the legacy shim keeps `_resolve_industry`'s outputs, except the
    deliberate warehouse→manufacturing kill
"""
import pytest

from app.core.services.scope_registry.categories import (
    CATEGORIES,
    ancestry,
    categories_for_naics,
    legacy_industry_for,
    resolve_category,
    resolve_legacy_industry,
)


# ---------------------------------------------------------------------------
# Taxonomy structure


def test_every_parent_exists_and_is_declared_before_its_child():
    seen = set()
    for slug, cat in CATEGORIES.items():
        if cat.parent is not None:
            assert cat.parent in CATEGORIES
            assert cat.parent in seen, f"{slug} declared before its parent"
        seen.add(slug)


def test_slugs_are_snake_case():
    for slug in CATEGORIES:
        assert slug == slug.lower()
        assert " " not in slug


@pytest.mark.parametrize("slug,chain", [
    ("ophthalmology", ["ophthalmology", "medical_offices", "healthcare"]),
    ("medical_offices", ["medical_offices", "healthcare"]),
    ("fast_food", ["fast_food", "hospitality"]),
    ("warehousing", ["warehousing"]),
    ("manufacturing", ["manufacturing"]),
])
def test_ancestry(slug, chain):
    assert ancestry(slug) == chain


def test_ancestry_unknown_slug_is_empty_not_error():
    assert ancestry("med_spas") == []


# ---------------------------------------------------------------------------
# NAICS resolution


@pytest.mark.parametrize("naics,chain", [
    # The plan's acceptance pairs.
    ("621111", ["ophthalmology", "medical_offices", "healthcare"]),
    ("621320", ["ophthalmology", "medical_offices", "healthcare"]),
    ("493110", ["warehousing"]),          # NOT manufacturing
    ("332710", ["manufacturing"]),        # machine shop
    ("236220", ["construction"]),
    ("484121", ["transportation"]),
    ("722513", ["fast_food", "hospitality"]),
    ("621210", ["medical_offices", "healthcare"]),  # dental offices: 6212
    ("621511", ["healthcare"]),   # medical labs: healthcare, NOT medical_offices
    ("621910", ["healthcare"]),   # ambulance services: healthcare, NOT medical_offices
    ("445110", ["retail"]),
    ("541511", ["technology"]),   # custom programming: 5415; 5411 does not prefix-match
    ("541110", ["legal"]),        # offices of lawyers: 5411
])
def test_categories_for_naics(naics, chain):
    assert categories_for_naics(naics) == chain


def test_naics_longest_prefix_wins_over_sector():
    # 493 (warehousing) must beat 49 (transportation).
    assert categories_for_naics("493110") == ["warehousing"]
    # …while other 49x codes stay transportation.
    assert categories_for_naics("492110") == ["transportation"]


@pytest.mark.parametrize("bad", [None, "", "  ", "n/a", "abc"])
def test_naics_no_match_is_empty_not_error(bad):
    assert categories_for_naics(bad) == []


def test_naics_accepts_formatted_codes():
    assert categories_for_naics("6211-11") == ["ophthalmology", "medical_offices", "healthcare"]


# ---------------------------------------------------------------------------
# resolve_category — the seven legacy vocabularies round-trip


# (a) _INDUSTRY_ALIASES keys (compliance_service, now deleted) — every legacy
# key resolves; warehouse now lands on warehousing.
@pytest.mark.parametrize("raw,slug", [
    ("restaurant", "hospitality"), ("hospitality", "hospitality"),
    ("food", "hospitality"), ("hotel", "hospitality"),
    ("health", "healthcare"), ("healthcare", "healthcare"),
    ("medical", "healthcare"), ("clinic", "healthcare"),
    ("hospital", "healthcare"), ("nursing", "healthcare"),
    ("pharmacy", "healthcare"), ("dental", "healthcare"),
    ("physician", "healthcare"), ("outpatient", "healthcare"),
    ("ambulatory", "healthcare"),
    ("retail", "retail"), ("store", "retail"), ("shop", "retail"),
    ("warehouse", "warehousing"),               # the kill
    ("manufacturing", "manufacturing"), ("industrial", "manufacturing"),
    ("construction", "construction"),            # first-class in the taxonomy
    ("technology", "technology"), ("software", "technology"),
    ("saas", "technology"), ("professional services", "technology"),
    ("consulting", "technology"),
    ("fast food", "fast_food"), ("fast_food", "fast_food"),
    ("biotech", "biotech"), ("pharma", "biotech"),
    ("pharmaceutical", "biotech"), ("pharmaceuticals", "biotech"),
    ("life_sciences", "biotech"), ("life sciences", "biotech"),
    ("biopharma", "biotech"),
])
def test_legacy_alias_keys_resolve(raw, slug):
    assert resolve_category(raw) == slug


# (b) industry_compliance_profiles.name (migration indprofrestore01)
@pytest.mark.parametrize("raw,slug", [
    ("Restaurant / Hospitality", "hospitality"),
    ("Healthcare", "healthcare"),
    ("Retail", "retail"),
    ("Tech / Professional Services", "technology"),
    ("Fast Food", "fast_food"),
    ("Construction / Manufacturing", "manufacturing"),
])
def test_profile_names_resolve(raw, slug):
    assert resolve_category(raw) == slug


# (c) compliance_categories.industry_tag — colon tags resolve on their prefix
@pytest.mark.parametrize("raw,slug", [
    ("healthcare", "healthcare"),
    ("healthcare:oncology", "healthcare"),
    ("healthcare:behavioral_health", "healthcare"),
    ("biotech:pharma", "biotech"),
    ("manufacturing:quality", "manufacturing"),
    ("manufacturing:procurement", "manufacturing"),
])
def test_industry_tags_resolve(raw, slug):
    assert resolve_category(raw) == slug


# (d) admin FE INDUSTRIES (IndustryRequirements.tsx, canonical slugs since PR #25)
@pytest.mark.parametrize("raw", [
    "healthcare", "biotech", "hospitality", "retail", "technology",
    "fast food", "manufacturing",
])
def test_fe_industries_resolve(raw):
    assert resolve_category(raw) is not None


# (e) signup INDUSTRY_OPTIONS (industryConstants.ts) — every option except the
# explicit catch-all resolves into the taxonomy
@pytest.mark.parametrize("raw,slug", [
    ("healthcare", "healthcare"), ("biotech", "biotech"),
    ("dental", "healthcare"), ("technology", "technology"),
    ("retail", "retail"), ("hospitality", "hospitality"),
    ("education", "education"), ("legal", "legal"),
    ("financial_services", "financial_services"),
    ("construction", "construction"), ("manufacturing", "manufacturing"),
    ("nonprofit", "nonprofit"), ("real_estate", "real_estate"),
    ("transportation", "transportation"),
])
def test_signup_options_resolve(raw, slug):
    assert resolve_category(raw) == slug


def test_signup_catch_all_stays_unresolved():
    assert resolve_category("other") is None


# (f) GUIDED_INDUSTRY_PLAYBOOK keys (handbook_service)
@pytest.mark.parametrize("raw,slug", [
    ("hospitality", "hospitality"), ("healthcare", "healthcare"),
    ("retail", "retail"), ("manufacturing", "manufacturing"),
    ("technology", "technology"),
])
def test_playbook_keys_resolve(raw, slug):
    assert resolve_category(raw) == slug


def test_playbook_general_stays_unresolved():
    # "general" is the playbook's fallback, not an industry.
    assert resolve_category("general") is None


# (g) HEALTHCARE_SPECIALTIES (industryConstants.ts) — runtime specialties
# resolve to a healthcare-rooted category (nonprofit is its own root: the
# specialty tag healthcare:nonprofit resolves via its prefix instead).
@pytest.mark.parametrize("raw", [
    "oncology", "primary_care", "cardiology", "pediatric", "pharmacy",
    "behavioral_health", "telehealth", "managed_care", "devices",
    "transplant", "orthopedics", "neurology", "dermatology", "emergency",
    "surgery",
])
def test_healthcare_specialties_resolve_to_healthcare(raw):
    slug = resolve_category(raw)
    assert slug is not None
    assert ancestry(slug)[-1] == "healthcare"


@pytest.mark.parametrize("raw", [
    # Display forms — underscores fold to spaces in normalization, so the
    # tag form and the human-readable form land on the same alias.
    "Primary Care", "Managed Care", "Behavioral Health", "primary_care",
])
def test_specialty_display_forms_resolve(raw):
    slug = resolve_category(raw)
    assert slug is not None
    assert ancestry(slug)[-1] == "healthcare"


@pytest.mark.parametrize("raw", [
    # Generic specialty words are exact-match ONLY. Substring capture would
    # resolve these non-healthcare businesses to healthcare — a behavior the
    # legacy resolver never had (it returned "" for all of these).
    "consumer devices", "emergency restoration services", "tree surgery",
    "organ transplant logistics",  # …resolves via "logistics", not "transplant"
])
def test_generic_specialty_words_do_not_substring_capture(raw):
    slug = resolve_category(raw)
    assert slug is None or ancestry(slug)[-1] != "healthcare"


# The plan's previously-unresolvable strings
@pytest.mark.parametrize("raw,slug", [
    ("logistics", "warehousing"),
    ("distribution center", "warehousing"),
    ("fulfillment center", "warehousing"),
    ("warehousing", "warehousing"),
    ("transportation", "transportation"),
    ("shipping", "transportation"),
    ("trucking", "transportation"),
])
def test_new_vocabulary_resolves(raw, slug):
    assert resolve_category(raw) == slug


# Fuzzy inputs keep the legacy substring semantics
@pytest.mark.parametrize("raw,slug", [
    ("healthcare provider", "healthcare"),
    ("fast food restaurant", "hospitality"),  # legacy dict order: restaurant first
    ("Ophthalmology", "ophthalmology"),
    ("  Retail  ", "retail"),
])
def test_fuzzy_resolution(raw, slug):
    assert resolve_category(raw) == slug


@pytest.mark.parametrize("raw", [None, "", "   ", "asdfgh"])
def test_unresolvable_is_none(raw):
    assert resolve_category(raw) is None


# ---------------------------------------------------------------------------
# Legacy shim — resolve_legacy_industry must keep _resolve_industry's contract


@pytest.mark.parametrize("raw,expected", [
    # Preserved outputs (the old resolver's own test vectors)
    ("Manufacturing", "manufacturing"),
    ("hospital", "healthcare"),
    ("restaurant", "hospitality"),
    ("SaaS", "technology"),
    ("fast_food", "fast food"),
    ("Fast Food", "fast food"),
    ("biopharma", "biotech"),
    ("construction", "manufacturing"),  # combined legacy profile, unchanged
    ("dental", "healthcare"),
    ("", ""),
    (None, ""),
    ("asdfgh", ""),
    # The one deliberate change
    ("warehouse", ""),
    # New taxonomy with no legacy vocabulary → "" (industry_tag matching unchanged)
    ("transportation", ""),
    ("education", ""),
    ("financial_services", ""),
])
def test_resolve_legacy_industry(raw, expected):
    assert resolve_legacy_industry(raw) == expected


def test_legacy_industry_walks_ancestry():
    # ophthalmology has no legacy word of its own path stops at healthcare
    assert legacy_industry_for("ophthalmology") == "healthcare"
    assert legacy_industry_for("fast_food") == "fast food"
    assert legacy_industry_for("warehousing") == ""


def test_compliance_service_shim_delegates():
    """`_resolve_industry` is now a shim — same function object contract."""
    from app.core.services.compliance_service import _resolve_industry

    for raw in ("hospital", "warehouse", "SaaS", "Fast Food", None, "other"):
        assert _resolve_industry(raw) == resolve_legacy_industry(raw)
