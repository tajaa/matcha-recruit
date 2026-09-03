"""list_employee_document_expiries — the Compliance tab's employee expiry roster.

Three behaviours worth pinning, all of them regressions the first draft of the
endpoint shipped with:

1. The per-credential-type warning window comes from the data
   (`credential_types.warning_days`, resolved through the shared
   `WARNING_DAYS_SQL` precedence), not a hardcoded constant. A tenant that
   curates a 60-day license must not be told "current" on day 45.
2. Employees are returned most-urgent-first. Alphabetical order buries an
   expired credential under colleagues who need nothing.
3. Work permits keep the 14-day window `routes/employees/work_permits.py`
   already reports as `validity` for the same permit.

No DB: the endpoint issues exactly one `conn.fetch`, so a fake conn returning
canned rows exercises the whole assembly path.
"""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

from app.core.routes.compliance import credentials as compliance_credentials


TODAY = date.today()


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""

    async def fetch(self, query, *_args):
        self.query = query
        return self.rows


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_exc):
        return False


_AUTO = object()


def _row(*, first, last, employee_id, document_type="Professional License",
         kind="credential", expiry_date=None, stored_status="verified",
         warning_days=14, document_id=_AUTO, location_name=None):
    return {
        "employee_id": employee_id,
        "first_name": first,
        "last_name": last,
        "document_id": uuid4() if document_id is _AUTO else document_id,
        "kind": kind,
        "document_type": document_type,
        "expiry_date": expiry_date,
        "stored_status": stored_status,
        "location_name": location_name,
        "warning_days": warning_days,
    }


def _call(rows):
    conn = _FakeConn(rows)
    with (
        mock.patch.object(
            compliance_credentials, "resolve_company_id",
            mock.AsyncMock(return_value=uuid4()),
        ),
        mock.patch.object(
            compliance_credentials, "get_connection",
            return_value=_ConnectionContext(conn),
        ),
    ):
        result = asyncio.run(compliance_credentials.list_employee_document_expiries(
            company_id=None,
            current_user=SimpleNamespace(id=uuid4()),
        ))
    return result, conn


def test_credential_warning_window_follows_the_configured_days():
    """A 60-day type flags at 45 days out; a 14-day type does not."""
    curated, default = uuid4(), uuid4()
    result, _ = _call([
        _row(first="Ada", last="Curated", employee_id=curated,
             expiry_date=TODAY + timedelta(days=45), warning_days=60),
        _row(first="Bo", last="Default", employee_id=default,
             expiry_date=TODAY + timedelta(days=45), warning_days=14),
    ])

    by_id = {employee["employee_id"]: employee for employee in result}
    assert by_id[str(curated)]["status"] == "expiring_soon"
    assert by_id[str(default)]["status"] == "no_actionable_expiry"
    assert by_id[str(default)]["documents"][0]["expiry_status"] == "current"


def test_employees_are_ordered_most_urgent_first():
    """Urgency beats the alphabet, and names still break ties within a status."""
    result, _ = _call([
        _row(first="Amy", last="Aaronson", employee_id=uuid4(),
             expiry_date=TODAY + timedelta(days=400)),
        _row(first="Zed", last="Zimmer", employee_id=uuid4(),
             expiry_date=TODAY - timedelta(days=1)),
        _row(first="Mia", last="Miller", employee_id=uuid4(),
             expiry_date=TODAY + timedelta(days=3)),
        _row(first="Ann", last="Archer", employee_id=uuid4(), expiry_date=None),
        _row(first="Abe", last="Abbott", employee_id=uuid4(),
             expiry_date=TODAY - timedelta(days=30)),
    ])

    assert [employee["status"] for employee in result] == [
        "expired", "expired", "expiring_soon", "unknown", "no_actionable_expiry",
    ]
    # Ties inside `expired` fall back to last name, first name.
    assert [employee["employee_name"] for employee in result][:2] == ["Abe Abbott", "Zed Zimmer"]


def test_work_permits_use_the_fourteen_day_window():
    inside, outside = uuid4(), uuid4()
    result, _ = _call([
        _row(first="Ivy", last="Inside", employee_id=inside, kind="work_permit",
             document_type="Work permit", stored_status="active",
             expiry_date=TODAY + timedelta(days=10), warning_days=14),
        _row(first="Otto", last="Outside", employee_id=outside, kind="work_permit",
             document_type="Work permit", stored_status="active",
             expiry_date=TODAY + timedelta(days=20), warning_days=14),
    ])

    by_id = {employee["employee_id"]: employee for employee in result}
    assert by_id[str(inside)]["status"] == "expiring_soon"
    assert by_id[str(outside)]["status"] == "no_actionable_expiry"


def test_employee_with_no_documents_is_not_actionable():
    result, _ = _call([
        _row(first="Nora", last="Nothing", employee_id=uuid4(), document_id=None),
    ])

    assert result[0]["status"] == "no_actionable_expiry"
    assert result[0]["documents"] == []


def test_most_severe_document_drives_the_employee_rollup():
    employee_id = uuid4()
    result, _ = _call([
        _row(first="Sam", last="Stacked", employee_id=employee_id,
             document_type="Food Handler", expiry_date=TODAY + timedelta(days=400)),
        _row(first="Sam", last="Stacked", employee_id=employee_id,
             document_type="Professional License", expiry_date=TODAY - timedelta(days=2)),
    ])

    assert len(result) == 1
    assert result[0]["status"] == "expired"
    # Documents are ordered by severity too, so the actionable one reads first.
    assert result[0]["documents"][0]["document_type"] == "Professional License"


def test_query_resolves_the_window_instead_of_hardcoding_one():
    """The SQL must join the template table and project a warning_days column."""
    _, conn = _call([_row(first="Any", last="Body", employee_id=uuid4())])

    assert "credential_requirement_templates crt" in conn.query
    assert "AS warning_days" in conn.query
    assert "crt.warning_days" in conn.query


def test_endpoint_is_gated_on_credential_templates():
    """shared_router's mount only asks for compliance/compliance_lite, so the
    credentialing entitlement has to be asserted on the route itself."""
    route = next(
        r for r in compliance_credentials.shared_router.routes
        if getattr(r, "path", None) == "/employee-document-expiries"
    )

    # require_feature closes over the flag name.
    gated_features = {
        cell.cell_contents
        for dependency in route.dependencies
        for cell in (getattr(dependency.dependency, "__closure__", None) or ())
        if isinstance(cell.cell_contents, str)
    }
    assert "credential_templates" in gated_features
