"""
Creator routes for the Creator/Influencer Management Platform.
Handles creator profiles, revenue tracking, expenses, and platform connections.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from ..database import get_connection
from ..dependencies import (
    get_current_user,
    require_creator,
    require_creator_record,
)
from ..models.auth import CurrentUser
from ..models.creator import (
    CreatorCreate,
    CreatorUpdate,
    CreatorResponse,
    CreatorPublicResponse,
    PlatformConnectionResponse,
    RevenueStreamCreate,
    RevenueStreamUpdate,
    RevenueStreamResponse,
    RevenueEntryCreate,
    RevenueEntryUpdate,
    RevenueEntryResponse,
    ExpenseCreate,
    ExpenseUpdate,
    ExpenseResponse,
    RevenueSummary,
    RevenueOverview,
    MonthlyRevenue,
)

router = APIRouter()


def parse_jsonb(value):
    """Parse JSONB value from database."""
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return value


def row_to_creator_response(row) -> CreatorResponse:
    """Convert database row to CreatorResponse."""
    return CreatorResponse(
        id=row["id"],
        user_id=row["user_id"],
        display_name=row["display_name"],
        bio=row["bio"],
        profile_image_url=row["profile_image_url"],
        niches=parse_jsonb(row["niches"]),
        social_handles=parse_jsonb(row["social_handles"]) or {},
        audience_demographics=parse_jsonb(row["audience_demographics"]) or {},
        metrics=parse_jsonb(row["metrics"]) or {},
        is_verified=row["is_verified"],
        is_public=row["is_public"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# =============================================================================
# Creator Profile Endpoints
# =============================================================================

@router.get("/me", response_model=CreatorResponse)
async def get_my_creator_profile(
    creator: dict = Depends(require_creator_record)
):
    """Get the current creator's profile."""
    return row_to_creator_response(creator)


