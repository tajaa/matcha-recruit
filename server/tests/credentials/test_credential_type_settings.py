from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
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
    def __init__(
        self,
        *,
        existing_ids=(),
        configured=False,
        selected_ids=(),
        catalog_type_id=None,
        fail_filter_item_insert=False,
    ):
        self.existing_ids = set(existing_ids)
        self.configured = configured
        self.selected_ids = set(selected_ids)
        self.catalog_type_id = catalog_type_id or uuid4()
        self.fail_filter_item_insert = fail_filter_item_insert
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "company_credential_type_filters" in query:
            return self.configured
        return None

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "SELECT id FROM credential_types" in query:
            return [{"id": value} for value in self.existing_ids]
        if "WITH filter_state AS" in query:
            return [{
                "id": self.catalog_type_id,
                "label": "Food Handler Card",
                "_is_configured": self.configured,
                "_is_selected": self.catalog_type_id in self.selected_ids,
            }]
        if "SELECT ct.*" in query or "SELECT * FROM credential_types" in query:
            return [{"id": uuid4(), "label": "Food Handler Card"}]
        return []

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        if self.fail_filter_item_insert and "INSERT INTO company_credential_type_filter_items" in query:
            raise asyncpg.ForeignKeyViolationError("catalog row disappeared")
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
async def test_update_credential_type_settings_maps_fk_race_to_422(monkeypatch):
    selected_id = uuid4()
    conn = _Connection(
        existing_ids={selected_id},
        fail_filter_item_insert=True,
    )
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_credential_type_settings(
            CredentialTypeVisibilityUpdate(credential_type_ids=[selected_id]),
            user=SimpleNamespace(id=uuid4()),
            company_id=uuid4(),
        )

    assert exc_info.value.status_code == 422
    assert "reload" in exc_info.value.detail


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


@pytest.mark.asyncio
async def test_update_credential_type_settings_rejects_empty_selection(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_credential_type_settings(
            CredentialTypeVisibilityUpdate(credential_type_ids=[]),
            user=SimpleNamespace(id=uuid4()),
            company_id=uuid4(),
        )

    assert exc_info.value.status_code == 422
    assert "at least one" in exc_info.value.detail
    assert not conn.calls


@pytest.mark.asyncio
async def test_get_credential_type_settings_reports_company_selection(monkeypatch):
    company_id = uuid4()
    selected_id = uuid4()
    conn = _Connection(
        configured=True,
        selected_ids={selected_id},
        catalog_type_id=selected_id,
    )
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    result = await routes.get_credential_type_settings(
        user=SimpleNamespace(id=uuid4()), company_id=company_id
    )

    assert result["is_configured"] is True
    assert result["manageable"] is True
    assert result["selected_type_ids"] == [selected_id]
    assert result["credential_types"][0]["label"] == "Food Handler Card"
    assert "_is_configured" not in result["credential_types"][0]
    assert len(conn.calls) == 1


@pytest.mark.asyncio
async def test_get_credential_type_settings_unscoped_admin_is_read_only(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))

    result = await routes.get_credential_type_settings(
        user=SimpleNamespace(id=uuid4()), company_id=None
    )

    assert result["manageable"] is False
    assert result["is_configured"] is False
    assert result["selected_type_ids"] == []
    # SQL NULL equality matches no tenant row, so the single combined query
    # cannot read another company's selection.
    assert len(conn.calls) == 1
    assert conn.calls[0][2] == (None,)


@pytest.mark.asyncio
async def test_admin_without_company_gets_no_tenant_scope():
    admin = SimpleNamespace(id=uuid4(), role="admin")

    assert await routes.credential_settings_scope(company_id=None, user=admin) is None


@pytest.mark.asyncio
async def test_scoped_admin_resolves_the_named_company(monkeypatch):
    company_id = uuid4()
    admin = SimpleNamespace(id=uuid4(), role="admin")
    seen = {}

    async def _resolve(user, requested_company_id=None):
        seen["requested"] = requested_company_id
        return {"company_id": requested_company_id}

    monkeypatch.setattr(routes, "resolve_accessible_company_scope", _resolve)

    resolved = await routes.credential_settings_scope(company_id=company_id, user=admin)

    assert resolved == company_id
    assert seen["requested"] == company_id


@pytest.mark.asyncio
async def test_write_scope_rejects_an_unscoped_caller():
    with pytest.raises(HTTPException) as exc_info:
        await routes.credential_settings_company_id(company_id=None)

    assert exc_info.value.status_code == 403
