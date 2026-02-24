from io import BytesIO
import mimetypes
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ...matcha.dependencies import get_client_company_id, require_admin_or_client
from ..models.auth import CurrentUser
from ..models.handbook import (
    CompanyHandbookProfileInput,
    CompanyHandbookProfileResponse,
    HandbookAcknowledgementSummary,
    HandbookChangeRequestResponse,
    HandbookCreateRequest,
    HandbookDetailResponse,
    HandbookDistributionResponse,
    HandbookGuidedDraftRequest,
    HandbookGuidedDraftResponse,
    HandbookListItemResponse,
    HandbookPublishResponse,
    HandbookUpdateRequest,
    HandbookWizardDraftResponse,
    HandbookWizardDraftUpsertRequest,
)
from ..services.handbook_service import GuidedDraftRateLimitError, HandbookService
from ..services.storage import get_storage

router = APIRouter(prefix="/handbooks", tags=["handbooks"])


@router.get("", response_model=List[HandbookListItemResponse])
async def list_handbooks(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    return await HandbookService.list_handbooks(str(company_id))


@router.get("/profile", response_model=CompanyHandbookProfileResponse)
async def get_handbook_profile(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    return await HandbookService.get_or_default_profile(str(company_id))


@router.put("/profile", response_model=CompanyHandbookProfileResponse)
async def update_handbook_profile(
    data: CompanyHandbookProfileInput,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    return await HandbookService.upsert_profile(str(company_id), data, str(current_user.id))


@router.post("/upload")
async def upload_handbook_file(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    storage = get_storage()
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    uploaded_url = await storage.upload_file(
        file_bytes=file_bytes,
        filename=file.filename or "handbook.pdf",
        prefix="handbooks",
        content_type=file.content_type,
    )
    return {
        "url": uploaded_url,
        "filename": file.filename or "handbook.pdf",
        "company_id": str(company_id),
    }


@router.post("", response_model=HandbookDetailResponse)
async def create_handbook(
    data: HandbookCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    try:
        return await HandbookService.create_handbook(
            str(company_id),
            data,
            str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/guided-draft", response_model=HandbookGuidedDraftResponse)
async def guided_handbook_draft(
    data: HandbookGuidedDraftRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    try:
        return await HandbookService.generate_guided_draft(
            str(company_id),
            data,
        )
    except GuidedDraftRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wizard-draft", response_model=Optional[HandbookWizardDraftResponse])
async def get_handbook_wizard_draft(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    return await HandbookService.get_wizard_draft(str(company_id), str(current_user.id))


@router.put("/wizard-draft", response_model=HandbookWizardDraftResponse)
async def upsert_handbook_wizard_draft(
    data: HandbookWizardDraftUpsertRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    try:
        return await HandbookService.upsert_wizard_draft(
            str(company_id),
            str(current_user.id),
            data.state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/wizard-draft")
async def delete_handbook_wizard_draft(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    deleted = await HandbookService.delete_wizard_draft(str(company_id), str(current_user.id))
    return {"deleted": deleted}


@router.get("/{handbook_id}", response_model=HandbookDetailResponse)
async def get_handbook(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    handbook = await HandbookService.get_handbook_by_id(handbook_id, str(company_id))
    if handbook is None:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return handbook


@router.put("/{handbook_id}", response_model=HandbookDetailResponse)
async def update_handbook(
    handbook_id: str,
    data: HandbookUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        handbook = await HandbookService.update_handbook(
            handbook_id,
            str(company_id),
            data,
            str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if handbook is None:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return handbook


@router.post("/{handbook_id}/publish", response_model=HandbookPublishResponse)
async def publish_handbook(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    handbook = await HandbookService.publish_handbook(handbook_id, str(company_id))
    if handbook is None:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return handbook


@router.post("/{handbook_id}/archive")
async def archive_handbook(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await HandbookService.archive_handbook(handbook_id, str(company_id))
    if not success:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return {"message": "Handbook archived successfully"}


@router.get("/{handbook_id}/changes", response_model=List[HandbookChangeRequestResponse])
async def list_handbook_changes(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    handbook = await HandbookService.get_handbook_by_id(handbook_id, str(company_id))
    if handbook is None:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return await HandbookService.list_change_requests(handbook_id, str(company_id))


@router.post("/{handbook_id}/changes/{change_id}/accept", response_model=HandbookChangeRequestResponse)
async def accept_handbook_change(
    handbook_id: str,
    change_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    change = await HandbookService.resolve_change_request(
        handbook_id,
        str(company_id),
        change_id,
        "accepted",
        str(current_user.id),
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return change


@router.post("/{handbook_id}/changes/{change_id}/reject", response_model=HandbookChangeRequestResponse)
async def reject_handbook_change(
    handbook_id: str,
    change_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    change = await HandbookService.resolve_change_request(
        handbook_id,
        str(company_id),
        change_id,
        "rejected",
        str(current_user.id),
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return change


@router.post("/{handbook_id}/distribute", response_model=HandbookDistributionResponse)
async def distribute_handbook(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        result = await HandbookService.distribute_to_employees(
            handbook_id,
            str(company_id),
            str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return result


@router.get("/{handbook_id}/acknowledgements", response_model=HandbookAcknowledgementSummary)
async def get_handbook_acknowledgements(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    summary = await HandbookService.get_acknowledgement_summary(handbook_id, str(company_id))
    if summary is None:
        raise HTTPException(status_code=404, detail="Handbook not found")
    return summary


@router.get("/{handbook_id}/pdf")
async def download_handbook_pdf(
    handbook_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    handbook = await HandbookService.get_handbook_by_id(handbook_id, str(company_id))
    if handbook is None:
        raise HTTPException(status_code=404, detail="Handbook not found")

    # Upload-sourced handbooks must serve the original uploaded document.
    if handbook.source_type == "upload":
        if not handbook.file_url:
            raise HTTPException(status_code=409, detail="Uploaded handbook file is missing")
        try:
            file_bytes = await get_storage().download_file(handbook.file_url)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Failed to download uploaded handbook file") from exc
        filename = handbook.file_name or "employee-handbook"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return StreamingResponse(
            BytesIO(file_bytes),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    try:
        pdf_bytes, filename = await HandbookService.generate_handbook_pdf_bytes(handbook_id, str(company_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
