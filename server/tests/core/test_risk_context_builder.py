"""Matcha-work risk mode context builds from the relocated insurance risk_index."""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from app.matcha.services.matcha_work import matcha_work_mode_contexts as ctx


def test_risk_context_is_empty_when_there_is_nothing_to_say(monkeypatch):
    seen = {}

    async def _index(conn, company_id):
        seen["index"] = company_id
        return {"index": None}

    async def _review(conn, company_id):
        seen["review"] = company_id
        return {"lines": [], "contracts": []}

    @asynccontextmanager
    async def _conn():
        yield object()

    monkeypatch.setattr("app.matcha.services.insurance.risk_index.compute_risk_index", _index)
    monkeypatch.setattr("app.matcha.services.insurance.limit_adequacy.build_review", _review)
    monkeypatch.setattr(ctx, "get_connection", _conn)

    company_id = uuid4()
    assert asyncio.run(ctx._build_risk_context_uncached(company_id)) == ""
    assert seen == {"index": company_id, "review": company_id}
