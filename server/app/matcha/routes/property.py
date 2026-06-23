"""Commercial-property routes (`/property`, feature `property`).

Tenant-facing Statement of Values: the company records its buildings (COPE +
values); the engine computes TIV, insurance-to-value, and a COPE grade. Property
LIMITS ride the existing limit-adequacy engine (`line='property'`) and property
LOSS RUNS ride the broker loss-development surface — this router owns the SOV.
Catastrophe enrichment (geocode + per-peril hazard) is layered on in Phase 3.
Business-facing, tenant-isolated.
"""

import csv
import io
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import property_sov as sov
from ..services import property_sov_parser as sov_parser
from ..services import property_exposure as exposure
from ..services import property_recommendations as recs
from ..services import submission_readiness as sr
from ..models.property import BuildingUpsert, BuildingBulkInsert, BulkUploadResult

logger = logging.getLogger(__name__)
router = APIRouter()

# Columns for the CSV template + bulk-upload (the BuildingUpsert scalar fields).
_CSV_FIELDS = [
    "name", "address", "city", "state", "zipcode", "county", "occupancy",
    "construction_type", "year_built", "sq_ft", "stories", "roof_year", "sprinklered",
    "protection_class", "building_value", "contents_value", "bi_value",
    "replacement_cost", "insured_value", "note",
]
_MAX_BULK_ROWS = 1000
_MAX_CSV_BYTES = 10 * 1024 * 1024
_MAX_PARSE_BYTES = 15 * 1024 * 1024
# Gemini SOV parse accepts a PDF or a CSV/text export; xlsx must be saved-as-CSV first.
_PARSE_MIME_OK = ("pdf", "csv", "text", "plain", "tab-separated", "octet-stream")


def _trigger_cat(building_id) -> None:
    """Best-effort: queue geocode + catastrophe enrichment for a building. Never
    inline (external calls) and never fatal — if the broker/worker is down the
    periodic ``property_cat_refresh`` sweep picks it up later."""
    try:
        from app.workers.tasks.property_cat_refresh import refresh_property_cat
        refresh_property_cat.delay(building_id=str(building_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("property: could not queue cat refresh for %s: %s", building_id, exc)


async def _insert_buildings(conn, company_id, user_id, items: list[dict], bg: BackgroundTasks) -> dict:
    """Insert a list of building dicts, collecting a per-row result. Shared by the CSV
    bulk-upload and the parse→review→import paths. Cat refresh is queued per created id."""
    created, failed, errors, ids = 0, 0, [], []
    for i, data in enumerate(items, start=1):
        try:
            row = await sov.upsert_building(conn, company_id, None, data, user_id)
            if row:
                ids.append(row["id"])
                created += 1
                bg.add_task(_trigger_cat, row["id"])
            else:
                failed += 1
                errors.append({"row": i, "name": data.get("name") or "", "error": "insert failed"})
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"row": i, "name": data.get("name") or "", "error": str(exc)})
    return {"total_rows": created + failed, "created": created, "failed": failed, "errors": errors, "ids": ids}


