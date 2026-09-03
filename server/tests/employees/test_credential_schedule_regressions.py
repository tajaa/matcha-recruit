import asyncio
import inspect
from datetime import date
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
