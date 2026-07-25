"""get_company_audit_overview — the company-wide Audit tab aggregate. No DB.

Four steps: short-circuit on whether ANY component row is projected -> one
company-wide reconcile -> one grouped status read -> a visibility pass per
LOCATION named by both of the reads above (never per row, and never
collapsible into one query — see the function's own docstring on why
`_filter_with_preemption` is set-relative), against which the status rows are
then assembled and filtered.

These tests decouple "does the aggregate assemble/filter correctly" from
"does reconcile write the right rows" (already covered by
test_component_status.py) by monkeypatching `reconcile_component_status` and
`get_location_requirements` to spies/stubs, and feeding the two direct
`conn.fetch()` calls the aggregate itself makes (the short-circuit query and
the grouped status read) through a fake conn.
"""
import asyncio
import inspect
from uuid import UUID, uuid4

import pytest

from app.core.services import compliance_status as cs
from app.core.services.compliance_status import get_company_audit_overview, rollup


def _run(coro):
    return asyncio.run(coro)


async def _no_gate(alias="cat", *, conn=None):
    return ""


class _FakeReq:
    """Stands in for a RequirementResponse — only the 2 fields
    get_company_audit_overview reads off it."""

    def __init__(self, jurisdiction_requirement_id, has_components, affected_employee_count=None):
        self.jurisdiction_requirement_id = jurisdiction_requirement_id
        self.has_components = has_components
        self.affected_employee_count = affected_employee_count


class _ReconcileSpy:
    """Replaces reconcile_component_status — records every call, does nothing."""

    def __init__(self):
        self.calls = []

    async def __call__(self, conn, company_id, *, features=None):
        self.calls.append((company_id, features))
        return {"evaluated": 0, "changed": 0}


class _VisibilitySpy:
    """Replaces compliance_service.get_location_requirements. `visible_by_loc`
    maps location_id -> list[_FakeReq] to return for that location."""

    def __init__(self, visible_by_loc):
        self.visible_by_loc = visible_by_loc
        self.calls = []

    async def __call__(self, location_id, company_id, category=None, *, conn=None):
        self.calls.append(location_id)
        return self.visible_by_loc.get(location_id, [])


def _status_row(*, location_id, catalog_id, component_key, status, basis,
                 title="Workplace Violence Prevention Plan",
                 statute_citation="Cal. Lab. Code § 6401.9",
                 category="workplace_safety",
                 authority_level="state", authority_display_name="California",
                 component_count=5,
                 location_name=None, city="Fresno", state="CA"):
    return {
        "location_id": location_id, "catalog_id": catalog_id,
        "component_key": component_key, "status": status, "basis": basis,
        "title": title, "statute_citation": statute_citation, "category": category,
        "authority_level": authority_level, "authority_display_name": authority_display_name,
        "component_count": component_count,
        "location_name": location_name, "city": city, "state": state,
    }


class _AuditFakeConn:
    """Answers exactly the 2 direct `conn.fetch()` calls
    get_company_audit_overview makes itself: the short-circuit candidate
    query and the grouped status read. Everything else (reconcile,
    visibility) is monkeypatched away entirely."""

    def __init__(self, candidate_rows, status_rows):
        self.candidate_rows = candidate_rows
        self.status_rows = status_rows
        self.fetch_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append(query)
        if "requirement_components rc " in query and "DISTINCT cr.location_id" in query:
            return self.candidate_rows
        if "FROM requirement_compliance_status rcs" in query:
            return self.status_rows
        raise AssertionError(f"unexpected conn.fetch: {query[:120]!r}")


def _patch(monkeypatch, *, reconcile=None, visibility=None):
    monkeypatch.setattr(
        "app.core.services.compliance_service.codified_gate_sql", _no_gate
    )
    if reconcile is not None:
        monkeypatch.setattr(cs, "reconcile_component_status", reconcile)
    if visibility is not None:
        monkeypatch.setattr(
            "app.core.services.compliance_service.get_location_requirements", visibility
        )


# ── short-circuit ────────────────────────────────────────────────────────────

def test_no_projected_components_returns_empty_overview(monkeypatch):
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({})
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    conn = _AuditFakeConn(candidate_rows=[], status_rows=[])

    result = _run(get_company_audit_overview(conn, uuid4(), features={}))

    assert result == {"statutes": [], "summary": rollup([]), "location_count": 0}


