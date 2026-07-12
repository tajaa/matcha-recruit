"""Finch unified-API HRIS service — pulls employee data from any Finch-connected
payroll/HRIS provider.

Mirrors the shape of ``GustoHRISService`` in ``hris_service.py`` (same method
signatures, same normalized-output keys) so the existing
``hris_sync_orchestrator._sync_single_employee`` upsert pipeline consumes Finch
records with no changes.

Auth model: Finch Connect (OAuth authorization-code). The access token is stored
encrypted in ``integration_connections.secrets['access_token']`` — same slot the
Gusto OAuth flow uses. There is no client_credentials fallback (Finch is per-employer
OAuth only).

Field paths were verified against Finch's public API docs (2026-07): the work
location lives at ``employment.location`` (``work_location`` kept as a defensive
fallback), ``flsa_status`` values are ``exempt`` / ``non_exempt`` / ``unknown`` /
null, and benefit types follow the documented enum (``s125_medical``,
``fsa_medical``, …). Still validate end-to-end against a live sandbox connection
before enabling for real customer connections (provider-specific gaps are common).

Set ``config['mode'] = 'finch_mock'`` to serve the mock dataset below through this
class (plain ``mock`` routes to the base ``HRISService`` instead — see
``hris_service.get_hris_service``).
"""

import asyncio
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from .hris_service import HRISProvisioningError, is_mock_mode, normalize_hris_locations

logger = logging.getLogger(__name__)

FINCH_BASE_URL = os.getenv("FINCH_BASE_URL", "https://api.tryfinch.com")
# Finch pins behavior to a dated API version via this header.
FINCH_API_VERSION = os.getenv("FINCH_API_VERSION", "2020-09-17")

# Batch size for the POST /employer/{individual,employment} detail endpoints.
_FINCH_BATCH = 50

# Finch's documented benefit-type enum values that carry an employer HEALTH
# PREMIUM (drives the termination premium-leak estimate). The enum has no plain
# "health"/"medical" type; s125_dental / s125_vision / retirement types are
# deliberately excluded. So are hsa_pre / hsa_post: an employer HSA contribution
# is a deposit into the employee's account, not a premium the employer keeps
# paying after termination — counting it would inflate the leak.
_HEALTH_BENEFIT_TYPES = frozenset({"s125_medical", "fsa_medical"})


def _is_health_benefit(benefit_type: Optional[str]) -> bool:
    """True when a Finch benefit type represents an employer health premium.

    Exact-matches the documented enum, plus a substring fallback for
    provider-custom types (e.g. a custom "medical_plan"), excluding
    dental/vision.
    """
    btype = (benefit_type or "").lower()
    if btype in _HEALTH_BENEFIT_TYPES:
        return True
    if "dental" in btype or "vision" in btype:
        return False
    return "medical" in btype


