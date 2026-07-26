"""Coterie carrier integration — small-commercial quote + bind.

Mirrors the shape of ``finch_service`` (a thin API client that reads config it is
handed, plus retry/backoff and a mock mode), but Coterie authenticates with a
platform-level partner API key rather than per-company OAuth — so there is no
``integration_connections`` row and no per-company token. ``COTERIE_MODE=mock``
(the default until a real partner appointment + credentials exist) returns
representative canned quotes/binds so the whole quote→bind flow is exercisable
end-to-end without live credentials.

Layers:
- ``build_payload`` — PURE mapper (company/location/roster rows → a Coterie quote
  request). DB-free, so it is unit-tested without a database.
- ``build_quote_request`` — fetches the rows for a company and calls ``build_payload``.
- ``CoterieService`` — the API client (``get_quote`` / ``bind_quote``).
- persistence helpers over ``insurance_quotes`` + the bind → ``company_certificates``
  + ``company_coverage_lines`` write.
"""

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# --- Partner config (env, module scope — like the Finch OAuth config) ----------
COTERIE_BASE_URL = os.getenv("COTERIE_BASE_URL", "https://api.coterieinsurance.com/v1")
COTERIE_API_KEY = os.getenv("COTERIE_API_KEY", "")
# 'mock' (default) returns canned quotes; 'live' calls the real API. Unset key in
# live mode raises at call time (never silently returns a fake quote in live mode).
COTERIE_MODE = os.getenv("COTERIE_MODE", "mock").strip().lower()

# --- Carrier capability tiering ------------------------------------------------
# Only quote/bind/policy_docs/webhooks are confirmed-available from Coterie's
# public docs; loss-runs, FNOL, and premium-credit feeds are unconfirmed until a
# partner sandbox appointment. Features that depend on them (Claims Bridge,
# Risk-to-Rate) call ``has_capability`` and 501 when the capability is off — the
# same shape as Finch's ``_require_finch_oauth_config`` 503 guard.
#   COTERIE_CAPS      — comma-list of confirmed-live capabilities (live mode).
#   COTERIE_MOCK_CAPS — capabilities to expose in mock mode ("all" = every known
#                       capability, so the whole product is demoable pre-sandbox).
_ALL_CAPABILITIES = {"quote", "bind", "policy_docs", "webhooks", "loss_runs", "fnol", "credits"}
_CONFIRMED_CAPABILITIES = {"quote", "bind", "policy_docs", "webhooks"}


def _parse_caps(raw: str, default: set) -> set:
    raw = (raw or "").strip()
    if not raw:
        return set(default)
    if raw.lower() == "all":
        return set(_ALL_CAPABILITIES)
    return {c.strip().lower() for c in raw.split(",") if c.strip()} & _ALL_CAPABILITIES


COTERIE_CAPS = _parse_caps(os.getenv("COTERIE_CAPS", ""), _CONFIRMED_CAPABILITIES)
COTERIE_MOCK_CAPS = _parse_caps(os.getenv("COTERIE_MOCK_CAPS", "all"), _ALL_CAPABILITIES)


def has_capability(name: str) -> bool:
    """True if the carrier connection exposes ``name`` in the current mode. In
    mock mode the mock-cap set applies (default: all), so the full flow is
    exercisable before live partner credentials exist."""
    caps = set(COTERIE_MOCK_CAPS) if is_mock_mode() else set(COTERIE_CAPS)
    return name in caps

# Our line keys → Coterie product codes. Kept here so the mapping is one place.
_LINE_TO_PRODUCT = {"bop": "BOP", "gl": "GL", "wc": "WC", "professional": "PL"}
# Line key → the limit_adequacy line a bound policy upserts into. BOP packages
# GL + property; we record the GL leg on coverage lines (property is separate).
_LINE_TO_COVERAGE = {"bop": "gl", "gl": "gl", "wc": "wc", "professional": "professional"}
_LINE_LABEL = {"bop": "Business Owner's Policy", "gl": "General Liability",
               "wc": "Workers' Comp", "professional": "Professional Liability"}


