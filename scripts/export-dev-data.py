#!/usr/bin/env python3
"""Export dev rows as SQL for prod — whole test tenants, or whole tables.

FOR THE THREE TEST TENANTS, DON'T CALL THIS DIRECTLY — use the wrapper:

    ./scripts/sync-test-tenants.sh           # show what would change
    ./scripts/sync-test-tenants.sh --apply   # do it

This script is the engine underneath, for anything the wrapper does not cover:

    ./scripts/export-dev-data.py --tenant "Some Company" --table admin_updates \
                                 --mode update --scrub-emails \
                                 --out scripts/sql/push.sql
    ./scripts/seed-prod.sh scripts/sql/push.sql --dry-run   # always first
    ./scripts/seed-prod.sh scripts/sql/push.sql

It NEVER touches prod. It reads dev and writes a .sql file (plus a .undo.sql).
`seed-prod.sh` remains the single path that writes to prod, so its guardrails —
DDL block, reserved-email block, single-transaction envelope, rehearsal, typed
confirm — all still apply. A second prod-write path would be a second,
less-guarded one.

NOTHING IS EVER DELETED
    A prod row this export does not mention is untouched, in either mode. What
    differs is what happens to a row prod already has:

      --mode skip    (default) prod wins — the row is left exactly as prod has
                     it. Purely additive.
      --mode update  dev wins — the row is refreshed from dev. Correct for TEST
                     tenants, where dev is the source of truth and the point of
                     the sync is that dev has newer data. Wrong for anything
                     real, which is why it is not the default.

HOW A TENANT IS COLLECTED
    Start at the companies row, then walk the live foreign-key graph:

      DESCEND  from a collected row into every table that references it
               (company_id, org_id, and any other FK — the graph is read from
               pg_constraint, not from a hand-kept list, so a new table with a
               company FK is picked up the day it lands).

      ASCEND   from a collected row into the rows it references, because the
               INSERT would otherwise fail a foreign key on prod (a client row
               needs its users row). Ascended rows are NEVER descended from —
               that is the rule that bounds the walk. Without it, one tenant
               reaches its broker, and the broker reaches every other client
               that broker has.

    Shared catalogs (jurisdictions, compliance categories, …) are assumed to
    exist on prod already and are not exported; anything skipped is reported so
    a genuinely missing parent shows up as a line to read rather than a foreign
    key error twenty minutes later.

KNOWN SHARP EDGES
    - seed-prod.sh greps the WHOLE file for DDL keywords, string literals
      included. Tenant prose containing "create" or "drop" trips GUARD 1. This
      script warns when that will happen; read the hits, then pass --allow-ddl
      to seed-prod.sh once you have confirmed they are all inside data.
    - Dev demo tenants are full of realistic fake domains (@360bh.org,
      @nexuscorp.com) that resolve in DNS. On prod those are reachable by the
      invitation and reminder senders — the 2026-05-15 bounce storm. Use
      --scrub-emails; --allow-real-emails on seed-prod.sh is the wrong lever.
    - The .undo.sql deletes the exported rows outright. Two caveats: a row that
      already existed on prod was skipped by the insert but WILL be deleted by
      the undo, so only undo a tenant prod did not previously have; and a delete
      fails if some table outside the export references an exported row (shared
      templates pointing at tenant research logs do this), which has to be
      resolved by hand.

VALIDATION
    Dry-running against dev proves the SQL parses and every value round-trips,
    but not that the ordering is right — the rows are already there, so every
    insert is a no-op. To prove insert order, delete and re-insert inside one
    rolled-back transaction:

        { echo "BEGIN;";
          echo "SET session_replication_role = replica;";  cat push.undo.sql
          echo "SET session_replication_role = origin;";   cat push.sql
          echo "ROLLBACK;"; } | psql "$DEV_DSN" -v ON_ERROR_STOP=1

    (Triggers are off for the delete half only, because undo order cannot
    satisfy references from outside the export; the insert half runs with
    foreign keys fully enforced, which is the half under test.)

    The real gate is still `seed-prod.sh --dry-run` against prod: there the rows
    are absent, so every insert actually executes before the rollback.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from datetime import date

import asyncpg

DEFAULT_DSN = "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha"

# Shared reference data. Present on prod already, enormous, and not tenant-owned
# — exporting it would bloat the file and risk clobbering catalog rows that prod
# has legitimately moved past. Skipped as ASCEND targets, and reported.
GLOBAL_TABLES = {
    "jurisdictions",
    "jurisdiction_requirements",
    "compliance_categories",
    "business_categories",
    "industry_specialties",
    "authority_index_items",
    "platform_settings",
    "scheduler_settings",
    "matcha_lite_pricing",
    "alembic_version",
    # Shared research ledger, NOT tenant data. It is keyed
    # (jurisdiction, industry_tag, category) and merely stamped with whichever
    # tenant triggered the fill, so it has a company FK and looks tenant-scoped
    # to the graph walk. Copying it would tell prod a cell is already
    # researched while prod's catalog has none of the rows — and the sweep
    # would then skip exactly the research prod still needs.
    "jurisdiction_vertical_coverage",
}

# Never worth carrying to prod: telemetry and infrastructure bookkeeping. A demo
# tenant does not need 3,000 usage_events rows, and replaying webhook-event ids
# would poison the real dedupe table.
DEFAULT_EXCLUDE = {
    "usage_events",
    "stripe_webhook_events",
    "admin_updates_backup",
}

# Table-specific SQL appended after the inserts. admin_updates renders in
# `position` order, and dev positions were assigned against dev's own row set —
# inserting them next to prod's would interleave wrongly. Re-deriving from date
# is idempotent and matches how the changelog is meant to read.
POST_HOOKS = {
    "admin_updates": """
