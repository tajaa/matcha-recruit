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


class TestEntityTypeSpecialtyMap:
    """One vertical must have ONE tag, and inference must never mint one.

    `infer_facility_profile` constrains entity_type to a CLOSED ENUM, so the
    mapping to a specialty slug is a lookup, not a heuristic. An earlier
    suffix-stripping version mangled the enum's own values ("nursing_facility" →
    "nursing", "Urgent Care" → "urgent") and could persist a company-name-shaped
    slug into healthcare_specialties — minting a disjoint ledger namespace and a
    Gemini discovery run for a vertical that doesn't exist. Signup is the only
    place a new specialty enters the vocabulary.
    """

    def test_vertical_enum_values_map_to_their_specialty(self):
        from app.core.services.vertical_coverage import _specialty_from_entity_type

        assert _specialty_from_entity_type("dental") == "dental"
        assert _specialty_from_entity_type("pharmacy") == "pharmacy"
        assert _specialty_from_entity_type("behavioral_health") == "behavioral_health"
        assert _specialty_from_entity_type("dialysis_center") == "dialysis"

    def test_facility_shapes_are_not_verticals(self):
        from app.core.services.vertical_coverage import _specialty_from_entity_type

        # hospital/clinic/fqhc describe the FACILITY, not an industry vertical —
        # trigger profiles handle those. Mapping them to a specialty would scope
        # every plain clinic into a phantom vertical.
        for shape in ("hospital", "clinic", "fqhc", "nursing_facility",
                      "ambulatory_surgery_center", "lab", "other"):
            assert _specialty_from_entity_type(shape) is None

    def test_free_text_never_mints_a_specialty(self):
        from app.core.services.vertical_coverage import _specialty_from_entity_type

        assert _specialty_from_entity_type("Dental Surgery Center of Excellence") is None
        assert _specialty_from_entity_type("Urgent Care") is None
        assert _specialty_from_entity_type("") is None
        assert _specialty_from_entity_type(None) is None


class TestUnreadableTriggerFailsOpenNotCrash:
    """A trigger we cannot parse must not take down the projection.

    `_decode_jsonb` returns an unparseable value as-is (and jsonfix01 deliberately
    leaves such rows in the DB rather than guessing), so a garbage string is
    truthy. The evaluator used to die on `cond.get("type")` — one bad catalog row
    broke the compliance tab of every tenant whose chain contained it. It now
    absorbs a str itself: valid JSON is decoded, garbage is fail-CLOSED (the
    convention `_eval_condition` already uses for an unknown op — a trigger we
    can't read is not a trigger we can assert is met).
    """

    def test_evaluator_absorbs_a_string(self):
        from app.core.services.compliance_service import evaluate_trigger_conditions

        # Garbage → not matched, and crucially NOT an exception.
        assert evaluate_trigger_conditions("not-a-dict", {}) is False
        # A JSON-encoded trigger is the real case: no JSONB codec is registered
        # on the pool, so asyncpg hands these back as str on some read paths.
        assert evaluate_trigger_conditions(
            '{"type": "entity_type", "value": "behavioral_health"}',
            {"entity_type": "behavioral_health"},
        )
        assert not evaluate_trigger_conditions(
            '{"type": "entity_type", "value": "behavioral_health"}',
            {"entity_type": "dental"},
        )
        # A JSON scalar decodes cleanly but still isn't a condition.
        assert evaluate_trigger_conditions("42", {}) is False
        # ...except a literal null, which means "no trigger" — applies to all.
        assert evaluate_trigger_conditions("null", {}) is True

    def test_projection_guards_with_isinstance(self):
        # The guard is `isinstance(trigger, dict)` in _project_chain_to_location.
        # Assert the shape it relies on: a dict trigger evaluates, everything else
        # is skipped by the caller rather than passed in.
        from app.core.services.compliance_service import evaluate_trigger_conditions

        trigger = {"type": "entity_type", "value": "behavioral_health"}
        assert evaluate_trigger_conditions(trigger, {"entity_type": "behavioral_health"})
        assert not evaluate_trigger_conditions(trigger, {"entity_type": "dental"})
        # No trigger at all → applies to everyone.
        assert evaluate_trigger_conditions(None, {})


class TestNoRulePlaceholders:
    """"No rule applies here" rows belong in the CATALOG but not on the TAB.

    The research prompt deliberately asks for such a row instead of an empty list
    (an empty list reads downstream as a FAILED category), and `skip_existing`
    callers use their presence as "this category was researched". But the tab
    answers "what am I responsible for", and a row whose entire content is
    "nothing" is noise there.

    The flag has to come from the MODEL. There is no safe heuristic, and a real
    sweep proved it in both directions: `no_surprises_act` is the regulation_key of
    an actual federal statute (a title/key matcher would delete real law), while a
    genuine placeholder came back titled "State-Level Export Control Rule" — no
    "No..." prefix at all, so a matcher would have kept it.
    """

    def test_flagged_row_is_hidden(self):
        from app.core.services.compliance_service import _is_no_rule_placeholder

        assert _is_no_rule_placeholder({"metadata": {"no_rule_applies": True}})

    def test_flag_is_read_from_the_raw_research_shape_too(self):
        # A dict straight off a research pass carries the flag top-level; only a
        # row loaded from the catalog has it nested in metadata. The stream syncs
        # the RAW set on its fallback path, so both shapes must be understood.
        from app.core.services.compliance_service import _is_no_rule_placeholder

        assert _is_no_rule_placeholder({"no_rule_applies": True})

    def test_jsonb_string_metadata_is_decoded(self):
        # asyncpg hands JSONB back as a str.
        from app.core.services.compliance_service import _is_no_rule_placeholder

        assert _is_no_rule_placeholder({"metadata": '{"no_rule_applies": true}'})

    def test_real_law_survives(self):
        from app.core.services.compliance_service import _is_no_rule_placeholder

        # The exact row a title heuristic would have destroyed.
        assert not _is_no_rule_placeholder({
            "title": "No Surprises Act (NSA) Requirements",
            "regulation_key": "no_surprises_act",
            "metadata": {"grounding": "grounded"},
        })
        # And the one it would have wrongly kept, absent the flag.
        assert not _is_no_rule_placeholder({"title": "State-Level Export Control Rule"})

    def test_unflagged_and_legacy_rows_are_untouched(self):
        from app.core.services.compliance_service import (
            _drop_no_rule_placeholders, _is_no_rule_placeholder,
        )

        assert not _is_no_rule_placeholder({"metadata": None})
        assert not _is_no_rule_placeholder({})
        reqs = [
            {"title": "real", "metadata": {}},
            {"title": "filler", "metadata": {"no_rule_applies": True}},
            {"title": "legacy", "metadata": None},
        ]
        kept = _drop_no_rule_placeholders(reqs)
        assert [r["title"] for r in kept] == ["real", "legacy"]

    def test_coercion_defaults_to_false_not_none(self):
        # A model that omits the field must not produce a null that later reads as
        # truthy-unknown; absent means "this is a real requirement".
        from app.core.services.gemini_compliance import _coerce_requirement_shape

        out = _coerce_requirement_shape({"category": "minimum_wage"}, "minimum_wage")
        assert out["no_rule_applies"] is False

    def test_coercion_accepts_the_string_form(self):
        from app.core.services.gemini_compliance import _coerce_requirement_shape

        out = _coerce_requirement_shape(
            {"category": "minimum_wage", "no_rule_applies": "true"}, "minimum_wage")
        assert out["no_rule_applies"] is True
