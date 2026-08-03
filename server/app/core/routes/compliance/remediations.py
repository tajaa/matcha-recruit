"""remediations routes (L9 split)."""
from typing import List, Optional

from fastapi import Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.core.models.compliance import (
    RemediationDismissRequest,
    RemediationNoteRequest,
    RemediationRecord,
    RemediationReopenRequest,
)
from app.core.services.compliance_remediation import (
    annotate_issue,
    dismiss_issue,
    fetch_recent_remediations,
    reopen_issue,
)
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client

from ._shared import resolve_company_id, router, shared_router



@shared_router.get("/remediations", response_model=List[RemediationRecord])
async def list_remediations_endpoint(
    days: int = Query(90, ge=1, le=365),
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resolved + dismissed compliance issues — the documentation trail."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await fetch_recent_remediations(conn, company_id, days=days)




@router.post("/remediations/dismiss")
async def dismiss_remediation_endpoint(
    data: RemediationDismissRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dismiss an open issue as a false positive (with a reason). It re-surfaces
    only if its underlying values later change."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    if not (data.reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required to dismiss an issue")
    async with get_connection() as conn:
        ok = await dismiss_issue(conn, company_id, data.issue_key, data.reason.strip(), current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="No open issue with that key")
    return {"status": "dismissed", "issue_key": data.issue_key}




@router.post("/remediations/note")
async def annotate_remediation_endpoint(
    data: RemediationNoteRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Record a resolution note/method against an issue for the trail."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        ok = await annotate_issue(conn, company_id, data.issue_key, (data.note or "").strip(), current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown issue key")
    return {"status": "noted", "issue_key": data.issue_key}




@router.post("/remediations/reopen")
async def reopen_remediation_endpoint(
    data: RemediationReopenRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Undo a dismissal — return the issue to the active queue."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        ok = await reopen_issue(conn, company_id, data.issue_key, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="No dismissed issue with that key")
    return {"status": "open", "issue_key": data.issue_key}
