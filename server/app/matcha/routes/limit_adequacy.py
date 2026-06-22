"""Limit-adequacy + contract-review routes (`/limit-adequacy`, feature
`limit_adequacy`).

Gap-analysis #6/#28 (WTW "benchmarking + contractual-limit review = essential
tool"). The company records what it carries + uploads its contracts (Gemini
extracts the required limits); the engine diffs them → grounded gaps ("you carry
$1M GL but a contract requires $2M") plus a directional size/venue baseline.
Business-facing, tenant-isolated. Broker surfaces live in `broker_submission.py`.
"""

import json

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import limit_adequacy as la, contract_parser
from ..models.limit_adequacy import CoverageLineUpdate, ContractCreate, ContractUpdate

router = APIRouter()


@router.get("/review")
async def get_review(current_user=Depends(require_admin_or_client)):
    """Full adequacy analysis — carried vs contract-required vs baseline, per line."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await la.build_review(conn, company_id)


# --- carried coverage -------------------------------------------------------

@router.get("/coverage")
async def list_coverage(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT line, carrier, per_occurrence, aggregate, retention,
                      additional_insured, waiver_of_subrogation, primary_noncontributory,
                      effective_date, expiry_date, note, updated_at
               FROM company_coverage_lines WHERE company_id = $1 ORDER BY line""",
            company_id,
        )
    return {"lines": [dict(r) for r in rows], "catalog": la.COVERAGE_LINES,
            "endorsements": la.ENDORSEMENTS}


@router.put("/coverage/{line}")
async def upsert_coverage(line: str, body: CoverageLineUpdate,
                          current_user=Depends(require_admin_or_client)):
    if line not in la.LINE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown coverage line")
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO company_coverage_lines
                (company_id, line, carrier, per_occurrence, aggregate, retention,
                 additional_insured, waiver_of_subrogation, primary_noncontributory,
                 effective_date, expiry_date, note, updated_by, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
            ON CONFLICT ON CONSTRAINT uq_company_coverage_line DO UPDATE SET
                carrier = EXCLUDED.carrier,
                per_occurrence = EXCLUDED.per_occurrence,
                aggregate = EXCLUDED.aggregate,
                retention = EXCLUDED.retention,
                additional_insured = EXCLUDED.additional_insured,
                waiver_of_subrogation = EXCLUDED.waiver_of_subrogation,
                primary_noncontributory = EXCLUDED.primary_noncontributory,
                effective_date = EXCLUDED.effective_date,
                expiry_date = EXCLUDED.expiry_date,
                note = EXCLUDED.note,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            company_id, line, body.carrier, body.per_occurrence, body.aggregate, body.retention,
            body.additional_insured, body.waiver_of_subrogation, body.primary_noncontributory,
            body.effective_date, body.expiry_date, body.note, current_user.id,
        )
        return await la.build_review(conn, company_id)


@router.delete("/coverage/{line}")
async def delete_coverage(line: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM company_coverage_lines WHERE company_id = $1 AND line = $2",
            company_id, line,
        )
        return await la.build_review(conn, company_id)


# --- contracts --------------------------------------------------------------

@router.get("/contracts")
async def list_contracts(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, name, counterparty, status, requirements, ai_available,
                      source_filename, created_at, updated_at
               FROM company_contracts WHERE company_id = $1 ORDER BY created_at DESC""",
            company_id,
        )
    return {"contracts": [la._contract_row(r) for r in rows]}


@router.post("/contracts/upload")
async def upload_contract(file: UploadFile = File(...),
                          current_user=Depends(require_admin_or_client)):
    """Parse an uploaded contract PDF → extracted insurance requirements, store as
    a contract record the company reviews/edits. The PDF is parsed and discarded."""
    company_id = await get_client_company_id(current_user)
    is_pdf = (file.content_type == "application/pdf") or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Upload a PDF contract")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 15_000_000:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")

    parsed = await contract_parser.parse_contract(data)
    fname = (file.filename or "contract.pdf")[:255]
    name = (parsed.get("counterparty") or fname.rsplit(".", 1)[0])[:255]
    status = "parsed" if parsed["available"] else "error"
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO company_contracts
                 (company_id, name, counterparty, status, requirements, ai_available,
                  source_filename, uploaded_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               RETURNING id, name, counterparty, status, requirements, ai_available,
                         source_filename, created_at, updated_at""",
            company_id, name, parsed.get("counterparty"), status,
            json.dumps(parsed["requirements"]), parsed["available"], fname, current_user.id,
        )
    return la._contract_row(row)


@router.post("/contracts")
async def create_contract(body: ContractCreate, current_user=Depends(require_admin_or_client)):
    """Manual contract entry — key the requirements directly (no PDF)."""
    company_id = await get_client_company_id(current_user)
    reqs = _normalize_requirements(body.requirements)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO company_contracts
                 (company_id, name, counterparty, status, requirements, ai_available, uploaded_by)
               VALUES ($1,$2,$3,'manual',$4,FALSE,$5)
               RETURNING id, name, counterparty, status, requirements, ai_available,
                         source_filename, created_at, updated_at""",
            company_id, body.name, body.counterparty, json.dumps(reqs), current_user.id,
        )
    return la._contract_row(row)


@router.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, body: ContractUpdate,
                          current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM company_contracts WHERE id = $1 AND company_id = $2",
            contract_id, company_id,
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Contract not found")
        reqs = None if body.requirements is None else json.dumps(_normalize_requirements(body.requirements))
        row = await conn.fetchrow(
            """UPDATE company_contracts SET
                 name = COALESCE($3, name),
                 counterparty = COALESCE($4, counterparty),
                 requirements = COALESCE($5::jsonb, requirements),
                 status = CASE WHEN $5 IS NOT NULL AND status = 'error' THEN 'manual' ELSE status END,
                 updated_at = NOW()
               WHERE id = $1 AND company_id = $2
               RETURNING id, name, counterparty, status, requirements, ai_available,
                         source_filename, created_at, updated_at""",
            contract_id, company_id, body.name, body.counterparty, reqs,
        )
    return la._contract_row(row)


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM company_contracts WHERE id = $1 AND company_id = $2",
            contract_id, company_id,
        )
    return {"deleted": True}


# --- PDF --------------------------------------------------------------------

@router.get("/review.pdf")
async def review_pdf(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        review = await la.build_review(conn, company_id)
    name = company["name"] if company else "Client"
    pdf = await la.render_review_pdf(name, review)
    safe = name.replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="limit-adequacy-{safe}.pdf"'},
    )


def _normalize_requirements(requirements) -> list[dict]:
    """Pydantic requirement models → stored shape, with line keys normalized."""
    out: list[dict] = []
    for r in requirements or []:
        line = la.normalize_line(r.line)
        if not line:
            continue
        out.append({
            "line": line, "per_occurrence": r.per_occurrence, "aggregate": r.aggregate,
            "additional_insured": r.additional_insured,
            "waiver_of_subrogation": r.waiver_of_subrogation,
            "primary_noncontributory": r.primary_noncontributory,
            "note": r.note,
        })
    return out
