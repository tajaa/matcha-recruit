"""Tell-Us internal admin — brand claim approval queue.

Self-serve claim (routes/community.py:claim_brand) only ever files a PENDING
row in tellus_brand_claims — ownership and account_type flip ONLY here, on
approval. Mirrors the pre-existing assign_owner mechanics (brands.py) but
goes through a queue instead of an admin picking the account directly.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ....database import get_connection
from ...dependencies import require_tellus_admin
from ...models.tellus import TellusAccount, TellusAdminClaim, TellusClaimDecision
from ...services.admin_audit import record_admin_action
from ...services.points_service import notify_account

router = APIRouter(dependencies=[Depends(require_tellus_admin)])

_CLAIM_SELECT = """
    SELECT c.id, c.brand_id, b.slug AS brand_slug, b.name AS brand_name,
           c.status, c.created_at, c.decision_note,
           c.account_id, a.email AS account_email, a.display_name AS account_display_name,
           c.claimant_ip, c.note
    FROM tellus_brand_claims c
    JOIN tellus_brands b ON b.id = c.brand_id
    JOIN tellus_accounts a ON a.id = c.account_id
"""


@router.get("/admin/claims", response_model=list[TellusAdminClaim])
async def list_claims(
    status_f: str = Query(default="pending", alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"{_CLAIM_SELECT} WHERE c.status = $1 ORDER BY c.created_at LIMIT $2 OFFSET $3",
            status_f, limit, offset,
        )
    return [TellusAdminClaim(**dict(r)) for r in rows]


@router.post("/admin/claims/{claim_id}/approve", response_model=TellusAdminClaim)
async def approve_claim(
    claim_id: UUID, body: TellusClaimDecision,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            claim = await conn.fetchrow(
                "SELECT id, brand_id, account_id, status FROM tellus_brand_claims WHERE id = $1 FOR UPDATE",
                claim_id,
            )
            if claim is None:
                raise HTTPException(404, "Claim not found")
            if claim["status"] != "pending":
                raise HTTPException(409, f"Claim is already {claim['status']}.")

            brand = await conn.fetchrow(
                "SELECT owner_account_id FROM tellus_brands WHERE id = $1 FOR UPDATE", claim["brand_id"],
            )
            target = await conn.fetchrow(
                "SELECT id, email, account_type FROM tellus_accounts WHERE id = $1", claim["account_id"],
            )
            already_owns = await conn.fetchval(
                "SELECT 1 FROM tellus_brands WHERE owner_account_id = $1", claim["account_id"],
            )

            # Eligibility can have drifted since the claim was filed (brand
            # claimed elsewhere, claimant picked up a different brand) —
            # auto-reject instead of silently corrupting ownership.
            if brand["owner_account_id"] is not None or target is None or already_owns:
                await conn.execute(
                    "UPDATE tellus_brand_claims SET status = 'rejected', decided_at = NOW(), "
                    "decided_by = $1, decision_note = $2 WHERE id = $3",
                    admin.id, "Auto-rejected: brand or account no longer eligible.", claim_id,
                )
                await record_admin_action(
                    conn, admin, "brand.claim_reject", "brand", claim["brand_id"],
                    {"claim_id": str(claim_id), "reason": "auto: no longer eligible"},
                )
                raise HTTPException(409, "Brand or account is no longer eligible — claim auto-rejected.")

            flipped_type = False
            if target["account_type"] == "consumer":
                await conn.execute(
                    "UPDATE tellus_accounts SET account_type = 'brand', updated_at = NOW() WHERE id = $1",
                    claim["account_id"],
                )
                flipped_type = True

            await conn.execute(
                "UPDATE tellus_brands SET owner_account_id = $1, claimed_at = NOW(), updated_at = NOW() "
                "WHERE id = $2",
                claim["account_id"], claim["brand_id"],
            )
            await conn.execute(
                """INSERT INTO tellus_brand_members (brand_id, account_id, role, can_manage_inbox) VALUES ($1, $2, 'owner', TRUE)
                       ON CONFLICT (brand_id, account_id) DO UPDATE SET role = 'owner', can_manage_inbox = TRUE""",
                claim["brand_id"], claim["account_id"],
            )
            await conn.execute(
                "UPDATE tellus_brand_claims SET status = 'approved', decided_at = NOW(), "
                "decided_by = $1, decision_note = $2 WHERE id = $3",
                admin.id, body.decision_note, claim_id,
            )
            await record_admin_action(
                conn, admin, "brand.claim_approve", "brand", claim["brand_id"],
                {
                    "claim_id": str(claim_id), "account_id": str(claim["account_id"]),
                    "account_email": target["email"], "flipped_type": flipped_type,
                },
            )
            await notify_account(
                conn, claim["account_id"], "claim_decision", "Your business claim was approved",
                "Set up billing to unlock the brand dashboard.",
                reference_type="brand", reference_id=str(claim["brand_id"]),
            )
        row = await conn.fetchrow(f"{_CLAIM_SELECT} WHERE c.id = $1", claim_id)
    return TellusAdminClaim(**dict(row))


@router.post("/admin/claims/{claim_id}/reject", response_model=TellusAdminClaim)
async def reject_claim(
    claim_id: UUID, body: TellusClaimDecision,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    async with get_connection() as conn:
        async with conn.transaction():
            claim = await conn.fetchrow(
                "SELECT id, brand_id, account_id, status FROM tellus_brand_claims WHERE id = $1 FOR UPDATE",
                claim_id,
            )
            if claim is None:
                raise HTTPException(404, "Claim not found")
            if claim["status"] != "pending":
                raise HTTPException(409, f"Claim is already {claim['status']}.")

            await conn.execute(
                "UPDATE tellus_brand_claims SET status = 'rejected', decided_at = NOW(), "
                "decided_by = $1, decision_note = $2 WHERE id = $3",
                admin.id, body.decision_note, claim_id,
            )
            await record_admin_action(
                conn, admin, "brand.claim_reject", "brand", claim["brand_id"],
                {"claim_id": str(claim_id), "decision_note": body.decision_note},
            )
            await notify_account(
                conn, claim["account_id"], "claim_decision", "Your business claim was not approved",
                body.decision_note or "Contact support if you believe this is a mistake.",
                reference_type="brand", reference_id=str(claim["brand_id"]),
            )
        row = await conn.fetchrow(f"{_CLAIM_SELECT} WHERE c.id = $1", claim_id)
    return TellusAdminClaim(**dict(row))
