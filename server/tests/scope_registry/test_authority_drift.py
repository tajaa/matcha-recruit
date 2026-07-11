"""diff_authority_items — pure re-ingest drift diff, no DB.

The "a federal section was added / amended / repealed since the last sweep"
detector. See authority_ingest._record_drift for the I/O wrapper.
"""
from datetime import date

from app.core.services.scope_registry.authority_ingest import diff_authority_items


def _row(citation, heading=None, amendment_date=None):
    return {"citation": citation, "heading": heading, "amendment_date": amendment_date}


def test_first_ingest_has_no_baseline_so_no_drift():
    """Empty prior ⇒ empty diff (every item would else read as 'new' = noise)."""
    items = [_row("29 CFR 1910.1"), _row("29 CFR 1910.2")]
    assert diff_authority_items([], items) == []


def test_detects_new_amended_removed_and_ignores_unchanged():
    d1, d2 = date(2024, 1, 1), date(2025, 6, 1)
    prior = [
        _row("29 CFR 1910.1", "Asbestos", d1),      # unchanged
        _row("29 CFR 1910.2", "Old heading", d1),   # heading changes → amended
        _row("29 CFR 1910.99", "Repealed", d1),     # gone upstream → removed
    ]
    items = [
        _row("29 CFR 1910.1", "Asbestos", d1),
        _row("29 CFR 1910.2", "New heading", d1),
        _row("29 CFR 1910.500", "Brand new section", d2),  # not in prior → new
    ]

    drift = diff_authority_items(prior, items)
    by_type = {}
    for ct, cite, heading, od, nd in drift:
        by_type.setdefault(ct, []).append((cite, heading, od, nd))

    # 1 amended + 1 new + 1 removed = 3; unchanged 1910.1 produces nothing
    assert len(drift) == 3
    assert by_type["new"] == [("29 CFR 1910.500", "Brand new section", None, d2)]
    assert by_type["amended"] == [("29 CFR 1910.2", "New heading", d1, d1)]
    assert by_type["removed"] == [("29 CFR 1910.99", "Repealed", d1, None)]


def test_amendment_date_change_alone_is_not_drift():
    """A part-level amendment_date bump must NOT flag every unchanged section —
    eCFR stamps one part date on all sections, so date-only diffs are noise."""
    d1, d2 = date(2024, 1, 1), date(2025, 6, 1)
    prior = [_row("29 CFR 1910.5", "Same heading", d1)]
    items = [_row("29 CFR 1910.5", "Same heading", d2)]
    assert diff_authority_items(prior, items) == []


def test_none_vs_empty_heading_is_not_a_change():
    """A heading that is None on one side and '' on the other must not flag."""
    prior = [_row("x", None, None)]
    items = [_row("x", "", None)]
    assert diff_authority_items(prior, items) == []
