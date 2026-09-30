from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.services.matcha_work.agent_runtime import catalog, consent, conversation, grants
from app.matcha.services.matcha_work.agent_runtime.abilities import reservations
from app.matcha.services.matcha_work.gmail_service import (
    SCOPE_CALENDAR_EVENTS,
    SCOPE_GMAIL_COMPOSE,
    SCOPE_GMAIL_MODIFY,
    SCOPE_GMAIL_READONLY,
)

from .helpers import FakeConn, connection

BASE = frozenset({SCOPE_GMAIL_READONLY, SCOPE_GMAIL_COMPOSE})


async def _fetch(url):
    return {}, set()


def _catalog():
    return catalog.build_catalog(fetch_page=_fetch)


def _keys(situation):
    return [a.key for a in catalog.abilities_for(_catalog(), situation)]


def test_reading_the_web_and_shopping_need_nothing_switched_on():
    assert _keys(catalog.Situation(private=False)) == ["web", "shopping"]
    assert _keys(catalog.Situation(private=True)) == ["web", "shopping"]


def test_a_private_only_ability_is_not_available_in_a_project_chat():
    grants_on = {"email": {}, "calendar": {}}
    shared = catalog.Situation(private=False, grants=grants_on, google_connected=True, granted_scopes=BASE)
    assert _keys(shared) == ["web", "shopping"]
    email = next(a for a in _catalog() if a.key == "email")
    state = catalog.availability(email, shared)
    assert not state.available and "private conversation" in state.reason and state.private_only


def test_email_needs_consent_then_a_connection_then_its_scopes():
    email = next(a for a in _catalog() if a.key == "email")
    no_grant = catalog.availability(email, catalog.Situation(private=True))
    assert not no_grant.available and no_grant.needs_consent
    no_google = catalog.availability(email, catalog.Situation(private=True, grants={"email": {}}))
    assert not no_google.available and no_google.needs_connection and "Connect" in no_google.reason
    thin = catalog.availability(email, catalog.Situation(
        private=True, grants={"email": {}}, google_connected=True,
        granted_scopes=frozenset({SCOPE_GMAIL_READONLY})))
    assert not thin.available and SCOPE_GMAIL_COMPOSE in thin.missing_scopes
    ready = catalog.availability(email, catalog.Situation(
        private=True, grants={"email": {}}, google_connected=True, granted_scopes=BASE))
    # Usable, and it says what reconnecting would add (archive and label).
    assert ready.available and ready.missing_scopes == (SCOPE_GMAIL_MODIFY,) and ready.needs_connection
    full = catalog.availability(email, catalog.Situation(
        private=True, grants={"email": {}}, google_connected=True,
        granted_scopes=BASE | {SCOPE_GMAIL_MODIFY}))
    assert full.available and not full.missing_scopes and full.reason is None


def test_calendar_is_available_without_google_for_reminders():
    calendar = next(a for a in _catalog() if a.key == "calendar")
    state = catalog.availability(calendar, catalog.Situation(private=True, grants={"calendar": {}}))
    assert state.available and state.missing_scopes == (SCOPE_CALENDAR_EVENTS,)
    assert _keys(catalog.Situation(private=True, grants={"calendar": {}})) == ["web", "shopping", "calendar"]


def test_reservations_are_not_offered_without_the_browser_queue(monkeypatch):
    monkeypatch.delenv(reservations.BROWSER_QUEUE_ENV, raising=False)
    situation = catalog.Situation(private=True, grants={"reservations": {"contact": {"name": "A"}}})
    assert "reservations" not in _keys(situation)
    booking = next(a for a in _catalog() if a.key == "reservations")
    assert catalog.availability(booking, situation).reason == "Not set up on this server yet."
    monkeypatch.setenv(reservations.BROWSER_QUEUE_ENV, "agent_browser")
    assert "reservations" in _keys(situation)


def test_every_acting_ability_is_private_only_and_has_a_disclosure():
    for ability in _catalog():
        acts = any(tool.effect == "commit" for tool in ability.tools)
        if acts:
            assert ability.private_only, ability.key
            assert ability.consent_version == consent.current_version(ability.key)
            assert consent.disclosure_view(ability.key)["body"]
        else:
            assert ability.consent_version is None
    assert consent.current_version("web") is None and consent.disclosure_view("web") is None


# ── grants ─────────────────────────────────────────────────────────────────

def test_a_grant_counts_only_at_the_current_consent_version():
    current = consent.current_version("email")
    assert grants.is_active({"enabled": True, "consent_version": current}, "email")
    assert not grants.is_active({"enabled": True, "consent_version": "email-openai-0"}, "email")
    assert not grants.is_active({"enabled": False, "consent_version": current}, "email")
    assert not grants.is_active(None, "email")


@pytest.mark.asyncio
async def test_a_changed_disclosure_disables_until_reconsent():
    conn = FakeConn([("FROM mw_agent_ability_grants", [
        {"ability_key": "email", "enabled": True, "consent_version": "email-openai-0", "settings": "{}"},
        {"ability_key": "calendar", "enabled": True,
         "consent_version": consent.current_version("calendar"), "settings": '{"a": 1}'},
        {"ability_key": "reservations", "enabled": False,
         "consent_version": consent.current_version("reservations"), "settings": None},
    ])])
    assert await grants.load_grants(conn, uuid4()) == {"calendar": {"a": 1}}


