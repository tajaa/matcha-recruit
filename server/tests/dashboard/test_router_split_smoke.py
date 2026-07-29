"""dashboard router-split smoke tests — pure import/route-table checks, no DB.

Guards the 2026-07 split of routes/dashboard.py into a package: the route
table and the lazy cross-import contract with
routes/matcha_work/workspace.py:468 must survive untouched.
"""
from app.matcha.routes import dashboard


_EXPECTED_ROUTES = {
    ("/credential-expirations", ("GET",)),
    ("/escalated-queries", ("GET",)),
    ("/escalated-queries/{query_id}", ("GET",)),
    ("/escalated-queries/{query_id}/dismiss", ("PUT",)),
    ("/escalated-queries/{query_id}/resolve", ("PUT",)),
    ("/escalated-queries/{query_id}/status", ("PUT",)),
    ("/flags", ("GET",)),
    ("/flags/analyze", ("POST",)),
    ("/notifications", ("GET",)),
    ("/sidebar-badges", ("GET",)),
    ("/stats", ("GET",)),
    ("/upcoming", ("GET",)),
    ("/wage-gap/details", ("GET",)),
    ("/wage-gap/export.csv", ("GET",)),
    ("/tasks/dismiss", ("POST",)),
    ("/tasks/dismiss", ("DELETE",)),
    ("/tasks", ("GET",)),
    ("/tasks", ("POST",)),
    ("/tasks/{task_id}", ("PATCH",)),
    ("/tasks/{task_id}", ("DELETE",)),
}


def test_route_table_matches_pre_split_snapshot():
    routes = {(r.path, tuple(sorted(r.methods))) for r in dashboard.router.routes}
    assert routes == _EXPECTED_ROUTES
    assert len(dashboard.router.routes) == 20


def test_workspace_lazy_import_contract():
    """routes/matcha_work/workspace.py:468 does this exact import inside a
    function body — it must keep resolving without a workspace.py edit."""
    from app.matcha.routes.dashboard import (
        _UPCOMING_SOURCES,
        _apply_company_filter,
        _severity_from_days,
        UpcomingItem,
    )

    assert isinstance(_UPCOMING_SOURCES, list) and len(_UPCOMING_SOURCES) > 0
    assert _apply_company_filter("x {company_filter}", None) == "x TRUE"
    assert _severity_from_days(-1) == "critical"
    assert UpcomingItem is not None
