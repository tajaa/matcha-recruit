"""`adopt_editor_proposal` — the Schedule Pilot's "Stage this": a REST fill
scenario becomes the thread's staged `schedule_change`, in the exact shape
`schedule_skill.propose` produces, so the confirm turn is the same code path.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_adopt_editor_proposal.py -q
"""

import asyncio
import json
from datetime import date
from unittest import mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.services.scheduling import schedule_assistant_session as sessions

COMPANY, USER, LOCATION, SESSION, THREAD = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
WEEK = date(2026, 8, 23)


def _run(coro):
    return asyncio.run(coro)


class _Ctx:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_exc):
        return False


class _Conn:
    def __init__(self, *, session_row, proposal_row):
        self.session_row = session_row
        self.proposal_row = proposal_row
        self.executed = []

    def transaction(self):
        return _Ctx(self)

    async def fetchrow(self, query, *args):
        if "FROM schedule_assistant_sessions" in query:
            return self.session_row
        if "FROM schedule_chat_proposals" in query:
            return self.proposal_row
        return None

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))


def _op(index):
    return {
        "kind": "assign", "shift_id": f"s{index}", "shift_role": "shift lead",
        "starts_at": f"2026-08-2{4 + index}T06:00:00+00:00", "ends_at": f"2026-08-2{4 + index}T14:00:00+00:00",
        "to_employee_id": "e-dana", "to_employee_name": "Dana Reyes", "from_employee_id": None,
        "from_employee_name": None, "advisories": [],
        "review": {"verdict": "ok", "reasons": [], "before": {"minutes": 0, "shifts": 0, "days": 0},
                   "after": {"minutes": 480, "shifts": 1, "days": 1}},
    }


def _proposal_row(*, created_by=USER, status="proposed", surface="editor", kind="edit",
                  location=str(LOCATION), week="2026-08-23"):
    return {
        "id": uuid4(), "created_by": created_by, "status": status,
        "proposal": json.dumps({"kind": kind, "surface": surface, "ack": "Got it.", "ops": [_op(0), _op(1)],
                                "rejected": [], "jurisdiction": {"state": "CA", "status": "curated"},
                                "unfilled": [{"shift_id": "s9", "role": "barista", "reason": "unavailable",
                                              "exclusions": {"unavailable": 3}}]}),
        "parse": {"editor_location_id": location, "editor_week_start": week, "label": "Spread the leads"},
    }


def _session_row(*, current_state=None, user_id=USER, status="active", surface="schedule_assistant"):
    return {"location_id": LOCATION, "week_start": WEEK, "user_id": user_id, "thread_id": THREAD,
            "surface": surface, "status": status, "current_state": current_state or {}, "version": 4}


def _adopt(conn, proposal_id):
    with (
        mock.patch.object(sessions, "get_connection", lambda: _Ctx(conn)),
        mock.patch.object(sessions, "_assert_manager_location", mock.AsyncMock()),
    ):
        return _run(sessions.adopt_editor_proposal(
            company_id=COMPANY, user_id=USER, actor_role="client", session_id=SESSION, proposal_id=proposal_id,
        ))


