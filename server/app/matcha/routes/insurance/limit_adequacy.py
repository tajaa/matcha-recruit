"""Limit-adequacy + contract-review routes (`/limit-adequacy`, feature
`limit_adequacy`).

Gap-analysis #6/#28 (WTW "benchmarking + contractual-limit review = essential
tool"). The company records what it carries + uploads its contracts (Gemini
extracts the required limits); the engine diffs them → grounded gaps ("you carry
$1M GL but a contract requires $2M") plus a directional size/venue baseline.
Business-facing, tenant-isolated. Broker surfaces live in `broker_submission.py`.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ...services import limit_adequacy as la, risk_transfer as rt
from ...models.limit_adequacy import CoverageLineUpdate, ContractCreate, ContractUpdate

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
            f"SELECT {rt._CONTRACT_COLS} FROM company_contracts "
            "WHERE company_id = $1 ORDER BY created_at DESC",
            company_id,
        )
    return {"contracts": [la._contract_row(r) for r in rows]}


@router.post("/contracts/upload")
async def upload_contract(file: UploadFile = File(...),
                          current_user=Depends(require_admin_or_client)):
    """Parse an uploaded contract PDF → insurance requirements + indemnity clause,
    stored as a draft the company reviews, edits, and confirms. The source PDF is
    retained (private bucket) so clause findings stay verifiable."""
    company_id = await get_client_company_id(current_user)
    rt.validate_pdf_upload(file)
    data = await file.read()
    rt.validate_pdf_bytes(data)
    async with get_connection() as conn:
        return await rt.store_uploaded_contract(conn, company_id, current_user.id, data, file.filename)


@router.post("/contracts")
async def create_contract(body: ContractCreate, current_user=Depends(require_admin_or_client)):
    """Manual contract entry — key the requirements directly (no PDF)."""
    company_id = await get_client_company_id(current_user)
    reqs = rt.normalize_requirements(body.requirements)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""INSERT INTO company_contracts
                 (company_id, name, counterparty, status, requirements, ai_available, uploaded_by,
                  contract_type, governing_state, project_state, risk_transfer)
               VALUES ($1,$2,$3,'manual',$4,FALSE,$5,$6,$7,$8,$9)
               RETURNING {rt._CONTRACT_COLS}""",
            company_id, body.name, body.counterparty, json.dumps(reqs), current_user.id,
            body.contract_type, rt._norm_state(body.governing_state), rt._norm_state(body.project_state),
            json.dumps(body.risk_transfer.model_dump()) if body.risk_transfer else None,
        )
    return la._contract_row(row)


@router.put("/contracts/{contract_id}")
async def update_contract(contract_id: UUID, body: ContractUpdate,
                          current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await rt.update_contract(conn, company_id, contract_id, body)
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return row


@router.post("/contracts/{contract_id}/confirm")
async def confirm_contract(contract_id: UUID, current_user=Depends(require_admin_or_client)):
    """Vouch for the extracted terms — lifts the provisional label off the verdict."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await rt.confirm_contract(conn, company_id, contract_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return row


@router.get("/contracts/{contract_id}/review")
async def contract_review(contract_id: UUID, current_user=Depends(require_admin_or_client)):
    """Per-contract, pre-signature review: compliant / exposed / actions."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        review = await rt.build_contract_review(conn, company_id, contract_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return review


@router.get("/contracts/{contract_id}/review.pdf")
async def contract_review_pdf(contract_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        review = await rt.build_contract_review(conn, company_id, contract_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    pdf = await rt.render_contract_review_pdf(review)
    safe = str((review.get("contract") or {}).get("name") or "contract").replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="contract-review-{safe}.pdf"'},
    )


@router.get("/contracts/{contract_id}/file")
async def contract_source_file(contract_id: UUID, current_user=Depends(require_admin_or_client)):
    """Time-limited link to the retained source PDF (404 when it wasn't retained)."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        url = await rt.contract_source_url(conn, company_id, contract_id)
    if not url:
        raise HTTPException(status_code=404, detail="No source document on file")
    return {"url": url}


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: UUID, current_user=Depends(require_admin_or_client)):
    """Drop the row **and** the retained source PDF — otherwise a counterparty's
    contract outlives every reference to it in a bucket nobody can reach."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        storage_path = await conn.fetchval(
            "DELETE FROM company_contracts WHERE id = $1 AND company_id = $2 RETURNING storage_path",
            contract_id, company_id,
        )
    await rt.discard_source(storage_path)
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
