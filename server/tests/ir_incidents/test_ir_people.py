"""Unit tests for the IR people (no-roster identity) pure helpers.

Covers normalization + role extraction. DB-touching helpers
(_upsert_ir_person / _sync_incident_people) are exercised manually against
the dev DB per the plan's verification steps — not here (no live DB in CI).
"""
import sys
from types import ModuleType

# Stub google.genai before any app imports (mirrors test_ir_incidents.py).
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

import pytest

try:
    from app.matcha.routes.ir_incidents._shared import (
        _normalize_person_name,
        _gather_incident_people,
    )
except Exception:  # pragma: no cover - transitive import issue
    pytest.skip("Cannot import ir_incidents._shared", allow_module_level=True)


class TestNormalizePersonName:
    def test_casefold_and_collapse_whitespace(self):
        assert _normalize_person_name("  Jane   DOE ") == "jane doe"

    def test_reordered_case_still_differs(self):
        # Name-based identity is intentionally exact-after-normalization;
        # "Doe Jane" is a different normalized key than "Jane Doe".
        assert _normalize_person_name("Jane Doe") != _normalize_person_name("Doe Jane")

    def test_blank_returns_empty(self):
        assert _normalize_person_name(None) == ""
        assert _normalize_person_name("   ") == ""

    def test_dedup_key_matches_across_casing(self):
        assert _normalize_person_name("JANE DOE") == _normalize_person_name("jane doe")


class TestGatherIncidentPeople:
    def test_extracts_all_roles(self):
        entries = _gather_incident_people(
            reported_by_name="Jane Doe",
            reported_by_email="jane@example.com",
            witnesses=[{"name": "Bob", "contact": None}],
            category_data={
                "injured_person": "Sue",
                "parties_involved": [{"name": "Al", "role": "peer"}],
            },
        )
        roles = sorted((n, r) for n, _e, r in entries)
        assert ("Jane Doe", "reporter") in roles
        assert ("Bob", "witness") in roles
        assert ("Sue", "involved") in roles
        assert ("Al", "involved") in roles

    def test_reporter_email_preserved(self):
        entries = _gather_incident_people(
            reported_by_name="Jane Doe", reported_by_email="jane@example.com"
        )
        assert entries == [("Jane Doe", "jane@example.com", "reporter")]

    def test_anonymous_and_unknown_reporters_dropped(self):
        assert _gather_incident_people(reported_by_name="Anonymous") == []
        assert _gather_incident_people(reported_by_name="unknown") == []
        assert _gather_incident_people(reported_by_name="  ") == []

    def test_blank_witness_names_dropped(self):
        entries = _gather_incident_people(witnesses=[{"name": ""}, {"name": "  "}, {"name": "Real"}])
        assert entries == [("Real", None, "witness")]

    def test_empty_inputs_yield_nothing(self):
        assert _gather_incident_people() == []