@router.put("/me", response_model=CreatorResponse)
async def update_my_creator_profile(
    update: CreatorUpdate,
    current_user: CurrentUser = Depends(require_creator),
):
    """Update the current creator's profile."""
    async with get_connection() as conn:
        # Build update query dynamically
        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Convert lists/dicts to JSON
        for field in ["niches", "social_handles", "audience_demographics"]:
            if field in update_data and update_data[field] is not None:
                update_data[field] = json.dumps(update_data[field])

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]
        set_clauses.append(f"updated_at = NOW()")

        row = await conn.fetchrow(
            f"""
            UPDATE creators
            SET {", ".join(set_clauses)}
            WHERE user_id = ${len(update_data) + 1}
            RETURNING *
            """,
            *update_data.values(),
            current_user.id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Creator not found")

        return row_to_creator_response(row)


@router.get("/public/{creator_id}", response_model=CreatorPublicResponse)
async def get_public_creator_profile(creator_id: UUID):
    """Get a public creator profile (for marketplace discovery)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT * FROM creators WHERE id = $1 AND is_public = true""",
            creator_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Creator not found")

        return CreatorPublicResponse(
            id=row["id"],
            display_name=row["display_name"],
            bio=row["bio"],
            profile_image_url=row["profile_image_url"],
            niches=parse_jsonb(row["niches"]),
            audience_demographics=parse_jsonb(row["audience_demographics"]) or {},
            metrics=parse_jsonb(row["metrics"]) or {},
            is_verified=row["is_verified"],
        )


@router.get("/discover", response_model=list[CreatorPublicResponse])
async def discover_creators(
    niches: Optional[str] = Query(None, description="Comma-separated niches"),
    min_followers: Optional[int] = None,
    max_followers: Optional[int] = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
):
    """Discover public creators for the marketplace."""
    async with get_connection() as conn:
        query = "SELECT * FROM creators WHERE is_public = true"
        params = []
        param_count = 0

        if niches:
            niche_list = [n.strip() for n in niches.split(",")]
            param_count += 1
            query += f" AND niches ?| ${param_count}"
            params.append(niche_list)

        query += " ORDER BY is_verified DESC, created_at DESC"
        query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        return [
            CreatorPublicResponse(
                id=row["id"],
                display_name=row["display_name"],
                bio=row["bio"],
                profile_image_url=row["profile_image_url"],
                niches=parse_jsonb(row["niches"]),
                audience_demographics=parse_jsonb(row["audience_demographics"]) or {},
                metrics=parse_jsonb(row["metrics"]) or {},
                is_verified=row["is_verified"],
            )
            for row in rows
        ]


# =============================================================================
# Platform Connection Endpoints
# =============================================================================

@router.get("/me/platforms", response_model=list[PlatformConnectionResponse])
async def list_platform_connections(
    creator: dict = Depends(require_creator_record)
):
    """List all platform connections for the current creator."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, creator_id, platform, platform_username,
                      last_synced_at, sync_status, sync_error, platform_data, created_at
               FROM creator_platform_connections
               WHERE creator_id = $1
               ORDER BY created_at""",
            creator["id"],
        )
        return [
            PlatformConnectionResponse(
                id=row["id"],
                creator_id=row["creator_id"],
                platform=row["platform"],
                platform_username=row["platform_username"],
                last_synced_at=row["last_synced_at"],
                sync_status=row["sync_status"],
                sync_error=row["sync_error"],
                platform_data=parse_jsonb(row["platform_data"]) or {},
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.delete("/me/platforms/{platform}")
async def disconnect_platform(
    platform: str,
    creator: dict = Depends(require_creator_record)
):
    """Disconnect a platform from the creator account."""
    async with get_connection() as conn:
        result = await conn.execute(
            """DELETE FROM creator_platform_connections
               WHERE creator_id = $1 AND platform = $2""",
            creator["id"],
            platform,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Platform connection not found")
        return {"status": "disconnected", "platform": platform}


# =============================================================================
# Revenue Stream Endpoints
# =============================================================================

@router.post("/me/revenue-streams", response_model=RevenueStreamResponse)
async def create_revenue_stream(
    stream: RevenueStreamCreate,
    creator: dict = Depends(require_creator_record)
):
    """Create a new revenue stream."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO revenue_streams
               (creator_id, name, category, platform, description, tax_category)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING *""",
            creator["id"],
            stream.name,
            stream.category,
            stream.platform,
            stream.description,
            stream.tax_category,
        )
        return RevenueStreamResponse(**dict(row))


@router.get("/me/revenue-streams", response_model=list[RevenueStreamResponse])
async def list_revenue_streams(
    active_only: bool = True,
    creator: dict = Depends(require_creator_record)
):
    """List all revenue streams for the current creator."""
    async with get_connection() as conn:
        query = "SELECT * FROM revenue_streams WHERE creator_id = $1"
        if active_only:
            query += " AND is_active = true"
        query += " ORDER BY created_at"

        rows = await conn.fetch(query, creator["id"])
        return [RevenueStreamResponse(**dict(row)) for row in rows]


@router.put("/me/revenue-streams/{stream_id}", response_model=RevenueStreamResponse)
async def update_revenue_stream(
    stream_id: UUID,
    update: RevenueStreamUpdate,
    creator: dict = Depends(require_creator_record)
):
    """Update a revenue stream."""
    async with get_connection() as conn:
        # Verify ownership
        existing = await conn.fetchrow(
            "SELECT * FROM revenue_streams WHERE id = $1 AND creator_id = $2",
            stream_id, creator["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Revenue stream not found")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]

        row = await conn.fetchrow(
            f"""UPDATE revenue_streams
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            stream_id,
        )
        return RevenueStreamResponse(**dict(row))


@router.delete("/me/revenue-streams/{stream_id}")
async def delete_revenue_stream(
    stream_id: UUID,
    creator: dict = Depends(require_creator_record)
):
    """Delete a revenue stream."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM revenue_streams WHERE id = $1 AND creator_id = $2",
            stream_id, creator["id"]
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Revenue stream not found")
        return {"status": "deleted"}


# =============================================================================
# Revenue Entry Endpoints
# =============================================================================

@router.post("/me/revenue", response_model=RevenueEntryResponse)
async def create_revenue_entry(
    entry: RevenueEntryCreate,
    creator: dict = Depends(require_creator_record)
):
    """Create a new revenue entry."""
    async with get_connection() as conn:
        # Verify stream ownership if provided
        stream_name = None
        if entry.stream_id:
            stream = await conn.fetchrow(
                "SELECT * FROM revenue_streams WHERE id = $1 AND creator_id = $2",
                entry.stream_id, creator["id"]
            )
            if not stream:
                raise HTTPException(status_code=404, detail="Revenue stream not found")
            stream_name = stream["name"]

        row = await conn.fetchrow(
            """INSERT INTO revenue_entries
               (creator_id, stream_id, amount, currency, date, description,
                source, is_recurring, tax_category)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING *""",
            creator["id"],
            entry.stream_id,
            entry.amount,
            entry.currency,
            entry.date,
            entry.description,
            entry.source,
            entry.is_recurring,
            entry.tax_category,
        )
        result = RevenueEntryResponse(**dict(row))
        result.stream_name = stream_name
        return result


@router.get("/me/revenue", response_model=list[RevenueEntryResponse])
async def list_revenue_entries(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    stream_id: Optional[UUID] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    creator: dict = Depends(require_creator_record)
):
    """List revenue entries for the current creator."""
    async with get_connection() as conn:
        query = """
            SELECT re.*, rs.name as stream_name
            FROM revenue_entries re
            LEFT JOIN revenue_streams rs ON re.stream_id = rs.id
            WHERE re.creator_id = $1
        """
        params = [creator["id"]]
        param_count = 1

        if start_date:
            param_count += 1
            query += f" AND re.date >= ${param_count}"
            params.append(start_date)

        if end_date:
            param_count += 1
            query += f" AND re.date <= ${param_count}"
            params.append(end_date)

        if stream_id:
            param_count += 1
            query += f" AND re.stream_id = ${param_count}"
            params.append(stream_id)

        query += " ORDER BY re.date DESC"
        query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)
        return [RevenueEntryResponse(**dict(row)) for row in rows]


@router.put("/me/revenue/{entry_id}", response_model=RevenueEntryResponse)
async def update_revenue_entry(
    entry_id: UUID,
    update: RevenueEntryUpdate,
    creator: dict = Depends(require_creator_record)
):
    """Update a revenue entry."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM revenue_entries WHERE id = $1 AND creator_id = $2",
            entry_id, creator["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Revenue entry not found")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]

        row = await conn.fetchrow(
            f"""UPDATE revenue_entries
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            entry_id,
        )
        return RevenueEntryResponse(**dict(row))


@router.delete("/me/revenue/{entry_id}")
async def delete_revenue_entry(
    entry_id: UUID,
    creator: dict = Depends(require_creator_record)
):
    """Delete a revenue entry."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM revenue_entries WHERE id = $1 AND creator_id = $2",
            entry_id, creator["id"]
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Revenue entry not found")
        return {"status": "deleted"}


# =============================================================================
# Expense Endpoints
# =============================================================================

@router.post("/me/expenses", response_model=ExpenseResponse)
async def create_expense(
    expense: ExpenseCreate,
    creator: dict = Depends(require_creator_record)
):
    """Create a new expense entry."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO creator_expenses
               (creator_id, amount, currency, date, category, description,
                vendor, is_deductible, tax_category)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               RETURNING *""",
            creator["id"],
            expense.amount,
            expense.currency,
            expense.date,
            expense.category,
            expense.description,
            expense.vendor,
            expense.is_deductible,
            expense.tax_category,
        )
        return ExpenseResponse(**dict(row))


@router.get("/me/expenses", response_model=list[ExpenseResponse])
async def list_expenses(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    creator: dict = Depends(require_creator_record)
):
    """List expenses for the current creator."""
    async with get_connection() as conn:
        query = "SELECT * FROM creator_expenses WHERE creator_id = $1"
        params = [creator["id"]]
        param_count = 1

        if start_date:
            param_count += 1
            query += f" AND date >= ${param_count}"
            params.append(start_date)

        if end_date:
            param_count += 1
            query += f" AND date <= ${param_count}"
            params.append(end_date)

        if category:
            param_count += 1
            query += f" AND category = ${param_count}"
            params.append(category)

        query += " ORDER BY date DESC"
        query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)
        return [ExpenseResponse(**dict(row)) for row in rows]


@router.put("/me/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: UUID,
    update: ExpenseUpdate,
    creator: dict = Depends(require_creator_record)
):
    """Update an expense entry."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM creator_expenses WHERE id = $1 AND creator_id = $2",
            expense_id, creator["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Expense not found")

        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(update_data.keys())]

        row = await conn.fetchrow(
            f"""UPDATE creator_expenses
                SET {", ".join(set_clauses)}
                WHERE id = ${len(update_data) + 1}
                RETURNING *""",
            *update_data.values(),
            expense_id,
        )
        return ExpenseResponse(**dict(row))


