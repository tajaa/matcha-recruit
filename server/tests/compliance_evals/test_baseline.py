"""Baseline suite pure core — master-list integrity + diff logic.

No DB: the master-list is static and the present/missing diff is pure. These lock
(1) every enumerated key exists in the registry vocabulary (a typo would silently
never match a catalog row) and (2) the diff splits correctly.
"""
from app.core.compliance_registry import EXPECTED_REGULATION_KEYS
from app.core.services.compliance_evals.baseline import (
    baseline_checklist, diff_masterlist,
)
from app.core.services.compliance_evals.baseline_masterlist import (
    CA_STATE_LABOR_MASTERLIST, FEDERAL_LABOR_MASTERLIST, masterlist_keys,
)
from app.core.services.compliance_evals.scoring import baseline_score

ALL = FEDERAL_LABOR_MASTERLIST + CA_STATE_LABOR_MASTERLIST


# ── master-list integrity ───────────────────────────────────────────────────

def test_every_key_in_vocabulary():
    # a key not in EXPECTED_REGULATION_KEYS[category] can never match a catalog row
    bad = [(e.category, e.key) for e in ALL
           if e.key not in EXPECTED_REGULATION_KEYS.get(e.category, frozenset())]
    assert bad == [], f"master-list keys missing from vocabulary: {bad}"


def test_every_entry_has_real_citation_and_url():
    for e in ALL:
        assert e.citation and e.authority_url.startswith("http"), e


def test_federal_and_ca_nonempty():
    assert len(FEDERAL_LABOR_MASTERLIST) >= 20
    assert len(CA_STATE_LABOR_MASTERLIST) >= 15


def test_masterlist_keys_shape():
    keys = masterlist_keys(FEDERAL_LABOR_MASTERLIST)
    assert "leave" in keys and "fmla" in keys["leave"]
    assert all(isinstance(v, frozenset) for v in keys.values())


# ── diff_masterlist ─────────────────────────────────────────────────────────

def test_diff_splits_present_and_missing():
    entries = [e for e in FEDERAL_LABOR_MASTERLIST if e.category == "leave"][:1]
    e = entries[0]
    present, missing = diff_masterlist(entries, {f"{e.category}:{e.key}"})
    assert present == entries and missing == []
    present, missing = diff_masterlist(entries, set())
    assert present == [] and missing == entries


def test_checklist_marks_presence():
    e = FEDERAL_LABOR_MASTERLIST[0]
    rows = baseline_checklist([e], {f"{e.category}:{e.key}"})
    assert rows[0]["present"] is True and rows[0]["citation"] == e.citation
    rows = baseline_checklist([e], set())
    assert rows[0]["present"] is False


# ── baseline_score ──────────────────────────────────────────────────────────

def test_score_none_when_empty():
    assert baseline_score(0, 0) is None


def test_score_pct():
    assert baseline_score(3, 1) == 75.0
    assert baseline_score(27, 0) == 100.0