def test_short_circuit_runs_no_visibility_pipeline(monkeypatch):
    """The short-circuit is the whole cost story for every tenant with no
    decomposed statute in its jurisdictions — assert it runs nothing, don't
    assume it."""
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({})
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    conn = _AuditFakeConn(candidate_rows=[], status_rows=[])

    _run(get_company_audit_overview(conn, uuid4(), features={}))

    assert reconcile.calls == []
    assert visibility.calls == []
    # Only the candidate query ran — never the status read.
    assert len(conn.fetch_calls) == 1


# ── reconcile is company-wide, once ─────────────────────────────────────────

def test_reconcile_runs_once_for_the_company_not_per_location(monkeypatch):
    company_id = uuid4()
    loc_a, loc_b, loc_c = uuid4(), uuid4(), uuid4()
    catalog_id = uuid4()
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({
        loc_a: [_FakeReq(str(catalog_id), True)],
        loc_b: [_FakeReq(str(catalog_id), True)],
        loc_c: [_FakeReq(str(catalog_id), True)],
    })
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    conn = _AuditFakeConn(
        candidate_rows=[
            {"location_id": loc_a, "catalog_id": catalog_id},
            {"location_id": loc_b, "catalog_id": catalog_id},
            {"location_id": loc_c, "catalog_id": catalog_id},
        ],
        status_rows=[],
    )

    _run(get_company_audit_overview(conn, company_id, features={}))

    assert len(reconcile.calls) == 1
    assert reconcile.calls[0][0] == company_id


# ── visibility pass: once per candidate LOCATION ────────────────────────────

def test_visibility_pipeline_runs_once_per_candidate_location(monkeypatch):
    """Two catalog rows at the SAME location must not double the visibility
    call for that location — it is scoped to locations, not (location,
    catalog) pairs."""
    loc_a, loc_b = uuid4(), uuid4()
    cat_1, cat_2 = uuid4(), uuid4()
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({
        loc_a: [_FakeReq(str(cat_1), True), _FakeReq(str(cat_2), True)],
        loc_b: [_FakeReq(str(cat_1), True)],
    })
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    conn = _AuditFakeConn(
        candidate_rows=[
            {"location_id": loc_a, "catalog_id": cat_1},
            {"location_id": loc_a, "catalog_id": cat_2},
            {"location_id": loc_b, "catalog_id": cat_1},
        ],
        status_rows=[
            _status_row(location_id=loc_a, catalog_id=cat_1,
                        component_key="written_plan", status="unknown", basis=None),
            _status_row(location_id=loc_a, catalog_id=cat_2,
                        component_key="written_plan", status="unknown", basis=None),
            _status_row(location_id=loc_b, catalog_id=cat_1,
                        component_key="written_plan", status="unknown", basis=None),
        ],
    )

    _run(get_company_audit_overview(conn, uuid4(), features={}))

    assert sorted(visibility.calls, key=str) == sorted([loc_a, loc_b], key=str)


def test_candidate_location_with_no_status_rows_skips_the_pipeline(monkeypatch):
    """The visibility pass is the expensive part of this endpoint (a projection
    query, two set-relative filters and a roster scan, per location). A
    candidate location with no component status row contributes nothing to the
    output, so it must not be paid for."""
    loc_with, loc_without = uuid4(), uuid4()
    catalog_id = uuid4()
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({
        loc_with: [_FakeReq(str(catalog_id), True)],
        loc_without: [_FakeReq(str(catalog_id), True)],
    })
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    conn = _AuditFakeConn(
        candidate_rows=[
            {"location_id": loc_with, "catalog_id": catalog_id},
            {"location_id": loc_without, "catalog_id": catalog_id},
        ],
        status_rows=[
            _status_row(location_id=loc_with, catalog_id=catalog_id,
                        component_key="written_plan", status="unknown", basis=None),
        ],
    )

    result = _run(get_company_audit_overview(conn, uuid4(), features={}))

    assert visibility.calls == [loc_with]
    assert result["location_count"] == 1


# ── visibility filtering: the Requirements/Audit parity invariant ──────────

