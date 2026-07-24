"""DB-free lint over scripts/seed/benefits_sunset_dental.sql (+ its undo).

Mirrors the guards scripts/seed-prod.sh enforces at runtime (GUARD 1 / 1b /
2) plus the pack-authoring invariants from scripts/seed/README.md, so a
regression here is caught before anyone runs the pack against a real DB.
"""
from __future__ import annotations

import re
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[3] / "scripts" / "seed"
PACK = PACK_DIR / "benefits_sunset_dental.sql"
UNDO = PACK_DIR / "benefits_sunset_dental.undo.sql"

OWNED_TABLES = {
    "benefit_plans",
    "benefit_plan_tiers",
    "open_enrollment_periods",
    "life_event_changes",
    "benefit_elections",
    "benefit_roster_entries",
    "benefit_eligibility_exceptions",
    "benefit_renewal_risk",
}


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _statements(sql: str) -> list[str]:
    stripped = _strip_comments(sql)
    return [s.strip() for s in stripped.split(";") if s.strip()]


def _insert_block(sql: str, table: str) -> str:
    """Text of the first `INSERT INTO <table> ... ON CONFLICT DO NOTHING;` block,
    with `--` comments stripped — section comments like `-- 2026 medical
    (approved)` carry their own parens/quotes that would otherwise contaminate
    row parsing."""
    stripped = _strip_comments(sql)
    match = re.search(
        rf"INSERT INTO {re.escape(table)}\b.*?ON CONFLICT DO NOTHING;",
        stripped,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"no INSERT INTO {table} ... ON CONFLICT DO NOTHING; block found"
    return match.group(0)


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


# ── GUARD 2 — reserved email domains only ───────────────────────────────────

def test_all_emails_are_reserved_domains():
    stripped = _strip_comments(_pack_text())
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", stripped)
    assert emails, "expected at least one email literal in the pack"
    bad = [
        e for e in emails
        if not re.search(r"@(example\.(com|org|net)|[a-z0-9.-]+\.(test|invalid|localhost))$", e, re.IGNORECASE)
    ]
    assert not bad, f"non-reserved email domains: {bad}"


# ── README rule: every INSERT is idempotent ─────────────────────────────────

def test_every_insert_is_on_conflict_do_nothing():
    for stmt in _statements(_pack_text()):
        if stmt.lower().startswith("insert into"):
            assert "on conflict do nothing" in stmt.lower(), (
                f"INSERT missing ON CONFLICT DO NOTHING: {stmt[:80]}..."
            )


# ── README rule: only write the tables this pack owns ───────────────────────

def test_no_writes_to_unowned_tables():
    stripped = _strip_comments(_pack_text())
    targets = set(re.findall(r"INSERT INTO (\w+)", stripped, re.IGNORECASE))
    assert targets, "no INSERT INTO statements found"
    assert targets <= OWNED_TABLES, f"unexpected INSERT targets: {targets - OWNED_TABLES}"


# ── Undo covers every pinned-uuid prefix the pack introduces ────────────────

def test_undo_covers_every_pinned_uuid_prefix():
    pack_prefixes = set(re.findall(r"b09e11e5-(\d{4})-", _pack_text()))
    assert pack_prefixes, "expected pinned b09e11e5-#### uuid prefixes in the pack"
    undo_text = _undo_text()
    for prefix in pack_prefixes:
        assert f"b09e11e5-{prefix}-%'" in undo_text, (
            f"undo file has no DELETE ... LIKE 'b09e11e5-{prefix}-%' for prefix {prefix}"
        )


# ── Undo deletes children before parents (RESTRICT FKs) ─────────────────────

def test_undo_deletes_children_before_parents():
    order = re.findall(r"DELETE FROM (\w+)", _undo_text())
    assert "benefit_elections" in order
    assert "benefit_plans" in order
    assert "benefit_plan_tiers" in order
    elections_idx = order.index("benefit_elections")
    assert elections_idx < order.index("benefit_plans"), (
        "benefit_elections must be deleted before benefit_plans (ON DELETE RESTRICT)"
    )
    assert elections_idx < order.index("benefit_plan_tiers"), (
        "benefit_elections must be deleted before benefit_plan_tiers (ON DELETE RESTRICT)"
    )


# ── Schema invariant: at most one open OE period per company ───────────────

def test_only_one_open_oe_period():
    block = _insert_block(_pack_text(), "open_enrollment_periods")
    assert len(re.findall(r"'open'", block)) == 1, (
        "expected exactly one 'open' open_enrollment_periods row (uq_oe_open_per_company)"
    )


# ── Schema invariant: ck_election_waive (waived <-> plan/tier null-ness) ────

def _split_top_level_parens(text: str) -> list[str]:
    """Depth-aware split: each row is a top-level (...) group. Needed because
    `NOW() - INTERVAL '...'` has its own nested parens (JSON uses [] / {},
    but timestamp expressions don't), so a flat non-nested regex misreads
    NOW()'s parens as a row boundary."""
    rows: list[str] = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                rows.append(text[start:i])
                start = None
    return rows


def _election_rows(sql: str) -> list[str]:
    block = _insert_block(sql, "benefit_elections")
    values_section = block.split("VALUES", 1)[1]
    return _split_top_level_parens(values_section)


def test_waived_elections_have_null_plan_and_tier():
    for row in _election_rows(_pack_text()):
        waived_match = re.search(r",\s*(true|false)\s*,\s*'\[", row)
        assert waived_match, f"couldn't locate waived flag in election row: {row[:60]}..."
        waived = waived_match.group(1) == "true"
        has_null_plan_tier = bool(re.search(r"NULL\s*,\s*NULL\s*,\s*(true|false)\s*,\s*'\[", row))
        if waived:
            assert has_null_plan_tier, f"waived=true row must have NULL plan_id/tier_id: {row[:80]}..."
        else:
            assert not has_null_plan_tier, f"waived=false row must not have NULL plan_id/tier_id: {row[:80]}..."


# ── Schema invariant: ck_election_window (exactly one window FK) ───────────

def test_election_rows_reference_exactly_one_window():
    window_re = re.compile(
        r"^\s*'[^']+'\s*,\s*'[^']+'\s*,\s*'[^']+'\s*,\s*(NULL|'[^']+')\s*,\s*(NULL|'[^']+')\s*,"
    )
    for row in _election_rows(_pack_text()):
        m = window_re.match(row)
        assert m, f"couldn't parse id/company/employee/oe/life-event columns: {row[:80]}..."
        oe_field, life_event_field = m.group(1), m.group(2)
        non_null = [f for f in (oe_field, life_event_field) if f != "NULL"]
        assert len(non_null) == 1, (
            f"election row must reference exactly one of oe_period/life_event, got: {row[:80]}..."
        )


# ── Detector compatibility: exception dedup_key format ──────────────────────

def test_dedup_keys_match_detector_format():
    block = _insert_block(_pack_text(), "benefit_eligibility_exceptions")
    expected = {
        "new_hire_enrollment_gap:csv:nina.petrov@example.com",
        "termination_premium_leak:csv:tom.weller@example.com",
    }
    for key in expected:
        assert f"'{key}'" in block, f"expected dedup_key {key!r} in exceptions block"
