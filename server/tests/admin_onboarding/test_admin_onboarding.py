"""Pure-logic tests for the master-admin onboarding wizard.

No app boot, no DB — covers the bits that don't need either:
- INDUSTRY_SPECIALTIES catalog sanity
- AIScope Pydantic shape (defaults, validation, extra-field tolerance)
- build_missing_id stability
- ResolvedScope round-trip
- Bank-mapper category filtering against an in-memory fake conn
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports.
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

import asyncio
import json
from uuid import uuid4

import pytest

from app.core.models.admin_onboarding import (
    AIScope,
    AIScopeCategory,
    BasicsPayload,
    GapCheckResult,
    LocationInput,
    LocationsPayload,
    PatchSessionRequest,
    ResolvedScope,
    SizePayload,
)
from app.core.services.onboarding_scope_ai import (
    FEW_SHOT_EXAMPLES,
    INDUSTRY_SPECIALTIES,
    build_missing_id,
    expand_scope,
    map_to_bank,
)


# ── Catalog ─────────────────────────────────────────────────────────────


class TestIndustrySpecialties:
    def test_has_core_industries(self):
        for k in ("healthcare", "hospitality", "manufacturing", "retail", "construction"):
            assert k in INDUSTRY_SPECIALTIES

    def test_healthcare_includes_cardiology(self):
        assert "cardiology" in INDUSTRY_SPECIALTIES["healthcare"]

    def test_no_duplicates_within_industry(self):
        for industry, specialties in INDUSTRY_SPECIALTIES.items():
            assert len(specialties) == len(set(specialties)), f"duplicate in {industry}"


# ── Pydantic shapes ─────────────────────────────────────────────────────


class TestBasicsPayload:
    def test_required_fields(self):
        payload = BasicsPayload(
            business_name="Acme",
            industry="healthcare",
            owner_email="owner@example.com",
        )
        assert payload.business_name == "Acme"
        assert payload.specialty is None

    def test_rejects_empty_business_name(self):
        with pytest.raises(Exception):
            BasicsPayload(
                business_name="",
                industry="healthcare",
                owner_email="owner@example.com",
            )

    def test_rejects_bad_email(self):
        with pytest.raises(Exception):
            BasicsPayload(
                business_name="Acme",
                industry="healthcare",
                owner_email="not-an-email",
            )

    def test_description_round_trip(self):
        payload = BasicsPayload(
            business_name="BioCo",
            industry="biotech",
            owner_email="owner@example.com",
            description=(
                "BSL-2 lab; 8 UCSF grad students on rotation; handles human "
                "tissue samples; late-night work allowed; no minors."
            ),
        )
        assert payload.description and "BSL-2" in payload.description
        # JSON round-trip survives.
        dumped = payload.model_dump()
        again = BasicsPayload.model_validate(dumped)
        assert again.description == payload.description

    def test_empty_description_coerced_to_none(self):
        payload = BasicsPayload(
            business_name="BioCo",
            industry="biotech",
            owner_email="owner@example.com",
            description="   ",
        )
        assert payload.description is None

    def test_description_max_length_enforced(self):
        with pytest.raises(Exception):
            BasicsPayload(
                business_name="BioCo",
                industry="biotech",
                owner_email="owner@example.com",
                description="x" * 2001,
            )


class TestSizePayload:
    def test_defaults_to_manual(self):
        s = SizePayload()
        assert s.source == "manual"
        assert s.full_time == 0

    def test_rejects_negative_counts(self):
        with pytest.raises(Exception):
            SizePayload(full_time=-1)

    def test_rejects_bad_source(self):
        with pytest.raises(Exception):
            SizePayload(source="garbage")  # type: ignore[arg-type]


class TestLocations:
    def test_state_two_letter(self):
        loc = LocationInput(state="CA")
        assert loc.state == "CA"

    def test_state_too_long_rejected(self):
        with pytest.raises(Exception):
            LocationInput(state="CALI")

    def test_locations_payload_requires_at_least_one(self):
        with pytest.raises(Exception):
            LocationsPayload(locations=[])

    def test_empty_strings_coerced_to_none(self):
        # Frontend sends "" when the user picks the placeholder option.
        # Pydantic min_length=2 would reject "", so we coerce up-front.
        loc = LocationInput(state="", city="", county=" ", zipcode="")
        assert loc.state is None
        assert loc.city is None
        assert loc.county is None
        assert loc.zipcode is None

    def test_real_values_preserved(self):
        loc = LocationInput(state="TX", city="Austin", county="Travis")
        assert loc.state == "TX"
        assert loc.city == "Austin"
        assert loc.county == "Travis"


class TestPatchRequest:
    def test_partial_save(self):
        req = PatchSessionRequest(step="size")
        assert req.basics is None
        assert req.step == "size"


class TestAIScope:
    def test_round_trip(self):
        scope = AIScope(
            naics_sector="62",
            compliance_categories=[
                AIScopeCategory(category_slug="osha_general", scope="federal"),
            ],
        )
        dumped = scope.model_dump()
        again = AIScope.model_validate(dumped)
        assert again.compliance_categories[0].category_slug == "osha_general"


class TestResolvedScope:
    def test_existing_items(self):
        scope = ResolvedScope.model_validate({
            "existing": [
                {
                    "requirement_id": str(uuid4()),
                    "category_slug": "osha_general",
                    "scope_level": "federal",
                },
            ],
            "missing": [],
            "ambiguous": [],
        })
        assert len(scope.existing) == 1
        assert scope.existing[0].category_slug == "osha_general"


# ── build_missing_id ────────────────────────────────────────────────────


class TestBuildMissingId:
    def test_basic_shape(self):
        item = {
            "category_slug": "infection_control",
            "scope_level": "state",
            "state": "TX",
            "county": None,
            "city": None,
        }
        assert build_missing_id(item) == "infection_control::state::TX::-::-"

    def test_handles_missing_fields(self):
        assert build_missing_id({}) == "?::?::-::-::-"

    def test_includes_county_and_city(self):
        item = {
            "category_slug": "food_safety",
            "scope_level": "city",
            "state": "TX",
            "county": "Travis",
            "city": "Austin",
        }
        assert build_missing_id(item) == "food_safety::city::TX::Travis::Austin"

    def test_stable_for_dispatch_dedup(self):
        a = build_missing_id({"category_slug": "x", "scope_level": "state", "state": "CA"})
        b = build_missing_id({"category_slug": "x", "scope_level": "state", "state": "CA"})
        assert a == b


# ── map_to_bank against in-memory fake conn ────────────────────────────


class FakeConn:
    """Minimal asyncpg.Connection look-alike for bank mapping logic.

    Implements just enough of fetch / fetchrow to satisfy map_to_bank's
    queries. SQL parsing is by substring — brittle but adequate for unit
    coverage. Integration tests with a real Postgres are out of scope
    for the pure-helper suite.
    """

    def __init__(self, *, category_rows=None, jurisdiction_rows=None, requirement_rows=None):
        self.category_rows = category_rows or []
        self.jurisdiction_rows = jurisdiction_rows or {}
        self.requirement_rows = requirement_rows or {}

    async def fetch(self, query, *params):
        if "FROM compliance_categories" in query:
            slugs = params[0]
            return [r for r in self.category_rows if r["slug"] in slugs]
        if "FROM jurisdictions" in query and "level='state'" in query:
            return []
        if "level='county'" in query:
            return []
        if "level='city'" in query:
            return []
        if "FROM jurisdiction_requirements" in query:
            cat_id = params[0]
            return self.requirement_rows.get(str(cat_id), [])
        return []

    async def fetchrow(self, query, *params):
        if "FROM jurisdictions" in query and "level='state'" in query:
            code = params[0]
            return self.jurisdiction_rows.get(code)
        return None


class TestMapToBank:
    def test_empty_scope_returns_empty(self):
        scope = {"compliance_categories": [], "applicable_jurisdictions": []}
        result = asyncio.run(map_to_bank(scope, FakeConn()))
        assert result == {"existing": [], "missing": [], "ambiguous": []}

    def test_category_with_no_jurisdiction_context_marked_missing(self):
        scope = {
            "compliance_categories": [
                {"category_slug": "osha_general", "scope": "federal", "reason": "always applies"},
            ],
            "applicable_jurisdictions": [],
        }
        conn = FakeConn(category_rows=[{"id": "11111111-1111-1111-1111-111111111111", "slug": "osha_general"}])
        result = asyncio.run(map_to_bank(scope, conn))
        assert result["existing"] == []
        assert len(result["missing"]) == 1
        assert result["missing"][0]["category_slug"] == "osha_general"

    def test_unknown_category_slug_marked_missing(self):
        scope = {
            "compliance_categories": [
                {"category_slug": "made_up_slug", "scope": "federal"},
            ],
            "applicable_jurisdictions": [
                {"state": None, "county": None, "city": None},
            ],
        }
        conn = FakeConn(category_rows=[])
        result = asyncio.run(map_to_bank(scope, conn))
        # Slug not in bank → mapped as missing rather than crashing.
        assert any(m["category_slug"] == "made_up_slug" for m in result["missing"])

    def test_federal_match_populates_existing(self):
        cat_id = "22222222-2222-2222-2222-222222222222"
        req_id = "33333333-3333-3333-3333-333333333333"
        scope = {
            "compliance_categories": [
                {"category_slug": "osha_general", "scope": "federal"},
            ],
            "applicable_jurisdictions": [
                {"state": None, "county": None, "city": None},
            ],
        }
        conn = FakeConn(
            category_rows=[{"id": cat_id, "slug": "osha_general"}],
            requirement_rows={
                cat_id: [
                    {"id": req_id, "canonical_key": "osha-general", "title": "OSHA General Duty"},
                ],
            },
        )
        result = asyncio.run(map_to_bank(scope, conn))
        assert len(result["existing"]) == 1
        assert result["existing"][0]["requirement_id"] == req_id
        assert result["existing"][0]["scope_level"] == "federal"

    def test_jurisdictions_queries_use_actual_columns(self):
        """Regression: jurisdictions table has no 'code' or 'name' column.
        Queries must filter on state/county/city directly. Bug 2026-05-19:
        500 UndefinedColumnError on /admin/onboarding/.../resolve."""
        captured: list[str] = []

        class CapturingConn:
            async def fetch(self, q, *p):
                captured.append(q)
                if "FROM compliance_categories" in q:
                    return [{"id": "x" * 36, "slug": "osha_general"}]
                return []

            async def fetchrow(self, q, *p):
                captured.append(q)
                return None

        scope = {
            "compliance_categories": [
                {"category_slug": "osha_general", "scope": "state"},
            ],
            "applicable_jurisdictions": [
                {"state": "CA", "county": None, "city": None},
                {"state": "CA", "county": "Los Angeles", "city": None},
                {"state": "CA", "county": "Los Angeles", "city": "Long Beach"},
            ],
        }
        asyncio.run(map_to_bank(scope, CapturingConn()))
        juris_sql = [
            s for s in captured
            if "FROM jurisdictions" in s and "compliance_categories" not in s
        ]
        assert juris_sql, "expected at least one jurisdictions query"
        for s in juris_sql:
            assert "code = " not in s, f"stale 'code' column ref: {s}"
            assert " j.name " not in s and "j.name " not in s, f"stale 'name' column ref: {s}"
            assert "p.code" not in s and "gp.code" not in s, f"stale parent code ref: {s}"
        # State branch filters by state column; county/city branches by
        # their own columns.
        assert any("level='state'" in s and "state = $1" in s for s in juris_sql), juris_sql
        assert any(
            "level='county'" in s and "county ILIKE" in s for s in juris_sql
        ), juris_sql
        assert any(
            "level='city'" in s and "city ILIKE" in s for s in juris_sql
        ), juris_sql


# ── Few-shot examples ──────────────────────────────────────────────────


class TestFewShotExamples:
    def test_at_least_three_examples(self):
        # Three deliberately different shapes prime the model.
        assert len(FEW_SHOT_EXAMPLES) >= 3

    def test_each_example_has_input_and_output(self):
        for i, ex in enumerate(FEW_SHOT_EXAMPLES):
            assert "input" in ex, f"example {i} missing input"
            assert "output" in ex, f"example {i} missing output"

    def test_outputs_have_substantive_scope(self):
        # Each example output should list at least 3 categories — the point
        # of few-shot is to show shape, and "shape" includes density.
        for i, ex in enumerate(FEW_SHOT_EXAMPLES):
            out = ex["output"]
            assert len(out.get("compliance_categories", [])) >= 3, f"example {i} thin categories"
            assert len(out.get("required_certifications", [])) >= 1
            assert len(out.get("required_licenses", [])) >= 1
            assert len(out.get("applicable_jurisdictions", [])) >= 1

    def test_sports_medicine_example_specifics(self):
        # Spot-check the headline example referenced in the user request.
        sports = next(
            (ex for ex in FEW_SHOT_EXAMPLES
             if "Sports Medicine" in ex["input"]["business_name"]),
            None,
        )
        assert sports is not None
        slugs = [c["category_slug"] for c in sports["output"]["compliance_categories"]]
        assert any("hipaa" in s for s in slugs)
        assert any("ca_" in s for s in slugs)
        cert_slugs = [c["slug"] for c in sports["output"]["required_certifications"]]
        assert "clia_waived" in cert_slugs

    def test_examples_round_trip_through_json(self):
        # Examples get serialized into the Gemini prompt — must be JSON-safe.
        import json
        for ex in FEW_SHOT_EXAMPLES:
            assert json.dumps(ex)


# ── Gap check Pydantic shape ───────────────────────────────────────────


class TestGapCheckResult:
    def test_empty_arrays_round_trip(self):
        result = GapCheckResult(summary="Manifest looks comprehensive.")
        again = GapCheckResult.model_validate(result.model_dump())
        assert again.suggested_compliance_categories == []
        assert again.summary == "Manifest looks comprehensive."

    def test_populated_arrays(self):
        raw = {
            "suggested_compliance_categories": [
                {"category_slug": "irb_protocols", "scope": "federal", "reason": "grad-student research"},
            ],
            "suggested_certifications": [
                {"slug": "bbp_training", "name": "OSHA Bloodborne Pathogens Training", "reason": "tissue handling"},
            ],
            "suggested_licenses": [],
            "suggested_jurisdictions": [
                {"state": "CA", "county": None, "city": None, "reason": "all sites in CA"},
            ],
            "summary": "Two items to review",
        }
        result = GapCheckResult.model_validate(raw)
        assert len(result.suggested_compliance_categories) == 1
        assert result.suggested_compliance_categories[0].category_slug == "irb_protocols"
        assert result.suggested_jurisdictions[0].state == "CA"

    def test_jurisdiction_empty_strings_coerced(self):
        result = GapCheckResult.model_validate({
            "suggested_jurisdictions": [{"state": "", "county": " ", "city": ""}],
        })
        j = result.suggested_jurisdictions[0]
        assert j.state is None
        assert j.county is None
        assert j.city is None

    def test_bad_scope_rejected(self):
        with pytest.raises(Exception):
            GapCheckResult.model_validate({
                "suggested_compliance_categories": [
                    {"category_slug": "x", "scope": "global"},  # not a Literal value
                ],
            })


# ── expand_scope wrapper unwrapping ────────────────────────────────────


class _StubGeminiResponse:
    def __init__(self, text):
        self.text = text


class _StubGeminiModels:
    def __init__(self, text):
        self._text = text
        self.last_prompt: str = ""

    async def generate_content(self, *, model, contents, **_):
        self.last_prompt = contents
        return _StubGeminiResponse(self._text)


class _StubGeminiAio:
    def __init__(self, text):
        self.models = _StubGeminiModels(text)


class _StubGeminiClient:
    def __init__(self, text):
        self.aio = _StubGeminiAio(text)


class _ExpandConn:
    """Minimal conn satisfying _fetch_category_slugs (returns a few slugs)."""

    def __init__(self):
        self.slugs = [
            {"slug": "hipaa_privacy"},
            {"slug": "osha_general"},
            {"slug": "ca_workers_comp"},
        ]

    async def fetch(self, query, *params):
        if "FROM compliance_categories" in query:
            return self.slugs
        return []


def _run_expand(monkeypatch, gemini_text):
    client = _StubGeminiClient(gemini_text)
    monkeypatch.setattr(
        "app.core.services.onboarding_scope_ai._gemini_client",
        lambda: client,
    )
    basics = {
        "industry": "healthcare",
        "specialty": "behavioral_health",
        "business_name": "Test Co",
        "description": "ABA clinic in CA",
    }
    locations = [
        {"state": "CA", "city": "Los Angeles", "county": None, "facility_attributes": {}},
    ]
    result = asyncio.run(expand_scope(basics=basics, locations=locations, conn=_ExpandConn()))
    return result, client.aio.models.last_prompt


class TestExpandScopeUnwrap:
    def test_unwraps_input_output_dict_wrapper(self, monkeypatch):
        """Gemini sometimes echoes {input,output} — unwrap to output."""
        wrapped = json.dumps({
            "input": {"business_name": "Test Co"},
            "output": {
                "naics_sector": "62",
                "compliance_categories": [
                    {"category_slug": "hipaa_privacy", "scope": "federal", "reason": "x"},
                ],
                "required_certifications": [],
                "required_licenses": [],
                "applicable_jurisdictions": [{"state": "CA", "county": None, "city": None}],
            },
        })
        result, _ = _run_expand(monkeypatch, wrapped)
        assert result["naics_sector"] == "62"
        assert len(result["compliance_categories"]) == 1
        assert result["compliance_categories"][0]["category_slug"] == "hipaa_privacy"
        assert len(result["applicable_jurisdictions"]) == 1

    def test_unwraps_list_of_input_output(self, monkeypatch):
        """Gemini occasionally returns [{input,output}] — unwrap first."""
        wrapped = json.dumps([{
            "input": {"business_name": "Test Co"},
            "output": {
                "naics_sector": "62",
                "compliance_categories": [
                    {"category_slug": "osha_general", "scope": "federal", "reason": "y"},
                ],
                "required_certifications": [],
                "required_licenses": [],
                "applicable_jurisdictions": [],
            },
        }])
        result, _ = _run_expand(monkeypatch, wrapped)
        assert result["naics_sector"] == "62"
        assert len(result["compliance_categories"]) == 1

    def test_passes_through_flat_response(self, monkeypatch):
        """Flat AIScope-shaped response (the normal happy path)."""
        flat = json.dumps({
            "naics_sector": "62",
            "compliance_categories": [
                {"category_slug": "hipaa_privacy", "scope": "federal", "reason": "z"},
            ],
            "required_certifications": [],
            "required_licenses": [],
            "applicable_jurisdictions": [],
        })
        result, _ = _run_expand(monkeypatch, flat)
        assert result["naics_sector"] == "62"
        assert len(result["compliance_categories"]) == 1

    def test_prompt_labels_output_shape(self, monkeypatch):
        """Few-shot block must say EXPECTED OUTPUT — the raw {input, output}
        JSON dump was confusing Gemini. Pure prompt-shape regression."""
        flat = json.dumps({
            "naics_sector": "62",
            "compliance_categories": [],
            "required_certifications": [],
            "required_licenses": [],
            "applicable_jurisdictions": [],
        })
        _, prompt = _run_expand(monkeypatch, flat)
        assert "EXPECTED OUTPUT" in prompt
        assert "INPUT (for context only" in prompt
        # No bare wrapper JSON object literal (looser than the old raw dump,
        # but enough to catch a regression to dumping the FEW_SHOT_EXAMPLES
        # list directly).
        assert '"input": {' not in prompt or "EXPECTED OUTPUT" in prompt
