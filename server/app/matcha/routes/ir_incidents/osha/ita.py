"""OSHA ITA (Injury Tracking Application) electronic filing: per-establishment
pre-flight validation, the bulk `Establishment and Summary` CSV, stored API
credentials, direct submission, and the submission history.
"""
import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    ItaCredentialUpdate,
    ItaCredentialStatus,
    ItaSubmitRequest,
    ItaSubmitResponse,
    ItaSubmission,
    ItaSubmissionListResponse,
)
from app.matcha.routes.ir_incidents._shared import log_audit
from app.matcha.services.ir.naics_titles import naics_industry_description
from ._shared import _active_headcount, _aggregate_300a, _attest_export

logger = logging.getLogger(__name__)

router = APIRouter()

# OSHA ITA "Establishment and Summary" CSV header tokens, in upload order.
# Exact casing/underscores matter — the ITA validator rejects any deviation.
# (Confirm against the live OSHA ITA data dictionary before a production filing;
# the box→column G–M6 mapping is stable, only header strings could drift.)
ITA_CSV_COLUMNS = [
    "ein", "company_name", "establishment_name", "street_address", "city",
    "state", "zip_code", "naics_code", "industry_description", "size",
    "establishment_type", "year_filing_for", "annual_average_employees",
    "total_hours_worked", "no_injuries_illnesses", "total_deaths",
    "total_dafw_cases", "total_djtr_cases", "total_other_cases",
    "total_dafw_days", "total_djtr_days", "total_injuries",
    "total_skin_disorders", "total_respiratory_conditions", "total_poisonings",
    "total_hearing_loss", "total_other_illnesses",
]


# Single definition of the OSHA size bands, shared with the direct-filing path —
# the CSV export and the API submission must never disagree on the size code.
# Same reason for the EIN/zip normalizers: the pre-flight validator must judge
# the exact digits the API payload will carry, not the raw stored string.
from app.matcha.services.ir.ir_ita_submission import (  # noqa: E402
    ita_size_category as _ita_size_category,
    _normalize_ein,
    _normalize_zip,
)


# Mandatory ITA fields that can realistically be missing (city/state/zipcode are
# NOT NULL on business_locations; address/ein/naics/hours are the gaps).
def _missing_ita_fields(est: dict) -> list[str]:
    """Return the list of required ITA fields absent from an establishment dict.

    Pure (no DB) so it can be unit-tested. `est` carries the EIN/NAICS already
    resolved with company-level fallback, plus the address parts + hours/headcount.
    Mirrors what the ITA API requires to CREATE an establishment + 300A (data
    dictionary), so a filer sees the gap in the pre-flight checklist rather than
    as an OSHA rejection mid-submission. `ein` is kept required here for hygiene
    even though the API itself treats it as optional.

    Presence alone is not enough: OSHA field-validates EIN ("must be 9 digits")
    and zip ("must contain 5 or 9 digits") and rejects the whole batch when either
    is malformed. A present-but-invalid value passed this check silently and
    surfaced only as an opaque OSHA rejection at submit time, so the two are
    length-checked here on the same digits the payload builder sends.
    """
    missing = []
    # Required to create the establishment (address parts + naics + ein).
    for field in ("ein", "naics", "street_address", "city", "state", "zip_code"):
        val = est.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    # Present but malformed — OSHA rejects these, so they block the filing too.
    if "ein" not in missing and len(_normalize_ein(est.get("ein"))) != 9:
        missing.append("ein_invalid")
    if "zip_code" not in missing and len(_normalize_zip(est.get("zip_code"))) not in (5, 9):
        missing.append("zip_code_invalid")
    # Required on the 300A summary: both must be present AND > 0 (API validation).
    if not (est.get("total_hours_worked") or 0) > 0:
        missing.append("total_hours_worked")
    if not (est.get("annual_average_employees") or 0) > 0:
        missing.append("annual_average_employees")
    return missing


