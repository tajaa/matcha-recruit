"""Controls-evidence routes (`/controls-evidence`, feature `controls_evidence`).

Universal "proof of controls" register + underwriter packet (WTW p.85
"mitigation-evidence systems of record"). Auto-fills from existing HR / safety /
compliance data (reusing the EPL-readiness engine + IR/OSHA + credentialing +
safety-program queries); companies verify/annotate each control and export the
packet. Business-facing; tenant-isolated by company. The broker-facing surfaces
live in `broker_submission.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, Response

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ...services import controls_evidence as ce
from ...models.controls_evidence import ControlEvidenceUpdate

router = APIRouter()

_VALID_KEYS = {c["key"] for c in ce.CONTROL_CATALOG}


@router.get("/register")
async def get_register(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await ce.build_register(conn, company_id)


@router.get("/summary")
async def get_summary(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        reg = await ce.build_register(conn, company_id)
    return reg["summary"]


@router.put("/controls/{control_key}")
async def upsert_control(
    control_key: str,
    body: ControlEvidenceUpdate,
    current_user=Depends(require_admin_or_client),
):
    if control_key not in _VALID_KEYS:
        raise HTTPException(status_code=404, detail="Unknown control")
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO company_control_evidence
                (company_id, control_key, status, note, verified_at, updated_by, updated_at)
            VALUES ($1, $2, $3, $4, CASE WHEN $5 THEN NOW() ELSE NULL END, $6, NOW())
            ON CONFLICT ON CONSTRAINT uq_company_control_evidence DO UPDATE SET
                status = EXCLUDED.status,
                note = EXCLUDED.note,
                verified_at = CASE WHEN $5 THEN NOW() ELSE company_control_evidence.verified_at END,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            company_id, control_key, body.status, body.note, body.verified, current_user.id,
        )
        return await ce.build_register(conn, company_id)


@router.get("/packet.pdf")
async def packet_pdf(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        register = await ce.build_register(conn, company_id)
    name = company["name"] if company else "Client"
    pdf = await ce.render_controls_packet(name, register)
    safe = name.replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="proof-of-controls-{safe}.pdf"'},
    )
