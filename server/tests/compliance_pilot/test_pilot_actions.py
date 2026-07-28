"""Pure-function tests for the agentic Compliance Pilot's safety envelope.

No DB, no Gemini — everything here is a plain function over plain dicts.

    cd server && ./venv/bin/python -m pytest tests/compliance_pilot -q

Modeled on tests/huume/test_huume_actions.py, which covers the sibling envelope
this one was structurally copied from.
"""

import pytest

from app.core.services.compliance_pilot import actions

A = "1e2b3c4d-5678-4abc-9def-0123456789ab"
R1 = "aaaaaaaa-1111-4111-8111-111111111111"
R2 = "bbbbbbbb-2222-4222-8222-222222222222"
R3 = "cccccccc-3333-4333-8333-333333333333"


def _research_done(**overrides):
    row = {
        "id": A, "kind": "research", "status": "done", "staged_ids": [R1, R2],
        "result": {"staged_rows": [
            {"id": R1, "gate_ok": True, "gate_reason": None},
            {"id": R2, "gate_ok": False, "gate_reason": "source link is dead"},
        ]},
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------- #
# Argument coercion
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("ca", "CA"), ("  ny  ", "NY"), ("CA", "CA"),
    ("California", None),   # never truncate a name into a code
    ("C", None), ("C4", None), ("", None), (None, None),
])
def test_coerce_state(raw, expected):
    assert actions.coerce_state(raw) == expected


def test_coerce_categories_empty_is_none_not_empty_list():
    """`None` means "the admin asked for everything" downstream, so an empty
    list must collapse to it rather than reading as "zero categories"."""
    assert actions.coerce_categories([]) is None
    assert actions.coerce_categories(["", "   "]) is None
    assert actions.coerce_categories(None) is None
    assert actions.coerce_categories(["  clinical_safety "]) == ["clinical_safety"]


def test_coerce_uuid_normalizes_and_rejects():
    assert actions.coerce_uuid(A.upper()) == A
    assert actions.coerce_uuid("not-a-uuid") is None
    assert actions.coerce_uuid(None) is None
    assert actions.coerce_uuid_list([A, A.upper(), "x", None]) == [A]


# --------------------------------------------------------------------------- #
# The two-turn confirm gate
# --------------------------------------------------------------------------- #

def test_confirm_requires_the_proposal_to_predate_this_turn():
    """The whole safety envelope: an action staged during THIS turn is absent
    from the pre-turn snapshot, so it cannot be confirmed in the same breath."""
    row = {"id": A, "status": "proposed"}
    assert actions.evaluate_confirm(row, {A}).ok
    verdict = actions.evaluate_confirm(row, set())
    assert verdict.kind == "stage"
    assert not verdict.ok


@pytest.mark.parametrize("status,fragment", [
    ("running", "already running"),
    ("done", "already finished"),
    ("failed", "already failed"),
    ("cancelled", "was cancelled"),
    ("superseded", "replaced by a newer proposal"),
])
def test_confirm_refuses_non_proposed(status, fragment):
    verdict = actions.evaluate_confirm({"id": A, "status": status}, {A})
    assert verdict.kind == "refuse"
    assert fragment in verdict.message


def test_confirm_refuses_unknown_action():
    assert actions.evaluate_confirm(None, {A}).kind == "refuse"
    assert actions.evaluate_confirm({}, {A}).kind == "refuse"


def test_terminal_status_beats_the_two_turn_message():
    """A cancelled action confirmed in the turn that cancelled it should say it
    was cancelled, not "wait a turn" — the ordering of the checks is the point."""
    verdict = actions.evaluate_confirm({"id": A, "status": "cancelled"}, set())
    assert "was cancelled" in verdict.message


# --------------------------------------------------------------------------- #
# Cancel
# --------------------------------------------------------------------------- #

def test_cancel_allows_retracting_something_staged_this_turn():
    """Unlike confirm, cancelling is the safe direction — no two-turn wait."""
    assert actions.evaluate_cancel({"id": A, "status": "proposed"}).ok


@pytest.mark.parametrize("status", ["running", "done", "failed", "cancelled"])
def test_cancel_refuses_anything_not_proposed(status):
    assert actions.evaluate_cancel({"id": A, "status": status}).kind == "refuse"


# --------------------------------------------------------------------------- #
# Single-slot supersede
# --------------------------------------------------------------------------- #

def test_supersede_targets_takes_every_older_proposal_regardless_of_kind():
    acts = [
        {"id": "a", "kind": "research", "status": "proposed"},
        {"id": "b", "kind": "check_sources", "status": "proposed"},
        {"id": "c", "kind": "research", "status": "done"},
        {"id": "d", "kind": "research", "status": "running"},
        {"id": "e", "kind": "approve", "status": "cancelled"},
    ]
    assert actions.supersede_targets(acts, exclude_id="b") == ["a"]
    assert actions.supersede_targets(acts) == ["a", "b"]
    assert actions.supersede_targets([]) == []


# --------------------------------------------------------------------------- #
# stage_approve selection
# --------------------------------------------------------------------------- #

def test_approve_defaults_to_the_gate_passing_subset():
    verdict = actions.evaluate_stage_approve(_research_done())
    assert verdict.ok
    assert verdict.payload["ids"] == [R1]
    assert verdict.payload["gate_ok"] == 1
    assert verdict.payload["gate_blocked"] == 0
    assert verdict.payload["explicit_selection"] is False


def test_approve_keeps_gate_failing_rows_when_named_explicitly():
    """A gate failure never blocks approve — the row goes live uncodified with
    the reason recorded. Silently dropping it would make an explicit request
    quietly do less than it said."""
    verdict = actions.evaluate_stage_approve(_research_done(), [R2])
    assert verdict.ok
    assert verdict.payload["ids"] == [R2]
    assert verdict.payload["gate_blocked"] == 1
    assert verdict.payload["explicit_selection"] is True


def test_approve_refuses_ids_outside_the_run():
    verdict = actions.evaluate_stage_approve(_research_done(), [R1, R3])
    assert verdict.kind == "refuse"
    assert "aren't part of that research run" in verdict.message


def test_approve_refuses_when_nothing_passes_the_gate_and_names_why():
    row = _research_done(result={"staged_rows": [
        {"id": R1, "gate_ok": False, "gate_reason": "no regulation key"},
        {"id": R2, "gate_ok": False, "gate_reason": "source link is dead"},
    ]})
    verdict = actions.evaluate_stage_approve(row)
    assert verdict.kind == "refuse"
    assert "no regulation key" in verdict.message
    assert "source link is dead" in verdict.message


def test_approve_refuses_unfinished_or_wrong_kind_runs():
    assert actions.evaluate_stage_approve(_research_done(status="running")).kind == "refuse"
    assert actions.evaluate_stage_approve(_research_done(status="failed")).kind == "refuse"
    assert actions.evaluate_stage_approve(_research_done(kind="check_sources")).kind == "refuse"
    assert actions.evaluate_stage_approve(None).kind == "refuse"


def test_approve_falls_back_to_staged_ids_when_the_result_is_thin():
    """An older action row (or one written before staged_rows existed) still has
    its staged_ids column; an explicit selection must validate against it."""
    row = _research_done(result={})
    assert actions.evaluate_stage_approve(row, [R1]).payload["ids"] == [R1]
    # With no per-row gate detail there is no gate-passing subset to default to.
    assert actions.evaluate_stage_approve(row).kind == "refuse"


def test_approve_refuses_a_run_that_staged_nothing():
    row = _research_done(result={"staged_rows": []}, staged_ids=[])
    assert actions.evaluate_stage_approve(row).kind == "refuse"