async def _gather_ita_establishments(conn, company_id, year) -> list[dict]:
    """Build one ITA row dict per active establishment for the year.

    Each dict carries the resolved identity (EIN/NAICS with company fallback),
    the manual hours + headcount from the saved summary row (auto headcount when
    unsaved), and the recomputed 300A totals. Shared by validate + export.
    """
    company = await conn.fetchrow(
        "SELECT COALESCE(legal_name, name) AS company_name FROM companies WHERE id = $1",
        company_id,
    )
    company_name = company["company_name"] if company else ""

    locations = await conn.fetch(
        """
        SELECT bl.id, bl.name, bl.address, bl.city, bl.state, bl.zipcode,
               COALESCE(bl.ein, c.ein) AS ein,
               COALESCE(bl.naics, c.naics) AS naics
        FROM business_locations bl
        JOIN companies c ON c.id = bl.company_id
        WHERE bl.company_id = $1 AND bl.is_active = true
        ORDER BY bl.name
        """,
        company_id,
    )

    sole = len(locations) == 1
    rows = []
    for loc in locations:
        agg = await _aggregate_300a(conn, company_id, loc["id"], year)
        saved = await conn.fetchrow(
            "SELECT average_employees, total_hours_worked FROM osha_annual_summaries "
            "WHERE company_id = $1 AND location_id = $2 AND year = $3",
            company_id, loc["id"], year,
        )
        avg_emp = saved["average_employees"] if saved and saved["average_employees"] is not None else \
            await _active_headcount(
                conn, company_id, loc["id"],
                city=loc["city"], state=loc["state"], sole_location=sole,
            )
        hours = saved["total_hours_worked"] if saved else None

        rows.append({
            "location_id": str(loc["id"]),
            "establishment_name": loc["name"] or "",
            "company_name": company_name,
            "ein": loc["ein"],
            "naics": loc["naics"],
            "street_address": loc["address"],
            "city": loc["city"],
            "state": loc["state"],
            "zip_code": loc["zipcode"],
            "annual_average_employees": avg_emp,
            "total_hours_worked": hours,
            "agg": agg,
        })
    return rows


