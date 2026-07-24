"""DB-free tests for the bidirectional test-tenant merge engine
(scripts/sync_tenants.py). No database, no network — pure functions only.

Import mechanism matches tests/paid_channels/test_paid_channels.py's
TestMigrationSchema._load_migration: the hyphen in export-dev-data.py (and
the fact these live in scripts/, not a package) means this must be an
importlib.util.spec_from_file_location load, not a normal import.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolves types via sys.modules[cls.__module__] — a module
    # loaded via spec_from_file_location isn't registered there by default,
    # which is otherwise silent until a frozen/typed dataclass in the module
    # needs it (AttributeError: 'NoneType' object has no attribute '__dict__').
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


st = _load("sync_tenants", "sync_tenants.py")
edd = _load("export_dev_data", "export-dev-data.py")

RowSnap = st.RowSnap
lit = edd.lit


# ── decide_row: the four terminal shapes ────────────────────────────────────

def test_dev_only_row_inserts_to_prod():
    d = st.decide_row({"id": "1"}, None, has_updated_at=True)
    assert d.action == "insert" and d.target == "prod" and not d.warn


def test_prod_only_row_inserts_to_dev():
    d = st.decide_row(None, {"id": "1"}, has_updated_at=True)
    assert d.action == "insert" and d.target == "dev" and not d.warn


def test_identical_rows_noop():
    row = {"id": "1", "name": "same"}
    d = st.decide_row(dict(row), dict(row), has_updated_at=True)
    assert d.action == "noop" and d.target is None


def test_decide_row_raises_when_both_sides_absent():
    with pytest.raises(ValueError):
        st.decide_row(None, None, has_updated_at=True)


# ── decide_row: LWW via updated_at ──────────────────────────────────────────

def test_newer_dev_updated_at_updates_prod():
    dev = {"id": "1", "x": "a", "updated_at": "2026-07-24 10:00:00+00"}
    prod = {"id": "1", "x": "b", "updated_at": "2026-07-24 09:00:00+00"}
    d = st.decide_row(dev, prod, has_updated_at=True)
    assert d.action == "update" and d.target == "prod" and not d.warn


def test_newer_prod_updated_at_updates_dev():
    dev = {"id": "1", "x": "a", "updated_at": "2026-07-24 09:00:00+00"}
    prod = {"id": "1", "x": "b", "updated_at": "2026-07-24 10:00:00+00"}
    d = st.decide_row(dev, prod, has_updated_at=True)
    assert d.action == "update" and d.target == "dev" and not d.warn


def test_equal_updated_at_diff_rows_dev_wins_and_warns():
    dev = {"id": "1", "x": "a", "updated_at": "2026-07-24 10:00:00+00"}
    prod = {"id": "1", "x": "b", "updated_at": "2026-07-24 10:00:00+00"}
    d = st.decide_row(dev, prod, has_updated_at=True)
    assert d.action == "update" and d.target == "prod" and d.warn


def test_null_updated_at_one_side_falls_back_to_dev_wins_warn():
    dev = {"id": "1", "x": "a", "updated_at": None}
    prod = {"id": "1", "x": "b", "updated_at": "2026-07-24 10:00:00+00"}
    d = st.decide_row(dev, prod, has_updated_at=True)
    assert d.action == "update" and d.target == "prod" and d.warn


def test_no_updated_at_table_dev_wins_and_warns():
    dev = {"id": "1", "x": "a"}
    prod = {"id": "1", "x": "b"}
    d = st.decide_row(dev, prod, has_updated_at=False)
    assert d.action == "update" and d.target == "prod" and d.warn


def test_never_yields_delete():
    """No combination of inputs should ever produce a 'delete' action."""
    rows = [None, {"id": "1", "x": "a", "updated_at": "2026-01-01 00:00:00+00"},
            {"id": "1", "x": "b", "updated_at": "2026-01-02 00:00:00+00"}]
    for dev in rows:
        for prod in rows:
            if dev is None and prod is None:
                continue
            for has_ts in (True, False):
                assert st.decide_row(dev, prod, has_ts).action != "delete"


# ── parse_ts ─────────────────────────────────────────────────────────────

def test_timestamp_text_parsing_microseconds_and_tz():
    ts = st.parse_ts("2026-07-24 10:30:00.123456+00")
    assert isinstance(ts, datetime)
    assert ts.year == 2026 and ts.month == 7 and ts.day == 24
    assert ts.microsecond == 123456


def test_timestamp_parsing_none_and_null_literal():
    assert st.parse_ts(None) is None
    assert st.parse_ts("NULL") is None
    assert st.parse_ts("") is None


def test_timestamp_parsing_unparseable_is_none():
    assert st.parse_ts("not-a-timestamp") is None


def test_timestamp_ordering_survives_parse():
    earlier = st.parse_ts("2026-07-24 09:00:00+00")
    later = st.parse_ts("2026-07-24 10:00:00+00")
    assert later > earlier


# ── table_drift / compute_drift ─────────────────────────────────────────────

def test_equal_column_sets_no_drift():
    dev_only, prod_only = st.table_drift(["id", "name"], ["id", "name"])
    assert dev_only == [] and prod_only == []


def test_drift_column_added_one_side_marks_table_drifted():
    dev_only, prod_only = st.table_drift(["id", "name", "is_test"], ["id", "name"])
    assert dev_only == ["is_test"] and prod_only == []


def test_drift_table_missing_on_prod_marks_drifted():
    report = st.compute_drift({"companies": ["id"], "new_table": ["id"]}, {"companies": ["id"]})
    assert "new_table" in report.missing_on_prod
    assert "new_table" in report.drifted_tables


def test_drift_table_missing_on_dev_marks_drifted():
    report = st.compute_drift({"companies": ["id"]}, {"companies": ["id"], "legacy_table": ["id"]})
    assert "legacy_table" in report.missing_on_dev
    assert "legacy_table" in report.drifted_tables


def test_drift_report_no_drift_when_schemas_match():
    report = st.compute_drift({"companies": ["id", "name"]}, {"companies": ["id", "name"]})
    assert report.drifted_tables == set()


# ── merge_plan: ascend gating (the blast-radius safety rule) ────────────────

def test_ascended_row_missing_on_prod_inserts_do_nothing_shape():
    dev_side = {("k1",): RowSnap(row={"id": "k1"}, descend=False)}
    planned, stats = st.merge_plan("users", dev_side, {}, has_updated_at=False)
    assert len(planned) == 1
    assert planned[0].decision.action == "insert" and planned[0].decision.target == "prod"
    assert stats.inserted_to_prod == 1


def test_ascended_row_present_both_sides_never_updates_even_if_differs():
    dev_side = {("k1",): RowSnap(row={"id": "k1", "email": "a@example.com"}, descend=False)}
    prod_side = {("k1",): RowSnap(row={"id": "k1", "email": "b@example.com"}, descend=False)}
    planned, stats = st.merge_plan("users", dev_side, prod_side, has_updated_at=False)
    assert planned[0].decision.action == "noop"
    assert stats.updated_to_prod == 0 and stats.updated_to_dev == 0


def test_descended_row_present_both_sides_uses_lww():
    dev_side = {("k1",): RowSnap(row={"id": "k1", "x": "a", "updated_at": "2026-07-24 10:00:00+00"}, descend=True)}
    prod_side = {("k1",): RowSnap(row={"id": "k1", "x": "b", "updated_at": "2026-07-24 09:00:00+00"}, descend=True)}
    planned, _ = st.merge_plan("employees", dev_side, prod_side, has_updated_at=True)
    assert planned[0].decision.action == "update" and planned[0].decision.target == "prod"


def test_merge_plan_union_of_pks_deterministic_order():
    dev_side = {("b",): RowSnap(row={"id": "b"}, descend=True), ("a",): RowSnap(row={"id": "a"}, descend=True)}
    prod_side = {("c",): RowSnap(row={"id": "c"}, descend=True)}
    planned1, _ = st.merge_plan("t", dev_side, prod_side, False)
    planned2, _ = st.merge_plan("t", dev_side, prod_side, False)
    assert [p.key for p in planned1] == [p.key for p in planned2]
    assert {p.key for p in planned1} == {("a",), ("b",), ("c",)}


def test_merge_plan_stats_counts_per_direction():
    dev_side = {
        ("only_dev",): RowSnap(row={"id": "only_dev"}, descend=True),
        ("both_same",): RowSnap(row={"id": "both_same", "updated_at": "x"}, descend=True),
    }
    prod_side = {
        ("only_prod",): RowSnap(row={"id": "only_prod"}, descend=True),
        ("both_same",): RowSnap(row={"id": "both_same", "updated_at": "x"}, descend=True),
    }
    _, stats = st.merge_plan("t", dev_side, prod_side, has_updated_at=True)
    assert stats.inserted_to_prod == 1
    assert stats.inserted_to_dev == 1
    assert stats.noop == 1


# ── emit_upsert: conflict-target shape depends on descend ───────────────────

def test_ascended_row_emits_on_conflict_do_nothing_only():
    insert_sql, fixup = st.emit_upsert("users", ["id", "email"], ["id"], {"id": "1", "email": "a@example.com"}, descended=False, lit=lit)
    assert "ON CONFLICT DO NOTHING" in insert_sql
    assert "DO UPDATE" not in insert_sql
    assert fixup is None


def test_descended_row_conflict_emits_do_update():
    insert_sql, fixup = st.emit_upsert("employees", ["id", "name"], ["id"], {"id": "1", "name": "Ana"}, descended=True, lit=lit)
    assert 'ON CONFLICT ("id") DO UPDATE SET' in insert_sql
    assert '"name" = EXCLUDED."name"' in insert_sql
    assert fixup is None


def test_descended_row_with_no_non_pk_columns_emits_do_nothing():
    insert_sql, _ = st.emit_upsert("t", ["id"], ["id"], {"id": "1"}, descended=True, lit=lit)
    assert 'ON CONFLICT ("id") DO NOTHING' in insert_sql


def test_selfref_column_nulled_and_fixup_update_emitted():
    row = {"id": "1", "manager_id": "2", "name": "Ana"}
    insert_sql, fixup = st.emit_upsert("employees", ["id", "manager_id", "name"], ["id"], row,
                                       descended=True, lit=lit, self_ref_cols=["manager_id"])
    assert "'2'" not in insert_sql  # not written inline
    assert "NULL" in insert_sql
    assert fixup is not None
    assert 'SET "manager_id" = \'2\'' in fixup
    assert 'WHERE "id" = \'1\'' in fixup


def test_selfref_column_null_in_source_emits_no_fixup():
    row = {"id": "1", "manager_id": None, "name": "Ana"}
    _, fixup = st.emit_upsert("employees", ["id", "manager_id", "name"], ["id"], row,
                               descended=True, lit=lit, self_ref_cols=["manager_id"])
    assert fixup is None


# ── emit_undo_for: insert -> delete, update -> restore preimage ────────────

def test_undo_for_insert_is_delete_by_pk():
    sql = st.emit_undo_for("employees", ["id"], ["id", "name"], target_preimage=None,
                            key_values={"id": "1"}, lit=lit, descended=True)
    assert sql == 'DELETE FROM "employees" WHERE "id" = \'1\';'


def test_undo_for_update_restores_target_preimage():
    preimage = {"id": "1", "name": "Original Name"}
    sql = st.emit_undo_for("employees", ["id"], ["id", "name"], target_preimage=preimage,
                            key_values={"id": "1"}, lit=lit, descended=True)
    assert sql == 'UPDATE "employees" SET "name" = \'Original Name\' WHERE "id" = \'1\';'


def test_undo_never_touches_pk_columns_in_set_clause():
    preimage = {"id": "1", "name": "X"}
    sql = st.emit_undo_for("t", ["id"], ["id", "name"], target_preimage=preimage,
                            key_values={"id": "1"}, lit=lit, descended=True)
    set_clause = sql.split(" WHERE ")[0]
    assert 'SET "id" =' not in set_clause


def test_undo_for_ascended_insert_skips_delete_when_not_reachable():
    # Ascended row (e.g. a shared `users` row): "not reachable in target's
    # own FK walk" is NOT the same as "confirmed absent from target" — the
    # insert used ON CONFLICT DO NOTHING and may have no-op'd against a real
    # pre-existing row. Undo must not emit a DELETE that could destroy it.
    sql = st.emit_undo_for("users", ["id"], ["id", "email"], target_preimage=None,
                            key_values={"id": "1"}, lit=lit, descended=False)
    assert "DELETE" not in sql
    assert sql.startswith("--")


def test_undo_for_ascended_update_still_restores_preimage():
    # When the ascended row WAS reachable on target (so we have a real
    # preimage), the restore path is exactly as safe as the descended case.
    preimage = {"id": "1", "email": "orig@example.com"}
    sql = st.emit_undo_for("users", ["id"], ["id", "email"], target_preimage=preimage,
                            key_values={"id": "1"}, lit=lit, descended=False)
    assert sql == 'UPDATE "users" SET "email" = \'orig@example.com\' WHERE "id" = \'1\';'


# ── email normalization (make_email_scrubber shared with export-dev-data) ──

def test_email_normalization_makes_scrubbed_prod_row_equal_dev_row():
    scrub, _ = edd.make_email_scrubber()
    dev_email = "amara.osei@360bh.org"
    normalized = edd.EMAIL.sub(scrub, dev_email)
    # Same transform applied to what prod already holds (already scrubbed by
    # a prior one-way push) must be a no-op / converge to the same string.
    prod_email_already_scrubbed = normalized
    assert edd.EMAIL.sub(scrub, prod_email_already_scrubbed) == normalized
    assert normalized.endswith("@example.com")


def test_email_normalization_is_injective_across_domains():
    scrub, _ = edd.make_email_scrubber()
    a = edd.EMAIL.sub(scrub, "amara.osei@360bh.com")
    b = edd.EMAIL.sub(scrub, "amara.osei@360bh.org")
    assert a != b  # domain survives into the local part


def test_email_normalization_leaves_reserved_domains_untouched():
    scrub, _ = edd.make_email_scrubber()
    assert edd.EMAIL.sub(scrub, "maria.chen@example.com") == "maria.chen@example.com"


# ── lit(): control-character escaping (GUARD 1b false-positive root cause) ──

def test_lit_none_is_null():
    assert lit(None) == "NULL"


def test_lit_plain_string_single_quoted():
    assert lit("abc") == "'abc'"


def test_lit_quote_doubling():
    assert lit("it's") == "'it''s'"


def test_lit_newline_becomes_e_string():
    assert lit("done\nBegin next phase") == "E'done\\nBegin next phase'"


def test_lit_carriage_return_escaped():
    assert lit("a\rb") == "E'a\\rb'"


def test_lit_backslash_doubled_and_triggers_e_string():
    assert lit("a\\b") == "E'a\\\\b'"


def test_lit_backslash_before_newline_order():
    # Backslashes must be doubled BEFORE newlines become \n, or a literal
    # backslash-n already in the data would double-escape incorrectly.
    assert lit("a\\nb\nc") == "E'a\\\\nb\\nc'"


def test_lit_quote_inside_e_string_still_doubled():
    assert lit("it's\nfine") == "E'it''s\\nfine'"


def test_lit_output_never_contains_raw_newline():
    assert "\n" not in lit("multi\nline prose; begin next phase")


# ── _write_outputs: every exit path must leave fresh files (finding #5) ─────

_OUTPUT_NAMES = ("sync_to_prod.sql", "sync_to_prod.undo.sql",
                  "sync_to_dev.sql", "sync_to_dev.undo.sql")


def test_write_outputs_empty_produces_header_only_files(tmp_path):
    st._write_outputs(tmp_path, [], [], [], [])
    for name in _OUTPUT_NAMES:
        text = (tmp_path / name).read_text()
        assert text.startswith("--")
        assert "INSERT" not in text and "UPDATE" not in text and "DELETE" not in text


def test_write_outputs_overwrites_stale_mutations(tmp_path):
    # Simulates the early-return-with-stale-files bug: last run's diff must
    # not survive a run that found nothing to sync.
    for name in _OUTPUT_NAMES:
        (tmp_path / name).write_text('INSERT INTO "companies" VALUES (\'stale\');\n')
    st._write_outputs(tmp_path, [], [], [], [])
    for name in _OUTPUT_NAMES:
        assert "INSERT" not in (tmp_path / name).read_text()


def test_write_outputs_reverses_undo_order(tmp_path):
    st._write_outputs(tmp_path, ["i1;", "i2;"], ["u1;", "u2;"], [], [])
    undo = (tmp_path / "sync_to_prod.undo.sql").read_text()
    assert undo.index("u2;") < undo.index("u1;")


# ── companies drift is the abort predicate (finding #6) ─────────────────────

def test_companies_column_drift_marks_companies_drifted():
    # Exact shape this branch creates: dev has is_test, prod pre-testacct01.
    report = st.compute_drift(
        {"companies": ["id", "name", "is_test"], "clients": ["id", "company_id"]},
        {"companies": ["id", "name"], "clients": ["id", "company_id"]},
    )
    assert "companies" in report.drifted_tables
    assert "clients" not in report.drifted_tables  # children NOT drifted — the FK-orphan trap
