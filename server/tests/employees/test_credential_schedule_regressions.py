import asyncio
from uuid import uuid4

from app.core.services.credential_template_service import (
    ResolvedCredentialRequirement,
    assign_credential_requirements_to_employee,
)
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
