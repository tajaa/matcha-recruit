"""OSHA ITA (Injury Tracking Application) electronic submission.

Turns the existing "export a CSV and upload it to the ITA portal yourself" flow
into a direct API submission. The heavy lifting — establishment gathering, the
300A column math, field-completeness validation, reviewer attestation — already
lives in `routes/ir_incidents/osha.py`; this module maps the gathered data to
the ITA API JSON shapes and drives OSHA's three-step filing protocol.

Wire format confirmed against OSHA's published *Injury Tracking Application API
Documentation* (base `https://www.osha.gov/oshaApi/v1`). Filing is a three-step
protocol, in order:

  1. POST /establishments        create (or reuse) the establishment  -> id
  2. POST /forms/form300A        add the 300A summary for {establishment id, year}
  3. POST /submissions           formally submit -> this is what makes OSHA treat
                                 the data as complete and email a confirmation.

Establishments are persistent on OSHA's side and `establishment_name` must be
unique per account, so we GET the account's existing establishments first and
reuse a matching one rather than re-creating it (which would 409 on the second
filing / next year). Likewise an existing 300A for the year is PATCHed rather
than re-POSTed, which makes `resubmit=True` a true amendment.

Nothing here is auto-invoked; a missing token degrades to a clear
`not_configured` result rather than a 500, and the token is decrypted only at
the point of use and never logged or returned.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

import httpx

from app.core.services.secret_crypto import decrypt_secret
from app.matcha.services.naics_titles import naics_industry_description

logger = logging.getLogger(__name__)

# Overridable per environment. Default is the production ITA API base; point it
# at the sandbox (https://preview.osha.gov/oshaApi/v1) to exercise filing
# end-to-end without a real submission — sandbox data is purged periodically and
# does NOT satisfy an employer's filing obligation.
DEFAULT_ITA_API_URL = "https://www.osha.gov/oshaApi/v1"


def ita_size_category(avg_employees) -> int:
    """OSHA ITA establishment `size` code, per the API data dictionary:

        1  = fewer than 20 employees
        21 = 20 to 99
        22 = 100 to 249
        3  = 250 or more

    Based on the maximum number of employees at any point in the filing year.
    Canonical definition — osha.py imports this rather than keeping its own copy,
    so the CSV export and the direct API filing can't drift apart on the bands.
    """
    n = avg_employees or 0
    if n >= 250:
        return 3
    if n >= 100:
        return 22
    if n >= 20:
        return 21
    return 1


def _normalize_zip(value) -> str:
    """ITA `zip` must be a 5- or 9-digit number. Strip a hyphen from the common
    ZIP+4 form; leave anything else to the pre-flight validator / OSHA errors."""
    if not value:
        return ""
    digits = re.sub(r"[^0-9]", "", str(value))
    return digits


def build_ita_establishment_payload(est: dict) -> dict[str, Any]:
    """Map one gathered establishment dict (from `_gather_ita_establishments`)
    to the ITA API *establishment* JSON object (identity/address/naics/size only
    — the 300A summary is a separate object, see `build_ita_form300a_payload`).

    Pure — no DB, no network — so the mapping is unit-testable against fixtures.
    """
    payload: dict[str, Any] = {
        "establishment_name": est.get("establishment_name") or "",
        "company": {"company_name": est.get("company_name") or ""},
        "address": {
            "street": est.get("street_address") or "",
            "city": est.get("city") or "",
            "state": est.get("state") or "",
            "zip": _normalize_zip(est.get("zip_code")),
        },
        "naics": {
            "naics_code": est.get("naics") or "",
            "industry_description": naics_industry_description(est.get("naics")) or "",
        },
        "size": ita_size_category(est.get("annual_average_employees")),
        "establishment_type": 1,  # 1 = private (non-government). See module TODO.
    }
    # EIN is optional on the API (Required-to-CREATE: No) — only send it when we
    # actually have one rather than an empty nested object.
    ein = (est.get("ein") or "").strip()
    if ein:
        payload["ein"] = {"ein": ein}
    return payload


def build_ita_form300a_payload(est: dict, establishment_id, year: int) -> dict[str, Any]:
    """Map the recomputed 300A aggregate to the ITA *form300A* JSON object,
    bound to an OSHA establishment id. Numbers come straight from the validated
    aggregate, so an API filing is byte-identical to the CSV row.

    Pure — unit-testable against fixtures.
    """
    agg = est["agg"]
    return {
        "establishment": {"id": str(establishment_id)},
        "year_filing_for": year,
        "annual_average_employees": est.get("annual_average_employees") or 0,
        "total_hours_worked": est.get("total_hours_worked") or 0,
        # 1 = the establishment HAD recordable injuries/illnesses, 2 = it did not.
        "no_injuries_illnesses": 2 if agg["total_cases"] == 0 else 1,
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
    }


def _api_url() -> str:
    return os.getenv("OSHA_ITA_API_URL", DEFAULT_ITA_API_URL).rstrip("/")


def _norm_name(name) -> str:
    """Establishment-name key for reuse matching. OSHA enforces uniqueness; match
    case-insensitively after trimming so a casing/whitespace difference doesn't
    make us create a near-duplicate that then 409s."""
    return (name or "").strip().casefold()


class ITASubmissionResult:
    """Structured outcome of a submit attempt (no secrets)."""

    def __init__(self, *, status: str, submission_id: Optional[str] = None,
                 response: Optional[dict] = None, error: Optional[str] = None):
        self.status = status                # submitted | rejected | error | not_configured
        self.submission_id = submission_id
        self.response = response
        self.error = error


class _ITAError(Exception):
    """Internal: an ITA API step failed. Carries a user-safe message + the body
    for the persisted history row."""

    def __init__(self, message: str, response: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.response = response


def _extract_message(body: Any) -> Optional[str]:
    if isinstance(body, dict):
        return body.get("message") or body.get("error") or body.get("detail")
    return None


async def _post(client: httpx.AsyncClient, url: str, token: str, payload: Any) -> Any:
    """POST helper — returns the parsed body, raises `_ITAError` on non-2xx.
    Never logs or returns the token."""
    resp = await client.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:2000]}
    if not resp.is_success:
        msg = _extract_message(body) or f"OSHA ITA API returned HTTP {resp.status_code}."
        raise _ITAError(msg, response=body if isinstance(body, dict) else {"data": body})
    return body


async def _patch(client: httpx.AsyncClient, url: str, token: str, payload: Any) -> Any:
    resp = await client.patch(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:2000]}
    if not resp.is_success:
        msg = _extract_message(body) or f"OSHA ITA API returned HTTP {resp.status_code}."
        raise _ITAError(msg, response=body if isinstance(body, dict) else {"data": body})
    return body


def _results_list(body: Any) -> list[dict]:
    """The ITA API wraps create/add/submit responses in `{"results": [...]}`."""
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        return [r for r in body["results"] if isinstance(r, dict)]
    return []


async def _fetch_existing_establishments(client: httpx.AsyncClient, token: str) -> dict[str, dict]:
    """GET the account's establishments → {normalized_name: result_object}. The
    result object carries `id` and `links.form300ALinks` we reuse below."""
    resp = await client.get(
        f"{_api_url()}/establishments",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.is_success:
        # A failed list is not fatal — fall back to create-only (a duplicate name
        # will surface as a normal rejection with OSHA's own message).
        logger.info("ITA establishment list returned HTTP %s; proceeding create-only", resp.status_code)
        return {}
    out: dict[str, dict] = {}
    for r in _results_list(body):
        name = r.get("establishment_name")
        if name:
            out[_norm_name(name)] = r
    return out


def _form300a_links(est_obj: dict) -> list[str]:
    links = est_obj.get("links") or {}
    form_links = links.get("form300ALinks")
    if isinstance(form_links, list):
        return [x for x in form_links if isinstance(x, str)]
    return []


async def submit_establishments(
    encrypted_token: Optional[str],
    establishments: list[dict],
    year: int,
    *,
    resubmit: bool = False,
    timeout: float = 30.0,
) -> ITASubmissionResult:
    """Drive OSHA's three-step ITA filing for every establishment in the batch.

    `encrypted_token` is the stored (enc:v1:) API token; None/blank → a
    `not_configured` result (never an exception). Any transport/HTTP error at any
    step → an `error`/`rejected` result carrying OSHA's message. The token is
    decrypted only here and never logged or returned.
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

    base = _api_url()
    steps: dict[str, Any] = {}  # compact per-establishment trace for the history row
    submission_ids: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            existing = await _fetch_existing_establishments(client, token)

            submit_objects: list[dict[str, Any]] = []
            for est in establishments:
                name_key = _norm_name(est.get("establishment_name"))
                match = existing.get(name_key)

                # Step 1 — reuse or create the establishment.
                if match and match.get("id"):
                    establishment_id = str(match["id"])
                    est_obj = match
                else:
                    body = await _post(client, f"{base}/establishments", token,
                                       build_ita_establishment_payload(est))
                    results = _results_list(body)
                    if not results or not results[0].get("id"):
                        raise _ITAError(
                            f"OSHA did not return an id for establishment "
                            f"'{est.get('establishment_name')}'.",
                            response=body if isinstance(body, dict) else None,
                        )
                    establishment_id = str(results[0]["id"])
                    est_obj = results[0]

                # Step 2 — add or amend the 300A for the year.
                form_payload = build_ita_form300a_payload(est, establishment_id, year)
                existing_form_id = None
                for link in _form300a_links(est_obj):
                    # links look like /oshaApi/v1/forms/form300A/{id}; we can only
                    # cheaply reuse the id, then confirm the year on GET.
                    fid = link.rstrip("/").rsplit("/", 1)[-1]
                    if not fid:
                        continue
                    resp = await client.get(
                        f"{base}/forms/form300A/{fid}",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    )
                    if not resp.is_success:
                        continue
                    try:
                        fbody = resp.json()
                    except ValueError:
                        continue
                    for fr in _results_list(fbody):
                        if str(fr.get("year_filing_for", "")).strip() == str(year):
                            existing_form_id = str(fr.get("id") or fid)
                            break
                    if existing_form_id:
                        break

                if existing_form_id:
                    await _patch(client, f"{base}/forms/form300A/{existing_form_id}",
                                 token, {**form_payload, "id": existing_form_id})
                else:
                    await _post(client, f"{base}/forms/form300A", token, form_payload)

                submit_obj = {"establishment_id": establishment_id, "year_filing_for": year}
                if resubmit:
                    submit_obj["change_reason"] = "Amended filing"
                submit_objects.append(submit_obj)
                steps[est.get("establishment_name") or establishment_id] = {
                    "establishment_id": establishment_id,
                    "reused": bool(match),
                    "amended_300a": bool(existing_form_id),
                }

            # Step 3 — one submissions POST with the whole array. This is what
            # OSHA treats as "filing complete" and confirms by email.
            body = await _post(client, f"{base}/submissions", token,
                               submit_objects if len(submit_objects) != 1 else submit_objects[0])
            for r in _results_list(body):
                if r.get("id"):
                    submission_ids.append(str(r["id"]))

    except httpx.HTTPError as exc:
        logger.warning("ITA submit transport error: %s", exc)
        return ITASubmissionResult(status="error", error=f"Could not reach the OSHA ITA API: {exc}")
    except _ITAError as exc:
        logger.info("ITA submit rejected: %s", exc.message)
        return ITASubmissionResult(status="rejected", response=exc.response, error=exc.message)

    return ITASubmissionResult(
        status="submitted",
        submission_id=submission_ids[0] if submission_ids else None,
        response={"submission_ids": submission_ids, "establishments": steps},
    )
