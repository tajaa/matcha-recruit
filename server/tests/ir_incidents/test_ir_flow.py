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


# ---------------------------------------------------------------------------
# close_progress — the Copilot progress meter.
#
# The meter exists because the Copilot conversation is open-ended: from the
# user's side it looks like it could loop forever. Every assertion here is
# really about one property — the meter must never claim more (or less)
# completion than the close intercept will actually honor.
# ---------------------------------------------------------------------------

def _progress_incident(**kw):
    base = {
        "status": "open",
        "incident_type": "other",
        "severity": "medium",
        "title": "",
        "description": "",
        "root_cause": None,
        "osha_recordable": None,
        "category_data": {},
    }
    base.update(kw)
    return base


def _step(progress, key):
    return next(s for s in progress["steps"] if s["key"] == key)


class TestCloseProgressApplicability:
    def test_only_close_gates_are_counted(self):
        # The meter counts exactly what _close_incident_via_copilot enforces.
        # Triage and the treatment/injury question are NOT close gates — when
        # they were counted, Close succeeded at 60% and the closed record then
        # rendered "Complete" over unfilled segments.
        assert set(ir_flow._STEP_LABELS) == {
            "osha_emergency", "osha_recordable", "root_cause", "close",
        }

    def test_not_applicable_steps_are_excluded_from_the_denominator(self):
        # A property-damage report can never complete the OSHA chain, so
        # counting those steps would strand the meter below 100% forever.
        p = ir_flow.close_progress(_progress_incident(
            incident_type="property", description="A forklift dented a rack.",
        ))
        assert _step(p, "osha_recordable")["status"] == "not_applicable"
        assert _step(p, "osha_emergency")["status"] == "not_applicable"
        assert _step(p, "root_cause")["status"] == "not_applicable"
        assert p["total"] == 1  # just "close"

    def test_property_incident_can_reach_full_completion(self):
        p = ir_flow.close_progress(_progress_incident(
            incident_type="property", description="A forklift dented a rack.",
            status="closed",
        ))
        assert p["percent"] == 100
        assert p["is_complete"] is True
        assert p["next_step_key"] is None

    def test_safety_incident_surfaces_root_cause(self):
        p = ir_flow.close_progress(_progress_incident(
            incident_type="safety", severity="high",
            description="Worker slipped and cut their hand.",
        ))
        assert _step(p, "root_cause")["status"] == "pending"
        assert p["percent"] < 100

    def test_untriaged_incident_is_not_reported_as_progress(self):
        # Regression: incidents are CREATED with incident_type='other' /
        # severity='medium' (both valid), so a "triage" step keyed on
        # validity read done on a report nobody had classified — the meter
        # showed 1/2 and urged "Next: Close the incident" on an untriaged
        # report, then visibly regressed if it was later re-typed to safety.
        p = ir_flow.close_progress(_progress_incident(
            description="Something happened in the warehouse.",
        ))
        assert all(s["key"] != "triage" for s in p["steps"])
        assert p["next_step_key"] == "close"

    def test_osha_recordable_step_appears_only_after_treatment_is_true(self):
        before = ir_flow.close_progress(_progress_incident(
            incident_type="safety", description="Worker slipped.",
        ))
        assert _step(before, "osha_recordable")["status"] == "not_applicable"

        after = ir_flow.close_progress(_progress_incident(
            incident_type="safety", description="Worker slipped.",
            category_data={"treatment_beyond_first_aid": "true"},
        ))
        assert _step(after, "osha_recordable")["status"] == "pending"

    def test_skipping_the_osha_gate_does_not_clear_it_from_the_meter(self):
        # Regression, and the reason the meter exists at all: a skip silences
        # resolve_next_step but does NOT waive the close requirement — the
        # intercept's needs_osha_recordable ignores flow_skipped and redirects.
        # When the meter honored the skip it read 100% / "ready to close"
        # while the Close button bounced straight back into the skipped card.
        cd = {"treatment_beyond_first_aid": "true", "flow_skipped": ["osha"]}
        p = ir_flow.close_progress(_progress_incident(
            incident_type="safety", description="Worker slipped.", category_data=cd,
        ))
        assert _step(p, "osha_recordable")["status"] == "pending"
        assert p["percent"] < 100
        # ...and the close gate agrees it still blocks.
        assert ir_flow.needs_osha_recordable(category_data=cd, osha_recordable=None) is True

    def test_category_data_accepts_a_json_string(self):
        # asyncpg hands category_data back as either dict or str.
        p = ir_flow.close_progress(_progress_incident(
            incident_type="safety", description="Worker slipped.",
            category_data='{"treatment_beyond_first_aid": "true"}',
        ))
        assert _step(p, "osha_recordable")["status"] == "pending"

    def test_empty_incident_does_not_divide_by_zero(self):
        p = ir_flow.close_progress({})
        assert p["percent"] == 0
        assert p["total"] == 1

    def test_closed_incident_is_never_internally_inconsistent(self):
        # is_complete must imply a full bar. Previously a safety incident could
        # close with the treatment question unanswered, leaving is_complete=true
        # alongside a pending step, completed<total and a live next_step_hint.
        p = ir_flow.close_progress(_progress_incident(
            status="closed", incident_type="safety", severity="high",
            description="Worker slipped and cut their hand.",
            category_data={"root_cause_declined": True},
        ))
        assert p["is_complete"] is True
        assert p["completed"] == p["total"]
        assert p["percent"] == 100
        assert p["next_step_key"] is None
        assert p["next_step_hint"] == ""


