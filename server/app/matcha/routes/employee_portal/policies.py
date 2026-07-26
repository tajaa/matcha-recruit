"""Company policy search/read for the employee portal."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_connection
from app.matcha.dependencies import require_employee_record

from ._shared import _policies_dep

router = APIRouter()


@router.get("/policies", dependencies=_policies_dep)
async def search_policies(
    q: Optional[str] = None,
    employee: dict = Depends(require_employee_record)
):
    """Search company policies."""
    async with get_connection() as conn:
        if q:
            # Search by title or content
            policies = await conn.fetch(
                """SELECT id, title, description, content, version, status, created_at
                   FROM policies
                   WHERE company_id = $1
                   AND status = 'active'
                   AND (
                       title ILIKE $2 OR
                       description ILIKE $2 OR
                       content ILIKE $2
                   )
                   ORDER BY title ASC""",
                employee["org_id"], f"%{q}%"
            )
        else:
            # List all active policies
            policies = await conn.fetch(
                """SELECT id, title, description, content, version, status, created_at
                   FROM policies
                   WHERE company_id = $1 AND status = 'active'
                   ORDER BY title ASC""",
                employee["org_id"]
            )

        return {
            "policies": [
                {
                    "id": str(p["id"]),
                    "title": p["title"],
                    "description": p["description"],
                    "content": p["content"][:500] + "..." if p["content"] and len(p["content"]) > 500 else p["content"],
                    "version": p["version"],
                    "created_at": p["created_at"].isoformat() if p["created_at"] else None
                } for p in policies
            ],
            "total": len(policies)
        }


@router.get("/policies/{policy_id}", dependencies=_policies_dep)
async def get_policy(
    policy_id: UUID,
    employee: dict = Depends(require_employee_record)
):
    """Get a specific policy."""
    async with get_connection() as conn:
        policy = await conn.fetchrow(
            """SELECT id, title, description, content, file_url, version, status, created_at
               FROM policies
               WHERE id = $1 AND company_id = $2 AND status = 'active'""",
            policy_id, employee["org_id"]
        )

        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found"
            )

        return {
            "id": str(policy["id"]),
            "title": policy["title"],
            "description": policy["description"],
            "content": policy["content"],
            "file_url": policy["file_url"],
            "version": policy["version"],
            "created_at": policy["created_at"].isoformat() if policy["created_at"] else None
        }
