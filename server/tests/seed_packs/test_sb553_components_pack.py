"""DB-free lint over scripts/seed/sb553_components.sql (+ its undo).

Mirrors the guards scripts/seed-prod.sh enforces at runtime (GUARD 1 / 1b)
plus this pack's own invariants — no email literals expected here (it is
catalog data, no company_id anywhere), unlike benefits_sunset_dental.
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
EXPECTED_DERIVABLE_KEYS = {"annual_training", "violent_incident_log"}


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

def test_insert_is_on_conflict_do_nothing():
    stripped = _strip_comments(_pack_text())
    assert "on conflict do nothing" in stripped.lower()


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


# ── The 5 components, exactly, with the right derivable split ──────────────
# Each VALUES row is `(uuid, component_key, label, question, citation,
# suggested_fix, severity, derivation_key, sort_order)` — a fixed 9-column
# shape, so rows are parsed by splitting on top-level commas within each
# parenthesized tuple rather than one big regex.

def _rows() -> list[list[str]]:
    stripped = _strip_comments(_pack_text())
    values_block = stripped.split("JOIN (VALUES", 1)[1].split(") AS v(", 1)[0]
    rows: list[list[str]] = []
    depth, current, fields, in_str = 0, "", [], False
    for ch in values_block:
        if ch == "'" :
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


def test_exactly_five_components_with_expected_keys():
    rows = _rows()
    assert len(rows) == 5
    keys = {r[1].strip("'") for r in rows}
    assert keys == EXPECTED_COMPONENT_KEYS, keys


def test_every_component_has_a_statute_citation():
    for row in _rows():
        assert "Cal. Lab. Code" in row[4], f"row missing statute citation: {row}"


def test_derivation_key_set_on_exactly_the_two_derivable_components():
    derivable = {r[1].strip("'") for r in _rows() if r[7].strip() != "NULL"}
    assert derivable == EXPECTED_DERIVABLE_KEYS, derivable


def test_seed_derivation_keys_exist_in_the_registry():
    """Cross-file drift guard: the derivation_key STRINGS in the SQL must
    resolve in COMPONENT_DERIVATIONS. A typo here seeds cleanly and silently
    downgrades that component to attest-only, with no error anywhere."""
    from app.core.services.compliance_status import COMPONENT_DERIVATIONS
    keys = {r[7].strip().strip("'") for r in _rows() if r[7].strip() != "NULL"}
    assert keys == {"wvp_training", "wvp_incident_log"}
    assert keys <= set(COMPONENT_DERIVATIONS)


# ── Undo covers the pinned prefix ───────────────────────────────────────────

def test_undo_covers_the_pinned_prefix():
    assert "5b553c00-" in _pack_text()
    assert "5b553c00-%'" in _undo_text()


def test_undo_targets_the_owned_table():
    assert "requirement_components" in _undo_text()
