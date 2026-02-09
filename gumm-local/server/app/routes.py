from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, HTTPException

from .database import get_connection
from .schemas import (
    CafeCreate,
    LocalCreate,
    LocalUpdate,
    RedemptionCreate,
    RewardProgramCreate,
    VisitCreate,
)

router = APIRouter()


def _serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _row_to_dict(row: asyncpg.Record | None) -> dict | None:
    if row is None:
        return None
    return {key: _serialize_value(value) for key, value in row.items()}


def _rows_to_dict(rows: list[asyncpg.Record]) -> list[dict]:
    return [_row_to_dict(row) for row in rows if row is not None]


async def _ensure_cafe_exists(conn: asyncpg.Connection, cafe_id: UUID):
    exists = await conn.fetchval("SELECT 1 FROM local_cafes WHERE id = $1", cafe_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Cafe not found")


async def _ensure_local_exists(conn: asyncpg.Connection, cafe_id: UUID, local_id: UUID):
    exists = await conn.fetchval(
        "SELECT 1 FROM local_customers WHERE id = $1 AND cafe_id = $2",
        local_id,
        cafe_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Local customer not found")


async def _ensure_program_belongs_to_cafe(conn: asyncpg.Connection, cafe_id: UUID, program_id: UUID):
    exists = await conn.fetchval(
        "SELECT 1 FROM local_reward_programs WHERE id = $1 AND cafe_id = $2 AND active = true",
        program_id,
        cafe_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Reward program not found for this cafe")


async def _compute_program_progress(
    conn: asyncpg.Connection,
    cafe_id: UUID,
    local_id: UUID,
    program: asyncpg.Record,
) -> dict:
    visits_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM local_visits
        WHERE cafe_id = $1 AND customer_id = $2 AND program_id = $3
        """,
        cafe_id,
        local_id,
        program["id"],
    )
    redemptions_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM local_redemptions
        WHERE cafe_id = $1 AND customer_id = $2 AND program_id = $3
        """,
        cafe_id,
        local_id,
        program["id"],
    )

    visits_required = int(program["visits_required"])
    completed_cycles = int(visits_count) // visits_required
    available_rewards = max(completed_cycles - int(redemptions_count), 0)
    stamps_toward_next = int(visits_count) % visits_required

    if available_rewards > 0:
        visits_to_next_reward = 0
    else:
        visits_to_next_reward = visits_required - stamps_toward_next
        if visits_to_next_reward == 0:
            visits_to_next_reward = visits_required

    return {
        "program": _row_to_dict(program),
        "stamps_earned": int(visits_count),
        "stamps_toward_next_reward": stamps_toward_next,
        "rewards_redeemed": int(redemptions_count),
        "available_rewards": available_rewards,
        "visits_required": visits_required,
        "visits_to_next_reward": visits_to_next_reward,
    }


async def _build_local_progress(conn: asyncpg.Connection, cafe_id: UUID, local_id: UUID) -> dict:
    local_row = await conn.fetchrow(
        "SELECT * FROM local_customers WHERE id = $1 AND cafe_id = $2",
        local_id,
        cafe_id,
    )
    if local_row is None:
        raise HTTPException(status_code=404, detail="Local customer not found")

    programs = await conn.fetch(
        """
        SELECT *
        FROM local_reward_programs
        WHERE cafe_id = $1 AND active = true
        ORDER BY created_at ASC
        """,
        cafe_id,
    )

    program_progress = []
    for program in programs:
        program_progress.append(await _compute_program_progress(conn, cafe_id, local_id, program))

    total_visits = await conn.fetchval(
        "SELECT COUNT(*) FROM local_visits WHERE cafe_id = $1 AND customer_id = $2",
        cafe_id,
        local_id,
    )
    total_rewards = await conn.fetchval(
        "SELECT COUNT(*) FROM local_redemptions WHERE cafe_id = $1 AND customer_id = $2",
        cafe_id,
        local_id,
    )

    return {
        "local": _row_to_dict(local_row),
        "total_visits": int(total_visits),
        "total_rewards_redeemed": int(total_rewards),
        "program_progress": program_progress,
    }


@router.get("/cafes")
async def list_cafes():
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM local_cafes ORDER BY created_at DESC"
        )
        return _rows_to_dict(rows)


@router.post("/cafes", status_code=201)
async def create_cafe(payload: CafeCreate):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO local_cafes (id, name, neighborhood, accent_color)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            uuid4(),
            payload.name,
            payload.neighborhood,
            payload.accent_color,
        )
        return _row_to_dict(row)


