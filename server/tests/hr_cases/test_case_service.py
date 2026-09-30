"""HR case service — numbering, one open case per incident, the single
stage writer, dismissal. No DB: QueryConn dispatches on SQL text.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_case_service.py -q
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.hr_cases import case_service as svc
from app.matcha.services.hr_cases.case_service import CaseError
from tests._helpers.routes import QueryConn, Queue

COMPANY = uuid4()


class TxConn(QueryConn):
    def transaction(self):
        return self


def case_row(**kw):
    base = {
        "id": uuid4(), "company_id": COMPANY, "case_number": "HRC-2026-0001", "origin": "intake_triage",
        "stage": "flagged", "source_incident_id": uuid4(), "employee_id": None, "action_type": None,
        "occurrence_dates": [], "gm_user_id": None, "opened_by": None, "thread_id": None,
        "draft_file_id": None, "signed_file_id": None,
        "triage": '{"phase": "intake", "violations": []}', "review": None, "verification": None,
        "decision": None, "decision_reason": None, "decided_by": None, "decided_at": None,
        "delivered_at": None, "delivered_by": None, "attention_reasons": [],
        "attention_acknowledged_by": None, "attention_acknowledged_at": None, "dismissed_reason": None,
        "created_at": datetime(2026, 9, 29, tzinfo=timezone.utc), "updated_at": datetime(2026, 9, 29, tzinfo=timezone.utc),
        "closed_at": None, "incident_number": "IR-1", "incident_title": "Slip", "incident_occurred_at": None,
        "employee_name": None, "gm_name": None,
    }
    base.update(kw)
    return base


def test_serialize_decodes_json_and_adds_stage_info():
    out = svc.serialize(case_row(stage="hr_review"))
    assert out["triage"] == {"phase": "intake", "violations": []}
    assert out["stage_label"] == "HR review"
    assert out["column"] == "review"
    assert "approve" in out["allowed_events"]
    assert len(out["checklist"]) == 7


def test_serialize_tolerates_bad_json():
    assert svc.serialize(case_row(triage="{not json"))["triage"] is None


@pytest.mark.asyncio
async def test_case_number_format():
    conn = QueryConn(fetchval={"INSERT INTO hr_case_settings": 7})
    number = await svc.next_case_number(conn, COMPANY, now=datetime(2027, 1, 2, tzinfo=timezone.utc))
    assert number == "HRC-2027-0007"


@pytest.mark.asyncio
async def test_settings_default_when_missing():
    conn = QueryConn(fetchrow={"FROM hr_case_settings": None})
    settings = await svc.get_settings(conn, COMPANY)
    assert settings["triage_min_confidence"] == 0.60


@pytest.mark.asyncio
async def test_open_case_creates_and_records_event():
    new_id = uuid4()
    incident = uuid4()
    conn = TxConn(
        fetchval={"INSERT INTO hr_case_settings": 1, "INSERT INTO hr_cases": new_id},
        # No open case yet, then the new one read back.
        fetchrow={"FROM hr_cases c": Queue([None, case_row(id=new_id)])},
    )
    case, created = await svc.open_case(conn, company_id=COMPANY, origin="manual", incident_id=incident)
    assert created is True and case["id"] == new_id
    assert conn.args_for("INSERT INTO hr_case_events")[2] == "opened"
    # Opens for one incident are serialized before anything is looked up.
    assert conn.args_for("pg_advisory_xact_lock")[0] == f"hr_case_open:{incident}"


@pytest.mark.asyncio
async def test_open_case_converges_on_existing_open_case():
    existing = case_row(case_number="HRC-2026-0003")
    conn = TxConn(
        fetchval={"INSERT INTO hr_case_settings": 4, "INSERT INTO hr_cases": None},
        fetchrow={"FROM hr_cases c": existing},
    )
    case, created = await svc.open_case(conn, company_id=COMPANY, origin="close_check", incident_id=uuid4())
    assert created is False and case["case_number"] == "HRC-2026-0003"
    assert not any("hr_case_events" in s for s in conn.sql_for("execute"))
    # Found before numbering: no case number is burned on a duplicate open.
    assert not any("hr_case_settings" in s for s in conn.sql_for("fetchval"))


@pytest.mark.asyncio
async def test_open_case_conflict_without_visible_case_is_409():
    conn = TxConn(
        fetchval={"INSERT INTO hr_case_settings": 4, "INSERT INTO hr_cases": None},
        fetchrow={"FROM hr_cases c": None},
    )
    with pytest.raises(CaseError) as exc:
        await svc.open_case(conn, company_id=COMPANY, origin="manual", incident_id=uuid4())
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_apply_event_moves_stage_and_writes_trail():
    cid = uuid4()
    conn = TxConn(fetchrow={
        "FOR UPDATE": {"id": cid, "stage": "hr_review"},
        "FROM hr_cases c": case_row(id=cid, stage="approved"),
    })
    out = await svc.apply_event(
        conn, company_id=COMPANY, case_id=cid, event="approve", actor_user_id=uuid4(),
        sets={"decision": "approved", "review": {"ok": True}},
    )
    assert out["stage"] == "approved"
    update_sql = [s for s in conn.sql_for("execute") if s.startswith("UPDATE hr_cases")][0]
    assert "review = $5::jsonb" in update_sql and "decision = $4" in update_sql
    args = conn.args_for("UPDATE hr_cases")
    assert args[2] == "approved" and args[4] == '{"ok": true}'
    ev = conn.args_for("INSERT INTO hr_case_events")
    assert ev[2:5] == ("approve", "hr_review", "approved")


@pytest.mark.asyncio
async def test_apply_event_stamps_closed_at_on_terminal():
    cid = uuid4()
    conn = TxConn(fetchrow={"FOR UPDATE": {"id": cid, "stage": "flagged"}, "FROM hr_cases c": case_row(stage="dismissed")})
    await svc.apply_event(conn, company_id=COMPANY, case_id=cid, event="dismiss", actor_user_id=None)
    assert "closed_at = NOW()" in [s for s in conn.sql_for("execute") if s.startswith("UPDATE hr_cases")][0]


@pytest.mark.asyncio
async def test_apply_event_refuses_skipping_a_step():
    conn = TxConn(fetchrow={"FOR UPDATE": {"id": uuid4(), "stage": "flagged"}})
    with pytest.raises(CaseError) as exc:
        await svc.apply_event(conn, company_id=COMPANY, case_id=uuid4(), event="delivered", actor_user_id=None)
    assert exc.value.status == 409
    assert not any(s.startswith("UPDATE hr_cases") for s in conn.sql_for("execute"))


@pytest.mark.asyncio
async def test_apply_event_unknown_case_and_unsettable_column():
    with pytest.raises(CaseError) as exc:
        await svc.apply_event(TxConn(fetchrow={"FOR UPDATE": None}), company_id=COMPANY,
                              case_id=uuid4(), event="approve", actor_user_id=None)
    assert exc.value.status == 404
    with pytest.raises(ValueError):
        await svc.apply_event(TxConn(), company_id=COMPANY, case_id=uuid4(), event="approve",
                              actor_user_id=None, sets={"stage": "closed"})


@pytest.mark.asyncio
async def test_dismiss_requires_a_reason():
    with pytest.raises(CaseError) as exc:
        await svc.dismiss_case(TxConn(), company_id=COMPANY, case_id=uuid4(), actor_user_id=uuid4(), reason=" no ")
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_get_case_with_events_and_missing():
    cid = uuid4()
    conn = QueryConn(
        fetchrow={"FROM hr_cases c": case_row(id=cid)},
        fetch={"FROM hr_case_events": [{"event": "opened", "from_stage": None, "to_stage": "flagged",
                                        "details": '{"origin": "manual"}', "created_at": None, "actor_name": None}]},
    )
    case = await svc.get_case(conn, company_id=COMPANY, case_id=cid, with_events=True)
    assert case["events"][0]["details"] == {"origin": "manual"}
    with pytest.raises(CaseError):
        await svc.get_case(QueryConn(fetchrow={"FROM hr_cases c": None}), company_id=COMPANY, case_id=cid)


@pytest.mark.asyncio
async def test_list_cases_scopes_and_hides_old_closed():
    conn = QueryConn(fetch={"FROM hr_cases c": [case_row()]})
    out = await svc.list_cases(conn, company_id=COMPANY)
    assert len(out) == 1
    sql = conn.sql_for("fetch")[0]
    assert "c.company_id = $1" in sql and "30 days" in sql
    conn2 = QueryConn(fetch={"FROM hr_cases c": Queue([[]])})
    await svc.list_cases(conn2, company_id=COMPANY, include_closed=True)
    assert "30 days" not in conn2.sql_for("fetch")[0]


@pytest.mark.asyncio
async def test_latest_case_includes_closed_and_dismissed():
    row = case_row(stage="dismissed")
    conn = TxConn(fetchrow={"FROM hr_cases c": row})
    got = await svc.find_latest_case_for_incident(conn, company_id=COMPANY, incident_id=uuid4())
    assert got["stage"] == "dismissed"
    sql = conn.sql_for("fetchrow")[0]
    assert "NOT IN ('closed', 'dismissed')" not in sql and "ORDER BY c.created_at DESC" in sql
