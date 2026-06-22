"""Claims-readiness / defense packet for an IR incident (PDF download).

A defensible documentation record (timeline + witnesses + investigation docs +
policy-violation mapping + corrective actions) repackaged from existing incident
data. Tenant-isolated; rides the package's `incidents` feature gate. 2-segment
path so it never shadows / is shadowed by CRUD's `/{incident_id}`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.services import claims_readiness

router = APIRouter()


@router.get("/{incident_id}/claims-readiness.pdf")
async def incident_claims_readiness_pdf(
    incident_id: UUID, current_user=Depends(require_admin_or_client)
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    async with get_connection() as conn:
        data = await claims_readiness.build_incident_packet(conn, incident_id, company_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    pdf = await claims_readiness.render_incident_packet_pdf(data)
    num = str(data["incident"].get("incident_number") or incident_id).replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="claims-readiness-{num}.pdf"'},
    )
