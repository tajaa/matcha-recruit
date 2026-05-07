"""EmployeeCreateRequest accepts is_supervisor + work_state passthrough."""

from app.matcha.routes.employees import EmployeeCreateRequest


def test_create_request_accepts_is_supervisor_true():
    req = EmployeeCreateRequest(
        work_email="jane@example.com",
        first_name="Jane",
        last_name="Doe",
        work_state="CA",
        is_supervisor=True,
    )
    assert req.is_supervisor is True
    assert req.work_state == "CA"


def test_create_request_is_supervisor_default_none():
    req = EmployeeCreateRequest(
        work_email="bob@example.com",
        first_name="Bob",
        last_name="Smith",
    )
    assert req.is_supervisor is None


def test_create_request_legacy_email_alias_still_works():
    req = EmployeeCreateRequest(
        email="legacy@example.com",
        first_name="Sam",
        last_name="Q",
        work_state="NY",
        is_supervisor=False,
    )
    assert req.resolved_work_email() == "legacy@example.com"
    assert req.is_supervisor is False
