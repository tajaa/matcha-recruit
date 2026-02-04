"""Audit logging for Tier 1 structured data operations."""

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import asyncpg


class AuditEventType:
    """Constants for audit event types."""

    # Fetch events
    FETCH_START = "fetch_start"
    FETCH_SUCCESS = "fetch_success"
    FETCH_ERROR = "fetch_error"

    # Parse events
    PARSE_REJECT = "parse_reject"
    BOUNDS_REJECT = "bounds_reject"
    DATE_REJECT = "date_reject"

    # Usage events
    TIER1_USE = "tier1_use"
    TIER1_SKIP = "tier1_skip"
    TIER1_FALLBACK = "tier1_fallback"

    # Verification events
    VERIFICATION_PENDING = "verification_pending"
    VERIFICATION_APPROVED = "verification_approved"
    VERIFICATION_REJECTED = "verification_rejected"

    # Circuit breaker events
    CIRCUIT_OPEN = "circuit_open"
    CIRCUIT_CLOSE = "circuit_close"


async def log_tier1_event(
    conn: asyncpg.Connection,
    event_type: str,
    source_id: Optional[UUID] = None,
    jurisdiction_id: Optional[UUID] = None,
    cache_id: Optional[UUID] = None,
    details: Optional[dict[str, Any]] = None,
    triggered_by: Optional[str] = None,
) -> None:
    """
    Log a Tier 1 structured data event to the audit log.

    Args:
        conn: Database connection
        event_type: Type of event (use AuditEventType constants)
        source_id: ID of the structured data source
        jurisdiction_id: ID of the jurisdiction
        cache_id: ID of the cache entry
        details: Additional event details as dict
        triggered_by: What triggered this event (e.g., 'background_check', 'stream_check')
    """
    try:
        await conn.execute(
            """
            INSERT INTO structured_data_audit_log
            (event_type, source_id, jurisdiction_id, cache_id, details, triggered_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            event_type,
            source_id,
            jurisdiction_id,
            cache_id,
            json.dumps(details) if details else None,
            triggered_by,
        )
    except Exception as e:
        # Don't let audit logging failures break the main flow
        print(f"[Audit] Failed to log event {event_type}: {e}")


async def log_fetch_start(
    conn: asyncpg.Connection,
    source_id: UUID,
    source_url: str,
    triggered_by: str = "scheduler",
) -> None:
    """Log the start of a source fetch."""
    await log_tier1_event(
        conn,
        AuditEventType.FETCH_START,
        source_id=source_id,
        details={"source_url": source_url},
        triggered_by=triggered_by,
    )


async def log_fetch_success(
    conn: asyncpg.Connection,
    source_id: UUID,
    record_count: int,
    triggered_by: str = "scheduler",
) -> None:
    """Log successful source fetch."""
    await log_tier1_event(
        conn,
        AuditEventType.FETCH_SUCCESS,
        source_id=source_id,
        details={"record_count": record_count},
        triggered_by=triggered_by,
    )


async def log_fetch_error(
    conn: asyncpg.Connection,
    source_id: UUID,
    error: str,
    triggered_by: str = "scheduler",
) -> None:
    """Log source fetch error."""
    await log_tier1_event(
        conn,
        AuditEventType.FETCH_ERROR,
        source_id=source_id,
        details={"error": error},
        triggered_by=triggered_by,
    )


async def log_bounds_reject(
    conn: asyncpg.Connection,
    source_id: UUID,
    jurisdiction_name: str,
    value: float,
    reason: str,
) -> None:
    """Log rejection due to out-of-bounds value."""
    await log_tier1_event(
        conn,
        AuditEventType.BOUNDS_REJECT,
        source_id=source_id,
        details={
            "jurisdiction": jurisdiction_name,
            "value": value,
            "reason": reason,
        },
        triggered_by="parser",
    )


async def log_tier1_use(
    conn: asyncpg.Connection,
    jurisdiction_id: UUID,
    cache_ids: list[UUID],
    category: str,
    triggered_by: str,
) -> None:
    """Log when Tier 1 data is used in a compliance check."""
    await log_tier1_event(
        conn,
        AuditEventType.TIER1_USE,
        jurisdiction_id=jurisdiction_id,
        details={
            "cache_ids": [str(cid) for cid in cache_ids],
            "category": category,
            "count": len(cache_ids),
        },
        triggered_by=triggered_by,
    )


async def log_tier1_skip(
    conn: asyncpg.Connection,
    jurisdiction_id: UUID,
    reason: str,
    triggered_by: str,
) -> None:
    """Log when Tier 1 data is skipped (falling back to Tier 2/3)."""
    await log_tier1_event(
        conn,
        AuditEventType.TIER1_SKIP,
        jurisdiction_id=jurisdiction_id,
        details={"reason": reason},
        triggered_by=triggered_by,
    )


async def log_circuit_open(
    conn: asyncpg.Connection,
    source_id: UUID,
    consecutive_failures: int,
    open_until: datetime,
) -> None:
    """Log when circuit breaker opens for a source."""
    await log_tier1_event(
        conn,
        AuditEventType.CIRCUIT_OPEN,
        source_id=source_id,
        details={
            "consecutive_failures": consecutive_failures,
            "open_until": open_until.isoformat(),
        },
        triggered_by="circuit_breaker",
    )


async def log_circuit_close(
    conn: asyncpg.Connection,
    source_id: UUID,
) -> None:
    """Log when circuit breaker closes for a source."""
    await log_tier1_event(
        conn,
        AuditEventType.CIRCUIT_CLOSE,
        source_id=source_id,
        triggered_by="circuit_breaker",
    )
