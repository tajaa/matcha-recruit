"""Cappe public surface — form submissions."""
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...services.email import dashboard_url, send_cappe_form_alert_email
from .._shared import _site_owner
from ._common import _published_site, _reject_reserved

router = APIRouter()

# Max serialized size of a public form submission's `data` blob. Public form
# intake is unauthenticated and stored verbatim, so cap it to stop multi-MB
# junk payloads from bloating cappe_form_submissions.
_MAX_FORM_DATA_BYTES = 16 * 1024  # 16 KB


@router.post("/public/sites/{slug}/forms/{form_slug}", status_code=status.HTTP_201_CREATED)
async def public_submit_form(slug: str, form_slug: str, body: dict, request: Request, background: BackgroundTasks):
    """Store a submission. `body` shape: {data: {...}, submitter_email?: str}."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_form", 5, 60)
    await check_rate_limit(ip, "cappe_form_hr", 30, 3600)
    # TODO(captcha): verify a challenge token before insert (spam surface).

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        data = {k: v for k, v in (body or {}).items() if k not in ("submitter_email",)}
    submitter_email = (body or {}).get("submitter_email") if isinstance(body, dict) else None
    if submitter_email:
        submitter_email = str(submitter_email).strip().lower()
        _reject_reserved(submitter_email)

    # Cap the stored payload: this endpoint is public + unauthenticated and the
    # blob is persisted verbatim, so reject oversized submissions rather than let
    # them bloat the table.
    serialized_data = json.dumps(data)
    if len(serialized_data.encode("utf-8")) > _MAX_FORM_DATA_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Submission is too large",
        )

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        form = await conn.fetchrow(
            "SELECT id, name, status FROM cappe_forms WHERE site_id = $1 AND slug = $2", site["id"], form_slug
        )
        if form is None or form["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")
        await conn.execute(
            "INSERT INTO cappe_form_submissions (form_id, site_id, data, submitter_email) "
            "VALUES ($1, $2, $3, $4)",
            form["id"], site["id"], serialized_data, submitter_email,
        )
        owner = await _site_owner(conn, site["id"])

    # Best-effort alert to the creator (submission content is not echoed).
    if owner and owner["email"]:
        background.add_task(
            send_cappe_form_alert_email, owner["email"], owner["name"], site["name"],
            form["name"], dashboard_url(f"/sites/{site['id']}/forms"),
        )
    return {"ok": True}
