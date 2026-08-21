"""Location-scoped authorization for schedule eligibility cases."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException


@dataclass(frozen=True)
class EligibilityManagerScope:
    is_company_operations: bool
    managed_location_ids: frozenset[UUID]

    def permits(self, location_id: UUID | None) -> bool:
        return self.is_company_operations or (location_id is not None and location_id in self.managed_location_ids)


async def resolve_eligibility_manager_scope(conn, *, company_id: UUID, actor_user_id: UUID, actor_role: str) -> EligibilityManagerScope:
    if actor_role in {"admin", "client"}:
        return EligibilityManagerScope(True, frozenset())
    rows = await conn.fetch(
        """SELECT work_location_id FROM employees
           WHERE org_id=$1 AND user_id=$2
             AND COALESCE(employment_status, 'active')='active'
             AND (COALESCE(is_manager,false) OR COALESCE(is_supervisor,false))
             AND work_location_id IS NOT NULL""", company_id, actor_user_id,
    )
    return EligibilityManagerScope(False, frozenset(row["work_location_id"] for row in rows))


async def require_eligibility_case_access(conn, *, company_id: UUID, case_id: UUID, actor_user_id: UUID, actor_role: str, lock: bool = False):
    suffix = " FOR UPDATE" if lock else ""
    case = await conn.fetchrow(f"SELECT * FROM schedule_eligibility_cases WHERE id=$1 AND company_id=$2{suffix}", case_id, company_id)
    if not case:
        raise HTTPException(status_code=404, detail="Eligibility case not found")
    scope = await resolve_eligibility_manager_scope(conn, company_id=company_id, actor_user_id=actor_user_id, actor_role=actor_role)
    if not scope.permits(case["location_id"]):
        raise HTTPException(status_code=404, detail="Eligibility case not found")
    return case, scope