class CoterieError(Exception):
    """Coterie API / config failure surfaced to the caller."""


def is_mock_mode() -> bool:
    return COTERIE_MODE != "live"


# --- Pure payload builder ------------------------------------------------------

def build_payload(line: str, company_row, location_row, emp_agg: dict, overrides: dict) -> dict:
    """Assemble a Coterie quote request from company data + caller overrides.

    Pure — takes plain rows/dicts, no DB. ``emp_agg`` = {"headcount", "annual_payroll"}.
    ``overrides`` = the non-null fields the caller confirmed/edited on the form.
    """
    def pick(key, *fallbacks):
        v = overrides.get(key)
        if v is not None:
            return v
        for fb in fallbacks:
            if fb is not None:
                return fb
        return None

    company_row = company_row or {}
    location_row = location_row or {}
    return {
        "product": _LINE_TO_PRODUCT.get(line, line.upper()),
        "line": line,
        "business": {
            "legal_name": pick("legal_name", company_row.get("legal_name"), company_row.get("name")),
            "naics": pick("naics", company_row.get("naics")),
            "industry": company_row.get("industry"),
            "state": pick("state", location_row.get("state"), company_row.get("headquarters_state")),
            "zip": pick("zip_code", location_row.get("zipcode")),
        },
        "exposure": {
            "headcount": pick("headcount", emp_agg.get("headcount")),
            "annual_payroll": pick("annual_payroll", emp_agg.get("annual_payroll")),
            "annual_revenue": pick("annual_revenue"),
        },
    }


async def build_quote_request(conn, company_id: UUID, req) -> dict:
    """Fetch a company's rows and build the Coterie payload. ``req`` is a
    QuoteRequest; its set (non-null) fields override the derived defaults."""
    company_row = await conn.fetchrow(
        "SELECT name, legal_name, naics, industry, headquarters_state FROM companies WHERE id = $1",
        company_id,
    )
    location_row = await conn.fetchrow(
        """SELECT state, zipcode FROM business_locations
           WHERE company_id = $1 AND is_active IS NOT FALSE
           ORDER BY created_at ASC LIMIT 1""",
        company_id,
    )
    agg = await conn.fetchrow(
        """SELECT COUNT(*) AS headcount,
                  COALESCE(SUM(CASE WHEN pay_classification = 'hourly'
                                    THEN pay_rate * 2080 ELSE pay_rate END), 0) AS annual_payroll
           FROM employees
           WHERE org_id = $1 AND employment_status NOT IN ('terminated', 'offboarded')""",
        company_id,
    )
    emp_agg = {
        "headcount": int(agg["headcount"]) if agg and agg["headcount"] else None,
        "annual_payroll": float(agg["annual_payroll"]) if agg and agg["annual_payroll"] else None,
    }
    overrides = req.model_dump(exclude_unset=True, exclude={"line"})
    return build_payload(req.line, company_row, location_row, emp_agg, overrides)


# --- API client ----------------------------------------------------------------

