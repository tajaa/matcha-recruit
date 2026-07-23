"""Benefits open-enrollment engine: elections, OE periods, life events.

Distinct from ``benefits_eligibility.py`` (the roster-ingest + exception
detector). This module owns the durable enrollment model — everything here
FKs ``employees.id``, never the mutable ``benefit_roster_entries`` snapshot.

Pure helpers (``resolve_active_window``, ``allowed_transition``,
``validate_election_payload``, ``compute_policy_month``) take no DB
connection and are unit-tested directly in
``server/tests/benefits/test_enrollment_rules.py``.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

NUDGE_AFTER_DAYS = 7
CLOSING_SOON_DAYS = 3

# status -> allowed next statuses per action
_ELECTION_TRANSITIONS: dict[str, dict[str, str]] = {
    "draft": {"submit": "submitted", "edit": "draft"},
    "submitted": {"approve": "approved", "reject": "rejected"},
    "approved": {},
    "rejected": {"edit": "draft"},
}


def allowed_transition(current_status: str, action: str) -> Optional[str]:
    """Return the resulting status for ``action`` from ``current_status``, or
    None if the transition is not allowed."""
    return _ELECTION_TRANSITIONS.get(current_status, {}).get(action)


def resolve_active_window(
    today: date,
    open_period_row: Optional[dict],
    approved_life_events: list[dict],
) -> Optional[dict]:
    """Pick the employee's active enrollment window.

    An open company-wide OE period covering ``today`` takes precedence;
    otherwise the most recently approved life event whose window hasn't
    lapsed. Returns ``{"kind": "oe"|"life_event", "id": ..., "row": ...}``
    or None.
    """
    if open_period_row is not None:
        starts_on = open_period_row["starts_on"]
        ends_on = open_period_row["ends_on"]
        if starts_on <= today <= ends_on:
            return {"kind": "oe", "id": open_period_row["id"], "row": open_period_row}

    eligible_events = [
        e for e in approved_life_events
        if e.get("window_ends_on") is not None and e["window_ends_on"] >= today
    ]
    if eligible_events:
        eligible_events = sorted(eligible_events, key=lambda e: e["window_ends_on"], reverse=True)
        chosen = eligible_events[0]
        return {"kind": "life_event", "id": chosen["id"], "row": chosen}

    return None


def validate_election_payload(
    plan_row: Optional[dict],
    tier_row: Optional[dict],
    waived: bool,
    plan_waivable_for_type: bool = True,
) -> None:
    """Raise ValueError if the plan/tier combination is inconsistent.

    Callers resolve plan_row/tier_row by id first (or None if not found /
    not in this company) and pass them in — this stays DB-free.
    """
    if waived:
        if not plan_waivable_for_type:
            raise ValueError("this plan type cannot be waived")
        return

    if plan_row is None:
        raise ValueError("plan not found")
    if tier_row is None:
        raise ValueError("tier not found")
    if str(tier_row["plan_id"]) != str(plan_row["id"]):
        raise ValueError("tier does not belong to plan")
    if plan_row.get("status") != "active":
        raise ValueError("plan is not active")


def compute_policy_month(today: date, plan_year_start: Optional[date]) -> Optional[int]:
    """Month-of-policy-year (1-12) given a plan year start date, else None."""
    if plan_year_start is None:
        return None
    return ((today.month - plan_year_start.month) % 12) + 1


def life_event_window_ends_on(event_date: date, today: date, window_days: int) -> date:
    return max(event_date, today) + timedelta(days=window_days)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

async def log_benefit_audit(
    conn,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    actor_role: Optional[str],
    entity_type: str,
    entity_id: Optional[UUID],
    action: str,
    detail: Optional[dict] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO benefit_enrollment_audit
            (company_id, actor_user_id, actor_role, entity_type, entity_id, action, detail)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        company_id,
        actor_user_id,
        actor_role,
        entity_type,
        entity_id,
        action,
        json.dumps(detail) if detail else "{}",
    )


# ---------------------------------------------------------------------------
# Email builders — pure, return (subject, html); no send here.
# ---------------------------------------------------------------------------

def _portal_link(app_base_url: str) -> str:
    return f"{app_base_url.rstrip('/')}/portal/benefits"


def build_window_opened_email(period_name: str, ends_on: date, app_base_url: str) -> tuple[str, str]:
    subject = f"Open enrollment is open: {period_name}"
    html = (
        f"<p>Open enrollment for <strong>{period_name}</strong> is now open, "
        f"through {ends_on.isoformat()}.</p>"
        f"<p><a href=\"{_portal_link(app_base_url)}\">Review your benefits</a></p>"
    )
    return subject, html


def build_unsubmitted_nudge_email(period_name: str, ends_on: date, app_base_url: str) -> tuple[str, str]:
    subject = f"Reminder: submit your benefits elections for {period_name}"
    html = (
        f"<p>You haven't submitted your benefits elections for "
        f"<strong>{period_name}</strong> yet. The window closes "
        f"{ends_on.isoformat()}.</p>"
        f"<p><a href=\"{_portal_link(app_base_url)}\">Submit your elections</a></p>"
    )
    return subject, html


def build_closing_soon_email(period_name: str, ends_on: date, app_base_url: str) -> tuple[str, str]:
    subject = f"Open enrollment closes soon: {period_name}"
    html = (
        f"<p><strong>{period_name}</strong> closes {ends_on.isoformat()}. "
        f"Submit your elections before then or your current coverage may lapse.</p>"
        f"<p><a href=\"{_portal_link(app_base_url)}\">Submit your elections</a></p>"
    )
    return subject, html