class TestCloseProgressMatchesCloseGuards:
    """The load-bearing invariant: if the meter shows no pending step, the
    close intercept's guards must all be clear — and vice versa. These call
    the exact predicates _close_incident_via_copilot consumes."""

    def test_root_cause_declined_satisfies_both(self):
        inc = _progress_incident(
            incident_type="safety", severity="high",
            description="Worker slipped.",
            category_data={
                "root_cause_declined": True,
                "treatment_beyond_first_aid": "false",
            },
        )
        p = ir_flow.close_progress(inc)
        assert _step(p, "root_cause")["status"] == "done"
        assert ir_flow.needs_root_cause(
            incident_type=inc["incident_type"], severity=inc["severity"],
            root_cause=inc["root_cause"], category_data=inc["category_data"],
        ) is False

    def test_root_cause_pending_matches_the_redirect_guard(self):
        inc = _progress_incident(incident_type="safety", severity="high", description="Slip.")
        p = ir_flow.close_progress(inc)
        assert _step(p, "root_cause")["status"] == "pending"
        assert ir_flow.needs_root_cause(
            incident_type=inc["incident_type"], severity=inc["severity"],
            root_cause=inc["root_cause"], category_data=inc["category_data"],
        ) is True

    def test_osha_emergency_alert_blocks_and_shows_pending(self):
        inc = _progress_incident(
            incident_type="safety", description="Amputation.",
            category_data={"osha_emergency_alert_active": True},
        )
        p = ir_flow.close_progress(inc)
        assert _step(p, "osha_emergency")["status"] == "pending"
        assert ir_flow.osha_emergency_blocking(inc["category_data"]) is True

    def test_acknowledged_emergency_clears_both(self):
        cd = {"osha_emergency_alert_active": False}
        p = ir_flow.close_progress(_progress_incident(
            incident_type="safety", description="Amputation.", category_data=cd,
        ))
        assert _step(p, "osha_emergency")["status"] == "done"
        assert ir_flow.osha_emergency_blocking(cd) is False

    def test_osha_recordable_pending_matches_the_redirect_guard(self):
        cd = {"treatment_beyond_first_aid": "true"}
        inc = _progress_incident(incident_type="safety", description="Cut.", category_data=cd)
        p = ir_flow.close_progress(inc)
        assert _step(p, "osha_recordable")["status"] == "pending"
        assert ir_flow.needs_osha_recordable(
            category_data=cd, osha_recordable=None,
        ) is True
        # ...and clears once the chain has run.
        assert ir_flow.needs_osha_recordable(category_data=cd, osha_recordable=True) is False

    def test_treatment_tri_state(self):
        assert ir_flow.treatment_beyond_first_aid({}) is None
        assert ir_flow.treatment_beyond_first_aid({"treatment_beyond_first_aid": "true"}) is True
        assert ir_flow.treatment_beyond_first_aid({"treatment_beyond_first_aid": True}) is True
        assert ir_flow.treatment_beyond_first_aid({"treatment_beyond_first_aid": "false"}) is False
