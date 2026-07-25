"""DB-free lint over scripts/seed/sb553_components.sql (+ its undo).

Mirrors the guards scripts/seed-prod.sh enforces at runtime (GUARD 1 / 1b)
plus this pack's own invariants — no email literals expected here (it is
catalog data, no company_id anywhere), unlike benefits_sunset_dental.

Component ids are no longer pinned constants (see the pack's own header note:
a pinned UUID assumed exactly one CA catalog match, and a second match would
silently seed nothing for it). Idempotency now comes from the real
`UNIQUE (jurisdiction_requirement_id, component_key)` constraint (reqcomp01),
named explicitly in the ON CONFLICT target — these tests check for that
target, not for a pinned-id prefix.
"""
from __future__ import annotations

import re
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[3] / "scripts" / "seed"
PACK = PACK_DIR / "sb553_components.sql"
UNDO = PACK_DIR / "sb553_components.undo.sql"

OWNED_TABLES = {"requirement_components"}

EXPECTED_COMPONENT_KEYS = {
    "written_plan", "annual_training", "violent_incident_log",
    "hazard_assessment", "annual_review",
}
# Only annual_training derives today. violent_incident_log's derivation was
# removed — a text match against ir_incidents proved an incident was
# mentioned, not that the statute's log (required fields + 5-year retention)
# exists — so it is attest-only now, like written_plan/hazard_assessment/
# annual_review.
EXPECTED_DERIVABLE_KEYS = {"annual_training"}


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _pack_text() -> str:
    return PACK.read_text()


def _undo_text() -> str:
    return UNDO.read_text()


# ── GUARD 1b — no transaction control (seed-prod.sh's exact regex) ─────────

def test_pack_has_no_transaction_control():
    stripped = _strip_comments(_pack_text())
    hits = re.findall(
        r"(^|;)[ \t]*(begin|commit|rollback|savepoint|release|start\s+transaction|"
        r"end\s+(transaction|work)|prepare\s+transaction)\b",
        stripped,
        re.IGNORECASE | re.MULTILINE,
    )
    assert not hits, f"pack contains transaction-control statements: {hits}"


# ── GUARD 1 — no DDL/privilege statements ───────────────────────────────────

def test_pack_has_no_ddl():
    stripped = _strip_comments(_pack_text())
    hits = re.findall(r"\b(create|drop|alter|truncate|grant|revoke)\b", stripped, re.IGNORECASE)
    assert not hits, f"pack contains DDL/privilege keywords: {hits}"


# ── README rule: idempotent ─────────────────────────────────────────────────

def test_insert_is_idempotent_on_conflict():
    stripped = _strip_comments(_pack_text())
    assert "do nothing" in stripped.lower()


def test_conflict_target_is_the_parent_key_unique():
    """The real uniqueness constraint (reqcomp01) is
    UNIQUE (jurisdiction_requirement_id, component_key) — the ON CONFLICT
    target must name it explicitly. Without an id column to rely on for
    idempotency, a bare `ON CONFLICT DO NOTHING` (no target) would raise
    "there is no unique or exclusion constraint matching the ON CONFLICT
    specification" the moment two component rows share nothing to conflict
    on by default."""
    stripped = _strip_comments(_pack_text())
    assert "ON CONFLICT (jurisdiction_requirement_id, component_key) DO NOTHING" in stripped


# ── README rule: only write the table this pack owns ───────────────────────

def test_no_writes_to_unowned_tables():
    stripped = _strip_comments(_pack_text())
    targets = set(re.findall(r"INSERT INTO (\w+)", stripped, re.IGNORECASE))
    assert targets == OWNED_TABLES, f"unexpected INSERT targets: {targets - OWNED_TABLES}"


# ── Catalog data, not tenant data — no company_id, no email literals ───────

def test_no_company_id_column():
    stripped = _strip_comments(_pack_text())
    assert "company_id" not in stripped.lower()


def test_no_email_literals():
    stripped = _strip_comments(_pack_text())
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", stripped)
    assert not emails, f"unexpected email literals in a catalog-only pack: {emails}"


