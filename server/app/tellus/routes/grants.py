"""Tell-Us brand/admin points grants.

A brand awards bonus points to the consumer who submitted a piece of useful
feedback. One grant per report (idempotent on the report id).
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_brand
from ..models.tellus import TellusAccount, TellusGrantRequest
from ..services.email import send_tellus_points_email
from ..services.points_service import award_points

router = APIRouter()


@router.post("/grants", status_code=status.HTTP_201_CREATED)
async def grant_points(
    body: TellusGrantRequest, background: BackgroundTasks,
    account: TellusAccount = Depends(require_brand),
):
    """Grant bonus points to the reporter of a report this brand owns."""
    async with get_connection() as conn:
        report = await conn.fetchrow(
            "SELECT reporter_account_id FROM tellus_reports WHERE id = $1 AND brand_id = $2",
            body.report_id, account.brand_id,
        )
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        reporter_id = report["reporter_account_id"]
        if reporter_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This feedback was anonymous — there's no one to award points to.",
            )

        result = await award_points(
            conn, reporter_id, "earn_grant", amount=body.points,
            reference_type="grant", reference_id=f"grant:{body.report_id}",
            description=body.description or f"Bonus from {account.display_name or 'a brand'}",
        )
        if not result["awarded"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You've already granted bonus points for this feedback.",
            )
        reporter = await conn.fetchrow(
            "SELECT email, display_name FROM tellus_accounts WHERE id = $1", reporter_id
        )

    if reporter:
        background.add_task(
            send_tellus_points_email, reporter["email"], reporter["display_name"],
            result["points"], "a bonus from a brand", result["balance"],
        )
    return {"awarded": True, "points": result["points"]}
