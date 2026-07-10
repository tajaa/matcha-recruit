"""Authority catalog + curated CA data integrity. Pure, no DB."""
import re

import pytest

from app.core.services.scope_registry.authority_sources import (
    CURATED_INDEXES,
    FEDERAL_ECFR_PARTS,
    all_index_slugs,
    curated_index_by_slug,
    federal_part_by_slug,
)
from app.core.services.scope_registry.curated_ca import CURATED_ROWS


def test_slugs_unique_across_catalog():
    slugs = all_index_slugs()
    assert len(slugs) == len(set(slugs))


def test_federal_parts_cover_the_plan_scope():
    slugs = {p.slug for p in FEDERAL_ECFR_PARTS}
    assert slugs == {
        "ecfr-29-1910", "ecfr-29-1904", "ecfr-29-825",
        "ecfr-40-260", "ecfr-40-261", "ecfr-40-262",
    }


def test_federal_parts_have_domain_and_federal_level():
    for p in FEDERAL_ECFR_PARTS:
        assert p.level == "federal"
        assert p.domain_categories, f"{p.slug} has no domain"


def test_1910_excludes_other_osha_domains():
    p = federal_part_by_slug("ecfr-29-1910")
    assert set(p.domain_excludes) == {"construction", "agriculture", "maritime"}


def test_curated_indexes_are_non_enumerable_ca_state():
    assert {c.slug for c in CURATED_INDEXES} == {"ca-labor-code", "ca-title-8", "ca-title-16"}
    for c in CURATED_INDEXES:
        assert c.jurisdiction["state"] == "CA"
        assert c.jurisdiction["level"] == "state"
        assert c.domain_categories


def test_every_curated_index_has_rows():
    for c in CURATED_INDEXES:
        assert CURATED_ROWS.get(c.slug), f"{c.slug} has no curated rows"


def test_curated_rows_well_formed_and_unique():
    for slug, rows in CURATED_ROWS.items():
        citations = [r["citation"] for r in rows]
        assert len(citations) == len(set(citations)), f"duplicate citation in {slug}"
        for r in rows:
            assert r["citation"].strip()
            assert r["heading"].strip()
            assert r["source_url"].startswith("http"), r["citation"]
            assert r["hierarchy"], r["citation"]


def test_ab701_labor_code_range_present():
    rows = CURATED_ROWS["ca-labor-code"]
    sections = {
        int(m.group(1))
        for r in rows
        for m in [re.search(r"§\s*(\d+)", r["citation"])]
        if m
    }
    # AB 701 lives at Labor Code §§ 2100–2112; assert the core provisions.
    assert {2100, 2101, 2102, 2103}.issubset(sections)
    assert all(2100 <= s <= 2112 for s in sections)


def test_title16_has_optometry_slice():
    rows = CURATED_ROWS["ca-title-16"]
    blob = " ".join(r["heading"].lower() for r in rows)
    assert "optometry" in blob or "optician" in blob


def test_unknown_slug_lookups_return_none():
    assert federal_part_by_slug("nope") is None
    assert curated_index_by_slug("nope") is None
