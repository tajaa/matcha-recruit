"""Shadow the scope registry against the live expand_scope path.

Commit 5 (SCOPE_REGISTRY_PLAN.md §8): on onboarding finalize, run
``resolve_scope`` alongside the authoritative ``expand_scope → map_to_bank``
path and record the diff in ``scope_shadow_log``. **expand_scope stays
authoritative** — this is read-only observation to build confidence before the
registry takes over the runtime path. It must never raise into the finalize
flow (it runs as a background task with its own connection, fully guarded).

Comparison space is ``regulation_key``. The expand path's ``existing`` items
carry a ``requirement_id`` (and ``canonical_key``), so their regulation_keys are
looked up from the row — reconciling the ``canonical_key`` vs ``regulation_key``
column split so both sides are compared in one key space. Rows with a NULL
``regulation_key`` (older catalog rows) aren't comparable and drop out of the
expand set; that gap is itself a finding the diff surfaces.

Expected, informative diffs (not bugs):
  * ``only_in_expand`` — the category-grab pulls conditional rows (FMLA, PSM)
    regardless of whether their trigger fires; the registry filters them by
    facility attributes. A subset here is the precision the registry adds.
  * ``only_in_resolve`` — an obligation the registry classifies as applicable
    that the category-grab missed (e.g. a cross-category universal rule).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import get_connection

from .resolve import parse_jsonb, resolve_scope

logger = logging.getLogger(__name__)


async def _expand_keys(conn, existing_items: List[Dict[str, Any]]) -> set:
    """regulation_keys behind the expand path's resolved bank rows."""
    req_ids = []
    for item in existing_items:
        rid = item.get("requirement_id")
        if rid:
            try:
                req_ids.append(UUID(str(rid)))
            except (ValueError, TypeError):
                continue
    if not req_ids:
        return set()
    rows = await conn.fetch(
        "SELECT DISTINCT regulation_key FROM jurisdiction_requirements "
        "WHERE id = ANY($1::uuid[]) AND regulation_key IS NOT NULL",
        req_ids,
    )
    return {r["regulation_key"] for r in rows}


async def record_shadow(
    *,
    session_id: UUID,
    company_id: Optional[UUID],
    industry: Optional[str],
    existing_items: List[Dict[str, Any]],
) -> None:
    """Compute the resolve-vs-expand diff and log it. Never raises.

    Runs the registry resolution over the company's real ``business_locations``
    (state/city + stored facility_attributes) and unions the codified keys.
    """
    try:
        async with get_connection() as conn:
            expand_keys = await _expand_keys(conn, existing_items)

            resolve_keys: set = set()
            unmodeled: List[Dict[str, Any]] = []
            locations = []
            if company_id:
                locations = await conn.fetch(
                    """
                    SELECT state, city, facility_attributes
                    FROM business_locations
                    WHERE company_id = $1 AND COALESCE(is_active, true)
                      AND state IS NOT NULL AND NOT COALESCE(is_company_wide, false)
                    """,
                    company_id,
                )

            for loc in locations:
                try:
                    res = await resolve_scope(
                        conn,
                        category=industry,
                        state=loc["state"],
                        city=loc["city"],
                        facility_attributes=parse_jsonb(loc["facility_attributes"]) or {},
                        use_cache=False,  # a shadow read must not pollute the cache
                    )
                except Exception:
                    logger.exception(
                        "scope shadow: resolve failed for company %s loc %s/%s",
                        company_id, loc["state"], loc["city"],
                    )
                    continue
                resolve_keys |= {
                    c["regulation_key"] for c in res["codified"] if c.get("regulation_key")
                }
                unmodeled.extend(res["unmodeled_coordinates"])

            only_in_resolve = sorted(resolve_keys - expand_keys)
            only_in_expand = sorted(expand_keys - resolve_keys)

            await conn.execute(
                """
                INSERT INTO scope_shadow_log
                    (session_id, company_id, resolve_keys, expand_keys,
                     only_in_resolve, only_in_expand, unmodeled_coordinates)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                session_id,
                company_id,
                sorted(resolve_keys),
                sorted(expand_keys),
                only_in_resolve,
                only_in_expand,
                json.dumps(unmodeled),
            )
            logger.info(
                "scope shadow session=%s: resolve=%d expand=%d "
                "only_resolve=%d only_expand=%d unmodeled=%d",
                session_id, len(resolve_keys), len(expand_keys),
                len(only_in_resolve), len(only_in_expand), len(unmodeled),
            )
    except Exception:
        # Shadow is observational — a failure here must never touch onboarding.
        logger.exception("scope shadow failed for session %s", session_id)
