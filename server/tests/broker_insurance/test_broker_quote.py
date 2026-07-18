"""Broker-placed quoting — payload synthesis + guards. DB-free (fake conn)."""

import asyncio
from uuid import uuid4

import pytest

from app.matcha.services import coterie_service as cs
from app.matcha.models.insurance import BrokerQuoteRequest


class _FakeConn:
    """Minimal async conn stub — one fetchrow, returns the seeded row."""
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, _query, *_args):
        return self._row


def test_external_payload_synthesized_from_snapshot():
    row = {"name": "Off Platform Co", "industry": "Retail", "headcount": 8, "primary_state": "TX"}
    req = BrokerQuoteRequest(line="bop")
    payload = asyncio.run(
        cs.build_quote_request_external(_FakeConn(row), uuid4(), req, broker_id=uuid4())
    )
    assert payload["product"] == "BOP"
    assert payload["business"]["legal_name"] == "Off Platform Co"  # name -> legal_name
    assert payload["business"]["state"] == "TX"                    # primary_state -> state
    assert payload["exposure"]["headcount"] == 8
    # external snapshots carry no payroll — stays None, mock quote fills a default
    assert payload["exposure"]["annual_payroll"] is None


def test_external_override_wins_and_unknown_client_raises():
    row = {"name": "Solo", "industry": None, "headcount": None, "primary_state": "CA"}
    req = BrokerQuoteRequest(line="wc", state="NY", headcount=25)
    payload = asyncio.run(
        cs.build_quote_request_external(_FakeConn(row), uuid4(), req, broker_id=uuid4())
    )
    assert payload["business"]["state"] == "NY"   # caller override beats snapshot
    assert payload["exposure"]["headcount"] == 25

    # a missing external client surfaces a typed error, never a raw None deref
    with pytest.raises(cs.CoterieError):
        asyncio.run(
            cs.build_quote_request_external(_FakeConn(None), uuid4(), req, broker_id=uuid4())
        )


def test_create_broker_quote_requires_exactly_one_subject():
    req = BrokerQuoteRequest(line="gl")
    # both subjects set -> guard rejects before any DB work (conn unused)
    with pytest.raises(cs.CoterieError):
        asyncio.run(cs.create_broker_quote(
            None, broker_id=uuid4(), req=req, created_by=None,
            company_id=uuid4(), external_client_id=uuid4()))
    # neither set -> also rejected
    with pytest.raises(cs.CoterieError):
        asyncio.run(cs.create_broker_quote(
            None, broker_id=uuid4(), req=req, created_by=None))


def test_fnol_ref_is_deterministic_in_mock(monkeypatch):
    monkeypatch.setattr(cs, "COTERIE_MODE", "mock")
    ref = cs.file_fnol("11111111-2222-3333-4444-555555555555", "IR-2026-014")
    assert ref == cs.file_fnol("11111111-2222-3333-4444-555555555555", "IR-2026-014")
    assert ref.startswith("FNOL-MOCK-")


def test_mock_loss_runs_shape():
    runs = cs.mock_loss_runs()
    assert len(runs) >= 1
    assert {"policy_year", "claims", "incurred_cents", "paid_cents", "open"} <= set(runs[0])