class CoterieService:
    def __init__(self, *, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {COTERIE_API_KEY}", "Content-Type": "application/json"}

    def _require_config(self):
        if not is_mock_mode() and not COTERIE_API_KEY:
            raise CoterieError("Coterie is in live mode but COTERIE_API_KEY is unset")

    async def _request_with_retry(self, client, method, url, *, max_attempts=4, **kwargs):
        """Retry transient 5xx + transport errors with linear backoff; return 4xx as-is."""
        import asyncio
        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code < 500:
                    return resp
                last_exc = CoterieError(f"Coterie {url} returned {resp.status_code}")
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise last_exc or CoterieError("Coterie request failed")

    async def test_connection(self) -> tuple[bool, Optional[str]]:
        if is_mock_mode():
            return True, None
        self._require_config()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(f"{COTERIE_BASE_URL}/ping", headers=self._headers())
                return (resp.status_code == 200), (None if resp.status_code == 200
                                                   else f"Coterie /ping returned {resp.status_code}")
        except Exception as e:  # noqa: BLE001 — surface any connectivity failure as a message
            return False, f"Connection failed: {e}"

    async def get_quote(self, payload: dict) -> dict:
        """Return {quote_ref, premium_cents, expires_at, raw}."""
        self._require_config()
        if is_mock_mode():
            return _mock_quote(payload)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "POST", f"{COTERIE_BASE_URL}/quotes",
                headers=self._headers(), json=payload,
            )
            if resp.status_code >= 400:
                raise CoterieError(f"Coterie quote failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            return {
                "quote_ref": data.get("id") or data.get("quoteId"),
                "premium_cents": _to_cents(data.get("premium") or data.get("totalPremium")),
                "expires_at": data.get("expiresAt"),
                "raw": data,
            }

    async def bind_quote(self, quote_ref: str, payload: dict) -> dict:
        """Bind an existing quote. Return {policy_number, effective_date, expiry_date, raw}."""
        self._require_config()
        if is_mock_mode():
            return _mock_bind(quote_ref, payload)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await self._request_with_retry(
                client, "POST", f"{COTERIE_BASE_URL}/quotes/{quote_ref}/bind",
                headers=self._headers(), json=payload,
            )
            if resp.status_code >= 400:
                raise CoterieError(f"Coterie bind failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            return {
                "policy_number": data.get("policyNumber") or data.get("id"),
                "effective_date": data.get("effectiveDate"),
                "expiry_date": data.get("expirationDate"),
                "raw": data,
            }


_service: Optional[CoterieService] = None


def get_coterie_service() -> CoterieService:
    global _service
    if _service is None:
        _service = CoterieService()
    return _service


def _to_cents(amount) -> Optional[int]:
    if amount is None:
        return None
    try:
        return int(round(float(amount) * 100))
    except (TypeError, ValueError):
        return None


def _mock_quote(payload: dict) -> dict:
    """Deterministic representative premium so the flow is testable without creds.
    Scales with headcount + payroll; never a live number."""
    exp = payload.get("exposure") or {}
    head = exp.get("headcount") or 5
    payroll = exp.get("annual_payroll") or (head * 45000)
    line = payload.get("line", "gl")
    base = {"bop": 1200, "gl": 800, "wc": 600, "professional": 900}.get(line, 800)
    premium = base + head * 60 + payroll * 0.004
    return {
        "quote_ref": f"MOCK-{line.upper()}-{head}",
        "premium_cents": int(round(premium * 100)),
        "expires_at": (date.today() + timedelta(days=30)).isoformat(),
        "raw": {"mock": True, "line": line, "premium": round(premium, 2)},
    }


def _mock_bind(quote_ref: str, payload: dict) -> dict:
    today = date.today()
    return {
        "policy_number": f"POL-{quote_ref}",
        "effective_date": today.isoformat(),
        "expiry_date": (today.replace(year=today.year + 1)).isoformat(),
        "raw": {"mock": True, "quote_ref": quote_ref},
    }


# --- Claims Bridge helpers (capability-gated at the route) ----------------------

def mock_loss_runs() -> list[dict]:
    """Representative loss-run rows so the Claims Bridge is demoable pre-sandbox.
    Never live figures — deterministic sample history."""
    this_year = date.today().year
    return [
        {"policy_year": this_year - 2, "claims": 3, "incurred_cents": 4_200_00,
         "paid_cents": 3_900_00, "open": 0},
        {"policy_year": this_year - 1, "claims": 1, "incurred_cents": 1_100_00,
         "paid_cents": 600_00, "open": 1},
        {"policy_year": this_year, "claims": 0, "incurred_cents": 0, "paid_cents": 0, "open": 0},
    ]


def file_fnol(incident_id: str, incident_number=None) -> str:
    """File a First Notice of Loss and return the carrier claim reference. Mock mode
    derives a deterministic ref from the incident; live FNOL awaits the carrier
    endpoint (the route already capability-gates on 'fnol')."""
    if is_mock_mode():
        tag = str(incident_number or incident_id).replace(" ", "")[:16].upper()
        return f"FNOL-MOCK-{tag}"
    # Live FNOL endpoint not yet available from the carrier partner API.
    raise CoterieError("fnol_not_available_live")


