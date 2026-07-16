"""Unit tests for the per-business compliance fit map.

All DB-free: `bucket_fit` / `classify_missing` are pure by design, so the rules
that decide what a business is told it's missing are testable without a live
catalog. Each test below pins a rule that a live run got wrong first.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.services.compliance_fit import (  # noqa: E402
    BENIGN_REASONS,
    REASON_COVERED_BY_STRICTER,
    REASON_NEVER_RESEARCHED,
    REASON_RESEARCHED_ELSEWHERE,
    REASON_STAGED,
    REASON_STALE_PROJECTION,
    bucket_fit,
    classify_missing,
    expected_for_industry,
    labor_floor,
)

CODIFIED = {
    "statute_citation": "Cal. Lab. Code § 1182.12",
    "citation_verified_at": "2026-07-16",
    "citation_item_id": "11111111-1111-1111-1111-111111111111",
}


def row(**kw):
    base = {
        "id": "22222222-2222-2222-2222-222222222222",
        "category": "overtime",
        "regulation_key": "daily_weekly_overtime",
        "requirement_key": None,
        "jurisdiction_level": "state",
        "country_code": "US",
        "title": "Daily Overtime",
        "jurisdiction_name": "California",
        "statute_citation": None,
        "citation_verified_at": None,
        "citation_item_id": None,
    }
    base.update(kw)
    return base


class TestExpectedForIndustry:
    def test_curated_industry_gets_its_core_plus_the_labor_floor(self):
        expected, provenance = expected_for_industry("healthcare")
        assert provenance == "core:healthcare"
        assert "hipaa_privacy" in expected                      # industry core
        assert "state_minimum_wage" in expected["minimum_wage"]  # labor floor merged

    def test_unknown_industry_falls_back_to_the_labor_floor_and_says_so(self):
        # 23 of 43 dev companies have no industry, and the column is free text
        # ("Technology", "test"). Guessing a keyset would invent obligations; the
        # provenance label is what stops the UI presenting a floor-only check as
        # an industry verdict.
        expected, provenance = expected_for_industry(None)
        assert provenance == "labor_floor_only"
        assert expected == labor_floor()
        assert "hipaa_privacy" not in expected

    def test_industry_without_a_curated_core_does_not_raise(self):
        # core_keys() raises for these on purpose; expected_for_industry must
        # absorb that rather than 500 a company detail page.
        expected, provenance = expected_for_industry("retail")
        assert provenance == "labor_floor_only"
        assert expected == labor_floor()


class TestCodifiedSplit:
    def test_trio_splits_visible_from_gated(self):
        fit = bucket_fit([row(**CODIFIED), row()], {})
        assert fit["counts"]["visible"] == 1
        assert fit["counts"]["gated"] == 1

    @pytest.mark.parametrize("drop", ["statute_citation", "citation_verified_at", "citation_item_id"])
    def test_any_third_of_the_trio_missing_means_gated(self, drop):
        # citation_item_id is ON DELETE SET NULL, so a citation string can
        # outlive the statute it points at. Two-thirds is not codified.
        partial = {**CODIFIED, drop: None}
        fit = bucket_fit([row(**partial)], {})
        assert fit["counts"]["gated"] == 1
        assert fit["counts"]["visible"] == 0


class TestMinimumWageNormalization:
    # The catalog keys minimum-wage rows on rate_type, and `general` means a
    # different registry key at every level. Without normalize_key the map
    # reports a business missing a minimum wage it demonstrably has — and
    # disagrees with the completeness eval on the same rows.

    def test_state_level_general_satisfies_state_minimum_wage(self):
        r = row(category="minimum_wage", regulation_key="general", jurisdiction_level="state")
        fit = bucket_fit([r], {"minimum_wage": {"state_minimum_wage"}})
        assert fit["missing"] == []

    def test_city_level_general_is_local_not_state(self):
        # The live bug: an LA dental office's only `general` row is the CITY
        # rate, which must NOT satisfy the state key.
        r = row(category="minimum_wage", regulation_key="general", jurisdiction_level="city")
        fit = bucket_fit([r], {"minimum_wage": {"state_minimum_wage"}})
        assert [m["regulation_key"] for m in fit["missing"]] == ["state_minimum_wage"]

    def test_rate_type_dialect_maps_to_registry_key(self):
        r = row(category="minimum_wage", regulation_key="tipped", jurisdiction_level="state")
        fit = bucket_fit([r], {"minimum_wage": {"tipped_minimum_wage"}})
        assert fit["missing"] == []

    def test_normalization_only_applies_to_minimum_wage(self):
        r = row(category="overtime", regulation_key="general", jurisdiction_level="city")
        fit = bucket_fit([r], {"overtime": {"general"}})
        assert fit["missing"] == []


class TestClassifyMissing:
    def test_in_chain_and_synced_is_benign_not_a_gap(self):
        # The live false positive: California's state minimum wage IS in an LA
        # office's chain; the projection dropped it because the CITY rate
        # preempts. Calling that a gap floods the admin with non-work.
        assert classify_missing(
            "minimum_wage", "state_minimum_wage",
            chain_active={"minimum_wage": {"state_minimum_wage"}},
            chain_pending={}, catalog_anywhere={},
        ) == REASON_COVERED_BY_STRICTER
        assert REASON_COVERED_BY_STRICTER in BENIGN_REASONS

    def test_unsynced_beats_covered_by_stricter(self):
        # A row written after the location last synced was never CONSIDERED by
        # the projection, so it wasn't filtered. Ordering matters: classifying
        # it benign would file a delivery bug under "working as designed".
        assert classify_missing(
            "hipaa_privacy", "hipaa_breach_notification_rule",
            chain_active={"hipaa_privacy": {"hipaa_breach_notification_rule"}},
            chain_pending={}, catalog_anywhere={},
            chain_unsynced={"hipaa_privacy": {"hipaa_breach_notification_rule"}},
        ) == REASON_STALE_PROJECTION
        assert REASON_STALE_PROJECTION not in BENIGN_REASONS

    def test_pending_in_chain_is_staged(self):
        # Live: the FEDERAL hipaa_privacy_rule row sits pending. "Approve it" is
        # a different fix from "research it".
        assert classify_missing(
            "hipaa_privacy", "hipaa_privacy_rule",
            chain_active={}, chain_pending={"hipaa_privacy": {"hipaa_privacy_rule"}},
            catalog_anywhere={"hipaa_privacy": {"hipaa_privacy_rule"}},
        ) == REASON_STAGED

    def test_elsewhere_in_catalog_is_not_never_researched(self):
        # Live: active hipaa_privacy_rule rows exist — misparented onto Idaho,
        # Texas, AZ… none in an LA chain. "Re-parent" ≠ "go research it".
        assert classify_missing(
            "hipaa_privacy", "hipaa_privacy_rule",
            chain_active={}, chain_pending={},
            catalog_anywhere={"hipaa_privacy": {"hipaa_privacy_rule"}},
        ) == REASON_RESEARCHED_ELSEWHERE

    def test_nowhere_is_never_researched(self):
        assert classify_missing(
            "clinical_safety", "emtala",
            chain_active={}, chain_pending={}, catalog_anywhere={},
        ) == REASON_NEVER_RESEARCHED

    def test_no_catalog_context_degrades_to_never_researched(self):
        # A caller that can't see the catalog must not invent a benign reason.
        assert classify_missing("leave", "fmla", {}, {}, {}) == REASON_NEVER_RESEARCHED


class TestCountsAndBuckets:
    def test_gaps_excludes_benign_but_missing_counts_everything(self):
        fit = bucket_fit(
            [], {"minimum_wage": {"state_minimum_wage"}, "leave": {"fmla"}},
            chain_active={"minimum_wage": {"state_minimum_wage"}},
        )
        assert fit["counts"]["missing"] == 2
        assert fit["counts"]["gaps"] == 1           # only fmla is real work
        assert fit["counts"]["covered_by_stricter"] == 1

    def test_a_gated_row_is_not_also_missing(self):
        # It was researched and is merely withheld — counting it missing would
        # bill one obligation as two failures with two different fixes.
        r = row(category="leave", regulation_key="fmla")
        fit = bucket_fit([r], {"leave": {"fmla"}})
        assert fit["counts"]["gated"] == 1
        assert fit["missing"] == []

    def test_beyond_core_is_counted_not_flagged(self):
        # Core is a floor, not a cap: a real obligation off the checklist is
        # still real. It must never be reported as excess to prune.
        r = row(category="cobra", regulation_key="cobra_notice")
        fit = bucket_fit([r], {"leave": {"fmla"}})
        assert fit["counts"]["beyond_core"] == 1

    def test_keyless_row_never_satisfies_an_expected_key(self):
        r = row(regulation_key=None, requirement_key=None)
        fit = bucket_fit([r], {"overtime": {"daily_weekly_overtime"}})
        assert [m["regulation_key"] for m in fit["missing"]] == ["daily_weekly_overtime"]

    def test_legacy_composite_requirement_key_still_matches(self):
        # Rows predating regulation_key only carry `category:key`.
        r = row(regulation_key=None, requirement_key="overtime:daily_weekly_overtime")
        fit = bucket_fit([r], {"overtime": {"daily_weekly_overtime"}})
        assert fit["missing"] == []

    def test_empty_projection_reports_every_expected_key(self):
        fit = bucket_fit([], {"leave": {"fmla"}, "overtime": {"daily_weekly_overtime"}})
        assert fit["counts"]["missing"] == 2
        assert fit["counts"]["projected"] == 0
