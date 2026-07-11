"""ACORD form generation routes (`/acord`, feature `acord_forms`).

Branded ACORD 125/126/130/140 equivalents rendered from data already held.
Tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import acord_forms

router = APIRouter()


async def _require_company_id(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


@router.get("/forms")
async def list_forms(current_user=Depends(require_admin_or_client)):
    """The generatable ACORD forms."""
    await _require_company_id(current_user)
    return {"forms": [{"form": k, "label": v} for k, v in acord_forms.FORMS.items()]}


@router.get("/{form}.pdf")
async def get_form_pdf(form: str, current_user=Depends(require_admin_or_client)):
    """Render one branded ACORD form to PDF."""
    if form not in acord_forms.FORMS:
        raise HTTPException(status_code=404, detail="Unknown ACORD form")
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        ctx = await acord_forms.build_acord_context(conn, company_id)
    pdf = await acord_forms.render_acord_pdf(form, ctx)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="acord-{form}.pdf"'},
    )
