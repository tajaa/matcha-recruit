import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.models.auth import BusinessRegister
from app.core.routes import auth as auth_routes


class _FakeConnection:
    def __init__(self, table_exists: bool):
        self.table_exists = table_exists
        self.executed: list[tuple[str, tuple]] = []

    async def fetchval(self, query, *args):
        if "to_regclass" in query:
            return self.table_exists
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "INSERT 0 1"


def test_business_register_requires_headcount():
    with pytest.raises(ValidationError):
        BusinessRegister(
            company_name="Acme Corp",
            industry="Technology",
            company_size="11-50",
            email="owner@example.com",
            password="supersecret",
            name="Owner User",
        )


def test_business_register_rejects_non_positive_headcount():
    with pytest.raises(ValidationError):
        BusinessRegister(
            company_name="Acme Corp",
            industry="Technology",
            company_size="11-50",
            headcount=0,
            email="owner@example.com",
            password="supersecret",
            name="Owner User",
        )


def test_upsert_business_headcount_profile_persists_headcount_when_table_exists():
    conn = _FakeConnection(table_exists=True)

    asyncio.run(
        auth_routes._upsert_business_headcount_profile(
            conn,
            company_id=uuid4(),
            company_name="Acme Corp",
            owner_name="Jane Founder",
            headcount=42,
            updated_by=uuid4(),
        )
    )

    assert len(conn.executed) == 1
    query, args = conn.executed[0]
    assert "INSERT INTO company_handbook_profiles" in query
    assert args[3] == 42


def test_upsert_business_headcount_profile_skips_when_table_missing():
    conn = _FakeConnection(table_exists=False)

    asyncio.run(
        auth_routes._upsert_business_headcount_profile(
            conn,
            company_id=uuid4(),
            company_name="Acme Corp",
            owner_name="Jane Founder",
            headcount=42,
            updated_by=uuid4(),
        )
    )

    assert conn.executed == []
