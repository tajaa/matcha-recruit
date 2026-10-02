"""The HR Cases page's setup check: would a new incident open a case, and who
hears about it. No DB.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_readiness.py -q
"""
from uuid import uuid4

import pytest

from app.matcha.services.hr_cases import readiness


def test_ready_only_when_every_precondition_holds():
    ok = readiness.shape(threshold=0.6, handbook_sources=12, incidents_enabled=True, notified=["Ana"])
    assert ok == {
        "threshold": 0.6, "handbook_sources": 12, "incidents_enabled": True,
        "notified": ["Ana"], "ready": True,
    }
    assert not readiness.shape(threshold=0.6, handbook_sources=0, incidents_enabled=True, notified=["Ana"])["ready"]
    assert not readiness.shape(threshold=0.6, handbook_sources=12, incidents_enabled=False, notified=["Ana"])["ready"]
    assert not readiness.shape(threshold=0.6, handbook_sources=12, incidents_enabled=True, notified=[])["ready"]


def test_a_source_that_could_not_be_read_is_never_ready():
    unknown = readiness.shape(threshold=0.6, handbook_sources=None, incidents_enabled=None, notified=None)
    assert unknown["ready"] is False
    assert unknown["handbook_sources"] is None and unknown["incidents_enabled"] is None


@pytest.mark.asyncio
async def test_build_degrades_each_source_independently(monkeypatch):
    from app.core import feature_flags
    from app.matcha.services.discipline import discipline_policy_check
    from app.matcha.services.hr_cases import notifications

    async def corpus(conn, company_id):
        return {"index": {"handbook:1": {}, "policy:2": {}}}

    async def features(company_id, *, conn=None):
        raise RuntimeError("db down")

    async def recipients(conn, company_id):
        return [{"user_id": uuid4(), "name": "Ana"}]

    monkeypatch.setattr(discipline_policy_check, "build_check_corpus", corpus)
    monkeypatch.setattr(feature_flags, "get_company_features", features)
    monkeypatch.setattr(notifications, "hr_recipients", recipients)

    out = await readiness.build(object(), company_id=uuid4(), threshold=0.6)
    assert out["handbook_sources"] == 2
    assert out["incidents_enabled"] is None
    assert out["notified"] == ["Ana"]
    assert out["ready"] is False


@pytest.mark.asyncio
async def test_build_reports_no_handbook_when_the_corpus_is_missing(monkeypatch):
    from app.core import feature_flags
    from app.matcha.services.discipline import discipline_policy_check
    from app.matcha.services.hr_cases import notifications

    async def corpus(conn, company_id):
        return None

    async def features(company_id, *, conn=None):
        return {"incidents": True}

    async def recipients(conn, company_id):
        return []

    monkeypatch.setattr(discipline_policy_check, "build_check_corpus", corpus)
    monkeypatch.setattr(feature_flags, "get_company_features", features)
    monkeypatch.setattr(notifications, "hr_recipients", recipients)

    out = await readiness.build(object(), company_id=uuid4(), threshold=0.75)
    assert out["handbook_sources"] is None and out["notified"] == [] and out["ready"] is False
    assert out["threshold"] == 0.75
