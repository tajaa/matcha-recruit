import asyncio
import inspect
from datetime import date, datetime
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

from app.core.services import credential_template_service
from app.core.services.credential_template_service import (
    ResolvedCredentialRequirement,
    assign_credential_requirements_to_employee,
)
from app.matcha.routes.employees import credentials as employee_credentials
from app.matcha.routes.employee_portal.credential_documents import _VALID_DOC_TYPES


class ExistingRequirementConn:
    def __init__(self):
        self.executed: list[str] = []

    async def fetchval(self, query, *args):
        assert "employee_credential_requirements" in query
        return uuid4()

    async def execute(self, query, *args):
        self.executed.append(query)


def test_employee_moving_into_credential_scope_reuses_existing_requirement():
    """A role/location update must not create an orphan onboarding task."""
    conn = ExistingRequirementConn()
    requirement = ResolvedCredentialRequirement(
        credential_type_key="food_handler_card",
        credential_type_label="Food Handler Card",
        credential_type_id=uuid4(),
        template_id=uuid4(),
        notes="Required for food service staff",
    )

    assigned = asyncio.run(assign_credential_requirements_to_employee(
        conn, uuid4(), uuid4(), [requirement],
    ))

    assert assigned == 1
    assert len(conn.executed) == 1
    assert "UPDATE employee_credential_requirements" in conn.executed[0]
    assert "employee_onboarding_tasks" not in conn.executed[0]


def test_employee_portal_accepts_food_handler_documents():
    assert "food_handler_card" in _VALID_DOC_TYPES


def test_empty_luna_role_classification_degrades_without_error(monkeypatch, caplog):
    monkeypatch.setattr(
        credential_template_service,
        "_luna_credentials",
        lambda: ("test-key", "gpt-5.6-luna"),
    )
    monkeypatch.setattr(
        credential_template_service,
        "_generate_luna_text",
        mock.AsyncMock(return_value=""),
    )

    with caplog.at_level("WARNING", logger=credential_template_service.__name__):
        role = asyncio.run(credential_template_service._classify_role_via_luna(
            None,
            "Barista",
            [{"key": "non_clinical", "label": "Non-clinical"}],
        ))

    assert role is None
    assert "returned no role classification" in caplog.text
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


class UploadedBlockingRequirementConn:
    def __init__(self):
        self.query = ""
        self.args = ()
        self.requirement_id = uuid4()

    async def fetchrow(self, query, *args):
        self.query = query
        self.args = args
        return {"id": self.requirement_id, "has_expiration": True}


def test_food_handler_upload_materializes_company_wide_blocking_requirement():
    conn = UploadedBlockingRequirementConn()
    company_id, employee_id = uuid4(), uuid4()

    requirement = asyncio.run(
        credential_template_service.materialize_uploaded_schedule_blocking_requirement(
            conn,
            company_id=company_id,
            employee_id=employee_id,
            credential_type_key="food_handler_card",
        )
    )

    assert requirement["id"] == conn.requirement_id
    assert conn.args == (employee_id, company_id, "food_handler_card")
    assert "schedule_blocking" in conn.query
    assert "applies_company_wide = true" in conn.query
    assert "ON CONFLICT (employee_id, credential_type_id) DO UPDATE" in conn.query


class OrphanDocumentConn:
    async def fetchrow(self, *_args):
        return None

    async def fetch(self, *_args):
        return []


def test_orphan_food_handler_document_gets_a_scheduler_requirement():
    expected = {"id": uuid4(), "has_expiration": True}
    materialize = mock.AsyncMock(return_value=expected)
    company_id, employee_id = uuid4(), uuid4()

    with mock.patch.object(
        employee_credentials,
        "materialize_uploaded_schedule_blocking_requirement",
        materialize,
    ):
        requirement = asyncio.run(employee_credentials._requirement_for_document_type(
            OrphanDocumentConn(),
            company_id=company_id,
            employee_id=employee_id,
            document_type="food_handler_card",
        ))

    assert requirement == expected
    materialize.assert_awaited_once_with(
        mock.ANY,
        company_id=company_id,
        employee_id=employee_id,
        credential_type_key="food_handler_card",
    )


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class ApproveDocumentConn:
    def __init__(self, *, document_id, employee_id, company_id):
        self.document = {
            "id": document_id,
            "employee_id": employee_id,
            "company_id": company_id,
            "document_type": "food_handler_card",
            "review_status": "pending",
            "extracted_data": None,
        }
        self.executed: list[tuple[str, tuple]] = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *_args):
        assert "credential_documents" in query
        return self.document

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


def test_food_handler_approval_persists_expiry_on_document_and_requirement():
    company_id, employee_id, document_id, requirement_id, user_id = (uuid4() for _ in range(5))
    expiry = date(2025, 1, 10)
    conn = ApproveDocumentConn(
        document_id=document_id,
        employee_id=employee_id,
        company_id=company_id,
    )

    with (
        mock.patch.object(
            employee_credentials, "get_client_company_id",
            mock.AsyncMock(return_value=company_id),
        ),
        mock.patch.object(
            employee_credentials, "get_connection",
            return_value=_ConnectionContext(conn),
        ),
        mock.patch.object(
            employee_credentials, "_requirement_for_document_type",
            mock.AsyncMock(return_value={"id": requirement_id, "has_expiration": True}),
        ),
    ):
        result = asyncio.run(employee_credentials.approve_credential_document(
            employee_id=employee_id,
            document_id=document_id,
            body=employee_credentials.ApproveRequest(expiration_date=expiry),
            current_user=SimpleNamespace(id=user_id),
        ))

    document_update = next(item for item in conn.executed if "UPDATE credential_documents" in item[0])
    requirement_update = next(item for item in conn.executed if "UPDATE employee_credential_requirements" in item[0])
    assert "expires_at = $3" in document_update[0]
    assert document_update[1][2] == expiry
    assert requirement_update[1][2] == expiry
    assert result["expiration_date"] == "2025-01-10"


