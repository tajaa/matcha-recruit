"""OSHA ITA (Injury Tracking Application) electronic submission.

Turns the existing "export a CSV and upload it to the ITA portal yourself" flow
into a direct API submission. The heavy lifting — establishment gathering, the
300A column math, field-completeness validation, reviewer attestation — already
lives in `routes/ir_incidents/osha.py`; this module only:

  1. maps an already-built establishment dict to the ITA API JSON shape
     (`build_ita_establishment_payload`, pure + unit-testable), and
  2. POSTs the batch to the ITA API with the company's stored token
     (`submit_establishments`).

IMPORTANT — the ITA API field names and endpoint path below mirror the public
"Establishment and Summary" data dictionary the CSV export already targets, but
they MUST be confirmed against the live OSHA ITA API data dictionary before a
production filing (same caveat the CSV path carries). Prod is Stripe-test /
pre-customer; nothing here is auto-invoked, and a missing token degrades to a
clear "not configured" result rather than a 500.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from app.core.services.secret_crypto import decrypt_secret
from app.matcha.services.naics_titles import naics_industry_description

logger = logging.getLogger(__name__)

# Overridable per environment. The default is the public ITA API base; the exact
# submission path is appended below and should be confirmed against the live
# data dictionary before go-live.
DEFAULT_ITA_API_URL = "https://www.osha.gov/injuryreporting/ita/api/v1"


def ita_size_category(avg_employees) -> int:
    """OSHA ITA establishment size code: 1 (<20), 2 (20–249), 3 (>=250).

    Canonical definition — osha.py imports this rather than keeping its own copy,
    so the CSV export and the direct API filing can't drift apart on the bands.
    """
    n = avg_employees or 0
    if n >= 250:
        return 3
    if n >= 20:
        return 2
    return 1


def build_ita_establishment_payload(est: dict, year: int) -> dict[str, Any]:
    """Map one gathered establishment dict (from `_gather_ita_establishments`)
    to the ITA API establishment+summary JSON object.

    Pure — no DB, no network — so the mapping is unit-testable against fixtures.
    Numbers come straight from the recomputed 300A aggregate, so an API filing is
    byte-identical to the validated CSV row.
    """
    agg = est["agg"]
    return {
        "establishment": {
            "ein": est.get("ein") or "",
            "company_name": est.get("company_name") or "",
            "establishment_name": est.get("establishment_name") or "",
            "street_address": est.get("street_address") or "",
            "city": est.get("city") or "",
            "state": est.get("state") or "",
            "zip_code": est.get("zip_code") or "",
            "naics_code": est.get("naics") or "",
            "industry_description": naics_industry_description(est.get("naics")) or "",
            "size": ita_size_category(est.get("annual_average_employees")),
            "establishment_type": 1,  # 1 = private (non-government)
            "year_filing_for": year,
            "annual_average_employees": est.get("annual_average_employees") or 0,
            "total_hours_worked": est.get("total_hours_worked") or 0,
        },
        "summary": {
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
        },
    }


def build_ita_batch(establishments: list[dict], year: int) -> list[dict[str, Any]]:
    """Map every establishment to its ITA payload object."""
    return [build_ita_establishment_payload(est, year) for est in establishments]


def _api_url() -> str:
    return os.getenv("OSHA_ITA_API_URL", DEFAULT_ITA_API_URL).rstrip("/")


class ITASubmissionResult:
    """Structured outcome of a submit attempt (no secrets)."""

    def __init__(self, *, status: str, submission_id: Optional[str] = None,
                 response: Optional[dict] = None, error: Optional[str] = None):
        self.status = status                # submitted | accepted | rejected | error | not_configured
        self.submission_id = submission_id
        self.response = response
        self.error = error


async def submit_establishments(
    encrypted_token: Optional[str],
    establishments: list[dict],
    year: int,
    *,
    timeout: float = 30.0,
) -> ITASubmissionResult:
    """POST the establishment batch to the ITA API.

    `encrypted_token` is the stored (enc:v1:) API token; None/blank → a
    `not_configured` result (never an exception) so the endpoint can tell the
    user to add credentials. Any transport/HTTP error → an `error` result with a
    safe message. The token is decrypted only here and never logged or returned.
    """
    if not encrypted_token:
        return ITASubmissionResult(status="not_configured",
                                   error="No OSHA ITA API token configured for this company.")
    try:
        token = decrypt_secret(encrypted_token)
    except ValueError:
        return ITASubmissionResult(status="error", error="Stored ITA token could not be read.")
    if not token:
        return ITASubmissionResult(status="not_configured",
                                   error="No OSHA ITA API token configured for this company.")

    payload = {"year_filing_for": year, "establishments": build_ita_batch(establishments, year)}
    url = f"{_api_url()}/establishments"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("ITA submit transport error: %s", exc)
        return ITASubmissionResult(status="error", error=f"Could not reach the OSHA ITA API: {exc}")

    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:2000]}

    if resp.is_success:
        submission_id = None
        if isinstance(body, dict):
            submission_id = body.get("submission_id") or body.get("id") or body.get("submissionId")
        return ITASubmissionResult(status="submitted", submission_id=submission_id, response=body if isinstance(body, dict) else {"data": body})

    # Non-2xx — surface a rejection with the API's message, without leaking auth.
    msg = None
    if isinstance(body, dict):
        msg = body.get("message") or body.get("error") or body.get("detail")
    return ITASubmissionResult(
        status="rejected",
        response=body if isinstance(body, dict) else {"data": body},
        error=msg or f"OSHA ITA API returned HTTP {resp.status_code}.",
    )
