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


# ---------------------------------------------------------------------------
# copilot_evidence — the preponderance-of-evidence + duration tracker.
#
# A second, independent read on "how much is left" that answers a question
# close_progress can't: not "what does the law require to close" but "how
# well-documented is this record" — a property-damage report can clear every
# close gate while still having no photos, no witnesses, no corrective action.
# Plus a severity-scaled days-open budget so an investigation can't drift
# open indefinitely unnoticed.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


def _evidence_incident(**kw):
    base = {
        "status": "reported",
        "incident_type": "other",
        "severity": "medium",
        "description": "",
        "root_cause": None,
        "corrective_actions": None,
        "category_data": {},
    }
    base.update(kw)
    return base


def _naive_utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestCopilotEvidenceScore:
    def test_root_cause_excluded_from_denominator_when_not_required(self):
        # incident_type='other' / severity='medium' owes no root cause, so the
        # ceiling is the other four factors (15+15+20+25 = 75). All four done
        # must reach a full 100, not strand at 75/100 — otherwise every
        # no-injury report is permanently "insufficient".
        e = ir_flow.copilot_evidence(
            _evidence_incident(description="A rack was dented."),
            document_count=1, witness_count=1, corrective_action_count=1,
        )
        assert e["score"] == 100
        assert e["sufficient"] is True
        assert e["missing"] == []
        assert "Root cause analysis" not in e["signals"]

    def test_root_cause_required_incident_missing_it_is_insufficient(self):
        # safety/high owes a root cause (denominator now includes its 25).
        e = ir_flow.copilot_evidence(
            _evidence_incident(
                incident_type="safety", severity="high",
                description="Worker slipped.",
            ),
            document_count=1, witness_count=1, corrective_action_count=1,
        )
        # 15+15+20+25 earned of 100 = 75, below the 80 threshold.
        assert e["score"] == 75
        assert e["sufficient"] is False
        assert e["missing"] == ["Root cause analysis"]

    def test_threshold_is_inclusive_at_the_boundary(self):
        # Exactly 80 (everything but the 20-weight documents factor) must count
        # as sufficient — the check is score >= threshold.
        e = ir_flow.copilot_evidence(
            _evidence_incident(
                incident_type="safety", severity="high",
                description="Worker slipped.", root_cause="Wet floor, no signage.",
            ),
            document_count=0, witness_count=1, corrective_action_count=1,
        )
        assert e["score"] == 80
        assert e["sufficient"] is True
        assert e["missing"] == ["Supporting documents"]

    def test_signals_and_missing_partition_the_applicable_factors(self):
        e = ir_flow.copilot_evidence(
            _evidence_incident(description="Something happened."),
            document_count=0, witness_count=0, corrective_action_count=0,
        )
        assert e["signals"] == ["Incident description"]
        # documents/witnesses/corrective all pending; root cause not applicable.
        assert set(e["missing"]) == {
            "Witness statements", "Supporting documents", "Corrective actions",
        }
        assert "Root cause analysis" not in e["missing"]

    def test_declined_root_cause_counts_as_done_from_json_string(self):
        # asyncpg hands category_data back as either dict or str; an explicit
        # decline satisfies the root-cause factor (same rule as close_progress).
        e = ir_flow.copilot_evidence(
            _evidence_incident(
                incident_type="safety", severity="high",
                description="Worker slipped.",
                category_data='{"root_cause_declined": true}',
            ),
            document_count=1, witness_count=1, corrective_action_count=1,
        )
        assert "Root cause analysis" in e["signals"]
        assert e["score"] == 100

    def test_legacy_free_text_corrective_actions_satisfies_the_factor(self):
        # The factor is satisfied by a structured CAPA row OR the legacy
        # free-text ir_incidents.corrective_actions column.
        e = ir_flow.copilot_evidence(
            _evidence_incident(
                description="A rack was dented.",
                corrective_actions="Retrained the operator.",
            ),
            document_count=1, witness_count=1, corrective_action_count=0,
        )
        assert "Corrective actions" in e["signals"]

    def test_empty_incident_scores_zero_without_raising(self):
        e = ir_flow.copilot_evidence({})
        assert e["score"] == 0
        assert e["sufficient"] is False
        assert e["days_open"] == 0


class TestCopilotEvidenceDuration:
    def test_severity_scales_the_open_days_budget(self):
        for severity, expected in [
            ("critical", 7), ("high", 14), ("medium", 30), ("low", 45),
        ]:
            e = ir_flow.copilot_evidence(_evidence_incident(severity=severity))
            assert e["max_days"] == expected

    def test_unknown_severity_falls_back_to_default_budget(self):
        e = ir_flow.copilot_evidence(_evidence_incident(severity="bogus"))
        assert e["max_days"] == 30

    def test_open_incident_past_budget_is_overdue(self):
        e = ir_flow.copilot_evidence(_evidence_incident(
            severity="medium",
            reported_at=_naive_utc_now() - timedelta(days=40),
        ))
        assert e["days_open"] == 40
        assert e["is_overdue"] is True

    def test_open_incident_within_budget_is_not_overdue(self):
        e = ir_flow.copilot_evidence(_evidence_incident(
            severity="medium",
            reported_at=_naive_utc_now() - timedelta(days=5),
        ))
        assert e["is_overdue"] is False

    def test_terminal_incident_freezes_days_open_and_never_overdue(self):
        opened = _naive_utc_now() - timedelta(days=100)
        e = ir_flow.copilot_evidence(_evidence_incident(
            status="closed", severity="critical",
            reported_at=opened, resolved_at=opened + timedelta(days=5),
        ))
        assert e["days_open"] == 5  # frozen at resolved_at, not 100 days to "now"
        assert e["is_overdue"] is False

    def test_closed_incident_never_overdue_even_when_it_ran_long(self):
        opened = _naive_utc_now() - timedelta(days=100)
        e = ir_flow.copilot_evidence(_evidence_incident(
            status="resolved", severity="critical",
            reported_at=opened, resolved_at=opened + timedelta(days=90),
        ))
        assert e["days_open"] == 90
        assert e["is_overdue"] is False

    def test_timezone_aware_timestamp_does_not_raise(self):
        # F1: reported_at may arrive tz-aware if the column is ever migrated to
        # TIMESTAMPTZ; a mixed naive/aware subtraction would 500 the endpoint.
        e = ir_flow.copilot_evidence(_evidence_incident(
            severity="medium",
            reported_at=datetime.now(timezone.utc) - timedelta(days=10),
        ))
        assert e["days_open"] == 10
        assert e["is_overdue"] is False