def test_document_removal_preserves_last_confirmed_expiry_for_worker_enforcement():
    route_source = inspect.getsource(employee_credentials.delete_credential_document)
    requirement_update = route_source.split("UPDATE employee_credential_requirements", 1)[1]
    assert "expires_at = NULL" not in requirement_update


class ListCredentialDocumentsConn:
    """Only the tenant check runs here; the projection itself is patched.

    The `is_current` SQL is covered against a real database in
    `test_credential_current_document_sql.py` — a fake connection cannot
    execute it, and asserting on the query text tests the formatting, not the
    behaviour.
    """

    def __init__(self):
        self.employee_lookup = ""

    def transaction(self):
        return _Transaction()

    async def fetchval(self, query, *_args):
        self.employee_lookup = query
        return uuid4()


def _credential_document_row(*, current: bool, filename: str, document_id=None):
    now = datetime(2026, 9, 3, 8, 0, 0)
    return {
        "id": document_id or uuid4(),
        "company_id": uuid4(),
        "employee_id": uuid4(),
        "document_type": "medical_license",
        "filename": filename,
        "file_path": f"private/{filename}",
        "mime_type": "application/pdf",
        "file_size": 100,
        "extracted_data": {"fields": {"license_number": {"value": "ABC123"}}},
        "extraction_status": "extracted",
        "review_status": "approved",
        "reviewed_by": None,
        "reviewed_at": now,
        "review_notes": None,
        "uploaded_by": None,
        "uploaded_via": "admin",
        "created_at": now,
        "updated_at": now,
        "expires_at": date(2027, 9, 3),
        "is_current": current,
    }


def test_credential_document_list_reports_the_resolved_current_document():
    """The list response carries `is_current` straight from the shared projection."""
    company_id, employee_id = uuid4(), uuid4()
    conn = ListCredentialDocumentsConn()
    fetch_documents = mock.AsyncMock(return_value=[
        _credential_document_row(current=True, filename="replacement.pdf"),
        _credential_document_row(current=False, filename="original.pdf"),
    ])

    with (
        mock.patch.object(
            employee_credentials, "get_client_company_id",
            mock.AsyncMock(return_value=company_id),
        ),
        mock.patch.object(
            employee_credentials, "get_connection",
            return_value=_ConnectionContext(conn),
        ),
        mock.patch.object(employee_credentials, "_fetch_credential_documents", fetch_documents),
    ):
        documents = asyncio.run(employee_credentials.list_credential_documents(
            employee_id=employee_id,
            current_user=SimpleNamespace(id=uuid4()),
        ))

    assert [d["is_current"] for d in documents] == [True, False]
    assert [d["filename"] for d in documents] == ["replacement.pdf", "original.pdf"]
    # Scoped to the caller's tenant, and the whole employee (not one document).
    assert fetch_documents.await_args.kwargs == {
        "employee_id": employee_id, "company_id": company_id,
    }


class ReclassifyDocumentConn:
    def __init__(self, *, document_id, employee_id, company_id):
        self.document = {
            "id": document_id,
            "employee_id": employee_id,
            "company_id": company_id,
            "document_type": "other",
            "filename": "license.pdf",
            "file_path": "private/license.pdf",
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
            "created_at": datetime(2026, 9, 3, 8, 0, 0),
            "updated_at": datetime(2026, 9, 3, 8, 0, 0),
            "expires_at": None,
        }
        self.executed: list[str] = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *_args):
        return self.document

    async def execute(self, query, *_args):
        self.executed.append(query)
        return "UPDATE 1"


def test_reclassification_response_reports_current_from_the_projection():
    """`UPDATE ... RETURNING *` has no `is_current` column.

    Reclassifying re-points the requirement, so the response has to be re-read
    through the projection instead of falling back to the model default, or a
    caller that trusts the response renders a current credential as history.
    """
    company_id, employee_id, document_id, requirement_id = (uuid4() for _ in range(4))
    conn = ReclassifyDocumentConn(
        document_id=document_id, employee_id=employee_id, company_id=company_id,
    )
    projected = _credential_document_row(
        current=True, filename="license.pdf", document_id=document_id,
    )

    with (
        mock.patch.object(
            employee_credentials, "get_client_company_id",
            mock.AsyncMock(return_value=company_id),
        ),
        mock.patch.object(
            employee_credentials, "get_connection",
            return_value=_ConnectionContext(conn),
        ),
        mock.patch.object(
            employee_credentials, "_requirement_for_document_type",
            mock.AsyncMock(return_value={"id": requirement_id, "has_expiration": False}),
        ),
        mock.patch.object(
            employee_credentials, "_fetch_credential_documents",
            mock.AsyncMock(return_value=[projected]),
        ),
    ):
        response = asyncio.run(employee_credentials.reclassify_credential_document(
            employee_id=employee_id,
            document_id=document_id,
            body=employee_credentials.ReclassifyCredentialDocumentRequest(
                document_type="medical_license",
            ),
            current_user=SimpleNamespace(id=uuid4()),
        ))

    assert response["is_current"] is True