@router.get("/cafes/{cafe_id}/programs")
async def list_programs(cafe_id: UUID):
    async with get_connection() as conn:
        await _ensure_cafe_exists(conn, cafe_id)
        rows = await conn.fetch(
            """
            SELECT *
            FROM local_reward_programs
            WHERE cafe_id = $1
            ORDER BY created_at ASC
            """,
            cafe_id,
        )
        return _rows_to_dict(rows)


@router.post("/cafes/{cafe_id}/programs", status_code=201)
async def create_program(cafe_id: UUID, payload: RewardProgramCreate):
    async with get_connection() as conn:
        await _ensure_cafe_exists(conn, cafe_id)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO local_reward_programs (id, cafe_id, name, visits_required, reward_description)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                uuid4(),
                cafe_id,
                payload.name,
                payload.visits_required,
                payload.reward_description,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="Program name already exists for this cafe") from exc

        return _row_to_dict(row)


@router.get("/cafes/{cafe_id}/locals")
async def list_locals(cafe_id: UUID):
    async with get_connection() as conn:
        await _ensure_cafe_exists(conn, cafe_id)
        rows = await conn.fetch(
            """
            SELECT
                c.*,
                COALESCE(v.total_visits, 0) AS total_visits,
                COALESCE(r.total_rewards_redeemed, 0) AS total_rewards_redeemed
            FROM local_customers c
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_visits
                FROM local_visits
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) v ON v.customer_id = c.id
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_rewards_redeemed
                FROM local_redemptions
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) r ON r.customer_id = c.id
            WHERE c.cafe_id = $1
            ORDER BY c.is_vip DESC, COALESCE(v.total_visits, 0) DESC, c.created_at DESC
            """,
            cafe_id,
        )
        return _rows_to_dict(rows)


@router.post("/cafes/{cafe_id}/locals", status_code=201)
async def create_local(cafe_id: UUID, payload: LocalCreate):
    async with get_connection() as conn:
        await _ensure_cafe_exists(conn, cafe_id)
        row = await conn.fetchrow(
            """
            INSERT INTO local_customers (id, cafe_id, full_name, phone, email, favorite_order, notes, is_vip)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            uuid4(),
            cafe_id,
            payload.full_name,
            payload.phone,
            payload.email,
            payload.favorite_order,
            payload.notes,
            payload.is_vip,
        )
        return _row_to_dict(row)


@router.patch("/cafes/{cafe_id}/locals/{local_id}")
async def update_local(cafe_id: UUID, local_id: UUID, payload: LocalUpdate):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    async with get_connection() as conn:
        await _ensure_local_exists(conn, cafe_id, local_id)

        set_parts = []
        values = [local_id, cafe_id]
        for idx, (field, value) in enumerate(updates.items(), start=3):
            set_parts.append(f"{field} = ${idx}")
            values.append(value)

        sql = f"""
            UPDATE local_customers
            SET {', '.join(set_parts)}
            WHERE id = $1 AND cafe_id = $2
            RETURNING *
        """
        row = await conn.fetchrow(sql, *values)
        return _row_to_dict(row)


@router.post("/cafes/{cafe_id}/locals/{local_id}/visits", status_code=201)
async def record_visit(cafe_id: UUID, local_id: UUID, payload: VisitCreate):
    async with get_connection() as conn:
        await _ensure_local_exists(conn, cafe_id, local_id)

        if payload.program_id is not None:
            await _ensure_program_belongs_to_cafe(conn, cafe_id, payload.program_id)

        row = await conn.fetchrow(
            """
            INSERT INTO local_visits (id, cafe_id, customer_id, program_id, order_total, visit_note)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            uuid4(),
            cafe_id,
            local_id,
            payload.program_id,
            payload.order_total,
            payload.visit_note,
        )

        return {
            "visit": _row_to_dict(row),
            "progress": await _build_local_progress(conn, cafe_id, local_id),
        }


