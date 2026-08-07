"""Audit trail for Tell-Us internal admin mutations.

Call record_admin_action() inside the SAME transaction as the mutation so an
audit row never exists for a rolled-back write (and vice versa).
"""
import json
from typing import Any, Optional
from uuid import UUID

# Registry of every action name — the audit-viewer filter dropdown reads this.
ADMIN_ACTIONS = (
    "account.suspend", "account.unsuspend", "account.force_logout",
    "account.verify_email", "account.password_reset_issued", "account.points_adjust",
    "brand.plan_comp", "brand.plan_cancel", "brand.assign_owner", "brand.unassign_owner",
    "brand.claim_requested", "brand.claim_approve", "brand.claim_reject", "brand.claim_cancelled",
    "report.moderate", "dm_thread.block", "dm_thread.unblock",
    "earning_rule.update", "badge.update", "listing.update",
    "board_post.moderate", "board_reply.moderate",
)


def serialize_detail(detail: Optional[dict[str, Any]]) -> Optional[str]:
    """JSONB-safe serialization: UUID/datetime coerced via default=str.
    None passes through (NULL column). Pure — unit-tested."""
    if detail is None:
        return None
    return json.dumps(detail, default=str)


async def record_admin_action(
    conn, actor, action: str, target_type: str,
    target_id: Optional[str | UUID], detail: Optional[dict[str, Any]] = None,
) -> None:
    await conn.execute(
        """INSERT INTO tellus_admin_audit
               (actor_account_id, actor_email, action, target_type, target_id, detail)
           VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
        actor.id, actor.email, action, target_type,
        str(target_id) if target_id is not None else None,
        serialize_detail(detail),
    )