# ── Jurisdiction predicate must constrain country, not just state+level ────
# Matches the idiom already used by compliance_evals/golden.py, state_guides.py,
# and _jurisdictions.py on the same (state, level) predicate — a bare
# `j.state = 'CA' AND j.level = 'state'` would also match a hypothetical
# non-US CA-coded jurisdiction.

def test_jurisdiction_predicate_constrains_country():
    stripped = _strip_comments(_pack_text())
    assert "j.state = 'CA'" in stripped
    assert "j.level = 'state'" in stripped
    assert "country_code" in stripped


# ── No pinned component UUIDs ────────────────────────────────────────────────
# A pinned id assumed exactly one CA catalog row matches the WHERE clause; a
# second match (regulation_key already spans unrelated statutes across
# states, and dedup migration 92583427c259 exists precisely because catalog
# rows collide) would silently seed zero components for it, no error.

def test_no_pinned_component_uuids():
    stripped = _strip_comments(_pack_text())
    assert "5b553c00" not in stripped


# ── The 5 components, exactly, with the right derivable split ──────────────
# Each VALUES row is `(component_key, label, question, citation,
# suggested_fix, severity, derivation_key, sort_order)` — a fixed 8-column
# shape (no id column — left to gen_random_uuid()), so rows are parsed by
# splitting on top-level commas within each parenthesized tuple rather than
# one big regex.

def _rows() -> list[list[str]]:
    stripped = _strip_comments(_pack_text())
    values_block = stripped.split("JOIN (VALUES", 1)[1].split(") AS v(", 1)[0]
    rows: list[list[str]] = []
    depth, current, fields, in_str = 0, "", [], False
    for ch in values_block:
        if ch == "'":
            in_str = not in_str
            current += ch
        elif ch == "(" and not in_str:
            depth += 1
            if depth == 1:
                fields = []
                current = ""
                continue
            current += ch
        elif ch == ")" and not in_str:
            depth -= 1
            if depth == 0:
                fields.append(current.strip())
                rows.append(fields)
                current = ""
                continue
            current += ch
        elif ch == "," and not in_str and depth == 1:
            fields.append(current.strip())
            current = ""
        else:
            current += ch
    return rows


_COMPONENT_KEY = 0
_STATUTE_CITATION = 3
_DERIVATION_KEY = 6


def test_exactly_five_components_with_expected_keys():
    rows = _rows()
    assert len(rows) == 5
    keys = {r[_COMPONENT_KEY].strip("'") for r in rows}
    assert keys == EXPECTED_COMPONENT_KEYS, keys


def test_every_component_has_a_statute_citation():
    for row in _rows():
        assert "Cal. Lab. Code" in row[_STATUTE_CITATION], f"row missing statute citation: {row}"


def test_derivation_key_set_on_exactly_the_derivable_component():
    derivable = {r[_COMPONENT_KEY].strip("'") for r in _rows() if r[_DERIVATION_KEY].strip() != "NULL"}
    assert derivable == EXPECTED_DERIVABLE_KEYS, derivable


def test_seed_derivation_keys_exist_in_the_registry():
    """Cross-file drift guard: the derivation_key STRINGS in the SQL must
    resolve in COMPONENT_DERIVATIONS. A typo here seeds cleanly and silently
    downgrades that component to attest-only, with no error anywhere."""
    from app.core.services.compliance_status import COMPONENT_DERIVATIONS
    keys = {r[_DERIVATION_KEY].strip().strip("'") for r in _rows() if r[_DERIVATION_KEY].strip() != "NULL"}
    assert keys == {"wvp_training"}
    assert keys <= set(COMPONENT_DERIVATIONS)


# ── Undo deletes by key, not a pinned id prefix ─────────────────────────────

def test_undo_deletes_by_component_key_not_pinned_ids():
    undo = _undo_text()
    assert "5b553c00" not in undo
    for key in EXPECTED_COMPONENT_KEYS:
        assert f"'{key}'" in undo, f"undo is missing component_key {key!r}"


def test_undo_targets_the_owned_table():
    assert "requirement_components" in _undo_text()


def test_undo_scopes_by_the_same_jurisdiction_predicate_as_the_pack():
    undo = _undo_text()
    assert "j.state = 'CA'" in undo
    assert "j.level = 'state'" in undo
    assert "workplace_violence_prevention" in undo
