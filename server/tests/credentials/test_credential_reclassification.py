from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.employees import credentials as routes


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self, *, company_id, employee_id, document_id):
        self.document = {
            "id": document_id,
            "company_id": company_id,
            "employee_id": employee_id,
            "document_type": "other",
            "filename": "forklift.pdf",
            "file_path": "private/forklift.pdf",
            "mime_type": "application/pdf",
            "file_size": 100,
            "extracted_data": None,
            "extraction_status": "extracted",
            "review_status": "approved",
            "reviewed_by": None,
            "reviewed_at": None,
            "review_notes": None,
            "uploaded_by": None,
            "uploaded_via": "admin",
            "created_at": None,
            "updated_at": None,
            "expires_at": None,
        }
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "SELECT * FROM credential_documents" in query:
            return self.document
        if "UPDATE credential_documents" in query:
            self.document = {
                **self.document,
                "document_type": args[0],
                "expires_at": args[1],
            }
            return self.document
        raise AssertionError(f"unexpected fetchrow: {query}")

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "OK"


def _connection_context(conn):
    @asynccontextmanager
    async def _get_connection():
        yield conn

    return _get_connection


async def _company_id(_user):
    return _company_id.value


@pytest.mark.asyncio
async def test_reclassify_accepts_employee_custom_requirement_and_tracks_expiration(monkeypatch):
    company_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    requirement_id = uuid4()
    expiration = date(2027, 6, 30)
    conn = _Connection(
        company_id=company_id,
        employee_id=employee_id,
        document_id=document_id,
    )
    _company_id.value = company_id

    async def _requirement(*_args, **_kwargs):
        return {"id": requirement_id, "has_expiration": True}

    monkeypatch.setattr(routes, "get_client_company_id", _company_id)
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))
    monkeypatch.setattr(routes, "_requirement_for_document_type", _requirement)

    result = await routes.reclassify_credential_document(
        employee_id,
        document_id,
        routes.ReclassifyCredentialDocumentRequest(
            document_type="custom_forklift",
            expiration_date=expiration,
        ),
        SimpleNamespace(id=uuid4()),
    )

    assert result["document_type"] == "custom_forklift"
    assert result["expires_at"] == expiration.isoformat()
    requirement_update = next(
        call for call in conn.calls
        if call[0] == "execute" and "SET status='verified'" in call[1]
    )
    assert requirement_update[2][2:] == (expiration, requirement_id)


@pytest.mark.asyncio
async def test_reclassify_rejects_custom_type_without_employee_requirement(monkeypatch):
    company_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    conn = _Connection(
        company_id=company_id,
        employee_id=employee_id,
        document_id=document_id,
    )
    _company_id.value = company_id

    async def _no_requirement(*_args, **_kwargs):
        return None

    monkeypatch.setattr(routes, "get_client_company_id", _company_id)
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))
    monkeypatch.setattr(routes, "_requirement_for_document_type", _no_requirement)

    with pytest.raises(HTTPException) as exc_info:
        await routes.reclassify_credential_document(
            employee_id,
            document_id,
            routes.ReclassifyCredentialDocumentRequest(
                document_type="custom_other_tenant",
            ),
            SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.status_code == 400
    assert not [call for call in conn.calls if "UPDATE credential_documents" in call[1]]


@pytest.mark.asyncio
async def test_reclassify_requires_expiration_for_approved_custom_type(monkeypatch):
    company_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    conn = _Connection(
        company_id=company_id,
        employee_id=employee_id,
        document_id=document_id,
    )
    _company_id.value = company_id

    async def _requirement(*_args, **_kwargs):
        return {"id": uuid4(), "has_expiration": True}

    monkeypatch.setattr(routes, "get_client_company_id", _company_id)
    monkeypatch.setattr(routes, "get_connection", _connection_context(conn))
    monkeypatch.setattr(routes, "_requirement_for_document_type", _requirement)

    with pytest.raises(HTTPException) as exc_info:
        await routes.reclassify_credential_document(
            employee_id,
            document_id,
            routes.ReclassifyCredentialDocumentRequest(
                document_type="custom_forklift",
            ),
            SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.status_code == 422
    assert "expiration" in exc_info.value.detail
    assert not [call for call in conn.calls if "UPDATE credential_documents" in call[1]]