@router.get("/sov")
async def get_sov(current_user=Depends(require_admin_or_client)):
    """Full Statement of Values: buildings (COPE/ITV/perils) + company rollup +
    submission-readiness completeness block."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        payload = await sov.build_sov(conn, company_id)
        payload["readiness"] = await sr.compute_property_readiness(conn, company_id, sov=payload)
    # Directional $ exposure — pure over the already-serialized buildings (no extra fetch).
    payload["exposure"] = exposure.portfolio_exposure(payload["buildings"])
    payload["plan"] = recs.build_plan(payload["buildings"], payload["rollup"], exposure=payload["exposure"])
    return payload


@router.get("/buildings")
async def list_buildings(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return {"buildings": await sov.list_buildings(conn, company_id)}


@router.post("/buildings")
async def create_building(body: BuildingUpsert, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        created = await sov.upsert_building(conn, company_id, None, body.model_dump(), current_user.id)
        result = await sov.build_sov(conn, company_id)
    if created:
        _trigger_cat(created["id"])
    return result


@router.get("/buildings/template")
async def buildings_template(current_user=Depends(require_admin_or_client)):
    """CSV template for the SOV bulk upload (header + one example row)."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    writer.writerow({
        "name": "Main Plant", "address": "123 Industrial Way", "city": "Dallas", "state": "TX",
        "zipcode": "75201", "county": "Dallas", "occupancy": "warehouse",
        "construction_type": "masonry_non_combustible", "year_built": "2008", "sq_ft": "40000",
        "stories": "1", "roof_year": "2015", "sprinklered": "true", "protection_class": "3",
        "building_value": "5000000", "contents_value": "1500000", "bi_value": "2000000",
        "replacement_cost": "6000000", "insured_value": "6000000", "note": "example row — delete before upload",
    })
    out.seek(0)
    return StreamingResponse(
        io.BytesIO(out.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=property_sov_template.csv"},
    )


@router.post("/buildings/bulk-upload", response_model=BulkUploadResult)
async def bulk_upload_buildings(
    bg: BackgroundTasks,
    file: UploadFile = File(..., description="CSV of buildings (use the template columns)"),
    current_user=Depends(require_admin_or_client),
):
    """Bulk-create buildings from a CSV matching the template. Lenient row coercion
    (unknown construction → null; the business edits afterward); per-row error report."""
    company_id = await get_client_company_id(current_user)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(contents) > _MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    try:
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}")
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    rows = list(reader)
    if len(rows) > _MAX_BULK_ROWS:
        raise HTTPException(status_code=413, detail=f"Too many rows: {len(rows)} (max {_MAX_BULK_ROWS}). Split into smaller files.")
    items = [b for b in (sov_parser.coerce_building(r) for r in rows) if b]
    if not items:
        raise HTTPException(status_code=400, detail="No building rows found in CSV")
    async with get_connection() as conn:
        result = await _insert_buildings(conn, company_id, current_user.id, items, bg)
    return BulkUploadResult(**result)


@router.post("/buildings/parse")
async def parse_sov_file(
    file: UploadFile = File(..., description="Carrier SOV — PDF or CSV"),
    current_user=Depends(require_admin_or_client),
):
    """Gemini-parse an uploaded SOV (PDF or CSV/text) into a reviewable building list.
    Does NOT insert — the business reviews/edits, then calls /buildings/bulk-insert."""
    await get_client_company_id(current_user)  # tenant gate (no write)
    mime = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    if not (any(m in mime for m in _PARSE_MIME_OK) or name.endswith((".pdf", ".csv", ".txt", ".tsv"))):
        raise HTTPException(status_code=400, detail="Upload a PDF or CSV SOV (export spreadsheets to CSV first).")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_PARSE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")
    fallback = "application/pdf" if name.endswith(".pdf") else "text/csv"
    return await sov_parser.parse_sov(data, mime or fallback)


@router.post("/buildings/bulk-insert", response_model=BulkUploadResult)
async def bulk_insert_buildings(
    body: BuildingBulkInsert,
    bg: BackgroundTasks,
    current_user=Depends(require_admin_or_client),
):
    """Commit a reviewed list of buildings (the parse→review→import confirm step)."""
    company_id = await get_client_company_id(current_user)
    items = [b.model_dump() for b in body.buildings]
    if not items:
        raise HTTPException(status_code=400, detail="No buildings to insert")
    if len(items) > _MAX_BULK_ROWS:
        raise HTTPException(status_code=413, detail=f"Too many buildings (max {_MAX_BULK_ROWS}).")
    async with get_connection() as conn:
        result = await _insert_buildings(conn, company_id, current_user.id, items, bg)
    return BulkUploadResult(**result)


@router.put("/buildings/{building_id}")
async def update_building(building_id: UUID, body: BuildingUpsert,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        updated = await sov.upsert_building(conn, company_id, building_id, body.model_dump(), current_user.id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Building not found")
        result = await sov.build_sov(conn, company_id)
    _trigger_cat(building_id)
    return result


@router.delete("/buildings/{building_id}")
async def delete_building(building_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        ok = await sov.delete_building(conn, company_id, building_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Building not found")
        return await sov.build_sov(conn, company_id)
