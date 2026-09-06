"""Import/review service for structured schedule break rules."""

from __future__ import annotations

import json
from typing import Sequence
from uuid import UUID

from app.core.models.schedule_break_rules import BreakRuleSetImport


async def import_break_rule_sets(
    conn,
    *,
    rows: Sequence[BreakRuleSetImport],
    actor_user_id: UUID,
) -> list[UUID]:
    """Insert pending rule sets; never approve as part of ingestion."""

    inserted: list[UUID] = []
    async with conn.transaction():
        for item in rows:
            rule_id = await conn.fetchval(
                """
                INSERT INTO schedule_break_rule_sets
                    (jurisdiction_id, industry_code, effective_from, effective_to,
                     rules, citation, authority_url, source_type, source_external_id,
                     source_version, review_status)
                VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,'pending')
                RETURNING id
                """,
                item.jurisdiction_id,
                item.industry_code,
                item.effective_from,
                item.effective_to,
                json.dumps(item.rules, sort_keys=True),
                item.citation,
                item.authority_url,
                item.source_type,
                item.source_external_id,
                item.source_version,
            )
            inserted.append(rule_id)
    return inserted


async def review_break_rule_set(
    conn,
    *,
    rule_set_id: UUID,
    decision: str,
    actor_user_id: UUID,
) -> dict:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    from app.matcha.services.scheduling.schedule_break_rule_store import (
        lock_schedule_break_rule_guidance,
        validate_break_rule_payload,
    )
    async with conn.transaction():
        await lock_schedule_break_rule_guidance(conn, exclusive=True)
        existing = await conn.fetchrow(
            """
            SELECT id, jurisdiction_id, rules, citation
            FROM schedule_break_rule_sets
            WHERE id = $1 AND is_active = true
            FOR UPDATE
            """,
            rule_set_id,
        )
        if not existing:
            raise LookupError("Rule set not found")
        if decision == "approved":
            if existing["jurisdiction_id"] is None:
                raise LookupError("Rule set cannot be approved without a jurisdiction")
            # Revalidate the locked database value.  A pending row could have
            # been inserted before strict validation existed or altered by an
            # operational repair after import.
            validate_break_rule_payload(existing["rules"], existing["citation"])
        row = await conn.fetchrow(
            """
            UPDATE schedule_break_rule_sets
            SET review_status = $2,
                reviewed_by = $3,
                reviewed_at = NOW(),
                updated_at = clock_timestamp()
            WHERE id = $1
            RETURNING id, review_status, reviewed_by, reviewed_at
            """,
            rule_set_id,
            decision,
            actor_user_id,
        )
    # Existing assignment guidance is a materialized view of rule status.
    # Dispatch is best-effort because the committed rule row itself is the
    # recovery record scanned whenever a worker starts.
    from app.workers.tasks.schedule_break_refresh import enqueue_schedule_break_recovery
    enqueue_schedule_break_recovery()
    return {
        "id": row["id"],
        "review_status": row["review_status"],
        "reviewed_by": row["reviewed_by"],
        "reviewed_at": row["reviewed_at"],
    }