# --- Persistence over insurance_quotes -----------------------------------------

def _serialize(row) -> dict:
    # broker-placement columns (brokerquote01) may be absent on a row that
    # predates the migration in a mixed-schema window — read defensively.
    def _opt(key):
        try:
            return row[key]
        except (KeyError, IndexError):
            return None

    presented_at = _opt("presented_at")
    return {
        "id": str(row["id"]),
        "line": row["line"],
        "carrier": row["carrier"],
        "status": row["status"],
        "quote_ref": row["quote_ref"],
        "premium_cents": row["premium_cents"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "error_message": row["error_message"],
        "certificate_id": str(row["certificate_id"]) if row["certificate_id"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "placement": _opt("placement") or "client",
        "presented_at": presented_at.isoformat() if presented_at else None,
        "commission_bps": _opt("commission_bps"),
        "broker_note": _opt("broker_note"),
        "external_client_id": str(_opt("external_client_id")) if _opt("external_client_id") else None,
    }


async def list_quotes(conn, company_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        "SELECT * FROM insurance_quotes WHERE company_id = $1 ORDER BY created_at DESC",
        company_id,
    )
    return [_serialize(r) for r in rows]


async def create_quote(conn, company_id: UUID, req, created_by: Optional[UUID]) -> dict:
    """Build the payload, call Coterie, persist the resulting quote row."""
    payload = await build_quote_request(conn, company_id, req)
    svc = get_coterie_service()
    try:
        result = await svc.get_quote(payload)
        status, err = "quoted", None
    except CoterieError as e:
        result, status, err = {"quote_ref": None, "premium_cents": None, "expires_at": None, "raw": {}}, "error", str(e)

    expires = result.get("expires_at")
    row = await conn.fetchrow(
        """
        INSERT INTO insurance_quotes
            (company_id, carrier, line, quote_ref, status, premium_cents,
             request_payload, quote_payload, error_message, expires_at, created_by)
        VALUES ($1, 'coterie', $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10)
        RETURNING *
        """,
        company_id, req.line, result.get("quote_ref"), status, result.get("premium_cents"),
        json.dumps(payload), json.dumps(result.get("raw") or {}), err,
        _parse_date(expires), created_by,
    )
    return _serialize(row)


async def bind_quote(conn, company_id: UUID, quote_id: UUID, uploaded_by: Optional[UUID]) -> dict:
    """Bind a quoted row: call Coterie, then in one transaction write a
    company_certificates row, upsert the bound coverage line, and flip status."""
    q = await conn.fetchrow(
        "SELECT * FROM insurance_quotes WHERE id = $1 AND company_id = $2", quote_id, company_id,
    )
    if not q:
        raise CoterieError("quote_not_found")
    if q["status"] == "bound":
        raise CoterieError("already_bound")
    # 'quoted' = fresh quote; 'presented' = a broker presented it to the client
    # for acceptance (the present->accept path). Both are bindable.
    if q["status"] not in ("quoted", "presented") or not q["quote_ref"]:
        raise CoterieError("not_quotable")

    payload = q["request_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    svc = get_coterie_service()
    bind = await svc.bind_quote(q["quote_ref"], payload)

    line_key = _LINE_TO_COVERAGE.get(q["line"], q["line"])
    carrier_name = "Coterie"
    eff = _parse_date(bind.get("effective_date"))
    exp = _parse_date(bind.get("expiry_date"))
    cert_lines = [{"line": line_key, "effective_date": bind.get("effective_date"),
                   "expiry_date": bind.get("expiry_date")}]

    async with conn.transaction():
        cert = await conn.fetchrow(
            """
            INSERT INTO company_certificates
                (company_id, holder_name, carrier, certificate_number, lines, expiry_date,
                 status, source, premium_cents, uploaded_by)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, 'coterie', $8, $9)
            RETURNING id
            """,
            company_id,
            (payload.get("business") or {}).get("legal_name"),
            carrier_name, bind.get("policy_number"), json.dumps(cert_lines), exp,
            "active" if exp and exp >= date.today() else "unknown",
            q["premium_cents"], uploaded_by,
        )
        # Reflect the bound policy on company_coverage_lines so limit_adequacy /
        # broker submission (which read carried coverage from there) see it.
        # Lazy import keeps this module's pure mappers/config free of the
        # limit_adequacy -> PDF import chain (so they're unit-testable standalone).
        from . import limit_adequacy as la
        if line_key in la.LINE_KEYS:
            await conn.execute(
                """
                INSERT INTO company_coverage_lines
                    (company_id, line, carrier, effective_date, expiry_date, note)
                VALUES ($1, $2, $3, $4, $5, 'Bound via Coterie')
                ON CONFLICT (company_id, line) DO UPDATE
                    SET carrier = EXCLUDED.carrier, effective_date = EXCLUDED.effective_date,
                        expiry_date = EXCLUDED.expiry_date, note = EXCLUDED.note,
                        updated_at = NOW()
                """,
                company_id, line_key, carrier_name, eff, exp,
            )
        row = await conn.fetchrow(
            """
            UPDATE insurance_quotes
               SET status = 'bound', certificate_id = $3,
                   quote_payload = quote_payload || $4::jsonb, updated_at = NOW()
             WHERE id = $1 AND company_id = $2
            RETURNING *
            """,
            quote_id, company_id, cert["id"],
            json.dumps({"bind": bind.get("raw") or {}, "policy_number": bind.get("policy_number"),
                        "policy_effective": bind.get("effective_date"),
                        "policy_expiry": bind.get("expiry_date")}),
        )
    return _serialize(row)


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


# --- Broker-placed quoting (Broker Quoting Desk) -------------------------------
# A broker quotes/presents/binds on behalf of a client in their book. On-platform
# clients reuse build_quote_request (rich company data). Off-platform clients have
# only a broker_external_clients snapshot, so we synthesize the row and reuse the
# same pure build_payload mapper.

async def build_quote_request_external(conn, external_client_id: UUID, req, *, broker_id: UUID) -> dict:
    """Build a Coterie payload for an off-platform (Broker Pro) client from its
    ``broker_external_clients`` snapshot. Ownership is enforced by the route; the
    ``broker_id`` filter here is defense-in-depth."""
    row = await conn.fetchrow(
        "SELECT name, industry, headcount, primary_state FROM broker_external_clients "
        "WHERE id = $1 AND broker_id = $2",
        external_client_id, broker_id,
    )
    if not row:
        raise CoterieError("external_client_not_found")
    company_row = {
        "name": row["name"], "legal_name": row["name"], "naics": None,
        "industry": row["industry"], "headquarters_state": row["primary_state"],
    }
    emp_agg = {"headcount": row["headcount"], "annual_payroll": None}
    overrides = req.model_dump(exclude_unset=True, exclude={"line", "commission_bps", "broker_note"})
    return build_payload(req.line, company_row, None, emp_agg, overrides)


async def create_broker_quote(conn, *, broker_id: UUID, req, created_by: Optional[UUID],
                              company_id: Optional[UUID] = None,
                              external_client_id: Optional[UUID] = None) -> dict:
    """Broker requests a quote for one client (tenant XOR external) and persists it
    as a broker-placed row. Returns the quote (status 'error' on carrier decline —
    never raises for a decline)."""
    if bool(company_id) == bool(external_client_id):
        raise CoterieError("exactly one of company_id / external_client_id required")
    if company_id is not None:
        payload = await build_quote_request(conn, company_id, req)
    else:
        payload = await build_quote_request_external(conn, external_client_id, req, broker_id=broker_id)

    svc = get_coterie_service()
    try:
        result = await svc.get_quote(payload)
        status, err = "quoted", None
    except CoterieError as e:
        result, status, err = {"quote_ref": None, "premium_cents": None, "expires_at": None, "raw": {}}, "error", str(e)

    row = await conn.fetchrow(
        """
        INSERT INTO insurance_quotes
            (company_id, external_client_id, broker_id, carrier, line, quote_ref, status,
             premium_cents, request_payload, quote_payload, error_message, expires_at,
             created_by, placement, commission_bps, broker_note)
        VALUES ($1, $2, $3, 'coterie', $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12,
                'broker', $13, $14)
        RETURNING *
        """,
        company_id, external_client_id, broker_id, req.line, result.get("quote_ref"), status,
        result.get("premium_cents"), json.dumps(payload), json.dumps(result.get("raw") or {}), err,
        _parse_date(result.get("expires_at")), created_by,
        getattr(req, "commission_bps", None), getattr(req, "broker_note", None),
    )
    return _serialize(row)


async def list_broker_quotes(conn, *, company_id: Optional[UUID] = None,
                             external_client_id: Optional[UUID] = None) -> list[dict]:
    if company_id is not None:
        rows = await conn.fetch(
            "SELECT * FROM insurance_quotes WHERE company_id = $1 ORDER BY created_at DESC",
            company_id,
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM insurance_quotes WHERE external_client_id = $1 ORDER BY created_at DESC",
            external_client_id,
        )
    return [_serialize(r) for r in rows]


async def present_quote(conn, *, company_id: UUID, quote_id: UUID,
                        commission_bps: Optional[int] = None,
                        broker_note: Optional[str] = None) -> dict:
    """Flip a quoted (on-platform) row to 'presented' so the client can accept and
    bind it on their own Insurance page. Tenant-only — off-platform clients have no
    self-serve surface to accept on."""
    q = await conn.fetchrow(
        "SELECT status FROM insurance_quotes WHERE id = $1 AND company_id = $2", quote_id, company_id,
    )
    if not q:
        raise CoterieError("quote_not_found")
    if q["status"] == "bound":
        raise CoterieError("already_bound")
    if q["status"] not in ("quoted", "presented"):
        raise CoterieError("not_quotable")
    row = await conn.fetchrow(
        """
        UPDATE insurance_quotes
           SET status = 'presented', presented_at = NOW(),
               commission_bps = COALESCE($3, commission_bps),
               broker_note = COALESCE($4, broker_note),
               updated_at = NOW()
         WHERE id = $1 AND company_id = $2
        RETURNING *
        """,
        quote_id, company_id, commission_bps, broker_note,
    )
    return _serialize(row)


async def bind_external_quote(conn, *, broker_id: UUID, external_client_id: UUID,
                              quote_id: UUID, bound_by: Optional[UUID]) -> dict:
    """Bind a quote for an off-platform client. No companies row exists, so this
    does NOT write a certificate or coverage line (those are tenant-scoped) — it
    calls the carrier, records the policy on the quote row, and flips status."""
    q = await conn.fetchrow(
        "SELECT * FROM insurance_quotes WHERE id = $1 AND external_client_id = $2 AND broker_id = $3",
        quote_id, external_client_id, broker_id,
    )
    if not q:
        raise CoterieError("quote_not_found")
    if q["status"] == "bound":
        raise CoterieError("already_bound")
    if q["status"] not in ("quoted", "presented") or not q["quote_ref"]:
        raise CoterieError("not_quotable")

    payload = q["request_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    svc = get_coterie_service()
    bind = await svc.bind_quote(q["quote_ref"], payload)

    row = await conn.fetchrow(
        """
        UPDATE insurance_quotes
           SET status = 'bound',
               quote_payload = quote_payload || $3::jsonb, updated_at = NOW()
         WHERE id = $1 AND external_client_id = $2
        RETURNING *
        """,
        quote_id, external_client_id,
        json.dumps({"bind": bind.get("raw") or {}, "policy_number": bind.get("policy_number"),
                    "policy_effective": bind.get("effective_date"),
                    "policy_expiry": bind.get("expiry_date")}),
    )
    return _serialize(row)