class FinchHRISService:
    """Client for the Finch API. Fetches and normalizes employee data.

    Parallel to ``GustoHRISService`` — exposes ``test_connection``,
    ``authenticate``, ``fetch_workers``, and ``normalize_worker``.
    """

    def __init__(self, *, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Finch-API-Version": FINCH_API_VERSION,
            "Content-Type": "application/json",
        }

    async def test_connection(self, config: dict, secrets: dict) -> tuple[bool, Optional[str]]:
        if is_mock_mode(config):
            return True, None
        try:
            token = await self.authenticate(config, secrets)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(
                    f"{FINCH_BASE_URL}/employer/company",
                    headers=self._headers(token),
                )
                if resp.status_code == 200:
                    return True, None
                return False, f"Finch /employer/company returned {resp.status_code}"
        except HRISProvisioningError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    async def authenticate(self, config: dict, secrets: dict) -> str:
        """Return the Finch access token. Finch is OAuth-only — the token is
        obtained via Finch Connect and stored encrypted in secrets."""
        if is_mock_mode(config):
            return "mock-finch-token"

        token = secrets.get("access_token")
        if not token:
            raise HRISProvisioningError(
                "auth_config_missing",
                "Missing Finch access_token — complete Finch Connect first",
                needs_action=True,
            )
        return token

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        max_attempts: int = 4,
        **kwargs,
    ) -> httpx.Response:
        """Issue a request, retrying transient failures (5xx + transport errors).

        Finch — especially the sandbox right after a connection is created — returns
        intermittent 5xx on /employer/* before settling. Retry with linear backoff so
        a flaky first call doesn't fail the whole sync. 4xx is returned as-is (caller
        decides), only 5xx and network errors are retried.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code < 500:
                    return resp
                logger.warning(
                    "[Finch] %s %s -> %d (attempt %d/%d), retrying",
                    method, url, resp.status_code, attempt + 1, max_attempts,
                )
            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning(
                    "[Finch] %s %s transport error %s (attempt %d/%d), retrying",
                    method, url, exc, attempt + 1, max_attempts,
                )
            if attempt < max_attempts - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
        return resp  # last 5xx response — caller raises a descriptive error

    async def fetch_workers(self, config: dict, secrets: dict) -> list[dict]:
        """List the employer directory, then hydrate each individual with
        identity + employment detail. Returns a list of merged raw Finch records."""
        if is_mock_mode(config):
            return _FINCH_MOCK_EMPLOYEES

        token = await self.authenticate(config, secrets)
        headers = self._headers(token)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # 1. Directory — paginated list of individuals (id + lightweight fields).
                ids: list[str] = []
                offset = 0
                page_limit = 100
                while True:
                    resp = await self._request_with_retry(
                        client,
                        "GET",
                        f"{FINCH_BASE_URL}/employer/directory",
                        headers=headers,
                        params={"limit": page_limit, "offset": offset},
                    )
                    if resp.status_code != 200:
                        raise HRISProvisioningError(
                            "fetch_failed", f"Finch directory fetch failed: {resp.status_code}"
                        )
                    body = resp.json()
                    individuals = body.get("individuals") or []
                    ids.extend(i["id"] for i in individuals if i.get("id"))
                    # Terminate on a short page. Finch's sandbox (and some providers)
                    # omit paging.total, and requesting an out-of-range offset 500s —
                    # so never rely on total; stop as soon as a page is under-full.
                    total = (body.get("paging") or {}).get("total")
                    offset += len(individuals)
                    if (
                        not individuals
                        or len(individuals) < page_limit
                        or (total is not None and offset >= total)
                    ):
                        break

                # 2. Hydrate identity + employment in batches.
                identities = await self._batch_detail(client, headers, "individual", ids)
                employments = await self._batch_detail(client, headers, "employment", ids)
        except HRISProvisioningError:
            raise
        except Exception as e:
            raise HRISProvisioningError("fetch_error", f"Finch fetch error: {str(e)}")

        # 3. Merge identity + employment per id into one raw record for normalize_worker.
        workers: list[dict] = []
        for fid in ids:
            workers.append({
                "id": fid,
                "individual": identities.get(fid, {}),
                "employment": employments.get(fid, {}),
            })

        logger.info("[Finch] Fetched %d employees", len(workers))
        return workers

    async def _batch_detail(
        self, client: httpx.AsyncClient, headers: dict, kind: str, ids: list[str]
    ) -> dict[str, dict]:
        """POST /employer/{kind} in batches; return {individual_id: body}."""
        out: dict[str, dict] = {}
        for start in range(0, len(ids), _FINCH_BATCH):
            chunk = ids[start:start + _FINCH_BATCH]
            resp = await self._request_with_retry(
                client,
                "POST",
                f"{FINCH_BASE_URL}/employer/{kind}",
                headers=headers,
                json={"requests": [{"individual_id": i} for i in chunk]},
            )
            if resp.status_code != 200:
                raise HRISProvisioningError(
                    "fetch_failed", f"Finch {kind} fetch failed: {resp.status_code}"
                )
            for entry in resp.json().get("responses") or []:
                iid = entry.get("individual_id")
                body = entry.get("body") or {}
                if iid:
                    out[iid] = body
        return out

    async def fetch_company(self, config: dict, secrets: dict) -> dict:
        """GET /employer/company — legal name, entity, EIN, and work locations."""
        if is_mock_mode(config):
            return _FINCH_MOCK_COMPANY
        token = await self.authenticate(config, secrets)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "GET", f"{FINCH_BASE_URL}/employer/company",
                headers=self._headers(token),
            )
        if resp.status_code != 200:
            raise HRISProvisioningError(
                "fetch_failed", f"Finch company fetch failed: {resp.status_code}"
            )
        return resp.json()

    async def fetch_locations(self, config: dict, secrets: dict) -> list[dict]:
        """Company work locations, normalized to the shared HRIS location shape.

        Returns ``[{name, line1, line2, city, state, postal_code, country}]`` —
        the same keys ``GustoHRISService.fetch_locations`` emits, so the sync
        orchestrator's ``business_locations`` upsert is provider-agnostic.
        """
        company = await self.fetch_company(config, secrets)
        return normalize_hris_locations(company.get("locations") or [])

    # ------------------------------------------------------------------
    # Benefits / deductions WRITE (Finch Deductions product)
    #
    # Only providers Finch supports for deductions-write expose these (e.g.
    # QuickBooks, Gusto, ADP). Square Payroll does NOT — calls 404/501 there.
    # Writes are async: POST returns a job_id; poll get_job() until complete.
    # ------------------------------------------------------------------
    async def get_benefit_meta(self, config: dict, secrets: dict) -> list[dict]:
        """List the benefit types the connected provider supports (the write schema)."""
        token = await self.authenticate(config, secrets)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "GET", f"{FINCH_BASE_URL}/employer/benefits/meta",
                headers=self._headers(token),
            )
        if resp.status_code != 200:
            raise HRISProvisioningError(
                "benefits_unsupported",
                f"Finch benefits not supported for this connection ({resp.status_code})",
            )
        body = resp.json()
        return body if isinstance(body, list) else (body.get("supported_benefits") or [])

    async def list_benefits(self, config: dict, secrets: dict) -> list[dict]:
        """List company-level benefits already configured in the provider."""
        token = await self.authenticate(config, secrets)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "GET", f"{FINCH_BASE_URL}/employer/benefits",
                headers=self._headers(token),
            )
        if resp.status_code != 200:
            raise HRISProvisioningError(
                "benefits_read_failed", f"Finch list benefits failed: {resp.status_code}",
            )
        body = resp.json()
        return body if isinstance(body, list) else (body.get("benefits") or [])

    async def create_benefit(
        self, config: dict, secrets: dict, *,
        benefit_type: str, description: str, frequency: str,
    ) -> dict:
        """Create a company-level benefit/deduction. Returns {benefit_id, job_id}.

        The write is async — Finch returns a job_id; the benefit becomes readable
        once the job completes. Poll get_job(job_id) for status.
        """
        token = await self.authenticate(config, secrets)
        payload = {"type": benefit_type, "description": description, "frequency": frequency}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "POST", f"{FINCH_BASE_URL}/employer/benefits",
                headers=self._headers(token), json=payload,
            )
        if resp.status_code not in (200, 201):
            raise HRISProvisioningError(
                "benefit_create_failed",
                f"Finch create benefit failed ({resp.status_code}): {resp.text[:200]}",
            )
        return resp.json()

    async def get_job(self, config: dict, secrets: dict, job_id: str) -> dict:
        """Poll an async Finch job (e.g. a benefits write). Returns the job body."""
        token = await self.authenticate(config, secrets)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "GET", f"{FINCH_BASE_URL}/jobs/automated/{job_id}",
                headers=self._headers(token),
            )
        if resp.status_code != 200:
            raise HRISProvisioningError(
                "job_read_failed", f"Finch job poll failed: {resp.status_code}",
            )
        return resp.json()

    async def list_enrolled(self, config: dict, secrets: dict, benefit_id: str) -> list[str]:
        """Return the individual_ids enrolled in a given company benefit."""
        token = await self.authenticate(config, secrets)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "GET", f"{FINCH_BASE_URL}/employer/benefits/{benefit_id}/enrolled",
                headers=self._headers(token),
            )
        if resp.status_code != 200:
            raise HRISProvisioningError(
                "benefits_read_failed", f"Finch enrolled read failed: {resp.status_code}",
            )
        body = resp.json()
        rows = body if isinstance(body, list) else (body.get("individual_ids") or body.get("enrolled") or [])
        out: list[str] = []
        for r in rows:
            if isinstance(r, str):
                out.append(r)
            elif isinstance(r, dict) and r.get("individual_id"):
                out.append(r["individual_id"])
        return out

    async def get_benefit_individuals(self, config: dict, secrets: dict, benefit_id: str) -> dict[str, dict]:
        """Per-individual enrollment detail for a benefit: contribution amounts.

        Returns ``{individual_id: {employee_deduction, company_contribution}}``.
        Amounts follow Finch's structured ``{amount, type}`` shape (amount in
        minor units / cents for ``type='fixed'``).
        """
        token = await self.authenticate(config, secrets)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "GET", f"{FINCH_BASE_URL}/employer/benefits/{benefit_id}/individuals",
                headers=self._headers(token),
            )
        if resp.status_code != 200:
            raise HRISProvisioningError(
                "benefits_read_failed", f"Finch benefit individuals read failed: {resp.status_code}",
            )
        body = resp.json()
        rows = body if isinstance(body, list) else (body.get("responses") or body.get("individuals") or [])
        out: dict[str, dict] = {}
        for entry in rows:
            iid = entry.get("individual_id")
            data = entry.get("body") or entry
            if iid:
                out[iid] = data
        return out

    async def fetch_benefit_facts(
        self, config: dict, secrets: dict, individual_ids: list[str]
    ) -> dict[str, dict]:
        """Per-employee benefit facts used by the eligibility-exception engine.

        Output: ``{individual_id: {has_benefits_enrollment, employer_health_premium_monthly}}``.

        Source is the Finch *Benefits* product (company benefit → enrolled
        individuals → per-individual company contribution). Health/medical
        benefits drive the employer-premium estimate that powers the
        termination "premium leak" detection.

        Benefit-type matching follows Finch's documented enum (see
        ``_is_health_benefit``). Real connections without the Benefits product,
        or providers that don't expose ``/benefits/{id}/individuals``, degrade
        to "no facts" — the caller treats unknown enrollment as ``None`` rather
        than a false signal.
        """
        if is_mock_mode(config):
            # Demo facts: first mock employee enrolled w/ employer premium, the
            # rest unenrolled — exercises both the leak and the gap path.
            facts: dict[str, dict] = {}
            for i, iid in enumerate(individual_ids):
                enrolled = (i % 2 == 0)
                facts[iid] = {
                    "has_benefits_enrollment": enrolled,
                    "employer_health_premium_monthly": 650.0 if enrolled else 0.0,
                }
            return facts

        facts: dict[str, dict] = {}
        try:
            benefits = await self.list_benefits(config, secrets)
        except HRISProvisioningError:
            return facts  # Benefits product not available — caller handles unknown.

        for benefit in benefits:
            if not _is_health_benefit(benefit.get("type")):
                continue
            bid = benefit.get("id") or benefit.get("benefit_id")
            if not bid:
                continue
            try:
                enrolled_ids = await self.list_enrolled(config, secrets, bid)
                contributions = await self.get_benefit_individuals(config, secrets, bid)
            except HRISProvisioningError:
                continue
            for iid in enrolled_ids:
                fact = facts.setdefault(
                    iid, {"has_benefits_enrollment": True, "employer_health_premium_monthly": 0.0}
                )
                fact["has_benefits_enrollment"] = True
                detail = contributions.get(iid) or {}
                comp = detail.get("company_contribution") or {}
                if not isinstance(comp, dict):
                    continue
                # `amount` is only a dollar figure when `type` is "fixed" — a
                # "percent" contribution's amount is a rate, and dividing it by 100
                # would report a fabricated premium (50% → "$50.00/mo"). A percent
                # contribution needs the plan's total premium to resolve, which
                # Finch doesn't expose here, so it degrades to "no premium fact".
                if (comp.get("type") or "").lower() != "fixed":
                    continue
                amount = comp.get("amount")
                if amount not in (None, ""):
                    try:
                        # Finch fixed amounts are in minor units (cents). ACCUMULATE
                        # across health benefits (e.g. s125_medical + fsa_medical) —
                        # assigning would let the last benefit overwrite the rest.
                        monthly = float(Decimal(str(amount)) / Decimal(100))
                        fact["employer_health_premium_monthly"] = round(
                            fact["employer_health_premium_monthly"] + monthly, 2
                        )
                    except (InvalidOperation, ValueError):
                        pass
        return facts

    @staticmethod
    def normalize_worker(finch_record: dict) -> dict:
        """Convert a merged Finch record to flat Matcha employee format.

        Output keys MUST match GustoHRISService.normalize_worker so the shared
        orchestrator upsert path is identical.
        """
        individual = finch_record.get("individual") or {}
        employment = finch_record.get("employment") or {}

        # Email: prefer work email from employment/individual, fall back to first listed.
        emails = individual.get("emails") or employment.get("emails") or []
        work_email = next((e.get("data") for e in emails if e.get("type") == "work" and e.get("data")), None)
        personal_email = next((e.get("data") for e in emails if e.get("type") == "personal" and e.get("data")), None)
        any_email = next((e.get("data") for e in emails if e.get("data")), None)
        email = work_email or any_email

        # Phone.
        phones = individual.get("phone_numbers") or []
        phone = next((p.get("data") for p in phones if p.get("data")), None)

        # Work location → state/city. Finch's documented schema puts the work
        # location on employment under `location` (line1/line2/city/state/
        # postal_code/country); `work_location` kept as a defensive fallback for
        # provider drift, then individual residence.
        work_loc = (
            employment.get("location")
            or employment.get("work_location")
            or individual.get("residence")
            or {}
        )

        # Employment type → Matcha enum (full_time|part_time|contractor|intern).
        emp = employment.get("employment") or {}
        emp_type = (emp.get("type") or "").lower()          # "employee" | "contractor"
        emp_subtype = (emp.get("subtype") or "").lower()    # "full_time" | "part_time" | ...
        if emp_type == "contractor":
            employment_type = "contractor"
        elif emp_subtype == "part_time":
            employment_type = "part_time"
        elif emp_subtype == "intern":
            employment_type = "intern"
        else:
            employment_type = "full_time"

        # Pay rate. Finch income.amount is in MINOR units (cents); income.unit gives cadence.
        income = employment.get("income") or {}
        pay_rate: Optional[Decimal] = None
        raw_amount = income.get("amount")
        if raw_amount not in (None, ""):
            try:
                pay_rate = (Decimal(str(raw_amount)) / Decimal(100)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                pay_rate = None

        # Pay classification → Matcha enum (hourly|exempt). Prefer the explicit FLSA
        # status when present — Finch's documented values are "exempt" / "non_exempt"
        # / "unknown" / null; else infer from income.unit. "fixed" = fixed salary →
        # exempt. NOTE: "salaried non-exempt" can't be distinguished from unit alone.
        # Compact out _/-/spaces before matching: the naive `"nonexempt" in flsa`
        # never matched Finch's "non_exempt" and misclassified it as exempt.
        flsa = (employment.get("flsa_status") or "").lower()
        flsa_compact = flsa.replace("_", "").replace("-", "").replace(" ", "")
        unit = (income.get("unit") or "").lower()
        if "nonexempt" in flsa_compact or unit == "hourly":
            pay_classification = "hourly"
        elif "exempt" in flsa_compact:
            pay_classification = "exempt"
        elif unit in ("yearly", "quarterly", "monthly", "weekly", "biweekly", "semimonthly", "daily", "fixed"):
            pay_classification = "exempt"
        else:
            pay_classification = None

        is_active = employment.get("is_active")
        employment_status = "active" if is_active in (True, None) else "terminated"

        # Home address — Finch carries the residence on the individual. Flatten the
        # structured object into the single `address` text column (line1/line2/city/
        # state/zip). Work `location` is kept separately (we already map work_city/state).
        residence = individual.get("residence") or {}
        addr_parts = [
            residence.get("line1"),
            residence.get("line2"),
            residence.get("city"),
            residence.get("state"),
            residence.get("postal_code"),
        ]
        address = ", ".join(p for p in addr_parts if p) or None

        # Termination date — Finch `employment.end_date` (null while active).
        termination_date = employment.get("end_date")

        # Manager — Finch gives the manager's individual_id (not a name). Carry the
        # raw HRIS id; the sync orchestrator resolves it to a Matcha employee.id in a
        # second pass once every worker in this org has a row.
        manager_obj = employment.get("manager") or individual.get("manager") or {}
        manager_hris_id = manager_obj.get("id")

        return {
            "hris_id": finch_record.get("id") or individual.get("id"),
            "first_name": individual.get("first_name") or employment.get("first_name"),
            "last_name": individual.get("last_name") or employment.get("last_name"),
            "email": email,
            "personal_email": personal_email if work_email else None,
            "phone": phone,
            "job_title": employment.get("title"),
            "department": (employment.get("department") or {}).get("name"),
            "employment_type": employment_type,
            "work_state": work_loc.get("state"),
            "work_city": work_loc.get("city"),
            "pay_rate": pay_rate,
            "pay_classification": pay_classification,
            "start_date": employment.get("start_date"),
            "termination_date": termination_date,
            "address": address,
            "manager_hris_id": manager_hris_id,
            "is_manager": False,
            "employment_status": employment_status,
            # Finch (like Gusto) does not carry clinical credentials — stays CSV/manual.
            "credentials": None,
        }


# ---------------------------------------------------------------------------
# Small mock dataset for Finch mode (dev / demo) — mirrors the merged shape that
# fetch_workers produces (id + individual + employment).
# ---------------------------------------------------------------------------

_FINCH_MOCK_COMPANY: dict = {
    "id": "finch-mock-company",
    "legal_name": "Finch Mock Co",
    "entity": {"type": "llc", "subtype": None},
    "ein": None,
    "locations": [
        {"line1": "1 Market St", "line2": None, "city": "San Francisco",
         "state": "CA", "postal_code": "94105", "country": "US"},
        {"line1": "500 W Temple St", "line2": None, "city": "Los Angeles",
         "state": "CA", "postal_code": "90012", "country": "US"},
    ],
}

_FINCH_MOCK_EMPLOYEES: list[dict] = [
    {
        "id": "finch-mock-001",
        "individual": {
            "id": "finch-mock-001",
            "first_name": "Alex",
            "last_name": "Rivera",
            "emails": [{"data": "alex.rivera@example.com", "type": "work"}],
            "phone_numbers": [{"data": "555-0101", "type": "work"}],
        },
        "employment": {
            "title": "Software Engineer",
            "department": {"name": "Engineering"},
            "employment": {"type": "employee", "subtype": "full_time"},
            "income": {"amount": 12000000, "unit": "yearly", "currency": "usd"},
            "flsa_status": "exempt",
            # Documented schema key is `location` (was `work_location` — kept
            # wrong here would mean mock never exercises the real path).
            "location": {"line1": "1 Market St", "state": "CA", "city": "San Francisco",
                         "postal_code": "94105", "country": "US"},
            "start_date": "2023-03-01",
            "is_active": True,
        },
    },
    {
        "id": "finch-mock-002",
        "individual": {
            "id": "finch-mock-002",
            "first_name": "Morgan",
            "last_name": "Chen",
            "emails": [{"data": "morgan.chen@example.com", "type": "work"}],
            "phone_numbers": [{"data": "555-0102", "type": "work"}],
        },
        "employment": {
            "title": "Outreach Worker",
            "department": {"name": "Field Operations"},
            "employment": {"type": "employee", "subtype": "part_time"},
            "income": {"amount": 2800, "unit": "hourly", "currency": "usd"},
            "flsa_status": "non_exempt",
            "location": {"line1": "500 W Temple St", "state": "CA", "city": "Los Angeles",
                         "postal_code": "90012", "country": "US"},
            "start_date": "2022-06-15",
            "is_active": True,
        },
    },
]


def get_finch_service() -> FinchHRISService:
    """Return a Finch HRIS service instance."""
    return FinchHRISService()
