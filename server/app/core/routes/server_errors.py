"""Admin endpoints for browsing server-side error reports."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_admin
from ...database import get_connection

router = APIRouter()

_VALID_KINDS = {
    "exception", "http_error", "db_error", "background_task",
    "celery_task", "startup", "warning", "unhandled",
}
_VALID_SOURCES = {"api", "celery", "worker", "startup"}


@router.get("/admin/server-errors", dependencies=[Depends(require_admin)])
async def list_server_errors(
    kind: Optional[str] = None,
    source: Optional[str] = None,
    resolved: Optional[bool] = None,
    search: Optional[str] = Query(None, description="Substring match on message"),
    since_hours: int = 24,
    limit: int = 100,
    offset: int = 0,
):
    if since_hours < 1 or since_hours > 720:
        since_hours = 24
    if limit < 1 or limit > 500:
        limit = 100
    if offset < 0:
        offset = 0
    if kind and kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail="invalid kind")
    if source and source not in _VALID_SOURCES:
        raise HTTPException(status_code=400, detail="invalid source")

    filters = ["last_seen > NOW() - ($1 || ' hours')::interval"]
    args: list[Any] = [str(since_hours)]
    if kind:
        args.append(kind)
        filters.append(f"kind = ${len(args)}")
    if source:
        args.append(source)
        filters.append(f"source = ${len(args)}")
    if resolved is True:
        filters.append("resolved_at IS NOT NULL")
    elif resolved is False:
        filters.append("resolved_at IS NULL")
    if search:
        args.append(f"%{search.lower()}%")
        filters.append(f"LOWER(message) LIKE ${len(args)}")

    args.append(limit)
    args.append(offset)

    async with get_connection() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM server_error_reports WHERE {' AND '.join(filters)}",
            *args[:-2],
        )
        rows = await conn.fetch(
            f"""
            SELECT id, fingerprint, kind, level, logger_name, message,
                   exception_type, traceback, source, hostname,
                   request_method, request_path, request_status,
                   user_id, user_email, context,
                   occurrences, first_seen, last_seen, resolved_at
            FROM server_error_reports
            WHERE {' AND '.join(filters)}
            ORDER BY last_seen DESC
            LIMIT ${len(args) - 1} OFFSET ${len(args)}
            """,
            *args,
        )

    return {
        "total": int(total or 0),
        "items": [
            {
                "id": str(r["id"]),
                "fingerprint": r["fingerprint"],
                "kind": r["kind"],
                "level": r["level"],
                "logger_name": r["logger_name"],
                "message": r["message"],
                "exception_type": r["exception_type"],
                "traceback": r["traceback"],
                "source": r["source"],
                "hostname": r["hostname"],
                "request_method": r["request_method"],
                "request_path": r["request_path"],
                "request_status": r["request_status"],
                "user_id": str(r["user_id"]) if r["user_id"] else None,
                "user_email": r["user_email"],
                "context": (
                    json.loads(r["context"]) if isinstance(r["context"], str)
                    else r["context"]
                ),
                "occurrences": int(r["occurrences"]),
                "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/admin/server-errors/stats", dependencies=[Depends(require_admin)])
async def server_errors_stats(since_hours: int = 24):
    if since_hours < 1 or since_hours > 720:
        since_hours = 24
    async with get_connection() as conn:
        by_kind = await conn.fetch(
            """
            SELECT kind, COUNT(*) as count, SUM(occurrences) as occurrences
            FROM server_error_reports
            WHERE last_seen > NOW() - ($1 || ' hours')::interval
              AND resolved_at IS NULL
            GROUP BY kind
            ORDER BY occurrences DESC
            """,
            str(since_hours),
        )
        top = await conn.fetch(
            """
            SELECT id, message, kind, exception_type, occurrences, last_seen
            FROM server_error_reports
            WHERE last_seen > NOW() - ($1 || ' hours')::interval
              AND resolved_at IS NULL
            ORDER BY occurrences DESC
            LIMIT 20
            """,
            str(since_hours),
        )
        by_source = await conn.fetch(
            """
            SELECT source, COUNT(*) as count, SUM(occurrences) as occurrences
            FROM server_error_reports
            WHERE last_seen > NOW() - ($1 || ' hours')::interval
              AND resolved_at IS NULL
            GROUP BY source
            """,
            str(since_hours),
        )

    return {
        "by_kind": [
            {"kind": r["kind"], "count": int(r["count"]), "occurrences": int(r["occurrences"] or 0)}
            for r in by_kind
        ],
        "by_source": [
            {"source": r["source"], "count": int(r["count"]), "occurrences": int(r["occurrences"] or 0)}
            for r in by_source
        ],
        "top": [
            {
                "id": str(r["id"]),
                "message": r["message"],
                "kind": r["kind"],
                "exception_type": r["exception_type"],
                "occurrences": int(r["occurrences"]),
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            }
            for r in top
        ],
    }


@router.post("/admin/server-errors/{error_id}/resolve", dependencies=[Depends(require_admin)])
async def resolve_server_error(error_id: str):
    async with get_connection() as conn:
        row = await conn.execute(
            "UPDATE server_error_reports SET resolved_at = NOW() WHERE id = $1 AND resolved_at IS NULL",
            error_id,
        )
    if row == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Not found or already resolved")
    return {"ok": True}


@router.post("/admin/server-errors/{error_id}/unresolve", dependencies=[Depends(require_admin)])
async def unresolve_server_error(error_id: str):
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE server_error_reports SET resolved_at = NULL WHERE id = $1",
            error_id,
        )
    return {"ok": True}


@router.delete("/admin/server-errors", dependencies=[Depends(require_admin)])
async def clear_server_errors(older_than_days: int = Query(30, ge=1, le=365)):
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM server_error_reports WHERE last_seen < NOW() - ($1 || ' days')::interval",
            str(older_than_days),
        )
    return {"ok": True, "result": result}
