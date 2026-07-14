"""Vertical-coverage rules: the category vocabulary and the tag shape.

These are the two defects that made the first dental fill produce 153 rows of
California wage law wearing a `healthcare:dental` tag while every event in the
build reported success. Both are pure functions of the code, so both are
testable without a database — which is the point: nothing about the original
failure was visible to a test, an eval, or `tsc`.
"""
import importlib

import pytest

from app.core.services import industry_specialties
from app.core.services import gemini_compliance as gc


class TestCategoryVocabulary:
    """A category confirmed at runtime must be as valid as one compiled in.

    `VALID_CATEGORIES` is a frozen constant built from `compliance_registry`, so
    it can only ever know the verticals someone hand-authored. Oncology's
    categories are in it; a dental practice's are not. When an unknown category
    fails validation, `research_location_compliance_parallel` drops it, its
    requested-category list empties, and it falls back to the generic labor
    default set — so the caller gets wage law back and the specialty path stamps
    the vertical's industry_tag onto it.
    """

    def test_registry_category_is_valid(self):
        assert gc.is_valid_category("minimum_wage")

    def test_unknown_category_is_invalid(self):
        assert not gc.is_valid_category("dental_radiology_safety")

    def test_registered_category_becomes_valid(self):
        gc.register_dynamic_categories(["dental_radiology_safety"])
        assert gc.is_valid_category("dental_radiology_safety")
        # ...and survives normalization, which is what the research path calls.
        assert gc._normalize_category_value("dental_radiology_safety") == "dental_radiology_safety"

    def test_none_and_empty_are_invalid(self):
        assert not gc.is_valid_category(None)
        assert not gc.is_valid_category("")

    def teardown_method(self):
        gc._DYNAMIC_CATEGORIES.clear()


class TestNoSilentFallback:
    """An all-unknown category list must yield nothing, never the default set.

    This is the actual harm: falling back here doesn't just under-deliver, it
    researches a DIFFERENT SUBJECT and hands it back under the caller's label.
    """

    @pytest.mark.asyncio
    async def test_all_unknown_categories_returns_empty(self):
        svc = gc.GeminiComplianceService.__new__(gc.GeminiComplianceService)
        result = await gc.GeminiComplianceService.research_location_compliance_parallel(
            svc, city="Los Angeles", state="CA",
            categories=["dental_radiology_safety", "amalgam_waste_management"],
        )
        assert result == [], (
            "unknown categories must return nothing — falling back to "
            "DEFAULT_RESEARCH_CATEGORIES researches wage law and the specialty "
            "path then tags it with the vertical's industry_tag"
        )


class TestIndustryTagShape:
    """A top-level industry's tag is the bare industry, not `x:x`.

    `_get_company_industry_tags` gives a hospitality company the tag
    `hospitality`, and `_filter_requirements_for_company` intersects that against
    each row's `applicable_industries`. A requirement written as
    `hospitality:hospitality` matches no company and is invisible forever.
    """

    def test_subspecialty_tag(self):
        assert industry_specialties.industry_tag("healthcare", "dental") == "healthcare:dental"

    def test_top_level_industry_collapses(self):
        assert industry_specialties.industry_tag("hospitality", "hospitality") == "hospitality"

    def test_slugify_round_trips_through_label(self):
        slug = industry_specialties.slugify("Dental Practice")
        assert slug == "dental_practice"
        assert industry_specialties.label_from_slug(slug) == "Dental Practice"
