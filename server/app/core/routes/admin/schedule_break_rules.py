"""Platform-admin review surface for structured schedule break rules."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from app.core.dependencies import require_admin
from app.core.models.schedule_break_rules import BreakRuleSetImport, BreakRuleSetReview
from app.core.services.schedule_break_rule_import import (
    import_break_rule_sets,
    review_break_rule_set,
)
from app.database import get_connection


router = APIRouter()


def _serialize(row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "jurisdiction_id": str(row["jurisdiction_id"]) if row["jurisdiction_id"] else None,
        "industry_code": row["industry_code"],
        "effective_from": row["effective_from"].isoformat(),
        "effective_to": row["effective_to"].isoformat() if row["effective_to"] else None,
        "rules": row["rules"],
        "citation": row["citation"],
        "authority_url": row["authority_url"],
        "source_type": row["source_type"],
        "source_external_id": row["source_external_id"],
        "source_version": row["source_version"],
        "review_status": row["review_status"],
        "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] else None,
        "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
    }


@router.post("/schedule-break-rules/import", dependencies=[Depends(require_admin)])
async def import_schedule_break_rules(
    payload: list[BreakRuleSetImport],
    current_user=Depends(require_admin),
):
    async with get_connection() as conn:
        try:
            ids = await import_break_rule_sets(
                conn,
                rows=payload,
                actor_user_id=current_user.id,
            )
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise HTTPException(status_code=409, detail="A rule with this source identity already exists")
            raise
    return {"imported": len(ids), "ids": [str(value) for value in ids], "review_status": "pending"}


@router.post("/schedule-break-rules/import-csv", dependencies=[Depends(require_admin)])
async def import_schedule_break_rules_csv(
    file: UploadFile = File(...),
    current_user=Depends(require_admin),
):
    raw = await file.read()
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        payload: list[BreakRuleSetImport] = []
        for row in rows:
            payload.append(BreakRuleSetImport(
                jurisdiction_id=UUID(row["jurisdiction_id"]) if row.get("jurisdiction_id") else None,
                industry_code=row.get("industry_code") or None,
                effective_from=date.fromisoformat(row["effective_from"]),
                effective_to=date.fromisoformat(row["effective_to"]) if row.get("effective_to") else None,
                rules=json.loads(row["rules_json"]),
                citation=row["citation"],
                authority_url=row.get("authority_url") or None,
                source_type="csv",
                source_external_id=row.get("source_external_id") or None,
                source_version=row.get("source_version") or None,
            ))
    except (UnicodeDecodeError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid schedule break CSV: {exc}")

    async with get_connection() as conn:
        ids = await import_break_rule_sets(conn, rows=payload, actor_user_id=current_user.id)
    return {"imported": len(ids), "ids": [str(value) for value in ids], "review_status": "pending"}


@router.get("/schedule-break-rules", dependencies=[Depends(require_admin)])
async def list_schedule_break_rules(
    review_status: str | None = Query(default=None),
    current_user=Depends(require_admin),
):
    del current_user
    async with get_connection() as conn:
        if review_status is None:
            rows = await conn.fetch(
                """
                SELECT id, jurisdiction_id, industry_code, effective_from, effective_to,
                       rules, citation, authority_url, source_type, source_external_id,
                       source_version, review_status, reviewed_by, reviewed_at
                FROM schedule_break_rule_sets
                WHERE is_active = true
                ORDER BY review_status, effective_from DESC, created_at DESC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, jurisdiction_id, industry_code, effective_from, effective_to,
                       rules, citation, authority_url, source_type, source_external_id,
                       source_version, review_status, reviewed_by, reviewed_at
                FROM schedule_break_rule_sets
                WHERE is_active = true AND review_status = $1
                ORDER BY effective_from DESC, created_at DESC
                """,
                review_status,
            )
    return {"rules": [_serialize(row) for row in rows]}


@router.post("/schedule-break-rules/{rule_set_id}/review", dependencies=[Depends(require_admin)])
async def review_schedule_break_rule(
    rule_set_id: UUID,
    body: BreakRuleSetReview,
    current_user=Depends(require_admin),
):
    async with get_connection() as conn:
        try:
            result = await review_break_rule_set(
                conn,
                rule_set_id=rule_set_id,
                decision=body.decision,
                actor_user_id=current_user.id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid schedule break rules: {exc}")
    return {
        "id": str(result["id"]),
        "review_status": result["review_status"],
        "reviewed_by": str(result["reviewed_by"]),
        "reviewed_at": result["reviewed_at"].isoformat(),
    }
