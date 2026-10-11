"""MANUAL ONLY: existing dev schema, rollback-only, reserved-domain data.

No DDL, live model calls, storage writes or notifications. Run yourself:
  RUN_DB_TESTS=1 RUN_HR_CASE_DB_WRITE_TESTS=1 DATABASE_URL=<dev URL> \
    ./venv/bin/python -m pytest tests/hr_cases/test_incident_review_realdb.py -v
"""
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.matcha.models.hr_cases import PolicyViolationReview
from app.matcha.services.hr_cases import case_service, draft_review, incident_review, notifications, triage, workflow
from app.matcha.services.hr_cases.case_service import CaseError
from tests._helpers.db import real_database_url, requires_real_db

pytestmark = [requires_real_db(), pytest.mark.skipif(
    os.getenv("RUN_HR_CASE_DB_WRITE_TESTS") != "1", reason="manual HR-case DB writes are not enabled",
), pytest.mark.asyncio]


@pytest_asyncio.fixture
async def db_case(monkeypatch):
    conn = await asyncpg.connect(real_database_url())
    tx = conn.transaction()
    await tx.start()
    try:
        user_id, company_id, employee_id, incident_id = (uuid4() for _ in range(4))
        email = f"hr-{user_id}@example.test"
        await conn.execute("INSERT INTO users (id, email, password_hash, role) VALUES ($1, $2, 'unusable-test-hash', 'client')", user_id, email)
        await conn.execute("INSERT INTO companies (id, name, owner_id) VALUES ($1, 'HR review test', $2)", company_id, user_id)
        await conn.execute(
            "INSERT INTO employees (id, org_id, first_name, last_name, email, work_state) "
            "VALUES ($1, $2, 'Test', 'Employee', $3, 'CA')", employee_id, company_id, f"employee-{employee_id}@example.test",
        )
        occurred = date.today() - timedelta(days=2)
        await conn.execute(
            """INSERT INTO ir_incidents (id, company_id, incident_number, title, description, incident_type,
                                         occurred_at, reported_by_name, created_by, involved_employee_ids)
               VALUES ($1, $2, $3, 'Attendance report', 'A missed shift was reported.', 'behavioral',
                       $4, 'Test Reporter', $5, $6)""",
            incident_id, company_id, f"IR-TEST-{incident_id}", datetime.combine(occurred, time()), user_id, [employee_id],
        )
        case, _ = await case_service.open_case(conn, company_id=company_id, origin="manual", incident_id=incident_id,
                                              employee_id=employee_id, gm_user_id=user_id, opened_by=user_id)

        @asynccontextmanager
        async def connect():
            yield conn  # all service transactions are savepoints of the rollback below

        # Actual SQL, access, gate and stage writers; only external calls fake.
        model = AsyncMock(return_value="Test Employee missed a reported shift. Expected improvement and signature.")
        monkeypatch.setattr(incident_review, "draft_letter", model)
        monkeypatch.setattr(draft_review, "ai_wording_review", AsyncMock(return_value=[]))
        monkeypatch.setattr(notifications, "send_step", AsyncMock())
        monkeypatch.setattr(notifications, "notify_step", AsyncMock())
        monkeypatch.setattr(notifications, "step_recipients", AsyncMock(return_value=[]))

        # File metadata goes to the real HR folder; no bytes ever leave the test.
        async def store(conn, **kw):
            from app.matcha.services.drive import drive_service
            folders = await drive_service.ensure_system_folders(conn, company_id)
            fid = await conn.fetchval(
                """INSERT INTO drive_files (company_id, folder_id, filename, storage_path, text_status, source, source_ref)
                   VALUES ($1, $2, 'test-letter.txt', 's3://example.test/manual-only', 'ok', 'system', $3) RETURNING id""",
                company_id, folders["hr_discipline_drafts"], kw.get("source_ref"),
            )
            return {"id": fid}
        monkeypatch.setattr(workflow, "store_draft_file", store)
        user = SimpleNamespace(id=user_id, email=email, role="client")
        payload = PolicyViolationReview(classification="policy_violation", employee_id=employee_id,
                                       action_type="verbal_warning", infraction_type="attendance", occurrence_dates=[occurred])
        yield SimpleNamespace(conn=conn, connect=connect, user=user, company_id=company_id, case_id=case["id"],
                              employee_id=employee_id, incident_id=incident_id, occurred=occurred, body=payload, model=model)
    finally:
        await tx.rollback()
        await conn.close()


async def test_advance_and_clean_incident_never_create_suggestion(db_case):
    d = db_case
    out = await incident_review.start_draft(d.connect, company_id=d.company_id, case_id=d.case_id, user=d.user)
    assert out["stage"] == "drafting"
    await d.conn.execute(
        "INSERT INTO hr_case_triage_log (incident_id, company_id, phase) VALUES ($1, $2, 'intake')", d.incident_id, d.company_id,
    )
    out = await triage._record(d.conn, incident={"id": d.incident_id}, company_id=d.company_id, phase="intake",
                               result={"available": True, "violations": []}, attempts=1)
    assert out["implicated"] is False
    case = await case_service.get_case(d.conn, company_id=d.company_id, case_id=d.case_id, with_events=True)
    assert not case["review"] and not case["draft_file_id"]
    assert "start_draft" in [e["event"] for e in case["events"]]
    d.model.assert_not_awaited()


async def test_confirm_edit_accept_and_separate_approval(db_case):
    d = db_case
    case = await incident_review.suggest(d.connect, company_id=d.company_id, case_id=d.case_id, user=d.user, body=d.body)
    suggestion_id = case["review"]["suggestion"]["id"]
    again = await incident_review.suggest(d.connect, company_id=d.company_id, case_id=d.case_id, user=d.user, body=d.body)
    assert again["review"]["suggestion"]["id"] == suggestion_id and d.model.await_count == 1
    case = await incident_review.accept_suggestion(d.connect, company_id=d.company_id, case_id=d.case_id, user=d.user,
                                                  suggestion_id=suggestion_id, letter="Test Employee: HR edited this draft. Expected improvement, acknowledgment and signature.")
    assert case["stage"] == "hr_review" and case["draft_file_id"] and case["decision"] is None
    case = await workflow.decide(d.conn, company_id=d.company_id, case_id=d.case_id, actor_user_id=d.user.id,
                                 decision="approve", reason="Reviewed the draft and advisories.")
    assert case["stage"] == "approved"


async def test_protected_absence_is_hard_422_before_model_or_draft(db_case):
    d = db_case
    await d.conn.execute(
        "INSERT INTO pto_requests (employee_id, request_type, start_date, end_date, hours, status) "
        "VALUES ($1, 'sick', $2, $2, 8, 'approved')", d.employee_id, d.occurred,
    )
    with pytest.raises(CaseError) as exc:
        await incident_review.suggest(d.connect, company_id=d.company_id, case_id=d.case_id, user=d.user, body=d.body)
    assert exc.value.status == 422
    d.model.assert_not_awaited()
    case = await case_service.get_case(d.conn, company_id=d.company_id, case_id=d.case_id)
    assert not case["review"] and not case["draft_file_id"]