-- Re-derive changelog ordering across the merged row set (dev positions were
-- assigned against dev's rows only, so they cannot be trusted next to prod's).
WITH ordered AS (
    SELECT id, (row_number() OVER (ORDER BY date DESC, position ASC)) - 1 AS rn
    FROM admin_updates
)
UPDATE admin_updates a SET position = o.rn FROM ordered o WHERE a.id = o.id;
""".strip(),
}

RESERVED_EMAIL = re.compile(
    r"@(example\.(com|org|net)|[a-z0-9.-]+\.(test|invalid|localhost))$", re.I
)
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
DDL_WORD = re.compile(r"\b(create|drop|alter|truncate|grant|revoke)\b", re.I)

# "skip"   — additive only; a row prod already has is left exactly as prod has it.
# "update" — dev wins on rows this export mentions. Correct for TEST tenants,
#            where dev is the source of truth. Never deletes either way: a prod
#            row this export does not mention is untouched in both modes.
MODE = "skip"


# --------------------------------------------------------------------------- #
# Schema introspection
# --------------------------------------------------------------------------- #
async def load_schema(conn):
    """Columns, primary keys and single-column foreign keys for public.*"""
    cols = defaultdict(list)
    for r in await conn.fetch(
        """
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN pg_tables t ON t.tablename = c.table_name AND t.schemaname = 'public'
        WHERE c.table_schema = 'public'
          AND c.is_generated = 'NEVER'
          AND c.identity_generation IS DISTINCT FROM 'ALWAYS'
        ORDER BY c.ordinal_position
        """
    ):
        cols[r["table_name"]].append(r["column_name"])

    pks = {}
    for r in await conn.fetch(
        """
        SELECT c.conrelid::regclass::text AS tbl,
               array_agg(a.attname ORDER BY k.ord) AS cols
        FROM pg_constraint c
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'p' AND c.connamespace = 'public'::regnamespace
        GROUP BY 1
        """
    ):
        pks[r["tbl"].replace("public.", "").strip('"')] = list(r["cols"])

    # Single-column FKs only. Composite FKs are rare here and a half-followed
    # composite edge is worse than a reported one.
    fks, composite = [], []
    for r in await conn.fetch(
        """
        SELECT c.conname,
               c.conrelid::regclass::text  AS child,
               c.confrelid::regclass::text AS parent,
               array_agg(ac.attname ORDER BY k.ord) AS child_cols,
               array_agg(ap.attname ORDER BY k.ord) AS parent_cols
        FROM pg_constraint c
        JOIN LATERAL unnest(c.conkey)  WITH ORDINALITY k(attnum, ord)  ON true
        JOIN LATERAL unnest(c.confkey) WITH ORDINALITY k2(attnum, ord) ON k2.ord = k.ord
        JOIN pg_attribute ac ON ac.attrelid = c.conrelid  AND ac.attnum = k.attnum
        JOIN pg_attribute ap ON ap.attrelid = c.confrelid AND ap.attnum = k2.attnum
        WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
        GROUP BY c.conname, c.conrelid, c.confrelid
        """
    ):
        clean = lambda t: t.replace("public.", "").strip('"')  # noqa: E731
        if len(r["child_cols"]) != 1:
            composite.append((clean(r["child"]), clean(r["parent"]), r["conname"]))
            continue
        fks.append({
            "child": clean(r["child"]), "child_col": r["child_cols"][0],
            "parent": clean(r["parent"]), "parent_col": r["parent_cols"][0],
        })
    return cols, pks, fks, composite


# --------------------------------------------------------------------------- #
# Row collection
# --------------------------------------------------------------------------- #
class Collector:
    def __init__(self, conn, cols, pks, fks, exclude):
        self.conn, self.cols, self.pks, self.fks = conn, cols, pks, fks
        self.exclude = exclude
        self.rows = defaultdict(dict)          # table -> pk tuple -> row
        self.children = defaultdict(list)      # parent table -> [fk]
        self.parents = defaultdict(list)       # child table -> [fk]
        for fk in fks:
            self.children[fk["parent"]].append(fk)
            self.parents[fk["child"]].append(fk)
        self.skipped_global = defaultdict(set)
        self.skipped_excluded = defaultdict(int)

    def _key(self, table, row):
        pk = self.pks.get(table)
        if not pk:
            # No primary key: fall back to the full row, so a table without one
            # still de-duplicates instead of being emitted once per path to it.
            return tuple(sorted((k, str(v)) for k, v in row.items()))
        return tuple(row[c] for c in pk)

    async def collect(self, table, row, descend):
        key = self._key(table, row)
        seen = self.rows[table]
        if key in seen:
            # Already have it. Upgrade an ascend-only visit to a descend if this
            # path warrants it, otherwise stop.
            if not descend or seen[key][1]:
                return
            seen[key] = (seen[key][0], True)
        else:
            seen[key] = (row, descend)

        # ASCEND — parents first, or the INSERT fails a foreign key on prod.
        for fk in self.parents[table]:
            val = row.get(fk["child_col"])
            if val is None:
                continue
            if fk["parent"] in GLOBAL_TABLES:
                self.skipped_global[fk["parent"]].add(str(val))
                continue
            if fk["parent"] in self.exclude:
                continue
            if fk["parent"] == table:
                continue  # self-reference: handled by the deferred UPDATE pass
            prow = await self.conn.fetchrow(
                f'SELECT * FROM "{fk["parent"]}" WHERE "{fk["parent_col"]}" = $1', val
            )
            if prow:
                await self.collect(fk["parent"], dict(prow), descend=False)

        if not descend:
            return

        # DESCEND — every table that references this row.
        pk = self.pks.get(table)
        for fk in self.children[table]:
            child = fk["child"]
            if child in self.exclude:
                continue
            if child in GLOBAL_TABLES:
                continue
            if not pk or fk["parent_col"] not in row:
                continue
            crows = await self.conn.fetch(
                f'SELECT * FROM "{child}" WHERE "{fk["child_col"]}" = $1',
                row[fk["parent_col"]],
            )
            for crow in crows:
                await self.collect(child, dict(crow), descend=True)


# --------------------------------------------------------------------------- #
# Emission
# --------------------------------------------------------------------------- #
def topo_order(tables, fks):
    """Parents before children. Cycles are broken deterministically by name and
    reported by the caller, since a cycle means some FK will be satisfied only
    after the whole file has run."""
    deps = {t: set() for t in tables}
    for fk in fks:
        if fk["child"] in deps and fk["parent"] in deps and fk["child"] != fk["parent"]:
            deps[fk["child"]].add(fk["parent"])
    out, done, cyclic = [], set(), []
    while len(done) < len(tables):
        ready = sorted(t for t in tables if t not in done and deps[t] <= done)
        if not ready:
            stuck = sorted(t for t in tables if t not in done)
            cyclic.extend(stuck)
            ready = [stuck[0]]
        for t in ready:
            out.append(t)
            done.add(t)
    return out, cyclic


def lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


async def fetch_as_text(conn, table, cols, pk, keys):
    """Re-read the collected rows with every column cast to text.

    Python's str() is not Postgres' output syntax: asyncpg decodes a text[] to a
    Python list, whose repr is ['a', 'b'] — which Postgres rejects as a
    malformed array literal on the way back in. Casting server-side means every
    type (arrays, jsonb, bytea, ranges, timestamps) round-trips in exactly the
    form its own input parser expects.
    """
    sel = ", ".join(f'"{c}"::text AS "{c}"' for c in cols)
    if len(pk) == 1:
        rows = await conn.fetch(
            f'SELECT {sel} FROM "{table}" WHERE "{pk[0]}"::text = ANY($1::text[])',
            [str(k[0]) for k in keys],
        )
    else:
        tup = ", ".join(f'"{c}"::text' for c in pk)
        vals = ", ".join(
            "(" + ", ".join(f"${i * len(pk) + j + 1}" for j in range(len(pk))) + ")"
            for i in range(len(keys))
        )
        flat = [str(v) for k in keys for v in k]
        rows = await conn.fetch(f'SELECT {sel} FROM "{table}" WHERE ({tup}) IN ({vals})', *flat)
    return [dict(r) for r in rows]


async def emit(conn, collector, order, self_ref_cols, targets_desc):
    lines, undo, stats, no_pk = [], [], [], []
    for table in order:
        rows = collector.rows.get(table)
        if not rows:
            continue
        cols = [c for c in collector.cols[table]]
        deferred = self_ref_cols.get(table, [])
        pk = collector.pks.get(table)
        conflict = f'({", ".join(chr(34) + c + chr(34) for c in pk)})' if pk else ""

        if not pk:
            # Without a primary key there is no conflict target, so the insert
            # could not be made idempotent and a re-run would duplicate.
            no_pk.append((table, len(rows)))
            continue
        text_rows = await fetch_as_text(conn, table, cols, pk, list(rows.keys()))

        lines.append(f"\n-- {table} ({len(text_rows)} rows)")
        fixups = []
        for row in text_rows:
            vals = []
            for c in cols:
                # Self-referencing columns are written NULL now and patched
                # after the table is fully inserted, so a parent row that comes
                # later in the same table cannot break the insert.
                v = None if (c in deferred and row.get(c) is not None) else row.get(c)
                vals.append(lit(v))
            collist = ", ".join(f'"{c}"' for c in cols)
            if MODE == "update":
                # Test tenants: dev is the source of truth, so a row prod
                # already has is refreshed rather than skipped. Still never
                # deletes — a prod row this export does not mention is
                # untouched.
                sets = ", ".join(
                    f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in pk
                )
                lines.append(
                    f'INSERT INTO "{table}" ({collist}) VALUES ({", ".join(vals)})'
                    + (f' ON CONFLICT {conflict} DO UPDATE SET {sets};' if sets
                       else f' ON CONFLICT {conflict} DO NOTHING;')
                )
            else:
                # Target-less ON CONFLICT on purpose: naming the primary key
                # would guard only that one constraint, and a row colliding on
                # a SECONDARY unique index (a users row with the same email
                # under a different id) would still raise and abort the whole
                # transaction on prod. Untargeted means "skip anything that
                # collides with what prod already has".
                lines.append(
                    f'INSERT INTO "{table}" ({collist}) VALUES ({", ".join(vals)})'
                    f' ON CONFLICT DO NOTHING;'
                )
            for c in deferred:
                if row.get(c) is not None and pk:
                    where = " AND ".join(f'"{p}" = {lit(row[p])}' for p in pk)
                    fixups.append(
                        f'UPDATE "{table}" SET "{c}" = {lit(row[c])} WHERE {where};'
                    )
        if fixups:
            lines.append(f"-- {table}: self-references, applied after the rows exist")
            lines.extend(fixups)
        if table in POST_HOOKS:
            lines.append("")
            lines.append(POST_HOOKS[table])
        stats.append((table, len(text_rows)))

        for row in text_rows:
            where = " AND ".join(f'"{p}" = {lit(row[p])}' for p in pk)
            undo.append(f'DELETE FROM "{table}" WHERE {where};')
    undo.reverse()  # children before parents
    return lines, undo, stats, no_pk


# --------------------------------------------------------------------------- #
async def main():
    ap = argparse.ArgumentParser(
        description="Export dev rows as additive SQL for seed-prod.sh",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("WHAT")[0],
    )
    ap.add_argument("--tenant", action="append", default=[],
                    help="Company name (exact, case-insensitive) or UUID. Repeatable.")
    ap.add_argument("--table", action="append", default=[],
                    help="Copy a whole table additively (e.g. admin_updates). Repeatable.")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Extra table to skip. Repeatable.")
    ap.add_argument("--mode", choices=("skip", "update"), default="skip",
                    help="skip (default): purely additive, prod wins on any row it "
                         "already has. update: dev wins on the rows in this export — "
                         "correct for test tenants, wrong for anything real. Neither "
                         "mode ever deletes.")
    ap.add_argument("--scrub-emails", action="store_true",
                    help="Rewrite every non-reserved email address to <local>@example.com "
                         "(deterministic, so the same address maps the same way everywhere). "
                         "Dev demo tenants are full of realistic fake domains that resolve in "
                         "DNS; on prod those are reachable by the invitation and reminder "
                         "senders. Use this unless you have a reason not to.")
    ap.add_argument("--out", help="Output .sql path (default: scripts/sql/push_dev_<date>.sql)")
    ap.add_argument("--dsn", default=os.getenv("DEV_DATABASE_URL", DEFAULT_DSN))
    args = ap.parse_args()

    global MODE
    MODE = args.mode

    if not args.tenant and not args.table:
        ap.error("nothing to export — pass --tenant and/or --table")

    out = args.out or f"scripts/sql/push_dev_{date.today().isoformat()}.sql"
    exclude = DEFAULT_EXCLUDE | set(args.exclude)

    conn = await asyncpg.connect(args.dsn)
    try:
        cols, pks, fks, composite = await load_schema(conn)
        collector = Collector(conn, cols, pks, fks, exclude)
        targets_desc = []

        for t in args.tenant:
            if re.fullmatch(r"[0-9a-f-]{36}", t, re.I):
                row = await conn.fetchrow("SELECT * FROM companies WHERE id = $1", t)
            else:
                row = await conn.fetchrow("SELECT * FROM companies WHERE lower(name) = lower($1)", t)
            if not row:
                print(f"!! no company matched {t!r}", file=sys.stderr)
                return 1
            print(f"   collecting tenant {row['name']} ({row['id']}) …", file=sys.stderr)
            await collector.collect("companies", dict(row), descend=True)
            targets_desc.append(f"tenant {row['name']} ({row['id']})")

        for t in args.table:
            if t not in cols:
                print(f"!! no such table: {t}", file=sys.stderr)
                return 1
            rows = await conn.fetch(f'SELECT * FROM "{t}"')
            print(f"   collecting table {t} ({len(rows)} rows) …", file=sys.stderr)
            for r in rows:
                await collector.collect(t, dict(r), descend=False)
            targets_desc.append(f"table {t} ({len(rows)} rows)")

        self_ref = defaultdict(list)
        for fk in fks:
            if fk["child"] == fk["parent"]:
                self_ref[fk["child"]].append(fk["child_col"])

        present = [t for t in collector.rows if collector.rows[t]]
        order, cyclic = topo_order(present, fks)
        body, undo, stats, no_pk = await emit(conn, collector, order, self_ref, targets_desc)
    finally:
        await conn.close()

    # Scrub before the file is written, so the .sql on disk is the thing that
    # gets reviewed and applied — no "remember to also pass the flag" step.
    scrubbed = 0
    if args.scrub_emails:
        mapping: dict[str, str] = {}

        def _scrub(m):
            nonlocal scrubbed
            addr = m.group(0)
            if RESERVED_EMAIL.search(addr):
                return addr
            if addr not in mapping:
                # The domain has to survive into the local part or the mapping
                # stops being injective: amara.osei@360bh.com and
                # amara.osei@360bh.org would both become amara.osei@example.com
                # and collide on users_email_key.
                local, domain = addr.split("@", 1)
                slug = re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")
                mapping[addr] = f"{local}+{slug}@example.com"
            scrubbed += 1
            return mapping[addr]

        body = [EMAIL.sub(_scrub, line) for line in body]
        undo = [EMAIL.sub(_scrub, line) for line in undo]
        targets_desc.append(
            f"emails scrubbed: {len(mapping)} distinct non-reserved addresses "
            f"rewritten to @example.com"
        )

    header = [
        "-- Additive export from DEV. Generated by scripts/export-dev-data.py —",
        "-- do not hand-edit; re-run the generator instead.",
        "--",
        "-- Exported:",
        *[f"--   {d}" for d in targets_desc],
        "--",
        "-- Every statement is INSERT … ON CONFLICT DO NOTHING: rows that already",
        "-- exist on prod are left exactly as prod has them. Nothing is updated or",
        "-- deleted. Apply with:",
        "--   ./scripts/seed-prod.sh <this file> --dry-run",
        "--   ./scripts/seed-prod.sh <this file>",
    ]
    with open(out, "w") as f:
        f.write("\n".join(header) + "\n" + "\n".join(body) + "\n")
    undo_path = out[:-4] + ".undo.sql"
    with open(undo_path, "w") as f:
        f.write(
            "-- Undo for " + os.path.basename(out) + "\n"
            "-- WARNING: deletes every exported row, including any that already\n"
            "-- existed on prod (the insert skipped those, this does not). Only\n"
            "-- run for a tenant that prod did not have before the push.\n\n"
            + "\n".join(undo) + "\n"
        )

    # ---- report ----------------------------------------------------------- #
    total = sum(n for _, n in stats)
    print(f"\n  wrote {out}", file=sys.stderr)
    print(f"        {undo_path}", file=sys.stderr)
    print(f"\n  {total} rows across {len(stats)} tables:", file=sys.stderr)
    for t, n in sorted(stats, key=lambda s: -s[1])[:20]:
        print(f"     {n:>7}  {t}", file=sys.stderr)
    if len(stats) > 20:
        print(f"     …and {len(stats) - 20} more tables", file=sys.stderr)

    if no_pk:
        print("\n  !! tables skipped — no primary key, so the insert could not be made",
              file=sys.stderr)
        print("     idempotent and a re-run would duplicate rows:", file=sys.stderr)
        for t, n in no_pk:
            print(f"     {t} ({n} rows)", file=sys.stderr)

    if collector.skipped_global:
        print("\n  shared catalogs referenced but NOT exported (assumed present on prod):",
              file=sys.stderr)
        for t, ids in sorted(collector.skipped_global.items()):
            print(f"     {t} ({len(ids)} distinct ids)", file=sys.stderr)
    if composite:
        print(f"\n  {len(composite)} composite FKs not followed:", file=sys.stderr)
        for c, p, n in composite[:5]:
            print(f"     {c} -> {p} ({n})", file=sys.stderr)
    if cyclic:
        print(f"\n  !! FK cycle among: {', '.join(sorted(set(cyclic)))}", file=sys.stderr)
        print("     ordering is best-effort; check the dry run.", file=sys.stderr)

    sql = open(out).read()
    bad = sorted({e for e in EMAIL.findall(sql) if not RESERVED_EMAIL.search(e)})
    if bad:
        print(f"\n  !! {len(bad)} non-reserved email domain(s) — seed-prod.sh GUARD 2 will",
              file=sys.stderr)
        print("     abort unless you pass --allow-real-emails:", file=sys.stderr)
        for e in bad[:10]:
            print(f"     {e}", file=sys.stderr)
    ddl = sorted({m.group(0).lower() for m in DDL_WORD.finditer(re.sub(r"--.*", "", sql))})
    if ddl:
        print(f"\n  !! DDL keyword(s) appear in the data ({', '.join(ddl)}) — seed-prod.sh",
              file=sys.stderr)
        print("     GUARD 1 greps string literals too. Read the hits, then use --allow-ddl",
              file=sys.stderr)
        print("     if every one of them is inside data.", file=sys.stderr)

    print("\n  next:  ./scripts/seed-prod.sh " + out + " --dry-run", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
