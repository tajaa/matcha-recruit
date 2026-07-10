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


def test_curated_index_set():
    assert {c.slug for c in CURATED_INDEXES} == {
        "us-flsa", "ca-labor-code", "ca-title-8", "ca-title-16",
    }
    for c in CURATED_INDEXES:
        assert c.domain_categories


def test_ca_curated_indexes_are_ca_state():
    for c in CURATED_INDEXES:
        if c.slug == "us-flsa":
            continue
        assert c.jurisdiction["state"] == "CA"
        assert c.jurisdiction["level"] == "state"


def test_us_flsa_is_a_federal_curated_index():
    flsa = next(c for c in CURATED_INDEXES if c.slug == "us-flsa")
    assert flsa.level == "federal"
    assert flsa.jurisdiction == {}  # NULL jurisdiction — applies to all US employers


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
    """AB 701 (warehouse quotas) lives at Labor Code §§ 2100-2112 — still present
    alongside the core wage-hour spine ca-labor-code now also carries."""
    sections = {
        int(m.group(1))
        for r in CURATED_ROWS["ca-labor-code"]
        for m in [re.search(r"§\s*(\d+)", r["citation"])]
        if m
    }
    assert {2100, 2101, 2102, 2103}.issubset(sections)


def test_ca_labor_code_carries_the_wage_hour_spine():
    citations = {r["citation"] for r in CURATED_ROWS["ca-labor-code"]}
    for core in ("Cal. Lab. Code § 1182.12", "Cal. Lab. Code § 510",
                 "Cal. Lab. Code § 512", "Cal. Lab. Code § 246",
                 "Cal. Lab. Code § 3700"):
        assert core in citations, core


def test_title16_has_optometry_slice():
    rows = CURATED_ROWS["ca-title-16"]
    blob = " ".join(r["heading"].lower() for r in rows)
    assert "optometry" in blob or "optician" in blob


def test_title16_citations_are_the_verified_set():
    """Web-verified 2026-07-10 — pins the corrected citations.

    An earlier draft invented §1516/§1517/§1524/§2541/§2559.2 (CE is §1536,
    contact-lens dispensing is BPC §2542, RDO registration is BPC §2550).
    Changing this set means re-verifying against the statute, not just
    editing the test.
    """
    citations = {r["citation"] for r in CURATED_ROWS["ca-title-16"]}
    assert citations == {
        "Cal. Bus. & Prof. Code § 3041",
        "Cal. Bus. & Prof. Code § 3041.3",
        "16 CCR § 1536",
        "Cal. Bus. & Prof. Code § 2542",
        "Cal. Bus. & Prof. Code § 2550",
    }


def test_no_fabricated_westlaw_urls():
    """calregs.westlaw permalinks use opaque GUIDs — a constructed one is fake."""
    for rows in CURATED_ROWS.values():
        for r in rows:
            assert "govt.westlaw.com" not in r["source_url"], r["citation"]


def test_unknown_slug_lookups_return_none():
    assert federal_part_by_slug("nope") is None
    assert curated_index_by_slug("nope") is None