def test_requirement_hidden_at_one_location_is_dropped_there(monkeypatch):
    """A catalog visible at location A but filtered out (preemption, industry,
    codified gate) at location B must appear in A's location list and NOT
    B's — the Audit tab must never show what the Requirements tab hides."""
    loc_a, loc_b = uuid4(), uuid4()
    catalog_id = uuid4()
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({
        loc_a: [_FakeReq(str(catalog_id), True, affected_employee_count=12)],
        loc_b: [_FakeReq(str(catalog_id), False)],  # has_components False at B
    })
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    conn = _AuditFakeConn(
        candidate_rows=[
            {"location_id": loc_a, "catalog_id": catalog_id},
            {"location_id": loc_b, "catalog_id": catalog_id},
        ],
        status_rows=[
            _status_row(location_id=loc_a, catalog_id=catalog_id,
                        component_key="annual_training", status="unknown", basis=None,
                        city="Fresno"),
            _status_row(location_id=loc_b, catalog_id=catalog_id,
                        component_key="annual_training", status="unknown", basis=None,
                        city="Oakland"),
        ],
    )

    result = _run(get_company_audit_overview(conn, uuid4(), features={}))

    assert len(result["statutes"]) == 1
    statute = result["statutes"][0]
    assert [loc["location_id"] for loc in statute["locations"]] == [str(loc_a)]
    assert statute["locations"][0]["employee_count"] == 12


# ── rollups are the shared pure rollup(), computed over the right row sets ─

def test_statute_summary_is_rollup_across_its_locations(monkeypatch):
    loc_a, loc_b = uuid4(), uuid4()
    catalog_id = uuid4()
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({
        loc_a: [_FakeReq(str(catalog_id), True)],
        loc_b: [_FakeReq(str(catalog_id), True)],
    })
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    rows = [
        _status_row(location_id=loc_a, catalog_id=catalog_id,
                    component_key="annual_training", status="compliant", basis="derived"),
        _status_row(location_id=loc_a, catalog_id=catalog_id,
                    component_key="written_plan", status="unknown", basis=None),
        _status_row(location_id=loc_b, catalog_id=catalog_id,
                    component_key="annual_training", status="non_compliant", basis="derived"),
    ]
    conn = _AuditFakeConn(
        candidate_rows=[
            {"location_id": loc_a, "catalog_id": catalog_id},
            {"location_id": loc_b, "catalog_id": catalog_id},
        ],
        status_rows=rows,
    )

    result = _run(get_company_audit_overview(conn, uuid4(), features={}))

    statute = result["statutes"][0]
    expected = rollup([{"status": r["status"], "basis": r["basis"]} for r in rows])
    assert statute["summary"] == expected


def test_company_summary_is_rollup_across_all_statutes(monkeypatch):
    loc_a = uuid4()
    cat_1, cat_2 = uuid4(), uuid4()
    reconcile = _ReconcileSpy()
    visibility = _VisibilitySpy({
        loc_a: [_FakeReq(str(cat_1), True), _FakeReq(str(cat_2), True)],
    })
    _patch(monkeypatch, reconcile=reconcile, visibility=visibility)
    rows = [
        _status_row(location_id=loc_a, catalog_id=cat_1,
                    component_key="annual_training", status="compliant", basis="derived",
                    title="Statute One"),
        _status_row(location_id=loc_a, catalog_id=cat_2,
                    component_key="written_plan", status="unknown", basis=None,
                    title="Statute Two"),
    ]
    conn = _AuditFakeConn(
        candidate_rows=[
            {"location_id": loc_a, "catalog_id": cat_1},
            {"location_id": loc_a, "catalog_id": cat_2},
        ],
        status_rows=rows,
    )

    result = _run(get_company_audit_overview(conn, uuid4(), features={}))

    assert len(result["statutes"]) == 2
    expected = rollup([{"status": r["status"], "basis": r["basis"]} for r in rows])
    assert result["summary"] == expected
    assert result["location_count"] == 1


# ── source-text invariants ───────────────────────────────────────────────────

def test_audit_read_filters_component_rows_only():
    """Whole-requirement rows (component_key IS NULL) must not leak into
    clause coverage — the same invariant compliance_risk.py and risk_index.py
    already enforce on their own requirement_compliance_status reads."""
    src = inspect.getsource(get_company_audit_overview)
    assert "component_key IS NOT NULL" in src


def test_authority_label_resolved_through_jurisdictions():
    """Authority must come from the bound `jurisdictions` row via
    _authority_label — never the untrustworthy free-text
    jurisdiction_level/jurisdiction_name columns."""
    src = inspect.getsource(get_company_audit_overview)
    assert "_authority_label(" in src
    assert "JOIN jurisdictions j" in src


def test_candidate_query_is_distinct():
    src = inspect.getsource(get_company_audit_overview)
    assert "SELECT DISTINCT" in src
