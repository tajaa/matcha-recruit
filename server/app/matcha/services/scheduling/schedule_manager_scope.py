"""Who may run a store's schedule, and which stores.

Business admins — exactly the roles `require_admin_or_client` admits — manage
every store, as they always have, and go through the original tenant checks
untouched. An `employee` manages the stores of their own active employee rows
flagged `is_manager`/`is_supervisor` with a work location: the predicate
`schedule_eligibility_authorization.resolve_eligibility_manager_scope` already
uses for eligibility cases and the Huume session. This module adds the caller's
own employee ids, which the request queue needs so a store manager never
reviews their own swap.

A scoped manager can read a shift with no store (it shows on every store's
board) but cannot change it: nothing ties it to a store they run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

# Mirrors `require_admin_or_client`. `individual` stays company-wide here even
# though the eligibility resolver treats it as scoped: these routes admitted it
# company-wide before store managers existed, and that must not change.
COMPANY_WIDE_ROLES = frozenset({"admin", "client", "individual"})

UNSCOPED_SHIFT_READ_ONLY = {
    "code": "unscoped_shift_read_only",
    "message": "This shift has no store, so only a business admin can change it.",
}

# One row per employee record the caller holds in this company. `manages` is
# the eligibility resolver's predicate, kept in step with it on purpose.
_ACTOR_ROWS_SQL = """
    SELECT id, work_location_id,
           (COALESCE(employment_status, 'active') = 'active'
            AND (COALESCE(is_manager, false) OR COALESCE(is_supervisor, false))
            AND work_location_id IS NOT NULL) AS manages
      FROM employees
     WHERE org_id = $1 AND user_id = $2
"""

# The same predicate without the company, for the route gate that runs before
# the company is resolved. The handler's resolver is the real check.
MANAGES_ANY_STORE_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM employees
         WHERE user_id = $1
           AND COALESCE(employment_status, 'active') = 'active'
           AND (COALESCE(is_manager, false) OR COALESCE(is_supervisor, false))
           AND work_location_id IS NOT NULL
    )
"""


def request_scope_sql(locs: str) -> str:
    """The one rule for which schedule requests a scoped manager handles.

    Every store the request touches must be theirs: the requester's, the
    coworker's on a swap or pickup, and both shifts'. A request on a shift with
    no store is left to business admins, matching the read-only rule above.
    Uses `REQUEST_SELECT`'s aliases (r, e, te, s, cs); ``locs`` is a uuid[]
    expression such as ``"$3::uuid[]"``. The list, the review and the
    notification recipients all build on this, so they cannot disagree.
    """
    return (
        f"(e.work_location_id = ANY({locs})"
        f" AND (r.shift_id IS NULL OR s.location_id = ANY({locs}))"
        f" AND (r.counter_shift_id IS NULL OR cs.location_id = ANY({locs}))"
        f" AND (r.target_employee_id IS NULL OR te.work_location_id = ANY({locs})))"
    )


@dataclass(frozen=True)
class ScheduleManagerScope:
    company_wide: bool
    location_ids: frozenset[UUID] = frozenset()
    actor_employee_ids: frozenset[UUID] = frozenset()

    def permits(self, location_id: Optional[UUID]) -> bool:
        return self.company_wide or (location_id is not None and location_id in self.location_ids)

    def assert_shift(self, location_id: Optional[UUID]) -> None:
        """Refuse a write to a shift outside a scoped manager's stores.

        Another store's shift is a 404, so the response says nothing about
        whether it exists (the eligibility-case rule).
        """
        if self.company_wide:
            return
        if location_id is None:
            raise HTTPException(status_code=403, detail=UNSCOPED_SHIFT_READ_ONLY)
        if location_id not in self.location_ids:
            raise HTTPException(status_code=404, detail="Shift not found")

    def is_own_request(self, employee_id: Optional[UUID], target_employee_id: Optional[UUID]) -> bool:
        return bool(self.actor_employee_ids) and (
            employee_id in self.actor_employee_ids or target_employee_id in self.actor_employee_ids
        )


COMPANY_WIDE = ScheduleManagerScope(company_wide=True)


async def resolve_schedule_manager_scope(conn, *, company_id: UUID, user) -> ScheduleManagerScope:
    """Company-wide for business admins (no query); the managed stores for an
    employee manager; 403 for anyone else, including a caller with no role."""
    role = getattr(user, "role", None)
    if role in COMPANY_WIDE_ROLES:
        return COMPANY_WIDE
    if role == "employee":
        rows = await conn.fetch(_ACTOR_ROWS_SQL, company_id, user.id)
        locations = frozenset(row["work_location_id"] for row in rows if row["manages"])
        if locations:
            return ScheduleManagerScope(
                company_wide=False,
                location_ids=locations,
                actor_employee_ids=frozenset(row["id"] for row in rows),
            )
    raise HTTPException(status_code=403, detail="You are not a manager for any store")
