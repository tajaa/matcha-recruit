"""Who is told about a flagged case, what they're told, and who has HR access.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_notifications_access.py -q
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.services.drive.drive_access import DriveActor, DriveCap
from app.matcha.services.drive.drive_service import DriveError
from app.matcha.services.hr_cases import access, notifications
from tests._helpers.routes import QueryConn, Queue

COMPANY = uuid4()


def test_messages_name_policies_and_copies_but_no_narrative():
    msgs = notifications.flagged_messages(
        case_number="HRC-2026-0004", incident_number="IR-12", policy_titles=["Attendance policy"],
        hr_names=["Dana", "Lee"], gm_name="Sam",
    )
    assert "IR-12" in msgs["gm"]["body"] and "Attendance policy" in msgs["gm"]["body"]
    assert "Dana and Lee in HR are copied" in msgs["gm"]["body"]
    assert msgs["hr"]["title"] == "HRC-2026-0004: incident flagged"
    assert "Sam, who reported it, was notified" in msgs["hr"]["body"]


def test_messages_anonymous_and_single_hr():
    msgs = notifications.flagged_messages(
        case_number="HRC-1", incident_number=None, policy_titles=[], hr_names=["Dana"], gm_name=None,
    )
    assert "Dana in HR is copied" in msgs["gm"]["body"]
    assert "reported anonymously" in msgs["hr"]["body"]
    assert "a company policy" in msgs["hr"]["body"]


@pytest.mark.asyncio
async def test_gm_resolution_prefers_creator_then_email():
    creator = uuid4()
    conn = QueryConn(fetchval={"FROM users u": creator})
    assert await notifications.resolve_gm_user_id(conn, company_id=COMPANY, incident={"created_by": creator}) == creator
    by_email = uuid4()
    conn = QueryConn(fetchval={"FROM users u": Queue([None, by_email])})
    got = await notifications.resolve_gm_user_id(
        conn, company_id=COMPANY, incident={"created_by": uuid4(), "reported_by_email": "gm@example.com"},
    )
    assert got == by_email
    assert "lower(u.email)" in conn.sql_for("fetchval")[1]
    assert await notifications.resolve_gm_user_id(QueryConn(), company_id=COMPANY, incident={}) is None


@pytest.mark.asyncio
async def test_hr_recipients_fall_back(monkeypatch):
    owner = {"user_id": uuid4(), "role": "client", "name": "Owner"}

    async def everyone(conn, *, user, company_id):
        return True
    monkeypatch.setattr(access, "has_hr_access", everyone)
    conn = QueryConn(fetch={"FROM clients c JOIN users u": Queue([[], []]), "FROM companies co": [owner]})
    assert await notifications.hr_recipients(conn, COMPANY) == [{"user_id": owner["user_id"], "name": "Owner"}]


@pytest.mark.asyncio
async def test_only_people_with_hr_access_are_told(monkeypatch):
    # No approvers; the owner has no HR access; of everyone else only the Work
    # admin does. The plain member must not hear about an HR matter.
    owner = {"user_id": uuid4(), "role": "client", "name": "Owner"}
    admin = {"user_id": uuid4(), "role": "client", "name": "Admin"}
    member = {"user_id": uuid4(), "role": "client", "name": "Member"}

    async def only_admin(conn, *, user, company_id):
        return user.id == admin["user_id"]
    monkeypatch.setattr(access, "has_hr_access", only_admin)
    conn = QueryConn(fetch={
        "FROM clients c JOIN users u": Queue([[], [admin, member]]),
        "FROM companies co": [owner],
    })
    assert await notifications.hr_recipients(conn, COMPANY) == [{"user_id": admin["user_id"], "name": "Admin"}]


@pytest.mark.asyncio
async def test_nobody_with_access_means_nobody_is_told(monkeypatch):
    async def nobody(conn, *, user, company_id):
        return False
    monkeypatch.setattr(access, "has_hr_access", nobody)
    member = {"user_id": uuid4(), "role": "client", "name": "Member"}
    conn = QueryConn(fetch={"FROM clients c JOIN users u": Queue([[member], [member]]), "FROM companies co": [member]})
    assert await notifications.hr_recipients(conn, COMPANY) == []


def test_a_reporter_who_left_is_not_called_anonymous():
    msgs = notifications.flagged_messages(
        case_number="HRC-1", incident_number="IR-3", policy_titles=["Attendance"],
        hr_names=["Dana"], gm_name=None, has_reporter=True,
    )
    assert "anonymously" not in msgs["hr"]["body"]
    assert "isn't an active member" in msgs["hr"]["body"]


@pytest.mark.asyncio
async def test_notify_flagged_sends_hr_and_gm_with_links(monkeypatch):
    from app.matcha.services import notification_service

    sent = []

    async def create(**kw):
        sent.append(kw)
    monkeypatch.setattr(notification_service, "create_notification", create)
    gm, hr = uuid4(), uuid4()

    async def recips(conn, company_id):
        return [{"user_id": hr, "name": "Dana"}, {"user_id": gm, "name": "Sam"}]
    monkeypatch.setattr(notifications, "hr_recipients", recips)
    case = {"id": uuid4(), "company_id": COMPANY, "case_number": "HRC-1", "gm_user_id": gm}
    incident = {"id": uuid4(), "incident_number": "IR-3"}
    await notifications.notify_flagged(QueryConn(fetchval={"FROM users u": "Sam"}), case=case, incident=incident, policy_titles=["X"])
    assert [(s["user_id"], s["link"].split("/")[1]) for s in sent] == [(hr, "work"), (gm, "app")]
    assert all(s["type"] == "hr_case_flagged" and s["send_email"] for s in sent)


@pytest.mark.asyncio
async def test_notify_flagged_never_raises(monkeypatch):
    async def boom(conn, company_id):
        raise RuntimeError("db")
    monkeypatch.setattr(notifications, "hr_recipients", boom)
    await notifications.notify_flagged(QueryConn(), case={"id": 1, "company_id": COMPANY, "gm_user_id": None},
                                       incident={"id": 2}, policy_titles=[])


# ── Access ──────────────────────────────────────────────────────────────


@pytest.fixture
def drive(monkeypatch):
    from app.matcha.services.drive import drive_service

    state = {"level": "operator", "caps": frozenset(), "error": False}

    async def load_actor(conn, *, user, company_id):
        return DriveActor(user_id=user.id, work_level=state["level"])

    async def seeded(conn, company_id):
        return {"hr_discipline": uuid4()}

    async def caps(conn, *, company_id, folder_id, actor):
        if state["error"]:
            raise DriveError(404, "gone")
        return {}, state["caps"]
    monkeypatch.setattr(drive_service, "load_actor", load_actor)
    monkeypatch.setattr(drive_service, "ensure_system_folders", seeded)
    monkeypatch.setattr(drive_service, "folder_caps", caps)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("level,caps,error,expected", [
    ("admin", frozenset(), False, True),
    ("operator", frozenset(), False, False),
    ("operator", frozenset({DriveCap.LIST, DriveCap.READ}), False, True),
    ("operator", frozenset({DriveCap.ADD}), False, False),  # drop-box is not HR access
    ("operator", frozenset(), True, False),
])
async def test_has_hr_access(drive, level, caps, error, expected):
    drive.update(level=level, caps=caps, error=error)
    user = SimpleNamespace(id=uuid4(), role="client")
    assert await access.has_hr_access(QueryConn(), user=user, company_id=COMPANY) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("step,to_hr,type_", [
    ("draft_submitted", True, "hr_case_draft_submitted"),
    ("draft_held", True, "hr_case_draft_held"),
    ("approved", False, "hr_case_approved"),
    ("changes_requested", False, "hr_case_changes_requested"),
    ("delivered", True, "hr_case_delivered"),
])
async def test_notify_step_routes_to_the_right_people(monkeypatch, step, to_hr, type_):
    from app.matcha.services import notification_service

    sent = []

    async def create(**kw):
        sent.append(kw)
    monkeypatch.setattr(notification_service, "create_notification", create)
    hr, gm = uuid4(), uuid4()

    async def recips(conn, company_id):
        return [{"user_id": hr, "name": "Dana"}]
    monkeypatch.setattr(notifications, "hr_recipients", recips)
    case = {"id": uuid4(), "company_id": COMPANY, "case_number": "HRC-9", "gm_user_id": gm}
    await notifications.notify_step(QueryConn(), case=case, step=step, actor_user_id=None, reason="Add dates")
    assert [s["user_id"] for s in sent] == [hr if to_hr else gm]
    assert sent[0]["type"] == type_
    assert sent[0]["link"].startswith("/work/hr-cases/" if to_hr else "/work/write-ups/")
    if step == "changes_requested":
        assert "Add dates" in sent[0]["body"]


@pytest.mark.asyncio
async def test_notify_step_skips_the_actor_and_survives_failures(monkeypatch):
    from app.matcha.services import notification_service

    hr = uuid4()

    async def recips(conn, company_id):
        return [{"user_id": hr, "name": "Dana"}]

    async def boom(**kw):
        raise RuntimeError("smtp")
    monkeypatch.setattr(notifications, "hr_recipients", recips)
    monkeypatch.setattr(notification_service, "create_notification", boom)
    case = {"id": uuid4(), "company_id": COMPANY, "case_number": "HRC-9", "gm_user_id": None}
    await notifications.notify_step(QueryConn(), case=case, step="delivered", actor_user_id=None)

    async def fail_recips(conn, company_id):
        raise RuntimeError("db")
    sent = []

    async def create(**kw):
        sent.append(kw)
    monkeypatch.setattr(notifications, "hr_recipients", fail_recips)
    monkeypatch.setattr(notification_service, "create_notification", create)
    await notifications.notify_step(QueryConn(), case=case, step="delivered", actor_user_id=None)
    assert sent == []
    await notifications.send(user_ids=[hr, hr, None], company_id=COMPANY, type="t", title="x", body="y",
                             link="/l", skip_user_id=None)
    assert len(sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,reasons,expect_hr,expect_gm", [
    ("closed", [], "hr_case_signed_filed", False),
    ("needs_attention", ["employee_comments"], "hr_case_signed_attention", False),
    # Anything of HR's on it: the manager isn't asked to replace it.
    ("needs_attention", ["illegible_scan", "employee_comments"], "hr_case_signed_attention", False),
    ("needs_attention", ["illegible_scan"], "hr_case_signed_attention", True),
    ("verifying", [], None, False),
])
async def test_notify_signed(monkeypatch, stage, reasons, expect_hr, expect_gm):
    from app.matcha.services import notification_service

    sent = []

    async def create(**kw):
        sent.append(kw)
    monkeypatch.setattr(notification_service, "create_notification", create)
    hr, gm = uuid4(), uuid4()

    async def recips(conn, company_id):
        return [{"user_id": hr, "name": "Dana"}]
    monkeypatch.setattr(notifications, "hr_recipients", recips)
    case = {"id": uuid4(), "company_id": COMPANY, "case_number": "HRC-9", "gm_user_id": gm,
            "stage": stage, "attention_reasons": reasons}
    await notifications.notify_signed(QueryConn(), case=case, actor_user_id=None)
    hr_sent = [s for s in sent if s["user_id"] == hr]
    gm_sent = [s for s in sent if s["user_id"] == gm]
    if expect_hr:
        assert hr_sent[0]["type"] == expect_hr
    else:
        assert hr_sent == []
    assert bool(gm_sent) is expect_gm
    if gm_sent:
        assert "comments" not in gm_sent[0]["body"].lower()
        assert "hard to read" in gm_sent[0]["body"]


@pytest.mark.asyncio
async def test_notify_signed_survives_recipient_failure(monkeypatch):
    async def boom(conn, company_id):
        raise RuntimeError("db")
    monkeypatch.setattr(notifications, "hr_recipients", boom)
    await notifications.notify_signed(QueryConn(), case={"id": uuid4(), "company_id": COMPANY, "case_number": "H",
                                                         "stage": "closed", "gm_user_id": None}, actor_user_id=None)
