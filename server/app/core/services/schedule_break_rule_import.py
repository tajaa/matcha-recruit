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
    row = await conn.fetchrow(
        """
        UPDATE schedule_break_rule_sets
        SET review_status = $2,
            reviewed_by = $3,
            reviewed_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
          AND is_active = true
          AND ($2 <> 'approved' OR jurisdiction_id IS NOT NULL)
        RETURNING id, review_status, reviewed_by, reviewed_at
        """,
        rule_set_id,
        decision,
        actor_user_id,
    )
    if not row:
        raise LookupError("Rule set not found or cannot be approved without a jurisdiction")
    return {
        "id": row["id"],
        "review_status": row["review_status"],
        "reviewed_by": row["reviewed_by"],
        "reviewed_at": row["reviewed_at"],
    }
