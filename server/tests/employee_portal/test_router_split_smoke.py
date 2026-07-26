"""employee_portal router-split smoke tests — pure import/route-table checks, no DB.

Guards the 2026-07 split of routes/employee_portal.py into a package: the
route table, Depends-list identity, and back-compat attribute surface must
survive untouched.
"""
import pytest

from app.matcha.routes import employee_portal
from app.matcha.routes.employee_portal import _shared


_EXPECTED_ROUTES = {
    ("/me", ("GET",)),
    ("/me", ("PATCH",)),
    ("/me/benefits", ("GET",)),
    ("/me/benefits/elections", ("PUT",)),
    ("/me/benefits/elections/submit", ("POST",)),
    ("/me/benefits/elections/{election_id}", ("DELETE",)),
    ("/me/benefits/life-events", ("GET",)),
    ("/me/benefits/life-events", ("POST",)),
    ("/me/credential-documents", ("GET",)),
    ("/me/credential-documents", ("POST",)),
    ("/me/documents", ("GET",)),
    ("/me/documents/{document_id}", ("GET",)),
    ("/me/documents/{document_id}/handbook", ("GET",)),
    ("/me/documents/{document_id}/sign", ("POST",)),
    ("/me/leave", ("GET",)),
    ("/me/leave/eligibility", ("GET",)),
    ("/me/leave/request", ("POST",)),
    ("/me/leave/{leave_id}", ("DELETE",)),
    ("/me/leave/{leave_id}", ("GET",)),
    ("/me/pto", ("GET",)),
    ("/me/pto/request", ("POST",)),
    ("/me/pto/request/{request_id}", ("DELETE",)),
    ("/me/schedule", ("GET",)),
    ("/me/schedule/requests", ("GET",)),
    ("/me/schedule/requests", ("POST",)),
    ("/me/schedule/requests/{request_id}", ("DELETE",)),
    ("/me/tasks", ("GET",)),
    ("/onboarding", ("GET",)),
    ("/onboarding/{task_id}", ("PATCH",)),
    ("/policies", ("GET",)),
    ("/policies/{policy_id}", ("GET",)),
    ("/priorities", ("GET",)),
    ("/priorities/{task_id}", ("PATCH",)),
}


def test_route_table_matches_pre_split_snapshot():
    routes = {(r.path, tuple(sorted(r.methods))) for r in employee_portal.router.routes}
    assert routes == _EXPECTED_ROUTES
    assert len(employee_portal.router.routes) == 33


def test_dep_lists_are_shared_singletons():
    """Each _*_dep list must be defined exactly once in _shared and imported
    everywhere else — recreating one would fracture dependency_overrides."""
    assert employee_portal._pto_dep is _shared._pto_dep
    assert employee_portal._policies_dep is _shared._policies_dep
    assert employee_portal._compliance_plus_dep is _shared._compliance_plus_dep
    assert employee_portal._schedule_dep is _shared._schedule_dep
    assert employee_portal._benefits_dep is _shared._benefits_dep


def test_back_compat_attributes_present():
    """tests/employees/test_internal_mobility_routes.py (pre-broken on main,
    unrelated to this split) still expects these names on the package."""
    assert hasattr(employee_portal, "require_employee_record")
    assert hasattr(employee_portal, "require_employee")
    assert hasattr(employee_portal, "require_feature")
