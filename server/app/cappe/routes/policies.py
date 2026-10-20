"""Cappe store policies — refund, shipping, terms, privacy (services/policies.py).

Every plan; nothing here is sold. The owner starts from our starter text and
edits it; an empty body takes the page down. Each write drops the store's
cached pages, whose footers link the policies.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappePolicies, CappePolicyUpdate
from ..services.policies import KINDS, TITLES, policy_path, starter
from ..services.render_cache import invalidate_site_render_cache
from ._shared import get_owned_site

router = APIRouter()


async def _view(conn, site_id) -> dict:
    rows = await conn.fetch("SELECT kind, body, updated_at FROM cappe_site_policies WHERE site_id = $1", site_id)
    saved = {r["kind"]: r for r in rows}
    return {"policies": [
        {"kind": k, "title": TITLES[k], "path": policy_path(k), "starter": starter(k),
         "body": saved[k]["body"] if k in saved else None,
         "updated_at": saved[k]["updated_at"] if k in saved else None}
        for k in KINDS
    ]}


@router.get("/sites/{site_id}/policies", response_model=CappePolicies)
async def get_policies(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        return await _view(conn, site_id)


@router.put("/sites/{site_id}/policies/{kind}", response_model=CappePolicies)
async def put_policy(
    site_id: UUID, kind: str, body: CappePolicyUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    if kind not in KINDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such policy")
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if body.body:
            await conn.execute(
                """INSERT INTO cappe_site_policies (site_id, kind, body) VALUES ($1, $2, $3)
                   ON CONFLICT (site_id, kind) DO UPDATE SET body = EXCLUDED.body, updated_at = NOW()""",
                site_id, kind, body.body,
            )
        else:
            await conn.execute("DELETE FROM cappe_site_policies WHERE site_id = $1 AND kind = $2", site_id, kind)
        view = await _view(conn, site_id)
    await invalidate_site_render_cache(site_id)
    return view
