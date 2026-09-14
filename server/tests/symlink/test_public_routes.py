"""Sym-link public routes over HTTP: the rate-limit ordering, the budgets and
the multipart handling that the route-table tests can only assert structurally.

DB, S3, Gemini and Redis are patched at the route module; request parsing,
check order and status mapping are real.

    cd server && ./venv/bin/python -m pytest tests/symlink/test_public_routes.py -q
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from tests._helpers.routes import QueryConn, connection_patch, route_client
from tests.symlink.test_routes_smoke import _load

MODULE = "app.matcha.routes.intake.symlink_public"
TOKEN = "tok_" + "a" * 40
COMPANY_ID = uuid4()
LINK_ID = uuid4()
SPEC = {
    "kind": "credential_upload",
    "fields": [],
    "attachments": [{"slot": "document", "label": "The document", "required": True, "accept": [".pdf"]}],
}
PDF = ("scan.pdf", b"%PDF-1.4 not really", "application/pdf")


def _row(**over):
    row = {
        "id": LINK_ID, "company_id": COMPANY_ID, "company_name": "Po Coffee Co",
        "title": "Food handler card", "kind": "credential_upload", "instructions": None,
        "recipient_name": "Maria", "recipient_email": "maria@example.com",
        "status": "pending", "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "spec": json.dumps(SPEC), "known_fields": "{}", "transcript": "[]",
        "turn_count": 0, "created_by": uuid4(),
    }
    row.update(over)
    return row


def _returns(value):
    async def fn(*_a, **_k):
        return value
    return fn


class _Conn(QueryConn):
    """QueryConn plus the `conn.transaction()` these handlers open (QueryConn is
    already an async context manager, so it can stand in for the transaction)."""

    def transaction(self):
        return self


class _Limits:
    """Records every rate-limit charge; chosen actions can be made to 429."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.peeks: list[tuple] = []
        self.block: set[str] = set()
        self.state = None  # what get_rate_limit_state returns (None = no Redis)

    async def check(self, key, action, limit, window):
        self.calls.append((key, action, limit, window))
        if action in self.block:
            raise HTTPException(status_code=429, detail="Too many requests.")

    async def peek(self, key, action, limit, window):
        self.peeks.append((key, action))
        return self.state

    def actions(self):
        return [call[1] for call in self.calls]


@pytest.fixture
def mod():
    return sys.modules.get(MODULE) or _load(MODULE, "app/matcha/routes/intake/symlink_public.py")


@pytest.fixture
def wired(mod, monkeypatch):
    rec = SimpleNamespace(
        limits=_Limits(), conn=_Conn(), row=_row(), fresh=None, passcode_ok=True,
        resolved=[], verified=[], staged=[], inserted=[],
    )

    async def resolve(token):
        rec.resolved.append(token)
        return rec.row

    async def fetch_by_id(_conn, _link_id, _company_id, for_update=False):
        return rec.fresh or rec.row

    async def stage_upload(file, **kw):
        rec.staged.append((file.filename, await file.read(), kw))
        return {"storage_path": "symlink/x/scan.pdf", "file_name": file.filename}

    async def insert_attachment(_conn, **kw):
        rec.inserted.append(kw)
        return {"id": uuid4(), "slot": kw["slot"]}, []

    def verify(given, _stored):
        rec.verified.append(given)
        return rec.passcode_ok

    monkeypatch.setattr(mod, "check_rate_limit", rec.limits.check)
    monkeypatch.setattr(mod, "get_rate_limit_state", rec.limits.peek)
    monkeypatch.setattr(mod, "_resolve", resolve)
    monkeypatch.setattr(mod, "_require_unlock", _returns(None))
    monkeypatch.setattr(mod, "_state", _returns({}))
    monkeypatch.setattr(mod.links, "fetch_by_id", fetch_by_id)
    monkeypatch.setattr(mod.links, "present_slots", _returns(set()))
    monkeypatch.setattr(mod.links, "log_audit", _returns(None))
    monkeypatch.setattr(mod.links, "record_unlock", _returns("unlock-token"))
    monkeypatch.setattr(mod.links, "save_turn", _returns(None))
    monkeypatch.setattr(mod.att, "stage_upload", stage_upload)
    monkeypatch.setattr(mod.att, "insert_attachment", insert_attachment)
    monkeypatch.setattr(mod.att, "serialize", lambda a: {"id": str(a["id"]), "slot": a["slot"]})
    monkeypatch.setattr(mod.att, "discard", _returns(None))
    monkeypatch.setattr(mod.passcode, "fetch_passcode", _returns({"code": "ABC234"}))
    monkeypatch.setattr(mod.passcode, "verify", verify)
    monkeypatch.setattr(mod.chat, "next_turn", _returns(
        {"assistant_message": "Thanks.", "fields": {}, "complete": False, "error": False}
    ))
    monkeypatch.setattr(mod.submissions, "stage", _returns({"id": uuid4()}))
    monkeypatch.setattr(mod.notify, "sender_contact", _returns((None, None)))
    with connection_patch(monkeypatch, mod, rec.conn), route_client(mod.router) as client:
        rec.client = client
        yield rec


def _keyed(limits):
    """(key, action) pairs — what was charged and against whom, without
    pinning the numbers (those live in the tables and test_routes_smoke)."""
    return [(call[0], call[1]) for call in limits.calls]


# ── upload: multipart is read by hand, after the limits ─────────────────────


def test_upload_reads_the_form_after_the_limits_and_stages_the_file(wired):
    res = wired.client.post(f"/sym/{TOKEN}/attachments", data={"slot": "document"}, files={"file": PDF})
    assert res.status_code == 200, res.text
    assert wired.limits.actions() == ["symlink_upload_ip", "symlink_upload_link", "symlink_upload_co"]
    (name, content, kw), = wired.staged
    assert (name, content) == ("scan.pdf", PDF[1])
    assert kw["accept"] == [".pdf"]
    assert wired.inserted[0]["slot"] == "document"