@router.delete("/me/expenses/{expense_id}")
async def delete_expense(
    expense_id: UUID,
    creator: dict = Depends(require_creator_record)
):
    """Delete an expense entry."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM creator_expenses WHERE id = $1 AND creator_id = $2",
            expense_id, creator["id"]
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Expense not found")
        return {"status": "deleted"}


@router.post("/me/expenses/{expense_id}/receipt")
async def upload_expense_receipt(
    expense_id: UUID,
    file: UploadFile = File(...),
    creator: dict = Depends(require_creator_record)
):
    """Upload a receipt for an expense."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM creator_expenses WHERE id = $1 AND creator_id = $2",
            expense_id, creator["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Expense not found")

        # TODO: Implement file upload to storage (S3, etc.)
        # For now, just return a placeholder
        receipt_url = f"/receipts/{expense_id}/{file.filename}"

        await conn.execute(
            "UPDATE creator_expenses SET receipt_url = $1 WHERE id = $2",
            receipt_url, expense_id
        )

        return {"status": "uploaded", "receipt_url": receipt_url}


# =============================================================================
# Dashboard/Analytics Endpoints
# =============================================================================

@router.get("/me/dashboard", response_model=RevenueOverview)
async def get_revenue_dashboard(
    creator: dict = Depends(require_creator_record)
):
    """Get revenue dashboard with summaries and trends."""
    async with get_connection() as conn:
        today = date.today()
        current_month_start = today.replace(day=1)
        prev_month_end = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        year_start = today.replace(month=1, day=1)

        async def get_summary(start: date, end: date) -> RevenueSummary:
            # Get revenue totals
            revenue_row = await conn.fetchrow(
                """SELECT COALESCE(SUM(amount), 0) as total,
                          COALESCE(jsonb_object_agg(
                              COALESCE(rs.category, 'uncategorized'),
                              cat_sum
                          ), '{}'::jsonb) as by_category
                   FROM revenue_entries re
                   LEFT JOIN revenue_streams rs ON re.stream_id = rs.id
                   LEFT JOIN LATERAL (
                       SELECT SUM(re2.amount) as cat_sum
                       FROM revenue_entries re2
                       LEFT JOIN revenue_streams rs2 ON re2.stream_id = rs2.id
                       WHERE re2.creator_id = $1 AND re2.date >= $2 AND re2.date <= $3
                       AND COALESCE(rs2.category, 'uncategorized') = COALESCE(rs.category, 'uncategorized')
                       GROUP BY COALESCE(rs2.category, 'uncategorized')
                   ) cat ON true
                   WHERE re.creator_id = $1 AND re.date >= $2 AND re.date <= $3""",
                creator["id"], start, end
            )

            # Get expense totals
            expense_row = await conn.fetchrow(
                """SELECT COALESCE(SUM(amount), 0) as total
                   FROM creator_expenses
                   WHERE creator_id = $1 AND date >= $2 AND date <= $3""",
                creator["id"], start, end
            )

            total_revenue = Decimal(str(revenue_row["total"] or 0))
            total_expenses = Decimal(str(expense_row["total"] or 0))

            return RevenueSummary(
                total_revenue=total_revenue,
                total_expenses=total_expenses,
                net_income=total_revenue - total_expenses,
                revenue_by_category={},
                revenue_by_stream={},
                expenses_by_category={},
                period_start=start,
                period_end=end,
            )

        # Get monthly trend (last 12 months)
        monthly_rows = await conn.fetch(
            """SELECT
                   TO_CHAR(date_trunc('month', re.date), 'YYYY-MM') as month,
                   SUM(re.amount) as revenue
               FROM revenue_entries re
               WHERE re.creator_id = $1 AND re.date >= $2
               GROUP BY date_trunc('month', re.date)
               ORDER BY month""",
            creator["id"],
            today - timedelta(days=365)
        )

        expense_monthly = await conn.fetch(
            """SELECT
                   TO_CHAR(date_trunc('month', date), 'YYYY-MM') as month,
                   SUM(amount) as expenses
               FROM creator_expenses
               WHERE creator_id = $1 AND date >= $2
               GROUP BY date_trunc('month', date)""",
            creator["id"],
            today - timedelta(days=365)
        )

        expense_by_month = {row["month"]: Decimal(str(row["expenses"])) for row in expense_monthly}

        monthly_trend = [
            MonthlyRevenue(
                month=row["month"],
                revenue=Decimal(str(row["revenue"])),
                expenses=expense_by_month.get(row["month"], Decimal("0")),
                net=Decimal(str(row["revenue"])) - expense_by_month.get(row["month"], Decimal("0")),
            )
            for row in monthly_rows
        ]

        return RevenueOverview(
            current_month=await get_summary(current_month_start, today),
            previous_month=await get_summary(prev_month_start, prev_month_end),
            year_to_date=await get_summary(year_start, today),
            monthly_trend=monthly_trend,
        )
