"""DB-free lint over scripts/seed/meal_break_timing.sql (+ its undo).

Mirrors the guards scripts/seed-prod.sh enforces at runtime (GUARD 1 / 1b / 2)
plus the pack-authoring invariants from scripts/seed/README.md. This pack is
reference law rather than tenant demo data, so it also pins the properties that
make it safe to run against a catalog other people maintain: it writes exactly
one requirement_key, it never touches the `meal_breaks:meal_break` rows it
clones scaffolding from, and every row carries a citation.
"""
from __future__ import annotations

import re
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[3] / "scripts" / "seed"
PACK = PACK_DIR / "meal_break_timing.sql"
UNDO = PACK_DIR / "meal_break_timing.undo.sql"

OWNED_KEY = "meal_breaks:meal_break_timing"
STATES = ("CA", "WA", "OR")


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _statements(sql: str) -> list[str]:
    """Split on statement-terminating semicolons only.

    A citation literal ('Cal. Lab. Code § 512(a); Brinker …') carries its own
    semicolon, so the naive `split(";")` other packs use would cut a statement
    in half here. seed-prod.sh hands the file to `psql -f` and strips comments
    with a quote-aware walker for the same reason.
    """
    stripped = _strip_comments(sql)
    statements: list[str] = []
    current: list[str] = []
    in_literal = False
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if in_literal:
            if char == "'" and stripped[index + 1:index + 2] == "'":
                current.append("''")
                index += 2
                continue
            if char == "'":
                in_literal = False
        elif char == "'":
            in_literal = True
        elif char == ";":
            statements.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    if "".join(current).strip():
        statements.append("".join(current).strip())
    return [statement for statement in statements if statement]


def _pack_text() -> str:
    return PACK.read_text()


def _undo_text() -> str:
    return UNDO.read_text()


# ── GUARD 1b — no transaction control (seed-prod.sh's exact regex) ─────────

def test_pack_has_no_transaction_control():
    for text in (_pack_text(), _undo_text()):
        hits = re.findall(
            r"(^|;)[ \t]*(begin|commit|rollback|savepoint|release|start\s+transaction|"
            r"end\s+(transaction|work)|prepare\s+transaction)\b",
            _strip_comments(text),
            re.IGNORECASE | re.MULTILINE,
        )
        assert not hits, f"transaction-control statements: {hits}"


# ── GUARD 1 — no DDL/privilege statements ─────────────────────────────────

def test_pack_has_no_ddl():
    for text in (_pack_text(), _undo_text()):
        hits = re.findall(
            r"\b(create|drop|alter|truncate|grant|revoke)\b",
            _strip_comments(text),
            re.IGNORECASE,
        )
        assert not hits, f"DDL/privilege keywords: {hits}"


# ── GUARD 2 — reference data carries no email literals at all ─────────────

def test_pack_writes_no_email_addresses():
    emails = re.findall(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", _strip_comments(_pack_text())
    )
    assert not emails, f"unexpected email literals in a law-reference pack: {emails}"


# ── README rule: every INSERT is idempotent ───────────────────────────────

def test_every_insert_is_idempotent():
    inserts = [s for s in _statements(_pack_text()) if s.lower().startswith("insert into")]
    assert len(inserts) == len(STATES)
    for stmt in inserts:
        assert re.search(r"on conflict\b.*\bdo nothing", stmt, re.IGNORECASE | re.DOTALL), (
            f"INSERT missing ON CONFLICT … DO NOTHING: {stmt[:80]}..."
        )


# ── README rule: additive only, one owned key ─────────────────────────────

def test_pack_only_inserts_into_jurisdiction_requirements():
    stripped = _strip_comments(_pack_text())
    assert set(re.findall(r"INSERT INTO (\w+)", stripped, re.IGNORECASE)) == {
        "jurisdiction_requirements",
    }
    assert not re.search(r"\b(update|delete)\b", stripped, re.IGNORECASE), (
        "pack must be additive: no UPDATE/DELETE of rows it did not create"
    )


def test_pack_writes_exactly_the_owned_requirement_key():
    written = set(re.findall(r"'(meal_breaks:[a-z_]+)'(?=,)", _pack_text()))
    assert written == {OWNED_KEY}, f"unexpected requirement_key writes: {written}"


def test_pack_reads_but_never_rewrites_the_base_meal_break_rows():
    # `meal_breaks:meal_break` may only appear in the SELECT's WHERE clause.
    for match in re.finditer(r"'meal_breaks:meal_break'", _pack_text()):
        preceding = _pack_text()[:match.start()].rsplit("INSERT INTO", 1)[-1]
        assert "WHERE base.requirement_key =" in preceding, (
            "the base meal_break row is a source to clone from, never a write target"
        )


def test_every_state_row_is_cited():
    for state in STATES:
        block = re.search(
            rf"INSERT INTO jurisdiction_requirements.*?j\.state = '{state}'",
            _strip_comments(_pack_text()),
            re.DOTALL,
        )
        assert block, f"no INSERT block scoped to {state}"
        assert re.search(r"(Cal\. Lab\. Code|WAC|OAR)", block.group(0)), (
            f"{state} row carries no statutory citation"
        )


def test_state_rows_are_scoped_to_state_level_jurisdictions():
    # A bare `j.state = 'CA'` would also match every CA city/county row.
    assert len(re.findall(r"j\.level = 'state'", _pack_text())) == len(STATES)


# ── Undo removes exactly what the pack added ──────────────────────────────

def test_undo_deletes_only_the_owned_key():
    deletes = _statements(_undo_text())
    assert len(deletes) == 1
    assert deletes[0].lower().startswith("delete from jurisdiction_requirements")
    assert OWNED_KEY in deletes[0]
