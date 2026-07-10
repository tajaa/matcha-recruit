#!/usr/bin/env python3
"""
Populate the scope-registry tables on the current DB (dev).

Ingests the authority catalog (curated CA slices + us-flsa; optionally the
enumerable federal eCFR parts), applies the citation-anchored seed, and confirms
the seed classifications so ``resolve_scope`` / the Scope Studio panels show real
data. Direct service calls — the admin API only dispatches Celery (a worker may
be off locally) and ``confirm_classifications`` runs the strata recompute inline.

Usage:
    python scripts/populate_scope_registry.py                       # + eCFR (network)
    python scripts/populate_scope_registry.py --curated-only        # offline
    python scripts/populate_scope_registry.py --admin-email me@x.com # pick the confirmer
    python scripts/populate_scope_registry.py --classify            # Gemini-classify remainder

Every step is idempotent: ingest upserts on (index, citation), the seed skips an
item that already has a classification, and confirm only touches provisional
seed rows. Safe to re-run. Targets whatever DATABASE_URL points at — intended
for the local dev DB, NOT prod.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SKIP_REDIS", "1")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Populate the scope registry on the current DB")
    parser.add_argument("--curated-only", action="store_true",
                        help="Skip the federal eCFR ingest (no network) — curated indexes only")
    parser.add_argument("--admin-email", default=None,
                        help="Email of the admin user recorded as confirmed_by (default: first admin)")
    parser.add_argument("--classify", action="store_true",
                        help="Gemini-classify indexes still carrying unclassified items (needs LIVE_API; "
                             "rows land provisional and are NOT auto-confirmed)")
    args = parser.parse_args()

    from app.config import load_settings
    from app.database import init_pool, close_pool, get_pool
    from app.core.services.scope_registry.authority_ingest import (
        ingest_all, ingest_curated_index,
    )
    from app.core.services.scope_registry.authority_sources import CURATED_INDEXES
    from app.core.services.scope_registry.seed import apply_seed
    from app.core.services.scope_registry.classify import confirm_classifications, classify_index
    from app.core.services.scope_registry.resolve import resolve_scope

    settings = load_settings()
    await init_pool(settings.database_url)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            # ── 1. Ingest ──────────────────────────────────────────────
            print("── Ingest ──")
            if args.curated_only:
                results, failures = [], []
                for spec in CURATED_INDEXES:
                    try:
                        results.append(await ingest_curated_index(conn, spec))
                    except Exception as exc:  # a missing CA jurisdiction row, etc.
                        failures.append({"slug": spec.slug, "error": str(exc)})
            else:
                results, failures = await ingest_all(conn)

            for r in results:
                print(f"  {r.slug:16} {r.item_count:4} items  "
                      f"{r.unclassified_count:4} unclassified  ({r.source_type})")
            for f in failures:
                print(f"  ! {f['slug']:16} FAILED: {f['error']}")

            # ── 2. Seed ────────────────────────────────────────────────
            print("── Seed ──")
            seed_res = await apply_seed(conn)
            print(f"  applied={seed_res['applied']}  inherited={seed_res['inherited']}")
            if seed_res["missing_citations"]:
                # Expected with --curated-only: the 29 CFR seed rows have no
                # ingested item yet. Informational, not an error.
                print(f"  (info) {len(seed_res['missing_citations'])} seed citations with no ingested "
                      f"item — e.g. {', '.join(seed_res['missing_citations'][:4])}")
            for w in seed_res["warnings"]:
                print(f"  (warn) {w}")

            # ── 3. Confirm the seed rows ───────────────────────────────
            print("── Confirm ──")
            admin_id = await conn.fetchval(
                "SELECT id FROM users WHERE ($1::text IS NULL OR email = $1) "
                "AND role = 'admin' ORDER BY created_at LIMIT 1",
                args.admin_email,
            )
            if admin_id is None:
                which = f" matching {args.admin_email!r}" if args.admin_email else ""
                print(f"  ! no admin user{which} — cannot confirm (confirmed_by is a real FK). "
                      f"Seed rows stay provisional.")
            else:
                item_ids = [
                    r["item_id"] for r in await conn.fetch(
                        "SELECT item_id FROM authority_item_classifications "
                        "WHERE status = 'provisional' AND proposed_by = 'seed'"
                    )
                ]
                if item_ids:
                    conf = await confirm_classifications(conn, item_ids, admin_id)
                    strata = conf.get("strata") or {}
                    print(f"  confirmed={conf['confirmed']} (by admin {admin_id})  "
                          f"strata={strata.get('strata_count', strata)}")
                else:
                    print("  nothing provisional-from-seed to confirm (already confirmed?)")

            # ── 4. Optional Gemini classify of the remainder ───────────
            if args.classify:
                print("── Classify (Gemini) ──")
                idx_rows = await conn.fetch(
                    "SELECT slug FROM authority_indexes WHERE unclassified_count > 0 ORDER BY slug"
                )
                for row in idx_rows:
                    try:
                        cres = await classify_index(conn, row["slug"])
                        print(f"  {row['slug']:16} classified={cres['classified']} "
                              f"inherited={cres['inherited']} left={cres['unclassified_count']}")
                    except Exception as exc:
                        print(f"  ! {row['slug']:16} classify FAILED: {exc}")

            # ── 5. Summary + smoke resolve ─────────────────────────────
            print("── Summary ──")
            for row in await conn.fetch(
                "SELECT slug, item_count, unclassified_count FROM authority_indexes ORDER BY level, slug"
            ):
                print(f"  {row['slug']:16} {row['item_count']:4} items  "
                      f"{row['unclassified_count']:4} unclassified")
            for row in await conn.fetch(
                "SELECT status, COUNT(*) n FROM authority_item_classifications GROUP BY status ORDER BY status"
            ):
                print(f"  classifications {row['status']:12} {row['n']}")

            smoke = await resolve_scope(
                conn, category="manufacturing", state="CA", city="Los Angeles",
                facility_attributes={"employee_count": 60}, use_cache=False,
            )
            print(f"  smoke resolve (manufacturing/CA/LA/60): {smoke['counts']}")
    finally:
        await close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
