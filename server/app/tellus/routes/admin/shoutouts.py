"""Tell-Us admin-only manual shoutout scan trigger."""
from uuid import UUID

from fastapi import APIRouter, Depends

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...models.tellus import TellusAccount
from ...services.admin_audit import record_admin_action
from ...services.shoutout.scan_service import scan_brand

router = APIRouter(dependencies=[Depends(require_tellus_admin)])


@router.post("/admin/shoutouts/{brand_id}/scan")
async def trigger_scan(brand_id: UUID, admin: TellusAccount = Depends(require_tellus_admin)):
    async with get_connection() as conn:
        result = await scan_brand(conn, brand_id, trigger="admin")
        async with conn.transaction():
            await record_admin_action(conn, admin, "shoutout.scan", "brand", brand_id, result)
    return result
