from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.models.credential_templates import CredentialTypeVisibilityUpdate
from app.core.routes.documents import credential_templates as routes


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self, *, existing_ids=()):
        self.existing_ids = set(existing_ids)
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "SELECT id FROM credential_types" in query:
            return [{"id": value} for value in self.existing_ids]
        if "SELECT ct.*" in query:
            return [{"id": uuid4(), "label": "Food Handler Card"}]
        return []

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "OK"


def _connection_context(conn):
    @asynccontextmanager
    async def _get_connection():
        yield conn

    return _get_connection


@pytest.mark.asyncio
async def test_list_credential_types_applies_company_filter(monkeypatch):
    company_id = uuid4()
    conn = _Connection()
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    result = await routes.list_credential_types(
        user=SimpleNamespace(id=uuid4()), company_id=company_id
    )

    assert result[0]["label"] == "Food Handler Card"
    query_call = conn.calls[0]
    assert "company_credential_type_filters" in query_call[1]
    assert "company_credential_type_filter_items" in query_call[1]
    assert query_call[2] == (company_id,)


@pytest.mark.asyncio
async def test_update_credential_type_settings_replaces_allowlist(monkeypatch):
    company_id = uuid4()
    user_id = uuid4()
    selected_id = uuid4()
    conn = _Connection(existing_ids={selected_id})
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    result = await routes.update_credential_type_settings(
        CredentialTypeVisibilityUpdate(credential_type_ids=[selected_id, selected_id]),
        user=SimpleNamespace(id=user_id),
        company_id=company_id,
    )

    assert result == {"ok": True, "selected_count": 1}
    writes = [call for call in conn.calls if call[0] == "execute"]
    assert "INSERT INTO company_credential_type_filters" in writes[0][1]
    assert writes[0][2] == (company_id, user_id)
    assert "DELETE FROM company_credential_type_filter_items" in writes[1][1]
    assert "UNNEST" in writes[2][1]
    assert writes[2][2] == (company_id, [selected_id])


@pytest.mark.asyncio
async def test_update_credential_type_settings_rejects_unknown_type(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_credential_type_settings(
            CredentialTypeVisibilityUpdate(credential_type_ids=[uuid4()]),
            user=SimpleNamespace(id=uuid4()),
            company_id=uuid4(),
        )

    assert exc_info.value.status_code == 422
    assert not [call for call in conn.calls if call[0] == "execute"]


@pytest.mark.asyncio
async def test_reset_credential_type_settings_restores_default(monkeypatch):
    company_id = uuid4()
    conn = _Connection()
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    result = await routes.reset_credential_type_settings(
        user=SimpleNamespace(id=uuid4()), company_id=company_id
    )

    assert result == {"ok": True}
    assert conn.calls[0][0] == "execute"
    assert "DELETE FROM company_credential_type_filters" in conn.calls[0][1]
    assert conn.calls[0][2] == (company_id,)


def test_company_is_required_for_credential_settings():
    with pytest.raises(HTTPException) as exc_info:
        routes._credential_settings_company_id(None)

    assert exc_info.value.status_code == 403