@router.get("/osha/ita/validate")
async def validate_ita_export(
    year: int = Query(..., description="Calendar year to validate for ITA filing"),
    current_user=Depends(require_admin_or_client),
):
    """Pre-flight: list establishments missing required ITA fields (EIN/NAICS/etc.).

    Returns [] when every active establishment is filing-ready. Lets the UI show
    a checklist without triggering a download attempt.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        establishments = await _gather_ita_establishments(conn, company_id, year)
        unassigned = await conn.fetchval(
            """
            SELECT COUNT(*) FROM ir_incidents
            WHERE company_id = $1
              AND osha_recordable = true
              AND EXTRACT(YEAR FROM occurred_at) = $2
              AND location_id IS NULL
            """,
            company_id, year,
        ) or 0

    problems = []
    for est in establishments:
        missing = _missing_ita_fields(est)
        if missing:
            problems.append({
                "location_id": est["location_id"],
                "establishment_name": est["establishment_name"],
                "missing": missing,
            })
    # Completeness pre-flight: recordables not tied to any establishment are
    # excluded from the ITA export entirely (they only show on the company-wide
    # 300 log). Surface them as a company-level, non-blocking problem entry so
    # the reviewer can't miss that N cases won't be filed. location_id is None
    # to distinguish it from a per-establishment missing-fields row.
    if unassigned:
        problems.append({
            "location_id": None,
            "establishment_name": f"{unassigned} unassigned recordable incident(s)",
            "missing": ["unassigned_location"],
        })
    return problems


@router.get("/osha/ita/export.csv")
async def export_ita_csv(
    year: int = Query(..., description="Calendar year for the ITA bulk export"),
    attested: bool = Query(False, description="Reviewer confirmed they reviewed the data before export"),
    current_user=Depends(require_admin_or_client),
):
    """Master ITA Establishment-and-Summary CSV — one row per establishment.

    Validates mandatory fields first; returns 400 with a structured list of
    offending establishments before streaming anything.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    async with get_connection() as conn:
        await _attest_export(conn, current_user, form="ita", year=year, attested=attested)
        establishments = await _gather_ita_establishments(conn, company_id, year)

    if not establishments:
        raise HTTPException(
            status_code=400,
            detail="No active business locations to file. Add at least one establishment.",
        )

    problems = []
    for est in establishments:
        missing = _missing_ita_fields(est)
        if missing:
            problems.append({
                "location_id": est["location_id"],
                "establishment_name": est["establishment_name"],
                "missing": missing,
            })
    if problems:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Cannot export ITA file — establishments are missing required fields.",
                "establishments": problems,
            },
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ITA_CSV_COLUMNS)
    writer.writeheader()
    for est in establishments:
        agg = est["agg"]
        writer.writerow({
            # Normalized to digits for the same reason the API payload is: the ITA
            # portal enforces "EIN can only contain numbers" and a 5-or-9-digit zip
            # on the uploaded file too, so a hyphenated EIN is rejected at the
            # portal instead of at submit. CSV and API must carry identical bytes.
            "ein": _normalize_ein(est["ein"]),
            "company_name": est["company_name"],
            "establishment_name": est["establishment_name"],
            "street_address": est["street_address"] or "",
            "city": est["city"] or "",
            "state": est["state"] or "",
            "zip_code": _normalize_zip(est["zip_code"]),
            "naics_code": est["naics"] or "",
            "industry_description": naics_industry_description(est["naics"]) or "",
            "size": _ita_size_category(est["annual_average_employees"]),
            "establishment_type": 1,  # 1 = private (not a government establishment)
            "year_filing_for": year,
            "annual_average_employees": est["annual_average_employees"] or 0,
            "total_hours_worked": est["total_hours_worked"] or 0,
            "no_injuries_illnesses": 1 if agg["total_cases"] == 0 else 0,
            "total_deaths": agg["total_deaths"],
            "total_dafw_cases": agg["total_days_away_cases"],
            "total_djtr_cases": agg["total_restricted_cases"],
            "total_other_cases": agg["total_other_recordable"],
            "total_dafw_days": agg["total_days_away"],
            "total_djtr_days": agg["total_days_restricted"],
            "total_injuries": agg["total_injuries"],
            "total_skin_disorders": agg["total_skin_disorders"],
            "total_respiratory_conditions": agg["total_respiratory"],
            "total_poisonings": agg["total_poisonings"],
            "total_hearing_loss": agg["total_hearing_loss"],
            "total_other_illnesses": agg["total_other_illnesses"],
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=osha_ita_{year}.csv"},
    )


@router.get("/osha/ita/credentials", response_model=ItaCredentialStatus)
async def get_ita_credentials_status(
    current_user=Depends(require_admin_or_client),
):
    """Whether an OSHA ITA API token is on file. Never returns the token."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT updated_at FROM osha_ita_credentials WHERE company_id = $1",
            company_id,
        )
    return ItaCredentialStatus(configured=row is not None, updated_at=row["updated_at"] if row else None)


@router.put("/osha/ita/credentials", response_model=ItaCredentialStatus)
async def set_ita_credentials(
    payload: ItaCredentialUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Store/replace the company's OSHA ITA API token (encrypted at rest)."""
    from app.core.services.secret_crypto import encrypt_secret

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    token = (payload.api_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="API token is required")

    encrypted = encrypt_secret(token)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO osha_ita_credentials (company_id, api_token, created_by, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (company_id) DO UPDATE
                SET api_token = EXCLUDED.api_token, updated_at = NOW()
            RETURNING updated_at
            """,
            company_id, encrypted, str(current_user.id),
        )
        # Never log the token — only that credentials were set.
        await log_audit(
            conn, None, str(current_user.id), "osha_ita_credentials_set",
            entity_type="osha_ita", entity_id=None, details=None,
        )
    return ItaCredentialStatus(configured=True, updated_at=row["updated_at"])


@router.post("/osha/ita/submit", response_model=ItaSubmitResponse)
async def submit_ita(
    payload: ItaSubmitRequest,
    current_user=Depends(require_admin_or_client),
):
    """Directly file the ITA Establishment-and-Summary batch via the OSHA API.

    Same reviewer-attestation + field-validation gates as the CSV export, then a
    single API call whose numbers are byte-identical to the validated CSV. Every
    attempt is recorded in osha_ita_submissions for an auditable filing history.
    A missing/invalid token yields a clean `not_configured` result, not a 500.

    Filing a year twice is refused with 409 unless `resubmit` is set (an amended
    filing). The check and the API call run under a per-(company, year) advisory
    lock held for the whole transaction, so a double-click can't slip two
    filings through the gap between the check and the insert.
    """
    from app.matcha.services.ir.ir_ita_submission import submit_establishments

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    year = payload.year
    async with get_connection() as conn, conn.transaction():
        # Serialize concurrent submits for this (company, year). Held until the
        # transaction commits — i.e. across the OSHA API call and the history
        # insert — so the duplicate check below can't race a second request.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1), $2::int)",
            f"ita_submit:{company_id}", year,
        )

        if not payload.resubmit:
            prior = await conn.fetchrow(
                """
                SELECT ita_submission_id, submitted_at
                FROM osha_ita_submissions
                WHERE company_id = $1 AND year = $2
                  AND status IN ('submitted', 'accepted')
                ORDER BY submitted_at DESC
                LIMIT 1
                """,
                company_id, year,
            )
            if prior:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "already_filed",
                        "message": (
                            f"{year} has already been filed with OSHA. "
                            "Set resubmit=true to file an amended submission."
                        ),
                        "year": year,
                        "submission_id": prior["ita_submission_id"],
                        "submitted_at": prior["submitted_at"].isoformat(),
                    },
                )

        # Reviewer attestation (403 + disclaimer when not attested) — same gate
        # as every OSHA export, since this IS the filing.
        await _attest_export(conn, current_user, form="ita_submit", year=year, attested=payload.attested)

        establishments = await _gather_ita_establishments(conn, company_id, year)
        if not establishments:
            raise HTTPException(
                status_code=400,
                detail="No active business locations to file. Add at least one establishment.",
            )

        problems = []
        for est in establishments:
            missing = _missing_ita_fields(est)
            if missing:
                problems.append({
                    "location_id": est["location_id"],
                    "establishment_name": est["establishment_name"],
                    "missing": missing,
                })
        if problems:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Cannot submit ITA filing — establishments are missing required fields.",
                    "establishments": problems,
                },
            )

        token_row = await conn.fetchrow(
            "SELECT api_token FROM osha_ita_credentials WHERE company_id = $1",
            company_id,
        )
        encrypted_token = token_row["api_token"] if token_row else None

        result = await submit_establishments(
            encrypted_token, establishments, year, resubmit=payload.resubmit,
        )

        # Persist every attempt (including not_configured) for the filing history.
        # ita_submission_id is a single column: with multiple establishments we
        # store the first submission id; the full per-establishment id list +
        # trace lives in response_payload.
        row = await conn.fetchrow(
            """
            INSERT INTO osha_ita_submissions
                (company_id, location_id, year, status, ita_submission_id,
                 establishment_count, response_payload, error_detail, submitted_by)
            VALUES ($1, NULL, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            company_id, year, result.status, result.submission_id,
            len(establishments),
            json.dumps(result.response) if result.response else None,
            result.error, str(current_user.id),
        )
        await log_audit(
            conn, None, str(current_user.id), "osha_ita_submitted",
            entity_type="osha_ita_submission", entity_id=str(row["id"]),
            details={"year": year, "status": result.status,
                     "establishment_count": len(establishments)},
        )

    return ItaSubmitResponse(
        status=result.status,
        submission_id=result.submission_id,
        establishment_count=len(establishments),
        error=result.error,
    )


@router.get("/osha/ita/submissions", response_model=ItaSubmissionListResponse)
async def list_ita_submissions(
    year: Optional[int] = Query(None),
    current_user=Depends(require_admin_or_client),
):
    """ITA filing history for this company (optionally one year)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with user")

    params = [company_id]
    year_clause = ""
    if year is not None:
        params.append(year)
        year_clause = "AND year = $2"

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, location_id, year, status, ita_submission_id,
                   establishment_count, error_detail, submitted_by, submitted_at
            FROM osha_ita_submissions
            WHERE company_id = $1 {year_clause}
            ORDER BY submitted_at DESC
            LIMIT 100
            """,
            *params,
        )
    submissions = [
        ItaSubmission(
            id=r["id"],
            location_id=r["location_id"],
            year=r["year"],
            status=r["status"],
            ita_submission_id=r["ita_submission_id"],
            establishment_count=r["establishment_count"],
            error_detail=r["error_detail"],
            submitted_by=r["submitted_by"],
            submitted_at=r["submitted_at"],
        )
        for r in rows
    ]
    return ItaSubmissionListResponse(submissions=submissions, total=len(submissions))