@router.get("/cafes/{cafe_id}/locals/{local_id}/progress")
async def local_progress(cafe_id: UUID, local_id: UUID):
    async with get_connection() as conn:
        await _ensure_local_exists(conn, cafe_id, local_id)
        return await _build_local_progress(conn, cafe_id, local_id)


@router.post("/cafes/{cafe_id}/locals/{local_id}/redeem", status_code=201)
async def redeem_reward(cafe_id: UUID, local_id: UUID, payload: RedemptionCreate):
    async with get_connection() as conn:
        await _ensure_local_exists(conn, cafe_id, local_id)
        await _ensure_program_belongs_to_cafe(conn, cafe_id, payload.program_id)

        program_row = await conn.fetchrow(
            "SELECT * FROM local_reward_programs WHERE id = $1",
            payload.program_id,
        )
        if program_row is None:
            raise HTTPException(status_code=404, detail="Reward program not found")

        progress = await _compute_program_progress(conn, cafe_id, local_id, program_row)
        if progress["available_rewards"] <= 0:
            raise HTTPException(
                status_code=400,
                detail="No available reward to redeem for this local on this program",
            )

        redemption_row = await conn.fetchrow(
            """
            INSERT INTO local_redemptions (id, cafe_id, customer_id, program_id, redemption_note)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            uuid4(),
            cafe_id,
            local_id,
            payload.program_id,
            payload.redemption_note,
        )

        return {
            "redemption": _row_to_dict(redemption_row),
            "progress": await _build_local_progress(conn, cafe_id, local_id),
        }


@router.get("/cafes/{cafe_id}/dashboard")
async def cafe_dashboard(cafe_id: UUID):
    async with get_connection() as conn:
        await _ensure_cafe_exists(conn, cafe_id)

        totals_row = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM local_customers WHERE cafe_id = $1) AS total_locals,
                (SELECT COUNT(*) FROM local_customers WHERE cafe_id = $1 AND is_vip = true) AS vip_locals,
                (SELECT COUNT(*) FROM local_visits WHERE cafe_id = $1) AS total_visits,
                (SELECT COUNT(*) FROM local_redemptions WHERE cafe_id = $1) AS rewards_redeemed
            """,
            cafe_id,
        )

        program_rows = await conn.fetch(
            """
            SELECT
                p.id,
                p.name,
                p.visits_required,
                p.reward_description,
                p.active,
                COALESCE(v.total_visits_logged, 0) AS total_visits_logged,
                COALESCE(v.participating_locals, 0) AS participating_locals,
                COALESCE(r.total_redemptions, 0) AS total_redemptions
            FROM local_reward_programs p
            LEFT JOIN (
                SELECT
                    program_id,
                    COUNT(*) AS total_visits_logged,
                    COUNT(DISTINCT customer_id) AS participating_locals
                FROM local_visits
                WHERE cafe_id = $1 AND program_id IS NOT NULL
                GROUP BY program_id
            ) v ON v.program_id = p.id
            LEFT JOIN (
                SELECT
                    program_id,
                    COUNT(*) AS total_redemptions
                FROM local_redemptions
                WHERE cafe_id = $1
                GROUP BY program_id
            ) r ON r.program_id = p.id
            WHERE p.cafe_id = $1
            ORDER BY p.created_at ASC
            """,
            cafe_id,
        )

        top_locals_rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.full_name,
                c.is_vip,
                COALESCE(v.total_visits, 0) AS total_visits,
                COALESCE(r.total_rewards_redeemed, 0) AS total_rewards_redeemed
            FROM local_customers c
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_visits
                FROM local_visits
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) v ON v.customer_id = c.id
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_rewards_redeemed
                FROM local_redemptions
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) r ON r.customer_id = c.id
            WHERE c.cafe_id = $1
            ORDER BY c.is_vip DESC, COALESCE(v.total_visits, 0) DESC, c.created_at ASC
            LIMIT 10
            """,
            cafe_id,
        )

        return {
            "totals": _row_to_dict(totals_row),
            "programs": _rows_to_dict(program_rows),
            "top_locals": _rows_to_dict(top_locals_rows),
        }
