"""A company's hidden credential types cannot be attached to a job."""
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import job_credential_requirements as svc


class _Connection:
    """Minimal asyncpg stand-in for the queries this write path runs."""

    def __init__(self, *, existing_ids=(), hidden_ids=(), inaccessible_ids=()):
        self.existing_ids = list(existing_ids)
        self.hidden_ids = set(hidden_ids)
        self.inaccessible_ids = set(inaccessible_ids)
        self.executed = []

    async def fetch(self, query, *args):
        if "SELECT id FROM credential_types" in query:
            return [{"id": value} for value in args[0] if value not in self.inaccessible_ids]
        if "FROM schedule_job_credential_requirements" in query and "FOR UPDATE" in query:
            return [{"credential_type_id": value} for value in self.existing_ids]
        if "company_credential_type_filter_items" in query:
            requested = args[1]
            return [{"id": value} for value in requested if value in self.hidden_ids]
        return []

    async def execute(self, query, *args):
        self.executed.append(query)
        return "OK"


@pytest.mark.asyncio
async def test_hidden_credential_type_cannot_be_added(monkeypatch):
    hidden_id = uuid4()
    conn = _Connection(hidden_ids={hidden_id})

    with pytest.raises(ValueError) as exc_info:
        await svc.replace_job_credential_requirements(
            conn, company_id=uuid4(), job_id=uuid4(),
            requirements=[{"credential_type_id": hidden_id, "is_required": True}],
            actor_user_id=uuid4(),
        )

    assert "not available" in str(exc_info.value)
    assert not conn.executed


@pytest.mark.asyncio
async def test_hidden_credential_type_already_configured_is_kept(monkeypatch):
    hidden_id = uuid4()
    conn = _Connection(existing_ids=[hidden_id], hidden_ids={hidden_id})
    monkeypatch.setattr(svc, "materialize_job_requirements", _noop_int)
    monkeypatch.setattr(svc, "fetch_job_credential_requirements", _noop_list)

    result = await svc.replace_job_credential_requirements(
        conn, company_id=uuid4(), job_id=uuid4(),
        requirements=[{"credential_type_id": hidden_id, "is_required": False}],
        actor_user_id=uuid4(),
    )

    assert result == []
    assert any("INSERT INTO schedule_job_credential_requirements" in query for query in conn.executed)


@pytest.mark.asyncio
async def test_other_tenant_custom_type_cannot_be_added():
    inaccessible_id = uuid4()
    conn = _Connection(inaccessible_ids={inaccessible_id})

    with pytest.raises(ValueError) as exc_info:
        await svc.replace_job_credential_requirements(
            conn, company_id=uuid4(), job_id=uuid4(),
            requirements=[{"credential_type_id": inaccessible_id, "is_required": True}],
            actor_user_id=uuid4(),
        )

    assert "do not exist" in str(exc_info.value)
    assert not conn.executed


async def _noop_int(*args, **kwargs):
    return 0


async def _noop_list(*args, **kwargs):
    return []
