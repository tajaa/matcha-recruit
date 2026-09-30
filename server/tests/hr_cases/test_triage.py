"""HR case intake/close triage — flag rule, one check per phase, unavailable
never read as clean, converging on an existing case.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_triage.py -q
"""
import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.matcha.services.hr_cases import case_service, notifications, triage
from tests._helpers.routes import QueryConn

COMPANY = uuid4()
INCIDENT = uuid4()


def result(*violations, available=True):
    return {"available": available, "violations": list(violations), "citations": ["c1"], "summary": "s"}


def v(relevance, confidence, title="Attendance policy"):
    return {"policy_title": title, "relevance": relevance, "confidence": confidence,
            "reasoning": "narrative quote here", "relevant_excerpt": "excerpt"}


@pytest.mark.parametrize("res,expected", [
    (result(v("violated", 0.8)), True),
    (result(v("bent", 0.6)), True),
    (result(v("violated", 0.59)), False),
    (result(v("related", 0.99)), False),
    (result(), False),
    (result({"relevance": "violated", "confidence": "high"}), False),
    (result("not a dict"), False),
])
def test_decide_flag(res, expected):
    assert triage.decide_flag(res, min_confidence=0.6) is expected


def test_summarize_drops_narrative():
    out = triage.summarize(result(v("violated", 0.9)), phase="intake")
    assert out["violations"] == [{"policy_title": "Attendance policy", "relevance": "violated", "confidence": 0.9}]
    assert "reasoning" not in str(out) and "excerpt" not in str(out)
    assert out["citation_count"] == 1


def test_single_involved_employee():
    eid = uuid4()
    assert triage._single_involved_employee({"involved_employee_ids": [str(eid)]}) == eid
    assert triage._single_involved_employee({"involved_employee_ids": [str(eid), str(uuid4())]}) is None
    assert triage._single_involved_employee({"involved_employee_ids": ["bad"]}) is None


INCIDENT_ROW = {
    "id": INCIDENT, "company_id": COMPANY, "incident_number": "IR-7", "title": "t", "description": "d",
    "incident_type": "behavioral", "severity": "medium", "created_by": uuid4(),
    "reported_by_email": None, "involved_employee_ids": [],
}