@pytest.mark.parametrize(
    ("data", "files", "detail"),
    [
        ({}, {"file": PDF}, "Missing or invalid attachment slot"),
        ({"slot": "x" * 65}, {"file": PDF}, "Missing or invalid attachment slot"),
        ({"slot": "document"}, None, "Missing file"),
        ({"slot": "passport"}, {"file": PDF}, "Unknown attachment slot"),
    ],
)
def test_upload_rejects_a_bad_form_before_staging_anything(wired, data, files, detail):
    res = wired.client.post(f"/sym/{TOKEN}/attachments", data=data, files=files)
    assert res.status_code == 422
    assert res.json()["detail"] == detail
    assert wired.staged == []


def test_a_per_ip_429_on_upload_never_reads_the_body(wired, monkeypatch):
    """The whole point of dropping File()/Form(): a flood is refused before
    Starlette parses (and spools) the multipart body."""

    def unreachable(self, *_a, **_k):
        raise AssertionError("the multipart body was parsed before the per-IP limit")

    monkeypatch.setattr(Request, "form", unreachable)
    wired.limits.block.add("symlink_upload_ip")
    res = wired.client.post(f"/sym/{TOKEN}/attachments", data={"slot": "document"}, files={"file": PDF})
    assert res.status_code == 429
    assert wired.resolved == []


# ── unlock: the tenant-wide failure ceiling ─────────────────────────────────


def test_unlock_refuses_before_verifying_once_the_tenant_failure_budget_is_spent(wired):
    wired.limits.state = {"used": 100, "limit": 100, "remaining": 0, "resets_in_seconds": 1200}
    res = wired.client.post(f"/sym/{TOKEN}/unlock", json={"passcode": "ABC234"})
    assert res.status_code == 429
    assert res.headers["retry-after"] == "1200"
    assert wired.verified == []


def test_a_wrong_passcode_charges_the_tenant_failure_budget(wired, mod):
    wired.passcode_ok = False
    res = wired.client.post(f"/sym/{TOKEN}/unlock", json={"passcode": "WRONG1"})
    assert res.status_code == 401
    assert (
        str(COMPANY_ID), "symlink_unlock_fail_co", mod.UNLOCK_FAILURES_PER_COMPANY_HOURLY, 3600,
    ) in wired.limits.calls


def test_a_right_passcode_peeks_at_the_failure_budget_but_never_spends_it(wired):
    res = wired.client.post(f"/sym/{TOKEN}/unlock", json={"passcode": "ABC234"})
    assert res.status_code == 200, res.text
    assert wired.limits.peeks == [(str(COMPANY_ID), "symlink_unlock_fail_co")]
    assert "symlink_unlock_fail_co" not in wired.limits.actions()


def test_honeypot_hits_are_metered_like_any_other_request(wired):
    """Deliberate: short-circuiting bots before the charge would make
    `internal_ref` a way to hit the endpoint unmetered."""
    res = wired.client.post(f"/sym/{TOKEN}/unlock", json={"passcode": "x", "internal_ref": "bot"})
    assert res.json() == {"unlock_token": "ok"}
    assert wired.limits.actions() == ["symlink_unlock_ip"]
    assert wired.resolved == []


# ── budgets on validate / delete / turn / submit ────────────────────────────


def test_validate_and_delete_charge_their_link_and_company_budgets(wired):
    assert wired.client.get(f"/sym/{TOKEN}").status_code == 200
    wired.conn.set("fetchrow", "UPDATE symlink_attachments", {"storage_path": "symlink/x/old.pdf"})
    assert wired.client.delete(f"/sym/{TOKEN}/attachments/{uuid4()}").status_code == 200
    company = str(COMPANY_ID)
    assert _keyed(wired.limits) == [
        ("testclient", "symlink_validate_ip"), (TOKEN, "symlink_validate_link"), (company, "symlink_validate_co"),
        ("testclient", "symlink_delete_ip"), (TOKEN, "symlink_delete_link"), (company, "symlink_delete_co"),
    ]


def test_a_turn_past_max_turns_answers_from_the_db_and_spends_no_budget(wired, mod, monkeypatch):
    wired.fresh = _row(turn_count=mod.chat.MAX_TURNS)
    monkeypatch.setattr(mod, "_state", _returns({"known_fields": {}, "complete": False}))
    res = wired.client.post(f"/sym/{TOKEN}/chat/turn", json={"message": "hello"})
    assert res.status_code == 200 and res.json()["limit_reached"] is True
    assert "symlink_turn_link" not in wired.limits.actions()


def test_a_turn_that_reaches_the_model_spends_the_budget(wired):
    res = wired.client.post(f"/sym/{TOKEN}/chat/turn", json={"message": "hello"})
    assert res.status_code == 200, res.text
    assert wired.limits.actions() == ["symlink_turn_ip", "symlink_turn_ip_hr", "symlink_turn_link", "symlink_turn_co"]


def test_the_loser_of_a_double_submit_410s_without_spending_an_attempt(wired):
    wired.fresh = _row(status="submitted")  # the winner committed first
    res = wired.client.post(f"/sym/{TOKEN}/submit", json={"fields": {}})
    assert res.status_code == 410
    assert "symlink_submit_link" not in wired.limits.actions()


def test_a_submit_spends_its_attempt_after_the_locked_recheck(wired):
    res = wired.client.post(f"/sym/{TOKEN}/submit", json={"fields": {}})
    assert res.status_code == 200, res.text
    assert wired.limits.actions() == ["symlink_submit_ip", "symlink_submit_link", "symlink_submit_co"]
