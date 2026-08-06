"""Tell-Us internal admin — audit trail reader."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...services.admin_audit import ADMIN_ACTIONS
from ...models.admin import TellusAdminAuditEntry
from ._shared import decode_audit_rows

router = APIRouter(dependencies=[Depends(require_tellus_admin)])


@router.get("/admin/audit")
async def list_audit(
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    clauses: list[str] = []
    params: list = []
    i = 1
    if target_type:
        clauses.append(f"target_type = ${i}")
        params.append(target_type)
        i += 1
    if target_id:
        clauses.append(f"target_id = ${i}")
        params.append(target_id)
        i += 1
    if action:
        clauses.append(f"action = ${i}")
        params.append(action)
        i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT id, actor_email, action, target_type, target_id, detail, created_at
                FROM tellus_admin_audit{where}
                ORDER BY created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
            *params, limit, offset,
        )
        total = await conn.fetchval(f"SELECT COUNT(*) FROM tellus_admin_audit{where}", *params)

    items = [TellusAdminAuditEntry(**d) for d in decode_audit_rows(rows)]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/admin/audit/actions")
async def list_audit_actions():
    return list(ADMIN_ACTIONS)