@pytest.fixture
def env(monkeypatch):
    """Patch every collaborator _triage reaches; returns a dict of knobs."""
    from app.core import feature_flags
    from app.database import pool
    from app.matcha.services.discipline import discipline_policy_check

    state = {
        "features": {"hr_cases": True},
        "claimed": 1,  # the attempt number the claim returns; None = not claimed
        "latest": None,
        "corpus": {"policies": []},
        "result": result(v("violated", 0.9)),
        "existing": None,
        "opened": [],
        "notified": [],
        "events": [],
    }
    conn = QueryConn(
        fetchval={"INSERT INTO hr_case_triage_log": None},
        fetchrow={"FROM ir_incidents": INCIDENT_ROW},
    )
    state["conn"] = conn

    state["open_conns"] = 0

    @asynccontextmanager
    async def direct(**kwargs):
        state.setdefault("direct_kwargs", []).append(kwargs)
        conn.set("fetchval", "INSERT INTO hr_case_triage_log", state["claimed"])
        state["open_conns"] += 1
        try:
            yield conn
        finally:
            state["open_conns"] -= 1

    async def features(company_id, conn=None):
        return state["features"]

    async def corpus(conn, company_id):
        state["conn_during_model"] = False
        return state["corpus"]

    async def check(corpus, incident):
        state.setdefault("conns_during_model", []).append(state["open_conns"])
        state["checked"] = incident["id"]
        state["checks"] = state.get("checks", 0) + 1
        results = state["result"]
        return results.pop(0) if isinstance(results, list) else results

    async def settings(conn, company_id):
        return {"triage_min_confidence": 0.6}

    async def find_open(conn, *, company_id, incident_id):
        return state["existing"]

    async def find_latest(conn, *, company_id, incident_id):
        return state["latest"]

    async def record_event(conn, **kw):
        state["events"].append(kw)

    async def open_case(conn, **kw):
        state["opened"].append(kw)
        return {"id": uuid4(), "company_id": COMPANY, "case_number": "HRC-2026-0001", "gm_user_id": kw["gm_user_id"]}, True

    async def gm(conn, *, company_id, incident):
        return incident["created_by"]

    async def notify(conn, *, case, incident, policy_titles):
        state["notified"].append(policy_titles)

    monkeypatch.setattr(pool, "connection_or_direct", direct)
    monkeypatch.setattr(feature_flags, "get_company_features", features)
    monkeypatch.setattr(discipline_policy_check, "build_check_corpus", corpus)
    monkeypatch.setattr(discipline_policy_check, "check_with_corpus", check)
    monkeypatch.setattr(triage, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(case_service, "get_settings", settings)
    monkeypatch.setattr(case_service, "find_open_case_for_incident", find_open)
    monkeypatch.setattr(case_service, "find_latest_case_for_incident", find_latest)
    monkeypatch.setattr(case_service, "record_event", record_event)
    monkeypatch.setattr(case_service, "open_case", open_case)
    monkeypatch.setattr(notifications, "resolve_gm_user_id", gm)
    monkeypatch.setattr(notifications, "notify_flagged", notify)
    return state


@pytest.mark.asyncio
async def test_flags_and_notifies_on_intake(env):
    out = await triage.triage_incident(str(INCIDENT), str(COMPANY))
    assert out["status"] == "flagged"
    assert env["opened"][0]["origin"] == "intake_triage"
    assert env["opened"][0]["gm_user_id"] == INCIDENT_ROW["created_by"]
    assert env["notified"] == [["Attendance policy"]]
    log_update = env["conn"].args_for("UPDATE hr_case_triage_log SET implicated = $3")
    assert log_update[2] is True


@pytest.mark.asyncio
async def test_close_phase_opens_close_check_case(env):
    out = await triage.triage_incident(str(INCIDENT), str(COMPANY), phase="close")
    assert out["status"] == "flagged"
    assert env["opened"][0]["origin"] == "close_check"


@pytest.mark.asyncio
async def test_module_off_does_nothing(env):
    env["features"] = {}
    assert (await triage.triage_incident(str(INCIDENT), str(COMPANY)))["status"] == "module_off"
    assert "checked" not in env


@pytest.mark.asyncio
async def test_second_check_same_phase_is_skipped(env):
    env["claimed"] = None
    assert (await triage.triage_incident(str(INCIDENT), str(COMPANY)))["status"] == "already_checked"
    assert "checked" not in env


@pytest.mark.asyncio
async def test_unavailable_is_not_clean(env):
    env["result"] = result(available=False)
    out = await triage.triage_incident(str(INCIDENT), str(COMPANY))
    assert out["status"] == "unavailable" and out["attempts"] == 1
    assert env["opened"] == []
    null_write = next(sql for sql in env["conn"].sql_for("execute") if "implicated = NULL" in sql)
    assert null_write
    # Retried once in the same run before giving up.
    assert env["checks"] == 2
    stored = env["conn"].args_for("implicated = NULL")[2]
    assert '"attempts": 1' in stored and '"available": false' in stored


@pytest.mark.asyncio
async def test_a_transient_failure_is_retried_and_can_succeed(env):
    env["result"] = [result(available=False), result(v("violated", 0.9))]
    assert (await triage.triage_incident(str(INCIDENT), str(COMPANY)))["status"] == "flagged"
    assert env["checks"] == 2


@pytest.mark.asyncio
async def test_a_failed_check_is_reclaimable_up_to_a_limit(env):
    await triage.triage_incident(str(INCIDENT), str(COMPANY))
    claim_sql = next(sql for sql in env["conn"].sql_for("fetchval") if "INSERT INTO hr_case_triage_log" in sql)
    # Only a finished "couldn't check" row with attempts left is taken over;
    # an in-flight claim (no `available` yet) or a real answer never is.
    assert "implicated IS NULL" in claim_sql and "->>'available' = 'false'" in claim_sql
    assert "< $4" in claim_sql
    assert env["conn"].args_for("INSERT INTO hr_case_triage_log")[3] == triage.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_a_dismissed_case_is_never_reopened_by_the_close_check(env):
    dismissed = {"id": uuid4(), "stage": "dismissed"}
    env["latest"] = dismissed
    out = await triage.triage_incident(str(INCIDENT), str(COMPANY), phase="close")
    assert out["status"] == "recorded" and out["case_id"] == str(dismissed["id"])
    assert env["opened"] == [] and env["notified"] == []
    assert env["events"][0]["event"] == "close_check_match"


def test_the_model_summary_is_never_kept():
    raw = result(v("violated", 0.9))
    raw["summary"] = "Dana was late three times and argued with a manager."
    out = triage.summarize(raw, phase="intake")
    assert "summary" not in out and "Dana" not in str(out)


@pytest.mark.asyncio
async def test_clean_opens_nothing(env):
    env["result"] = result(v("related", 0.9))
    assert (await triage.triage_incident(str(INCIDENT), str(COMPANY)))["status"] == "clean"
    assert env["opened"] == [] and env["notified"] == []


@pytest.mark.asyncio
async def test_existing_case_gets_an_event_not_a_second_case(env):
    env["existing"] = {"id": uuid4(), "stage": "hr_review"}
    env["result"] = result(v("related", 0.9))
    out = await triage.triage_incident(str(INCIDENT), str(COMPANY), phase="close")
    assert out["status"] == "recorded" and out["implicated"] is False
    assert env["events"][0]["event"] == "close_check_clean"
    assert env["opened"] == []


@pytest.mark.asyncio
async def test_bad_phase_and_errors_never_raise(env, monkeypatch):
    assert (await triage.triage_incident(str(INCIDENT), str(COMPANY), phase="later"))["status"] == "error"
    assert (await triage.triage_incident("not-a-uuid", str(COMPANY)))["status"] == "error"


@pytest.mark.asyncio
async def test_schedule_close_check_runs_in_background(monkeypatch):
    seen = []

    async def fake(incident_id, company_id, *, phase):
        seen.append((incident_id, company_id, phase))
    monkeypatch.setattr(triage, "triage_incident", fake)
    triage.schedule_close_check(COMPANY, INCIDENT)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert seen == [(str(INCIDENT), str(COMPANY), "close")]


def test_schedule_close_check_without_loop_is_noop():
    triage.schedule_close_check(COMPANY, INCIDENT)


@pytest.mark.asyncio
async def test_no_connection_is_held_across_the_model_call(env):
    await triage.triage_incident(str(INCIDENT), str(COMPANY))
    assert env["conns_during_model"] == [0]
    # Pooled, not a forced raw connection per incident.
    assert all("force_direct" not in kw for kw in env["direct_kwargs"])


@pytest.mark.asyncio
async def test_module_off_reads_no_incident(env):
    env["features"] = {}
    await triage.triage_incident(str(INCIDENT), str(COMPANY))
    assert not env["conn"].sql_for("fetchrow") and len(env["direct_kwargs"]) == 1
