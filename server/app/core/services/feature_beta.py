"""Beta status, manageable from admin without a deploy.

`feature_flags.BETA_FEATURES` is the code-level DEFAULT classification — a
newly-shipped flag can be declared beta with zero migration, and the CI
completeness check (see feature_flags.py) still runs against it. This module
adds a DB OVERRIDE layer on top: `feature_beta_overrides` lets an admin flip
any key's beta status live. A row with is_beta=false promotes a code-beta
flag to ready; is_beta=true declares beta a flag code doesn't.

Deliberately NOT consulted by `merge_company_features` — that function is
pure + sync because it runs in pool-free Celery workers, and a DB-consulting
read-time overlay there would need a cache on the hot path of every request
(same reasoning as the product_definitions "materialize, don't overlay" rule).
Beta status is only ever read at WRITE-time gates (assert_feature_allowed,
validate_features, the broker toggle normalizer) and two display surfaces
(GET /admin/feature-flags, /auth/me) — all of which already hold an open
connection, so loading the override set there costs nothing structural.

Table-missing (backend deployed ahead of its migration) degrades to the code
constant unchanged — same idiom as admin/_shared.py's
`_is_test_column_exists_cache`. That only disables the override layer; the
gate itself (BETA_FEATURES) still works.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.core.feature_flags import ALL_FEATURES, BETA_FEATURES

_table_exists_cache: Optional[bool] = None


async def _overrides_table_exists(conn) -> bool:
    global _table_exists_cache
    if _table_exists_cache is None:
        _table_exists_cache = bool(await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'feature_beta_overrides'"
        ))
    return _table_exists_cache


async def load_beta_features(conn) -> frozenset[str]:
    """The effective beta set: code default with DB overrides applied."""
    if not await _overrides_table_exists(conn):
        return BETA_FEATURES
    rows = await conn.fetch("SELECT feature_key, is_beta FROM feature_beta_overrides")
    effective = set(BETA_FEATURES)
    for row in rows:
        if row["is_beta"]:
            effective.add(row["feature_key"])
        else:
            effective.discard(row["feature_key"])
    return frozenset(effective)


async def set_beta_status(
    conn, feature_key: str, is_beta: bool, actor_user_id: Optional[UUID] = None,
) -> None:
    if feature_key not in ALL_FEATURES:
        raise ValueError(f"Unknown feature: {feature_key}")
    await conn.execute(
        """
        INSERT INTO feature_beta_overrides (feature_key, is_beta, updated_by, updated_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (feature_key) DO UPDATE
            SET is_beta = EXCLUDED.is_beta,
                updated_by = EXCLUDED.updated_by,
                updated_at = now()
        """,
        feature_key, is_beta, actor_user_id,
    )
