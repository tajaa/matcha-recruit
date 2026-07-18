"""FNOL dedupe — one incident is one loss. DB-free (fake conn).

Covers the three ways `tenant_fnol` must refuse to file twice, plus the carrier
error mapping. The route's real guard is the partial unique index
(`uq_insurance_claims_fnol_incident`, migration brokerquote03); these tests
drive the branches that index feeds, not the index itself.
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.broker import insurance as bi
from app.matcha.services import coterie_service as cs
from app.matcha.models.insurance import FnolRequest


INCIDENT = {"id": uuid4(), "incident_number": "IR-2026-014"}

# What the INSERT ... RETURNING * hands back, shaped for _serialize_claim.
INSERTED = {
    "id": uuid4(), "kind": "fnol", "carrier": "coterie",
    "claim_ref": "FNOL-MOCK-IR-2026-014", "status": "open",
    "incident_id": INCIDENT["id"], "amount_cents": None, "created_at": None,
}


class _FakeConn:
    """Scripts the three reads tenant_fnol makes: the incident lookup
    (fetchrow), the prior-FNOL pre-check (fetchval), and the insert (fetchrow).
    `insert_row=None` simulates ON CONFLICT DO NOTHING losing the race."""

    def __init__(self, *, prior_ref=None, insert_row=..., incident=INCIDENT):
        self.prior_ref = prior_ref
        self.insert_row = insert_row
        self.incident = incident
        self.queries = []

    async def fetchrow(self, query, *_args):
        self.queries.append(query)
        if "FROM ir_incidents" in query:
            return self.incident
        return None if self.insert_row is ... else self.insert_row

    async def fetchval(self, query, *_args):
        self.queries.append(query)
        return self.prior_ref


def _run(conn, monkeypatch, *, mode="mock"):
    monkeypatch.setattr(cs, "COTERIE_MODE", mode)
    monkeypatch.setattr(bi.coterie_service, "has_capability", lambda _n: True)

    @asynccontextmanager
    async def _fake_get_connection():
        yield conn

    monkeypatch.setattr(bi, "get_connection", _fake_get_connection)
    monkeypatch.setattr(bi, "_assert_broker_owns_company", _noop)
    monkeypatch.setattr(bi, "_broker_id", _broker_id)
    return asyncio.run(bi.tenant_fnol(
        uuid4(), FnolRequest(incident_id=INCIDENT["id"]), current_user=_User()))


async def _noop(*_a, **_kw):
    return None


async def _broker_id(*_a, **_kw):
    return uuid4()


class _User:
    id = uuid4()


def test_second_fnol_is_refused_before_the_carrier_is_called(monkeypatch):
    """The pre-check must fire BEFORE file_fnol — filing first and rejecting
    after would open a duplicate claim at the carrier that no row references."""
    called = []
    monkeypatch.setattr(bi.coterie_service, "file_fnol",
                        lambda *a, **k: called.append(a) or "FNOL-MOCK-X")
    conn = _FakeConn(prior_ref="FNOL-MOCK-IR-2026-014")

    with pytest.raises(HTTPException) as exc:
        _run(conn, monkeypatch)

    assert exc.value.status_code == 409
    assert "FNOL-MOCK-IR-2026-014" in exc.value.detail
    assert called == []                      # carrier never touched
    assert not any("INSERT INTO" in q for q in conn.queries)


def test_pre_check_is_company_scoped(monkeypatch):
    """The dedupe read filters on company_id, not incident_id alone — tenant
    isolation holds even if FNOL uniqueness scope is ever widened."""
    monkeypatch.setattr(bi.coterie_service, "file_fnol", lambda *a, **k: "FNOL-MOCK-X")
    conn = _FakeConn(prior_ref=None, insert_row=INSERTED)
    _run(conn, monkeypatch)

    pre_check = next(q for q in conn.queries if "FROM insurance_claims" in q)
    assert "company_id" in pre_check
    assert "kind = 'fnol'" in pre_check


def test_lost_race_returns_409_with_the_deterministic_ref(monkeypatch):
    """ON CONFLICT DO NOTHING returns no row when a concurrent post won. The
    ref is derived from the incident, so the winner's ref is the one computed
    here — no second lookup needed."""
    conn = _FakeConn(prior_ref=None, insert_row=None)

    with pytest.raises(HTTPException) as exc:
        _run(conn, monkeypatch)

    assert exc.value.status_code == 409
    assert cs.file_fnol(str(INCIDENT["id"]), INCIDENT["incident_number"]) in exc.value.detail


def test_live_carrier_error_is_mapped_not_a_raw_500(monkeypatch):
    """file_fnol raises CoterieError in live mode; the handler must route it
    through _raise_coterie like every other carrier call in this router."""
    conn = _FakeConn(prior_ref=None)

    with pytest.raises(HTTPException) as exc:
        _run(conn, monkeypatch, mode="live")

    assert exc.value.status_code == 502
    assert "fnol_not_available_live" in exc.value.detail
