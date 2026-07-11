"""Certificate-of-insurance tracking routes (`/coi`, feature `coi_tracking`).

Upload an inbound COI PDF → Gemini extracts carrier/limits/expiry → auto-verify
against the linked contract's required limits → expiry-tracked list. Certificates
are parsed-and-discarded (no PDF retained) in v1, mirroring contract intake.
Tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import coi_parser, coi_service

router = APIRouter()

_MAX_PDF_BYTES = 15 * 1024 * 1024


async def _require_company_id(current_user) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


@router.get("")
async def list_certs(current_user=Depends(require_admin_or_client)):
    """All certificates + status/gap rollup."""
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        return await coi_service.list_certificates(conn, company_id)


@router.post("")
async def upload_cert(
    file: UploadFile = File(...),
    holder_name: str | None = Form(None),
    contract_id: str | None = Form(None),
    current_user=Depends(require_admin_or_client),
):
    """Upload + parse a COI PDF, persist it, return the verified certificate list."""
    company_id = await _require_company_id(current_user)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Certificate PDF too large")

    parsed = await coi_parser.parse_certificate(data)
    cid = None
    if contract_id:
        try:
            cid = UUID(contract_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid contract_id")

    async with get_connection() as conn:
        await coi_service.create_certificate(
            conn, company_id, parsed,
            holder_name=holder_name, contract_id=cid,
            storage_path=None, source_filename=file.filename,
            uploaded_by=current_user.id,
        )
        return await coi_service.list_certificates(conn, company_id)


@router.delete("/{cert_id}")
async def delete_cert(cert_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await _require_company_id(current_user)
    async with get_connection() as conn:
        if not await coi_service.delete_certificate(conn, company_id, cert_id):
            raise HTTPException(status_code=404, detail="Certificate not found")
        return await coi_service.list_certificates(conn, company_id)
