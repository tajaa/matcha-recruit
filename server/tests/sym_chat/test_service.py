"""run_turn / create / cancel orchestration (services/sym_chat/service.py).

`QueryConn` answers by SQL substring; `get_connection` is patched on the
DEFINING module. The model call and notification side effects are faked so
the test can assert exactly who got what, and how many times.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.matcha.services.sym_chat import service
from tests._helpers.routes import QueryConn

COMPANY, CHAT, ME, OTHER = uuid4(), uuid4(), uuid4(), uuid4()
DECIDE_CFG = {"options": ["Thai Palace", "Burger Barn"]}
AGREE = {"proposals": [], "ok_with": ["Thai Palace"], "vetoes": [], "top_pick": None}


class TxConn(QueryConn):
    def transaction(self):
        @asynccontextmanager
        async def _tx():
            yield
        return _tx()


def _turn_conn(*, locked_status="open", other_stance=AGREE):
    old_shape = {"kind": "decide", "total": 2, "responded": 1, "options": [], "leading": None, "consensus": False}
    return TxConn(
        fetchrow={
            "SELECT id, kind, title": {
                "id": CHAT, "kind": "decide", "title": "Team lunch", "objective": "",
                "config": json.dumps(DECIDE_CFG), "status": "open",
            },
            "SELECT p.stance": {"stance": None, "name": "Dana"},
            "FOR UPDATE": {"status": locked_status, "shape": json.dumps(old_shape)},
        },
        fetchval={
            "COUNT(*) FROM mw_sym_chat_messages": 0,
            "COALESCE(MAX(seq)": 3,
        },
        fetch={
            "SELECT stance FROM mw_sym_chat_participants": [{"stance": None}, {"stance": json.dumps(other_stance)}],
            "SELECT role, content FROM mw_sym_chat_messages": [{"role": "user", "content": "Thai is fine"}],
            "SELECT user_id, stance FROM mw_sym_chat_participants": [
                {"user_id": ME, "stance": json.dumps(AGREE)},
                {"user_id": OTHER, "stance": json.dumps(other_stance)},
            ],
        },
    )


@pytest.fixture
def sent(monkeypatch):
    calls = {"notify": [], "push": []}

    async def notify(**kwargs):
        calls["notify"].append(kwargs)
        return {}

    async def push(user_ids, payload):
        calls["push"].append((list(user_ids), payload))

    async def fake_turn(kind, objective, config, transcript, current, known, name):
        return {"reply": "Noted — Thai works for you.", "stance": AGREE, "error": False}

    monkeypatch.setattr(service.notification_service, "create_notification", notify)
    monkeypatch.setattr(service.notification_service, "push_to_users", push)
    monkeypatch.setattr(service.extract, "next_turn", fake_turn)
    return calls


def _run(monkeypatch, conn):
    monkeypatch.setattr(service, "get_connection", lambda *a, **k: conn)
    return asyncio.run(service.run_turn(CHAT, COMPANY, ME, "Thai is fine"))


def test_turn_that_reaches_consensus_resolves_once_and_invites_everyone(monkeypatch, sent):
    conn = _turn_conn()
    out = _run(monkeypatch, conn)

    assert out["resolved"] is True and out["status"] == "resolved"
    assert out["shape"]["consensus"] and out["shape"]["leading"]["name"] == "Thai Palace"

    resolve_sql = [s for s in conn.sql_for("execute") if "status = 'resolved'" in s]
    assert len(resolve_sql) == 1
    resolution = json.loads(conn.args_for("status = 'resolved'")[2])
    assert resolution == {"kind": "decide", "choice": "Thai Palace"}

    feed = conn.args_for("INSERT INTO mw_sym_chat_updates")
    assert feed[1] == 3  # the seq the COALESCE(MAX(seq), 0) + 1 query returned
    assert feed[2] == "All 2 agree on Thai Palace. Sending invites to everyone."

    invites = [n for n in sent["notify"] if n["type"] == "sym_chat_resolved"]
    assert sorted(n["user_id"] for n in invites) == sorted([ME, OTHER])
    assert all(n["send_email"] for n in invites)
    assert sent["push"] == [([ME, OTHER], {"type": "sym_chat.updated", "sym_chat_id": str(CHAT), "status": "resolved"})]

    # The user message was stored before the model call, the reply after.
    inserts = [a for k, s, a in conn.calls if k == "execute" and "INSERT INTO mw_sym_chat_messages" in s]
    assert [a[-1] for a in inserts] == ["Thai is fine", "Noted — Thai works for you."]


def test_turn_after_a_concurrent_resolve_never_invites_twice(monkeypatch, sent):
    conn = _turn_conn(locked_status="resolved")
    out = _run(monkeypatch, conn)

    assert out["resolved"] is False and out["status"] == "resolved"
    assert sent["notify"] == [] and sent["push"] == []
    assert not any("UPDATE mw_sym_chat_participants" in s for s in conn.sql_for("execute"))
    # The reply is still recorded in the caller's tunnel.
    assert conn.args_for("'assistant'")[-1] == "Noted — Thai works for you."


def test_progress_turn_posts_a_feed_line_without_resolving(monkeypatch, sent):
    other = {"proposals": [], "ok_with": ["Burger Barn"], "vetoes": ["Thai Palace"], "top_pick": None}
    conn = _turn_conn(other_stance=other)
    out = _run(monkeypatch, conn)
    assert out["resolved"] is False and out["status"] == "open"
    assert not any("status = 'resolved'" in s for s in conn.sql_for("execute"))
    assert sent["notify"] == []
    assert len(sent["push"]) == 1


def test_closed_chat_and_non_member_are_refused_before_the_model(monkeypatch, sent):
    conn = _turn_conn()
    conn.set("fetchrow", "SELECT p.stance", None)
    with pytest.raises(service.SymChatError) as exc:
        _run(monkeypatch, conn)
    assert exc.value.status == 404

    conn = _turn_conn()
    conn.set("fetchrow", "SELECT id, kind, title", {
        "id": CHAT, "kind": "decide", "title": "t", "objective": "", "config": "{}", "status": "cancelled",
    })
    with pytest.raises(service.SymChatError) as exc:
        _run(monkeypatch, conn)
    assert exc.value.status == 409
    assert not any("INSERT INTO mw_sym_chat_messages" in s for s in conn.sql_for("execute"))


def test_turn_cap(monkeypatch, sent):
    conn = _turn_conn()
    conn.set("fetchval", "COUNT(*) FROM mw_sym_chat_messages", service.MAX_TURNS_PER_PARTICIPANT)
    with pytest.raises(service.SymChatError) as exc:
        _run(monkeypatch, conn)
    assert exc.value.status == 429


def test_create_rejects_people_outside_the_company(monkeypatch, sent):
    conn = TxConn(fetch={"FROM clients c JOIN users u": []})
    monkeypatch.setattr(service, "get_connection", lambda *a, **k: conn)
    with pytest.raises(service.SymChatError) as exc:
        asyncio.run(service.create_sym_chat(
            company_id=COMPANY, user_id=ME, kind="decide", title="Lunch", objective="",
            participant_ids=[OTHER], raw_config=DECIDE_CFG,
        ))
    assert exc.value.status == 400 and "company" in exc.value.detail
    assert sent["notify"] == []


def test_create_needs_someone_besides_the_organizer(monkeypatch, sent):
    with pytest.raises(service.SymChatError, match="at least one other"):
        asyncio.run(service.create_sym_chat(
            company_id=COMPANY, user_id=ME, kind="decide", title="Lunch", objective="",
            participant_ids=[ME], raw_config={},
        ))


def test_create_inserts_organizer_first_and_invites_only_the_others(monkeypatch, sent):
    conn = TxConn(
        fetch={
            "FROM clients c JOIN users u": [{"id": OTHER}],
            "SELECT p.user_id, p.responded_at": [],
            "FROM mw_sym_chat_updates": [],
            "FROM mw_sym_chat_messages": [],
        },
        fetchval={
            "SELECT COALESCE(NULLIF": "Dana",
            "INSERT INTO mw_sym_chats": CHAT,
            "COALESCE(MAX(seq)": 1,
        },
        fetchrow={"SELECT s.*": None},
    )
    monkeypatch.setattr(service, "get_connection", lambda *a, **k: conn)
    # get_detail at the end 404s on the fake (no row) — the writes are what we check.
    with pytest.raises(service.SymChatError):
        asyncio.run(service.create_sym_chat(
            company_id=COMPANY, user_id=ME, kind="decide", title="  Team   lunch ", objective="Friday",
            participant_ids=[OTHER, OTHER], raw_config=DECIDE_CFG,
        ))
    members = [a[1] for k, s, a in conn.calls if "INSERT INTO mw_sym_chat_participants" in s]
    assert members == [ME, OTHER]
    assert conn.args_for("INSERT INTO mw_sym_chats")[3] == "Team lunch"
    assert conn.args_for("INSERT INTO mw_sym_chat_updates")[2] == "Dana started this. Waiting on 2 people."
    assert [n["user_id"] for n in sent["notify"]] == [OTHER]
    assert sent["notify"][0]["type"] == "sym_chat_invited"


def test_cancel_is_organizer_only(monkeypatch, sent):
    conn = TxConn(fetchrow={"FOR UPDATE": {"created_by": OTHER, "status": "open", "shape": "{}"}})
    monkeypatch.setattr(service, "get_connection", lambda *a, **k: conn)
    with pytest.raises(service.SymChatError) as exc:
        asyncio.run(service.cancel(CHAT, COMPANY, ME))
    assert exc.value.status == 403


def test_detail_never_exposes_other_participants_stances_or_tunnels(monkeypatch):
    conn = TxConn(
        fetchrow={"SELECT s.*": {
            "id": CHAT, "kind": "decide", "title": "t", "objective": "", "config": "{}",
            "status": "open", "shape": "{}", "resolution": None, "resolved_at": None,
            "created_by": OTHER, "created_at": None, "is_member": 1,
        }},
        fetch={
            "SELECT p.user_id, p.responded_at": [
                {"user_id": OTHER, "responded_at": None, "stance": json.dumps({"vetoes": ["secret"]}), "name": "Org"},
                {"user_id": ME, "responded_at": None, "stance": json.dumps(AGREE), "name": "Dana"},
            ],
            "FROM mw_sym_chat_updates": [],
            "FROM mw_sym_chat_messages": [],
        },
    )
    monkeypatch.setattr(service, "get_connection", lambda *a, **k: conn)
    detail = asyncio.run(service.get_detail(CHAT, COMPANY, ME))
    assert detail["my_stance"] == AGREE
    assert "secret" not in json.dumps(detail)
    assert set(detail["participants"][0]) == {"user_id", "name", "responded", "is_organizer", "is_me"}
    # Tunnel query is scoped to the caller.
    assert conn.args_for("FROM mw_sym_chat_messages") == (CHAT, ME)