@pytest.mark.asyncio
async def test_enabling_email_needs_the_current_consent_version(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(grants, "connection_or_direct", connection(conn))
    for stale in (None, "email-openai-0"):
        with pytest.raises(HTTPException) as exc:
            await grants.enable(uuid4(), uuid4(), "email", consent_version=stale)
        assert exc.value.status_code == 409 and exc.value.detail["code"] == "consent_required"
        assert exc.value.detail["disclosure"]["version"] == consent.current_version("email")
    assert conn.calls == []
    user, company = uuid4(), uuid4()
    out = await grants.enable(user, company, "email", consent_version=consent.current_version("email"),
                              settings={"contact": {"name": "ignored"}})
    assert out == {"key": "email", "enabled": True, "settings": {}}
    insert = conn.ran("INSERT INTO mw_agent_ability_grants")[0]
    assert insert[2] == (user, company, "email", consent.current_version("email"), "{}")


@pytest.mark.asyncio
async def test_reservation_contact_details_are_validated(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(grants, "connection_or_direct", connection(conn))
    version = consent.current_version("reservations")
    bad = [
        {},
        {"contact": {"name": "", "phone": "+1 555 0100"}},
        {"contact": {"name": "Ana Lee"}},
        {"contact": {"name": "Ana Lee", "phone": "call me"}},
        {"contact": {"name": "Ana Lee", "email": "not-an-address"}},
    ]
    for settings in bad:
        with pytest.raises(HTTPException) as exc:
            await grants.enable(uuid4(), uuid4(), "reservations", consent_version=version, settings=settings)
        assert exc.value.status_code == 422
    out = await grants.enable(uuid4(), uuid4(), "reservations", consent_version=version, settings={
        "contact": {"name": " Ana Lee ", "phone": "+1 (555) 010-0100", "email": "ana@example.com"},
        "anything_else": "dropped",
    })
    assert out["settings"] == {"contact": {
        "name": "Ana Lee", "phone": "+1 (555) 010-0100", "email": "ana@example.com"}}


@pytest.mark.asyncio
async def test_disable_and_list(monkeypatch):
    conn = FakeConn([("SELECT ability_key", [
        {"ability_key": "email", "enabled": True, "consent_version": "v", "consented_at": None,
         "settings": '{"x": 1}'},
    ])])
    monkeypatch.setattr(grants, "connection_or_direct", connection(conn))
    assert (await grants.list_rows(uuid4()))["email"]["settings"] == {"x": 1}
    user = uuid4()
    assert await grants.disable(user, "email") == {"key": "email", "enabled": False}
    assert conn.ran("SET enabled = FALSE")[0][2] == (user, "email")


# ── the private conversation ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_is_idempotent_per_user_and_company():
    existing = uuid4()
    conn = FakeConn([("SELECT id FROM channels", existing)])
    assert await conversation.ensure_assistant_channel(conn, user_id=uuid4(), company_id=uuid4()) == existing
    assert conn.ran("INSERT INTO channels") == []


@pytest.mark.asyncio
async def test_ensure_creates_a_private_channel_with_its_owner_as_the_only_member():
    made, user, company = uuid4(), uuid4(), uuid4()
    conn = FakeConn([("SELECT id FROM channels", None), ("INSERT INTO channels", made)])
    assert await conversation.ensure_assistant_channel(conn, user_id=user, company_id=company) == made
    insert = conn.ran("INSERT INTO channels")[0]
    assert "'private', 'assistant'" in insert[1] and insert[2][0] == company and insert[2][4] == user
    member = conn.ran("INSERT INTO channel_members")[0]
    assert member[2] == (made, user) and "'owner'" in member[1]


@pytest.mark.asyncio
async def test_two_first_opens_at_once_end_on_the_same_channel():
    import asyncpg

    winner = uuid4()
    answers = iter([None, winner])
    conn = FakeConn([
        ("SELECT id FROM channels", lambda *_a: next(answers)),
        ("INSERT INTO channels", asyncpg.UniqueViolationError("duplicate")),
    ])
    assert await conversation.ensure_assistant_channel(conn, user_id=uuid4(), company_id=uuid4()) == winner


@pytest.mark.asyncio
async def test_a_second_member_makes_the_conversation_not_private():
    user = uuid4()

    def row(**over):
        base = {"channel_scope": "assistant", "assistant_user_id": user, "members": 1, "mine": 1}
        base.update(over)
        return base

    async def private(answer):
        return await conversation.is_private_conversation(
            FakeConn([("FROM channels ch", answer)]), channel_id=uuid4(), user_id=user)

    assert await private(row())
    assert not await private(row(members=2))
    assert not await private(row(mine=0))
    assert not await private(row(assistant_user_id=uuid4()))
    assert not await private(row(channel_scope="project_discussion"))
    assert not await private(None)