def test_the_scenario_becomes_a_confirmable_schedule_change_in_the_thread():
    proposal = _proposal_row()
    conn = _Conn(session_row=_session_row(current_state={"huume_choice": {"question": "?"}, "huume_plans": {}}),
                 proposal_row=proposal)
    result = _adopt(conn, proposal["id"])

    staged = result["current_state"]["huume_action"]
    assert staged["type"] == "schedule_change" and staged["status"] == "proposed"
    assert len(staged["confirm_id"]) == 8 and result["confirm_id"] == staged["confirm_id"]
    assert staged["proposal_id"] == str(proposal["id"]) and staged["kind"] == "assign"
    assert staged["operation_count"] == 2 and staged["operation_summary"] == {"assign": 2}
    assert staged["review"]["kind"] == "edit" and staged["review"]["proposal_id"] == str(proposal["id"])
    assert staged["compliance_status"] == "verified" and staged["rejected_count"] == 0
    # The seats the planner could not fill survive the round trip through the
    # persisted doc — the review pane and Huume's state block both read them.
    assert staged["unfilled_count"] == 1 and staged["review"]["unfilled"][0]["shift_id"] == "s9"
    assert staged["location_id"] == str(LOCATION) and staged["label"] == "Spread the leads"
    assert staged["adopted_from"] == "editor_scenario"
    assert staged["pill_text"].startswith("\U0001F4C5 Staged from the scenarios strip. Here's what I'd change:")
    # A pending question no longer applies; everything else in the state survives.
    assert "huume_choice" not in result["current_state"] and result["current_state"]["huume_plans"] == {}
    assert result["version"] == 5
    query, args = conn.executed[-1]
    assert query.startswith("UPDATE mw_threads SET current_state=$1::jsonb, version=$2")
    assert args[1] == 5 and args[2] == THREAD
    assert json.loads(args[0])["huume_action"]["confirm_id"] == staged["confirm_id"]


def test_a_displaced_huume_proposal_is_cancelled_so_it_cannot_be_applied_later():
    proposal = _proposal_row()
    old_proposal_id = uuid4()
    conn = _Conn(session_row=_session_row(current_state={"huume_action": {
        "type": "schedule_change", "status": "proposed", "confirm_id": "aaaa1111", "proposal_id": str(old_proposal_id),
    }}), proposal_row=proposal)
    _adopt(conn, proposal["id"])
    cancel = next(item for item in conn.executed if "UPDATE schedule_chat_proposals SET status='cancelled'" in item[0])
    assert cancel[1] == (old_proposal_id, COMPANY)


def test_a_displaced_week_draft_run_is_cancelled_too():
    proposal = _proposal_row()
    run_id = uuid4()
    conn = _Conn(session_row=_session_row(current_state={"huume_action": {
        "type": "schedule_week_draft", "status": "proposed", "confirm_id": "bbbb2222", "generation_run_id": str(run_id),
    }}), proposal_row=proposal)
    _adopt(conn, proposal["id"])
    cancel = next(item for item in conn.executed if "UPDATE schedule_generation_runs SET status='cancelled'" in item[0])
    assert cancel[1] == (run_id, COMPANY)


def test_an_applied_action_is_left_alone_when_displaced():
    proposal = _proposal_row()
    conn = _Conn(session_row=_session_row(current_state={"huume_action": {
        "type": "schedule_change", "status": "applied", "confirm_id": "cccc3333", "proposal_id": str(uuid4()),
    }}), proposal_row=proposal)
    _adopt(conn, proposal["id"])
    assert not any("cancelled" in item[0] for item in conn.executed)


@pytest.mark.parametrize("session_row, status", [
    (None, 404),
    (_session_row(user_id=uuid4()), 404),
    (_session_row(status="archived"), 404),
    (_session_row(surface="workspace"), 404),
])
def test_the_session_must_be_this_managers_live_schedule_chat(session_row, status):
    proposal = _proposal_row()
    with pytest.raises(HTTPException) as exc:
        _adopt(_Conn(session_row=session_row, proposal_row=proposal), proposal["id"])
    assert exc.value.status_code == status


@pytest.mark.parametrize("proposal_row, status", [
    (None, 404),
    (_proposal_row(created_by=uuid4()), 403),
    (_proposal_row(status="confirmed"), 409),
    (_proposal_row(surface="channel"), 400),
    (_proposal_row(kind="batch"), 400),
    (_proposal_row(location=str(uuid4())), 409),
    (_proposal_row(week="2026-08-30"), 409),
])
def test_the_proposal_must_be_the_callers_live_editor_scenario_for_this_scope(proposal_row, status):
    proposal_id = proposal_row["id"] if proposal_row else uuid4()
    conn = _Conn(session_row=_session_row(), proposal_row=proposal_row)
    with pytest.raises(HTTPException) as exc:
        _adopt(conn, proposal_id)
    assert exc.value.status_code == status
    assert not any("UPDATE mw_threads" in item[0] for item in conn.executed)
