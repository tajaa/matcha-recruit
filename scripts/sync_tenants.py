#!/usr/bin/env python3
"""Bidirectional dev <-> prod sync for `is_test` tenants.

Companion to export-dev-data.py, which is strictly one-way (dev -> prod).
This engine lets a test tenant (Sunset Smile Dental Group, 720 Behavioral,
Onc, ...) be edited on EITHER side and converges both. Tenants are whatever
`companies.is_test = true` names on either DB (union, keyed by UUID — never
name; company names are rewritten by anonymize_dev.sql) — no hardcoded
allowlist to maintain.

Not meant to be run directly for routine use — scripts/sync-test-tenants.sh
is the wrapper (tunnel management, locking, seed-prod.sh application). This
module is importable and its pure functions are unit-tested DB-free in
server/tests/tenant_sync/test_merge_engine.py.

MERGE RULES
    Row only on one side               -> insert onto the other.
    Row on both, byte-identical (text) -> noop.
    Row on both, differs, table has `updated_at` and both sides' values
        parse and differ               -> newer `updated_at` wins.
    Row on both, differs, no usable `updated_at` (column absent, or a NULL,
        or a tie)                      -> dev wins (dev is the historical
                                           source of truth) + WARN.
    A row that was only ever ASCENDED to (a shared parent this pack didn't
        directly own, e.g. a client's own `users` row) is NEVER updated in
        either direction, even if it "differs" — inserted-if-missing only,
        untargeted `ON CONFLICT DO NOTHING` (matches export-dev-data.py's
        --mode skip rationale: a secondary-unique collision must not abort
        the whole transaction). This is what keeps the automated blast
        radius to genuinely tenant-owned rows.
    DELETE is never emitted in either direction, ever, outside undo files.
    Schema drift (a table's column set differs between dev and prod) ->
        that table is excluded from the merge entirely, loudly (`DRIFT:`).

Snapshots of BOTH sides are taken before anything is decided, because
export-dev-data.py's update-mode INSERT writes the SOURCE row's `updated_at`
into the TARGET (`EXCLUDED."updated_at"`) — deciding from a live re-read
after a partial apply would compare an already-overwritten value.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parent.parent
_EXPORT_PATH = Path(__file__).resolve().parent / "export-dev-data.py"


def _load_export_dev_data():
    """Import export-dev-data.py (hyphenated filename) as a module, so this
    engine reuses its schema introspection / FK-walk / text-cast / literal
    helpers instead of re-implementing them a second, divergent way."""
    spec = importlib.util.spec_from_file_location("export_dev_data", _EXPORT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_dev_data"] = mod  # see test_merge_engine.py's _load() for why
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Pure core — DB-free, unit-tested directly.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    action: str            # "noop" | "insert" | "update"
    target: str | None     # "prod" | "dev" | None (noop)
    reason: str
    warn: bool = False


@dataclass(frozen=True)
class RowSnap:
    row: dict               # column -> text value (already ::text-cast)
    descend: bool           # True if this row was reached by DESCENDing (tenant-owned)


@dataclass
class MergeStats:
    inserted_to_prod: int = 0
    inserted_to_dev: int = 0
    updated_to_prod: int = 0
    updated_to_dev: int = 0
    noop: int = 0
    warned: int = 0

    def record(self, decision: "Decision"):
        if decision.action == "noop":
            self.noop += 1
        elif decision.action == "insert" and decision.target == "prod":
            self.inserted_to_prod += 1
        elif decision.action == "insert" and decision.target == "dev":
            self.inserted_to_dev += 1
        elif decision.action == "update" and decision.target == "prod":
            self.updated_to_prod += 1
        elif decision.action == "update" and decision.target == "dev":
            self.updated_to_dev += 1
        if decision.warn:
            self.warned += 1


@dataclass(frozen=True)
class PlannedRow:
    key: tuple
    decision: Decision
    dev_row: dict | None      # text-row pre-image, or None if absent on dev
    prod_row: dict | None     # text-row pre-image, or None if absent on prod


@dataclass(frozen=True)
class DriftReport:
    missing_on_dev: list       # tables that exist on prod only
    missing_on_prod: list      # tables that exist on dev only
    column_drift: dict         # table -> (dev_only_cols, prod_only_cols)

    @property
    def drifted_tables(self) -> set:
        return set(self.missing_on_dev) | set(self.missing_on_prod) | set(self.column_drift)


def table_drift(dev_cols: list, prod_cols: list) -> tuple:
    """Symmetric column-set difference. Both lists empty == in sync."""
    dev_set, prod_set = set(dev_cols), set(prod_cols)
    return (sorted(dev_set - prod_set), sorted(prod_set - dev_set))


def compute_drift(dev_schema_cols: dict, prod_schema_cols: dict) -> DriftReport:
    dev_tables, prod_tables = set(dev_schema_cols), set(prod_schema_cols)
    missing_on_dev = sorted(prod_tables - dev_tables)
    missing_on_prod = sorted(dev_tables - prod_tables)
    column_drift = {}
    for t in sorted(dev_tables & prod_tables):
        dev_only, prod_only = table_drift(dev_schema_cols[t], prod_schema_cols[t])
        if dev_only or prod_only:
            column_drift[t] = (dev_only, prod_only)
    return DriftReport(missing_on_dev, missing_on_prod, column_drift)


def parse_ts(text: str | None) -> datetime | None:
    """Parse a Postgres ::text timestamp/timestamptz literal. None on absent
    or unparseable input (caller treats that as 'no usable updated_at')."""
    if not text or text == "NULL":
        return None
    try:
        # asyncpg ::text output looks like '2026-07-24 10:00:00.123456+00' —
        # normalize to something datetime.fromisoformat accepts: space -> 'T',
        # and a bare 2-digit UTC offset -> '+00:00'.
        s = text.strip()
        s = re.sub(r"([+-]\d{2})$", r"\1:00", s)
        s = s.replace(" ", "T", 1)
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def decide_row(dev_row: dict | None, prod_row: dict | None, has_updated_at: bool) -> Decision:
    """Decide what happens to ONE tenant-owned (descended) row. Ascend-only
    rows never reach this function — merge_plan handles them first."""
    if dev_row is None and prod_row is None:
        raise ValueError("decide_row called with nothing on either side")
    if prod_row is None:
        return Decision("insert", "prod", "dev only")
    if dev_row is None:
        return Decision("insert", "dev", "prod only")
    if dev_row == prod_row:
        return Decision("noop", None, "identical")

    if has_updated_at:
        dev_ts = parse_ts(dev_row.get("updated_at"))
        prod_ts = parse_ts(prod_row.get("updated_at"))
        try:
            # dev_ts/prod_ts can be tz-aware on one side and naive on the
            # other if the column's type (timestamp vs timestamptz) drifted
            # between two hand-applied migrations — comparing them raises
            # TypeError. Treated the same as "unusable": falls through to
            # dev-wins below rather than aborting the whole sync mid-plan.
            comparable = dev_ts is not None and prod_ts is not None and dev_ts != prod_ts
        except TypeError:
            comparable = False
        if comparable:
            if dev_ts > prod_ts:
                return Decision("update", "prod", "dev newer (updated_at)")
            return Decision("update", "dev", "prod newer (updated_at)")
        return Decision(
            "update", "prod",
            "rows differ, updated_at tied or unusable — dev wins (source of truth)",
            warn=True,
        )
    return Decision(
        "update", "prod",
        "rows differ, table has no updated_at — dev wins (source of truth)",
        warn=True,
    )


def merge_plan(table: str, dev_side: dict, prod_side: dict, has_updated_at: bool):
    """dev_side / prod_side: {key: RowSnap}. Returns (list[PlannedRow], MergeStats)."""
    stats = MergeStats()
    planned = []
    for key in sorted(set(dev_side) | set(prod_side), key=repr):
        d = dev_side.get(key)
        p = prod_side.get(key)
        dev_row = d.row if d else None
        prod_row = p.row if p else None
        is_descended = (d.descend if d else False) or (p.descend if p else False)

        if not is_descended:
            # Shared/ascended row: insert-if-missing only, never overwritten —
            # this is what bounds the automated blast radius to tenant data.
            if dev_row is not None and prod_row is None:
                decision = Decision("insert", "prod", "ascended row missing on prod")
            elif prod_row is not None and dev_row is None:
                decision = Decision("insert", "dev", "ascended row missing on dev")
            else:
                decision = Decision("noop", None, "ascended row — never modified by sync")
        else:
            decision = decide_row(dev_row, prod_row, has_updated_at)

        stats.record(decision)
        planned.append(PlannedRow(key, decision, dev_row, prod_row))
    return planned, stats


def emit_upsert(table: str, cols: list, pk: list, source_row: dict, descended: bool, lit,
                 self_ref_cols: list | None = None) -> tuple:
    """One INSERT statement writing `source_row` onto the target table, plus
    an optional deferred fixup UPDATE. Descended (tenant-owned) rows get a
    real conflict-target DO UPDATE (idempotent re-apply). Ascended
    (shared-parent) rows get the target-less DO NOTHING export-dev-data.py
    already uses for exactly this reason — a secondary-unique collision on
    the target must not abort the whole sync.

    Self-referencing columns (e.g. employees.manager_id -> employees.id) are
    written NULL in the INSERT and patched by a deferred UPDATE after the
    row exists, exactly like export-dev-data.py's `emit()` — otherwise a
    fresh push of two rows that reference each other within the same table
    can fail a foreign key depending on iteration order. Returns
    (insert_sql, fixup_sql_or_None)."""
    self_ref_cols = self_ref_cols or []
    vals = []
    for c in cols:
        v = None if (c in self_ref_cols and source_row.get(c) is not None) else source_row.get(c)
        vals.append(lit(v))
    collist = ", ".join(f'"{c}"' for c in cols)
    if not descended:
        insert_sql = f'INSERT INTO "{table}" ({collist}) VALUES ({", ".join(vals)}) ON CONFLICT DO NOTHING;'
    else:
        conflict = "(" + ", ".join(f'"{p}"' for p in pk) + ")"
        sets = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in pk)
        if not sets:
            insert_sql = f'INSERT INTO "{table}" ({collist}) VALUES ({", ".join(vals)}) ON CONFLICT {conflict} DO NOTHING;'
        else:
            insert_sql = f'INSERT INTO "{table}" ({collist}) VALUES ({", ".join(vals)}) ON CONFLICT {conflict} DO UPDATE SET {sets};'

    fixup_sql = None
    if pk:
        fixup_sets = []
        for c in self_ref_cols:
            if source_row.get(c) is not None:
                fixup_sets.append(f'"{c}" = {lit(source_row[c])}')
        if fixup_sets:
            where = " AND ".join(f'"{p}" = {lit(source_row[p])}' for p in pk)
            fixup_sql = f'UPDATE "{table}" SET {", ".join(fixup_sets)} WHERE {where};'
    return insert_sql, fixup_sql


def emit_undo_for(table: str, pk: list, cols: list, target_preimage: dict | None, key_values: dict, lit,
                   descended: bool) -> str:
    """`target_preimage` is the TARGET side's row exactly as it was before
    this sync touched it (or None if the row wasn't reachable in the
    TARGET's own FK-walk snapshot — see the caveat below).
    None, descended row     -> the sync inserted a genuinely new row (both
             sides walk the same tenant-owned FK graph, so "not reachable"
             here really does mean "didn't exist") -> undo deletes it.
    None, ASCENDED row      -> emit_upsert used an untargeted
             `ON CONFLICT DO NOTHING`, specifically because an ascended row
             (e.g. a shared `users` row reached via a client/employee FK)
             may already exist on target under a key this run's target-side
             walk never reached (target's own FK graph can differ from
             source's — a cleared FK, a different assignee). `None` here
             means "not reachable", NOT "confirmed absent", so a DELETE
             could remove a real pre-existing target row the sync's insert
             merely no-op'd against. Skip the undo entirely rather than
             risk that.
    A row  -> the sync overwrote an existing row -> undo restores every
             column to its pre-sync value (more precise than a delete)."""
    where = " AND ".join(f'"{p}" = {lit(key_values[p])}' for p in pk)
    if target_preimage is None:
        if not descended:
            return (
                f'-- SKIPPED: ascended row "{table}" ({where}) not reachable in target\'s own '
                f"FK walk — its insert used ON CONFLICT DO NOTHING, so it may have been a "
                f"no-op against a real pre-existing row. Undo cannot safely tell; not deleting."
            )
        return f'DELETE FROM "{table}" WHERE {where};'
    sets = ", ".join(f'"{c}" = {lit(target_preimage.get(c))}' for c in cols if c not in pk)
    return f'UPDATE "{table}" SET {sets} WHERE {where};'


# ---------------------------------------------------------------------------
# DB-facing orchestration.
# ---------------------------------------------------------------------------

async def load_test_tenant_ids(dev_conn, prod_conn, dev_cols: dict, prod_cols: dict):
    """Union of `companies.id` where is_test, across both sides, keyed by
    UUID. Returns (ids: list[str], warnings: list[str])."""
    warnings = []
    ids = set()
    if "is_test" in dev_cols.get("companies", []):
        for r in await dev_conn.fetch("SELECT id::text AS id FROM companies WHERE is_test"):
            ids.add(r["id"])
    else:
        warnings.append("dev companies.is_test column missing — run migrate-dev.sh (testacct01)")
    if "is_test" in prod_cols.get("companies", []):
        for r in await prod_conn.fetch("SELECT id::text AS id FROM companies WHERE is_test"):
            ids.add(r["id"])
    else:
        warnings.append("prod companies.is_test column missing — run migrate-prod.sh (testacct01)")
    return sorted(ids), warnings


async def snapshot_side(conn, export_mod, cols, pks, fks, tenant_ids: list) -> tuple:
    """Walk the FK graph from each tenant's companies row on this connection
    and return (snapshot, collector, dropped).

    snapshot: {table: {key: RowSnap}} with every value already ::text-cast.
    dropped: {table: count} of rows the collector reached but whose str()-cast
        PK failed to match the ::text re-read (e.g. a float or citext column
        whose Python str() doesn't equal Postgres' ::text output). Those rows
        are silently absent from `snapshot` and therefore never sync in
        either direction unless the caller surfaces this count."""
    collector = export_mod.Collector(conn, cols, pks, fks, export_mod.DEFAULT_EXCLUDE)
    for tid in tenant_ids:
        row = await conn.fetchrow("SELECT * FROM companies WHERE id = $1", tid)
        if row is None:
            continue  # tenant exists on the other side only; nothing to ascend/descend here
        await collector.collect("companies", dict(row), descend=True)

    snapshot: dict = {}
    dropped: dict = {}
    for table, rows in collector.rows.items():
        if not rows:
            continue
        pk = pks.get(table)
        if not pk:
            continue  # no-PK tables can't be idempotently synced either direction
        table_cols = cols[table]
        keys = list(rows.keys())
        text_rows = await export_mod.fetch_as_text(conn, table, table_cols, pk, keys)
        by_key = {tuple(str(r[c]) for c in pk): r for r in text_rows}
        present = {
            key: RowSnap(row=by_key[tuple(str(v) for v in key)], descend=descend)
            for key, (_, descend) in rows.items()
            if tuple(str(v) for v in key) in by_key
        }
        miss = len(rows) - len(present)
        if miss:
            dropped[table] = miss
        snapshot[table] = present
    return snapshot, collector, dropped


async def run_sync(dev_dsn: str, prod_dsn: str, out_dir: Path, quiet: bool = False) -> int:
    export_mod = _load_export_dev_data()
    log = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))

    dev_conn = await asyncpg.connect(dev_dsn)
    prod_conn = await asyncpg.connect(prod_dsn)
    try:
        dev_cols, dev_pks, dev_fks, _ = await export_mod.load_schema(dev_conn)
        prod_cols, prod_pks, prod_fks, _ = await export_mod.load_schema(prod_conn)

        drift = compute_drift(dev_cols, prod_cols)
        if drift.drifted_tables:
            log(f"DRIFT: {len(drift.drifted_tables)} table(s) skipped (schema mismatch):")
            for t in sorted(drift.missing_on_prod):
                log(f"  DRIFT: {t} — exists on dev only (migrate-prod.sh not yet run)")
            for t in sorted(drift.missing_on_dev):
                log(f"  DRIFT: {t} — exists on prod only")
            for t, (dev_only, prod_only) in sorted(drift.column_drift.items()):
                log(f"  DRIFT: {t} — dev-only cols {dev_only}, prod-only cols {prod_only}")

        # A drifted `companies` table means the tenant-scoping root itself is
        # inconsistent between sides (e.g. dev has is_test, prod hasn't run
        # testacct01 yet). Every OTHER table is FK-anchored to companies but
        # is NOT in drifted_tables (only columns differ, not existence), so
        # without this check their rows would still be planned for insert —
        # landing on prod with no parent companies row to reference and
        # aborting the whole transaction on FK violation.
        if "companies" in drift.drifted_tables:
            log("DRIFT: companies itself is drifted — sync skipped entirely. "
                "Child rows would be pushed without their parent companies row "
                "and abort the whole transaction on FK. Run the pending "
                "migration (migrate-dev.sh / migrate-prod.sh) on the lagging "
                "side first.")
            _write_outputs(out_dir, [], [], [], [])
            return 2

        tenant_ids, tenant_warnings = await load_test_tenant_ids(dev_conn, prod_conn, dev_cols, prod_cols)
        for w in tenant_warnings:
            log(f"WARN: {w}")
        if not tenant_ids:
            log("WARN: no is_test tenants found on either side — nothing to sync")
            _write_outputs(out_dir, [], [], [], [])
            return 0 if not drift.drifted_tables else 2

        dev_snap, dev_collector, dev_dropped = await snapshot_side(dev_conn, export_mod, dev_cols, dev_pks, dev_fks, tenant_ids)
        prod_snap, prod_collector, prod_dropped = await snapshot_side(prod_conn, export_mod, prod_cols, prod_pks, prod_fks, tenant_ids)
        dropped_total = 0
        for side, dmap in (("dev", dev_dropped), ("prod", prod_dropped)):
            for t, n in sorted(dmap.items()):
                log(f"WARN: {side} {t}: {n} row(s) dropped from snapshot — PK text-cast mismatch (will not sync)")
                dropped_total += n

        # Preserve RAW (pre-scrub) snapshots before normalize_emails mutates
        # dev_snap/prod_snap in place. normalize_emails' scrubbed values are
        # correct for BOTH comparison (dev/prod must fold through the same
        # mapping to converge) AND the value actually WRITTEN to a target
        # (a real-looking email can't land on prod — GUARD 2 in
        # seed-prod.sh would block it). But an undo's target_preimage must
        # restore what that side genuinely had before this sync touched it —
        # using the scrubbed value there would restore a scrubbed email onto
        # a row that may have held a real-looking demo address (is_test
        # companies are deliberately NOT email-scrubbed by anonymize_dev.sql
        # — see its header note). Keys are untouched by normalize_emails
        # (only RowSnap.row values change), so raw/normalized snapshots stay
        # lookup-compatible by the same key.
        dev_snap_raw = {t: dict(rows) for t, rows in dev_snap.items()}
        prod_snap_raw = {t: dict(rows) for t, rows in prod_snap.items()}

        def raw_row(raw_snap, table, key):
            entry = raw_snap.get(table, {}).get(key)
            return entry.row if entry else None

        scrub, mapping = export_mod.make_email_scrubber()

        def normalize_emails(snap):
            for table, rows in snap.items():
                for key, snap_row in rows.items():
                    new_row = {
                        c: export_mod.EMAIL.sub(scrub, v) if isinstance(v, str) else v
                        for c, v in snap_row.row.items()
                    }
                    rows[key] = RowSnap(row=new_row, descend=snap_row.descend)

        normalize_emails(dev_snap)
        normalize_emails(prod_snap)
        if mapping:
            log(f"WARN: {len(mapping)} email(s) normalized for comparison (scrubbed to @example.com)")

        tables = sorted((set(dev_snap) | set(prod_snap)) - drift.drifted_tables)
        to_prod_lines, to_dev_lines = [], []
        to_prod_undo, to_dev_undo = [], []
        total_stats = MergeStats()

        # Self-referencing FK columns (e.g. employees.manager_id ->
        # employees.id) are written NULL then patched by a deferred UPDATE —
        # same reason export-dev-data.py does it: two rows in the same table
        # that reference each other can otherwise fail a foreign key
        # depending on which one this run happens to emit first.
        self_ref = {}
        for fk in dev_fks:
            if fk["child"] == fk["parent"]:
                self_ref.setdefault(fk["child"], []).append(fk["child_col"])

        # Parents before children, using dev's FK graph (drifted tables are
        # already excluded, so surviving tables share structure by assumption).
        order, cyclic = export_mod.topo_order(tables, dev_fks)
        if cyclic:
            log(f"WARN: FK cycle among {sorted(set(cyclic))} — ordering is best-effort")

        for table in order:
            dev_side = dev_snap.get(table, {})
            prod_side = prod_snap.get(table, {})
            if not dev_side and not prod_side:
                continue
            pk = dev_pks.get(table) or prod_pks.get(table)
            cols = dev_cols.get(table) or prod_cols.get(table)
            has_updated_at = "updated_at" in cols
            planned, stats = merge_plan(table, dev_side, prod_side, has_updated_at)
            table_self_ref = self_ref.get(table, [])
            prod_fixups, dev_fixups = [], []

            for p in planned:
                if p.decision.warn:
                    log(f"WARN: {table} {p.key}: {p.decision.reason}")
                if p.decision.action == "noop":
                    continue
                descended = bool(
                    (dev_side.get(p.key) and dev_side[p.key].descend)
                    or (prod_side.get(p.key) and prod_side[p.key].descend)
                )
                if p.decision.target == "prod":
                    source_row = p.dev_row
                    target_preimage = raw_row(prod_snap_raw, table, p.key)
                    key_values = dict(zip(pk, p.key))
                    insert_sql, fixup_sql = emit_upsert(table, cols, pk, source_row, descended, export_mod.lit, table_self_ref)
                    to_prod_lines.append(insert_sql)
                    if fixup_sql:
                        prod_fixups.append(fixup_sql)
                    to_prod_undo.append(emit_undo_for(table, pk, cols, target_preimage, key_values, export_mod.lit, descended))
                else:
                    source_row = p.prod_row
                    target_preimage = raw_row(dev_snap_raw, table, p.key)
                    key_values = dict(zip(pk, p.key))
                    insert_sql, fixup_sql = emit_upsert(table, cols, pk, source_row, descended, export_mod.lit, table_self_ref)
                    to_dev_lines.append(insert_sql)
                    if fixup_sql:
                        dev_fixups.append(fixup_sql)
                    to_dev_undo.append(emit_undo_for(table, pk, cols, target_preimage, key_values, export_mod.lit, descended))

            if prod_fixups:
                to_prod_lines.append(f"-- {table}: self-references, applied after the rows exist")
                to_prod_lines.extend(prod_fixups)
            if dev_fixups:
                to_dev_lines.append(f"-- {table}: self-references, applied after the rows exist")
                to_dev_lines.extend(dev_fixups)

            total_stats.inserted_to_prod += stats.inserted_to_prod
            total_stats.inserted_to_dev += stats.inserted_to_dev
            total_stats.updated_to_prod += stats.updated_to_prod
            total_stats.updated_to_dev += stats.updated_to_dev
            total_stats.noop += stats.noop
            total_stats.warned += stats.warned
    finally:
        await dev_conn.close()
        await prod_conn.close()

    _write_outputs(out_dir, to_prod_lines, to_prod_undo, to_dev_lines, to_dev_undo)

    log(
        f"\nsync_to_prod: {total_stats.inserted_to_prod} insert, {total_stats.updated_to_prod} update\n"
        f"sync_to_dev:  {total_stats.inserted_to_dev} insert, {total_stats.updated_to_dev} update\n"
        f"noop: {total_stats.noop}   warned: {total_stats.warned}   dropped: {dropped_total}"
    )
    return 2 if (drift.drifted_tables or total_stats.warned or dropped_total) else 0


def _write_outputs(out_dir: Path, to_prod_lines: list, to_prod_undo: list,
                    to_dev_lines: list, to_dev_undo: list) -> None:
    """Write all four output files. MUST run on every run_sync exit path that
    returns 0/2 — the shell wrapper (sync-test-tenants.sh) greps these files
    with has_mutations() and would otherwise re-apply LAST run's stale diff
    to prod on a run that found nothing new to sync."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_sql(out_dir / "sync_to_prod.sql", to_prod_lines, "dev -> prod")
    _write_sql(out_dir / "sync_to_prod.undo.sql", list(reversed(to_prod_undo)), "undo: dev -> prod")
    _write_sql(out_dir / "sync_to_dev.sql", to_dev_lines, "prod -> dev")
    _write_sql(out_dir / "sync_to_dev.undo.sql", list(reversed(to_dev_undo)), "undo: prod -> dev")


def _write_sql(path: Path, lines: list, label: str):
    header = (
        f"-- Generated by scripts/sync_tenants.py — do not hand-edit.\n"
        f"-- Direction: {label}\n"
        f"-- No BEGIN/COMMIT here; scripts/seed-prod.sh owns the transaction envelope.\n\n"
    )
    path.write_text(header + "\n".join(lines) + ("\n" if lines else ""))


async def _main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev-dsn", default=os.getenv("DEV_DATABASE_URL", "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha"))
    ap.add_argument("--prod-dsn", default=os.getenv("PROD_DATABASE_URL"))
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "scripts" / "sql"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    if not args.prod_dsn:
        print("!! --prod-dsn or PROD_DATABASE_URL required", file=sys.stderr)
        return 1
    return await run_sync(args.dev_dsn, args.prod_dsn, Path(args.out_dir), quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
