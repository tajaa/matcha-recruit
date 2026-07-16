"""Tests for the IR Copilot deterministic flow resolver (ir_flow.py).

Covers the injury-assessment (OSHA recordability) gate — specifically the
regression where near-miss reports intermittently triggered the "Injury
Assessment" (treatment-beyond-first-aid) card because their description
text used injury-cue words ("nearly fell", "almost struck") to describe a
hazard that did NOT result in an actual injury.
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports (ir_flow lazily imports from
# ir_incidents._shared, which pulls in email/storage services that import
# the genai SDK at module load time).
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

from app.matcha.services import ir_flow


def _incident(**overrides):
    base = {
        "status": "reported",
        "incident_type": "near_miss",
        "severity": "medium",
        "category_data": {},
        "osha_recordable": None,
        "title": "",
        "description": "",
    }
    base.update(overrides)
    return base


class TestHasInjurySignal:
    def test_safety_type_always_signals_injury(self):
        assert ir_flow._has_injury_signal({"title": "", "description": ""}, "safety") is True

    def test_near_miss_never_signals_injury_even_with_injury_keywords(self):
        incident = {
            "title": "Forklift near miss",
            "description": "A forklift nearly struck an employee who tripped and almost fell.",
        }
        assert ir_flow._has_injury_signal(incident, "near_miss") is False

    def test_other_type_uses_keyword_match(self):
        incident = {"title": "", "description": "Employee slipped and cut hand"}
        assert ir_flow._has_injury_signal(incident, "other") is True

    def test_other_type_no_keyword_no_signal(self):
        incident = {"title": "", "description": "Employee reported a policy question"}
        assert ir_flow._has_injury_signal(incident, "other") is False


class TestResolveNextStepNearMiss:
    def test_near_miss_with_injury_keywords_does_not_trigger_treatment_card(self):
        """Regression: near-miss reports describing a hazard in injury-cue
        language ("nearly fell", "almost struck") must not surface the
        Injury Assessment / treatment-beyond-first-aid gate — no injury
        occurred, so there is nothing to assess.

        Note: only the near-miss (no-signal) path is exercised here. The
        signal-found path lazily imports app.matcha.routes.ir_incidents._shared,
        whose parent package import boots the entire router zoo — per that
        package's own CLAUDE.md, unit tests here should not boot the full
        app, so that branch isn't covered from this fast test module.
        """
        incident = _incident(
            title="Near miss on loading dock",
            description="A forklift nearly struck an employee who tripped and almost fell.",
        )
        result = ir_flow.resolve_next_step(incident, [], 0, is_cold_start=False)
        assert result is None

    def test_near_miss_without_injury_keywords_also_no_card(self):
        incident = _incident(
            title="Chemical spill near miss",
            description="A container of solvent nearly tipped over near the walkway.",
        )
        result = ir_flow.resolve_next_step(incident, [], 0, is_cold_start=False)
        assert result is None
