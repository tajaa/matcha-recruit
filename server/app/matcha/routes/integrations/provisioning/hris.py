"""HRIS (Gusto/Finch) provisioning routes (J7 split)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.core.dependencies import require_admin
from app.core.services.secret_crypto import decrypt_secret, encrypt_secret
from app.database import get_connection
from app.matcha.dependencies import (
    get_client_company_id,
    require_admin_or_client,
    require_any_feature,
    require_feature,
    require_feature,
)
from app.matcha.services.google_workspace_service import GoogleWorkspaceService
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    retry_google_workspace_onboarding,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from app.matcha.services.hris_service import PROVIDER_HRIS, HRISProvisioningError

# Several handlers below already call logger.error(...) on their failure paths
# (Gusto company fetch; Finch Connect-session / sandbox / token exchange) but
# the module never defined one — so those lines raised NameError at request
# time, replacing a logged upstream error with a 500. Same class of bug as the
# IR NameErrors that test_review_fixes.py locks down.
from app.matcha.routes.integrations.provisioning._models import *  # noqa: F401,F403
from app.matcha.routes.integrations.provisioning._shared import (  # noqa: F401
    _json_object, _coerce_bool, _split_comma_list, _run_payload,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _hris_connection_status_payload(row) -> HRISConnectionStatus:
    if not row:
        return HRISConnectionStatus(
            connected=False,
            status="disconnected",
        )

    config = _json_object(row["config"])
    secrets = _json_object(row["secrets"])
    status_value = row["status"] or "disconnected"
    return HRISConnectionStatus(
        connected=status_value == "connected",
        status=status_value,
        mode=config.get("mode"),
        base_url=config.get("base_url"),
        gusto_company_id=config.get("gusto_company_id"),
        has_client_secret=bool(secrets.get("client_secret")),
        auto_sync_on_schedule=_coerce_bool(
            config.get("auto_sync_on_schedule"), False
        ),
        sync_interval_hours=config.get("sync_interval_hours", 24),
        last_tested_at=row["last_tested_at"],
        last_error=row["last_error"],
        updated_at=row["updated_at"],
    )
@router.get("/hris/status", response_model=HRISConnectionStatus,
            dependencies=[Depends(require_any_feature("hris_gusto", "hris_finch", "hris_import"))])
async def get_hris_connection_status(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM integration_connections WHERE company_id = $1 AND provider = $2",
            company_id,
            PROVIDER_HRIS,
        )
        payload = _hris_connection_status_payload(row)

        # Attach last sync info
        if row:
            last_sync = await conn.fetchrow(
                """SELECT completed_at, total_records FROM hris_sync_runs
                   WHERE connection_id = $1 AND status = 'completed'
                   ORDER BY completed_at DESC LIMIT 1""",
                row["id"],
            )
            if last_sync:
                payload.last_sync_at = last_sync["completed_at"]
                payload.total_synced_employees = last_sync["total_records"] or 0

    return payload
@router.post("/hris/connect", response_model=HRISConnectionStatus,
             dependencies=[Depends(require_any_feature("hris_gusto", "hris_finch", "hris_import"))])
async def connect_hris(
    request: HRISConnectionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)

    # Finch is OAuth-only (access_token minted by Finch Connect) — this endpoint
    # only stores client credentials, so a mode='finch' connection saved here
    # would fail auth on every sync. Point at the real flows instead.
    if request.mode == "finch":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Finch connections are established via Finch Connect — use "
                "GET /provisioning/hris/finch/authorize (or POST "
                "/provisioning/hris/finch/sandbox for sandbox testing)."
            ),
        )

    config = {
        "mode": request.mode,
        "base_url": request.base_url,
        "client_id": request.client_id,
        "gusto_company_id": request.gusto_company_id,
        "auto_sync_on_schedule": request.auto_sync_on_schedule,
        "sync_interval_hours": request.sync_interval_hours,
    }

    secrets_payload: dict = {}
    if request.client_secret:
        secrets_payload["client_secret"] = encrypt_secret(request.client_secret.strip())

    # Test connection if requested
    test_status = "connected"
    test_error = None
    if request.test_connection and request.mode != "mock":
        from app.matcha.services.hris_service import get_hris_service, GustoHRISService
        service = get_hris_service(request.mode)
        test_secrets = {
            "client_id": request.client_id or "",
            "client_secret": request.client_secret or "",
        }
        ok, err = await service.test_connection(config, test_secrets)
        if not ok:
            test_status = "error"
            test_error = err
        elif isinstance(service, GustoHRISService) and not config.get("gusto_company_id"):
            # Auto-discover company UUID from /v1/me so user doesn't need to look it up
            uuid, discover_err = await service.resolve_company_uuid(config, test_secrets)
            if uuid:
                config["gusto_company_id"] = uuid
            elif discover_err:
                test_status = "error"
                test_error = f"Connected but could not determine company: {discover_err}"

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO integration_connections
                (company_id, provider, status, config, secrets, last_tested_at, last_error, created_by, updated_by)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, NOW(), $6, $7, $7)
            ON CONFLICT (company_id, provider) DO UPDATE SET
                status = EXCLUDED.status,
                config = EXCLUDED.config,
                secrets = CASE
                    WHEN EXCLUDED.secrets != '{}'::jsonb THEN EXCLUDED.secrets
                    ELSE integration_connections.secrets
                END,
                last_tested_at = NOW(),
                last_error = EXCLUDED.last_error,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING *
            """,
            company_id,
            PROVIDER_HRIS,
            test_status,
            json.dumps(config),
            json.dumps(secrets_payload),
            test_error,
            current_user.id,
        )

    return _hris_connection_status_payload(row)
@router.post("/hris/disconnect",
             dependencies=[Depends(require_any_feature("hris_gusto", "hris_finch", "hris_import"))])
async def disconnect_hris(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM integration_connections WHERE company_id = $1 AND provider = $2",
            company_id,
            PROVIDER_HRIS,
        )
    return {"status": "disconnected"}
@router.post("/hris/sync", response_model=HRISSyncRunResponse,
             dependencies=[Depends(require_any_feature("hris_gusto", "hris_finch", "hris_import"))])
async def trigger_hris_sync(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Trigger a manual HRIS sync — fetches all employees from the HRIS and imports them."""
    company_id = await get_client_company_id(current_user)

    from app.matcha.services.hris_sync_orchestrator import start_hris_sync
    try:
        result = await start_hris_sync(
            company_id=company_id,
            triggered_by=current_user.id,
            trigger_source="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return HRISSyncRunResponse(
        sync_run_id=result["run_id"],
        status=result["status"],
        total_records=result.get("total_records", 0),
        created_count=result.get("created_count", 0),
        updated_count=result.get("updated_count", 0),
        skipped_count=result.get("skipped_count", 0),
        error_count=result.get("error_count", 0),
        errors=result.get("errors") or [],
        started_at=result.get("started_at"),
        completed_at=result.get("completed_at"),
        created_at=result.get("created_at"),
    )
@router.get("/hris/sync/history",
            dependencies=[Depends(require_any_feature("hris_gusto", "hris_finch", "hris_import"))])
async def get_hris_sync_history(
    current_user: CurrentUser = Depends(require_admin_or_client),
    limit: int = Query(default=20, ge=1, le=100),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, status, trigger_source, triggered_by,
                   total_records, created_count, updated_count, skipped_count, error_count,
                   errors, last_error, started_at, completed_at, created_at
            FROM hris_sync_runs
            WHERE company_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            company_id,
            limit,
        )
    return [
        HRISSyncRunResponse(
            sync_run_id=row["id"],
            status=row["status"],
            total_records=row["total_records"] or 0,
            created_count=row["created_count"] or 0,
            updated_count=row["updated_count"] or 0,
            skipped_count=row["skipped_count"] or 0,
            error_count=row["error_count"] or 0,
            errors=row["errors"] if isinstance(row["errors"], list) else [],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
@router.get("/hris/sync/{run_id}", response_model=HRISSyncRunResponse,
            dependencies=[Depends(require_any_feature("hris_gusto", "hris_finch", "hris_import"))])
async def get_hris_sync_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM hris_sync_runs WHERE id = $1 AND company_id = $2",
            run_id,
            company_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return HRISSyncRunResponse(
        sync_run_id=row["id"],
        status=row["status"],
        total_records=row["total_records"] or 0,
        created_count=row["created_count"] or 0,
        updated_count=row["updated_count"] or 0,
        skipped_count=row["skipped_count"] or 0,
        error_count=row["error_count"] or 0,
        errors=row["errors"] if isinstance(row["errors"], list) else [],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )
GUSTO_OAUTH_CLIENT_ID = os.getenv("GUSTO_OAUTH_CLIENT_ID")
GUSTO_OAUTH_CLIENT_SECRET = os.getenv("GUSTO_OAUTH_CLIENT_SECRET")
GUSTO_OAUTH_REDIRECT_URI = os.getenv("GUSTO_OAUTH_REDIRECT_URI")
def _require_gusto_oauth_config() -> None:
    """Raise 503 unless the Gusto OAuth env vars are present.

    Mirrors _require_finch_oauth_config. This used to be a module-level `raise`,
    which made an *optional* integration's credentials a hard requirement for
    importing app.matcha.routes at all — so every unit test touching any route
    module had to fake Gusto creds, and a deploy missing them died at import
    with no clue which of the ~30 routers was at fault. Finch, the primary HRIS
    path, never did this; Gusto now matches it.
    """
    missing = [
        name
        for name, value in (
            ("GUSTO_OAUTH_CLIENT_ID", GUSTO_OAUTH_CLIENT_ID),
            ("GUSTO_OAUTH_CLIENT_SECRET", GUSTO_OAUTH_CLIENT_SECRET),
            ("GUSTO_OAUTH_REDIRECT_URI", GUSTO_OAUTH_REDIRECT_URI),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Gusto OAuth is not configured (missing {', '.join(missing)})",
        )
GUSTO_BASE_URL = os.getenv("GUSTO_BASE_URL", "https://api.gusto-demo.com")
GUSTO_AUTHORIZE_URL = f"{GUSTO_BASE_URL}/oauth/authorize"
GUSTO_TOKEN_URL = f"{GUSTO_BASE_URL}/oauth/token"
GUSTO_ME_URL = f"{GUSTO_BASE_URL}/v1/me"
@router.get("/hris/authorize")
async def authorize_gusto_oauth(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return Gusto OAuth authorization URL."""
    _require_gusto_oauth_config()
    company_id = await get_client_company_id(current_user)

    # Check feature flag
    async with get_connection() as conn:
        company = await conn.fetchrow(
            "SELECT enabled_features FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        from app.core.feature_flags import merge_company_features
        features = merge_company_features(company["enabled_features"])
        # Gusto-direct path: gated by hris_gusto (or the legacy hris_import umbrella).
        if not (features.get("hris_gusto") or features.get("hris_import")):
            raise HTTPException(status_code=403, detail="Gusto HRIS import not enabled")

    state = secrets.token_urlsafe(32)

    # Store state in DB for CSRF validation
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO oauth_states (state, company_id, created_at) VALUES ($1, $2, NOW())",
            state,
            company_id,
        )

    params = {
        "client_id": GUSTO_OAUTH_CLIENT_ID,
        "redirect_uri": GUSTO_OAUTH_REDIRECT_URI,
        "response_type": "code",
        # companies:read covers /v1/companies/{id}/locations for the business-
        # locations ingest; older tokens without it degrade to no location data.
        "scope": "companies:read employees:read jobs:read compensations:read employee_addresses:read",
        "state": state,
    }
    oauth_url = f"{GUSTO_AUTHORIZE_URL}?{urlencode(params)}"
    return {"oauth_url": oauth_url}
@router.get("/hris/callback")
async def gusto_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle Gusto OAuth callback — exchange code for token."""
    _require_gusto_oauth_config()
    # Validate state
    async with get_connection() as conn:
        oauth_state = await conn.fetchrow(
            "SELECT company_id FROM oauth_states WHERE state = $1 AND created_at > NOW() - INTERVAL '10 minutes'",
            state,
        )
        if not oauth_state:
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        company_id = oauth_state["company_id"]

        # Exchange code for token
        credentials = base64.b64encode(f"{GUSTO_OAUTH_CLIENT_ID}:{GUSTO_OAUTH_CLIENT_SECRET}".encode()).decode()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    GUSTO_TOKEN_URL,
                    headers={"Authorization": f"Basic {credentials}"},
                    data={"grant_type": "authorization_code", "code": code, "redirect_uri": GUSTO_OAUTH_REDIRECT_URI},
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Gusto token exchange failed: {resp.status_code}")
                token_data = resp.json()
                access_token = token_data["access_token"]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Token exchange error: {str(e)}")

        # Get company UUID from /v1/companies (list accessible companies)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{GUSTO_BASE_URL}/v1/companies",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code != 200:
                    logger.error(f"[Gusto /v1/companies] {resp.status_code}: {resp.text}")
                    raise HTTPException(status_code=400, detail=f"Failed to get companies: {resp.status_code}")
                companies_data = resp.json()
                # Handle both list and dict response
                if isinstance(companies_data, list):
                    companies = companies_data
                elif isinstance(companies_data, dict):
                    companies = companies_data.get("companies", [])
                else:
                    companies = []
                if not companies:
                    raise HTTPException(status_code=400, detail="No company found in Gusto account")
                gusto_company_id = companies[0].get("uuid") or companies[0].get("id")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to get company UUID: {str(e)}")

        # Store in DB
        config = {
            "mode": "gusto",
            "gusto_company_id": gusto_company_id,
        }
        secrets_payload = {
            "access_token": encrypt_secret(access_token),
        }

        await conn.execute(
            """
            INSERT INTO integration_connections
                (company_id, provider, status, config, secrets, last_tested_at, created_by, updated_by)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, NOW(), $6, $6)
            ON CONFLICT (company_id, provider) DO UPDATE SET
                status = EXCLUDED.status,
                config = EXCLUDED.config,
                secrets = EXCLUDED.secrets,
                last_tested_at = NOW(),
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            """,
            company_id,
            PROVIDER_HRIS,
            "connected",
            json.dumps(config),
            json.dumps(secrets_payload),
            None,  # created_by — anonymous callback
        )

        # Clean up state
        await conn.execute("DELETE FROM oauth_states WHERE state = $1", state)

    # Redirect to frontend success page
    return RedirectResponse(url="/app/employees?hris=connected")
GUSTO_WEBHOOK_SECRET = os.getenv("GUSTO_WEBHOOK_SECRET", "")
# When true, unsigned or bad-signature events are rejected (fail closed). Default
# off so the live webhook keeps working until the signing scheme is verified in prod.
GUSTO_WEBHOOK_REQUIRE_SIGNATURE = os.getenv("GUSTO_WEBHOOK_REQUIRE_SIGNATURE", "").lower() == "true"
import logging as _logging
_whlog = _logging.getLogger(__name__)
@router.get("/hris/webhook/gusto/token")
async def get_gusto_verification_token(
    current_user: CurrentUser = Depends(require_admin),
):
    """Return the most-recent Gusto webhook verification token (setup convenience).

    Platform-admin only: the Gusto webhook is app-level (one subscription for the
    whole partner app, verified once by the operator), and the token table is not
    company-scoped — so this must not be exposed to per-tenant client admins.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT verification_token FROM gusto_webhook_tokens
               ORDER BY created_at DESC LIMIT 1""",
        )
    return {"verification_token": row["verification_token"] if row else None}
@router.post("/hris/webhook/gusto")
async def gusto_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Gusto webhook events and sync changes to Matcha."""
    from app.matcha.services.hris_sync_orchestrator import start_hris_sync
    body = await request.body()

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Subscription verification: Gusto POSTs a verification_token (no event_type)
    # before any secret is established. Capture it so the user can paste it into
    # Gusto's "Verify your subscription" form. Skip signature check here.
    verification_token = payload.get("verification_token")
    if verification_token and not payload.get("event_type"):
        _whlog.warning(f"[Gusto Webhook] VERIFICATION TOKEN: {verification_token}")
        async with get_connection() as conn:
            await conn.execute(
                """INSERT INTO gusto_webhook_tokens (verification_token, gusto_company_uuid, created_at)
                   VALUES ($1, $2, NOW())""",
                verification_token,
                payload.get("company_uuid"),  # may be null; best-effort
            )
        return {"received": True}

    # Signature verification. The header name + HMAC scheme below have never been
    # exercised in prod (secret was empty), so verification is advisory until proven:
    # mismatches are logged but accepted unless GUSTO_WEBHOOK_REQUIRE_SIGNATURE=true.
    # Rollout: set the secret → watch logs for "signature mismatch" → once a real
    # signed delivery verifies clean, flip GUSTO_WEBHOOK_REQUIRE_SIGNATURE=true to
    # fully fail closed (forged terminations rejected).
    if GUSTO_WEBHOOK_SECRET:
        sig = request.headers.get("X-Gusto-Signature", "")
        expected = hmac.new(
            GUSTO_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            if GUSTO_WEBHOOK_REQUIRE_SIGNATURE:
                raise HTTPException(status_code=400, detail="Invalid webhook signature")
            _whlog.warning(
                "[Gusto Webhook] signature mismatch — accepting (REQUIRE_SIGNATURE off). "
                "Verify header name/scheme against Gusto docs before enabling enforcement."
            )
    elif GUSTO_WEBHOOK_REQUIRE_SIGNATURE:
        _whlog.error("[Gusto Webhook] REQUIRE_SIGNATURE set but no secret configured — rejecting event")
        raise HTTPException(status_code=503, detail="Webhook signing secret not configured")
    else:
        _whlog.warning("[Gusto Webhook] no signing secret configured — accepting unsigned event")

    event_type = payload.get("event_type", "")
    entity_uuid = payload.get("entity_uuid") or payload.get("employee_uuid")
    # Gusto carries the company in resource_uuid (resource_type=Company);
    # fall back to other shapes defensively.
    company_uuid = (
        payload.get("resource_uuid")
        or payload.get("company_uuid")
        or (payload.get("resources") or [{}])[0].get("uuid")
    )

    # Log identifiers only — never the full payload (contains employee PII).
    _whlog.info(f"[Gusto Webhook] event={event_type} entity={entity_uuid} company={company_uuid}")

    if not entity_uuid or not company_uuid:
        return {"received": True}

    # Find the Matcha company that owns this Gusto connection
    async with get_connection() as conn:
        conn_row = await conn.fetchrow(
            """SELECT company_id FROM integration_connections
               WHERE provider = $1 AND config->>'gusto_company_id' = $2""",
            PROVIDER_HRIS,
            str(company_uuid),
        )
        if not conn_row:
            _whlog.warning(f"[Gusto Webhook] No connection found for company_uuid={company_uuid}")
            return {"received": True}

        matcha_company_id = conn_row["company_id"]

        if event_type in ("employee.terminated", "employee.termination_effective", "employee.deleted"):
            # Mark employee inactive in Matcha — scoped to the owning org
            result = await conn.execute(
                """UPDATE employees
                   SET employment_status = 'terminated', updated_at = NOW()
                   WHERE hris_id = $1 AND org_id = $2""",
                str(entity_uuid),
                matcha_company_id,
            )
            _whlog.info(f"[Gusto Webhook] Terminated employee hris_id={entity_uuid} result={result}")

        elif event_type in ("employee.created", "employee.updated", "employee.rehired"):
            # Re-sync via FastAPI BackgroundTasks (asyncio.create_task would be
            # cancelled when the response returns). No user → triggered_by=None.
            background_tasks.add_task(
                start_hris_sync,
                company_id=matcha_company_id,
                triggered_by=None,
                trigger_source="api",
            )
            _whlog.info(f"[Gusto Webhook] Queued re-sync for company={matcha_company_id}")

    return {"received": True}
FINCH_CLIENT_ID = os.getenv("FINCH_CLIENT_ID")
FINCH_CLIENT_SECRET = os.getenv("FINCH_CLIENT_SECRET")
FINCH_OAUTH_REDIRECT_URI = os.getenv("FINCH_OAUTH_REDIRECT_URI")
# Connect-session sandbox mode. Blank = live providers (real employer payroll).
# "provider" = connect to a provider's TEST environment (e.g. Gusto demo) through
# the real Connect UI — the way to rehearse onboarding a customer end-to-end.
# "finch" = Finch's own mock provider. Only forwarded to /connect/sessions when set.
FINCH_SANDBOX = (os.getenv("FINCH_SANDBOX") or "").strip()
FINCH_API_BASE_URL = os.getenv("FINCH_BASE_URL", "https://api.tryfinch.com")
FINCH_TOKEN_URL = f"{FINCH_API_BASE_URL}/auth/token"
FINCH_SESSIONS_URL = f"{FINCH_API_BASE_URL}/connect/sessions"
# Products requested at Connect time — must cover directory + individual +
# employment so FinchHRISService.fetch_workers can hydrate every record.
FINCH_PRODUCTS = os.getenv("FINCH_PRODUCTS", "company directory individual employment")
async def _finch_products_for_company(company_id) -> list[str]:
    """Products to request at Finch connect time for this company.

    Base set (FINCH_PRODUCTS) + the `benefits` product **only** when the company
    has the `hris_deductions` feature on — so deductions-write clients get a
    benefits-scoped token while everyone else connects unchanged. Never request
    benefits globally: an unsupported provider (e.g. Square) rejects it at connect.
    """
    from app.core.feature_flags import merge_company_features
    products = [p for p in FINCH_PRODUCTS.split() if p]
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1",
            company_id,
        )
    if row:
        feats = merge_company_features(row["enabled_features"], row["signup_source"])
        if feats.get("hris_deductions") and "benefits" not in products:
            products.append("benefits")
    return products
def _require_finch_oauth_config() -> None:
    """Raise 503 unless the Finch Connect env vars are present."""
    missing = [
        name
        for name, value in (
            ("FINCH_CLIENT_ID", FINCH_CLIENT_ID),
            ("FINCH_CLIENT_SECRET", FINCH_CLIENT_SECRET),
            ("FINCH_OAUTH_REDIRECT_URI", FINCH_OAUTH_REDIRECT_URI),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Finch Connect is not configured (missing {', '.join(missing)})",
        )
@router.get("/hris/finch/authorize",
            dependencies=[Depends(require_any_feature("hris_finch", "hris_import"))])
async def authorize_finch_oauth(
    provider: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a Finch Connect session for this company and return its connect URL.

    Uses the Connect Sessions API (POST /connect/sessions, Basic auth) — the current
    flow, and the only one that supports `sandbox="provider"` for rehearsing a real
    customer onboarding against a provider's test environment. The legacy
    `connect.tryfinch.com/authorize?client_id=…` URL is deprecated.

    `provider` (optional) pre-selects an integration (e.g. "gusto") and skips the
    Connect picker — handy for a scripted provider-sandbox test.
    """
    _require_finch_oauth_config()
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1", company_id
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        customer_name = company["name"] or f"Company {company_id}"

    state = secrets.token_urlsafe(32)

    body: dict = {
        "customer_id": str(company_id),
        "customer_name": customer_name,
        # Sessions API wants an array (the legacy authorize URL took a space string).
        # Adds `benefits` only when the company has hris_deductions enabled.
        "products": await _finch_products_for_company(company_id),
        "redirect_uri": FINCH_OAUTH_REDIRECT_URI,
    }
    if FINCH_SANDBOX:
        body["sandbox"] = FINCH_SANDBOX
    if provider:
        body["integration"] = {"provider": provider}

    basic = base64.b64encode(f"{FINCH_CLIENT_ID}:{FINCH_CLIENT_SECRET}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                FINCH_SESSIONS_URL,
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code not in (200, 201):
                logger.error(f"[Finch Connect Session] {resp.status_code}: {resp.text[:300]}")
                raise HTTPException(status_code=400, detail=f"Finch Connect session failed: {resp.status_code}")
            connect_url = resp.json()["connect_url"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Finch Connect session error: {str(e)}")

    # Persist state only after the session is created, then append it to the connect
    # URL for CSRF validation on the callback. Verified against Finch docs (2026-07):
    # Connect's authorize flow passes `state` through and echoes it back to the
    # redirect_uri alongside `code` (the Connect SDK's onSuccess receives {code, state}).
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO oauth_states (state, company_id, created_at) VALUES ($1, $2, NOW())",
            state,
            company_id,
        )
    sep = "&" if "?" in connect_url else "?"
    oauth_url = f"{connect_url}{sep}{urlencode({'state': state})}"
    return {"oauth_url": oauth_url}
@router.post("/hris/finch/sandbox",
             dependencies=[Depends(require_any_feature("hris_finch", "hris_import"))])
async def create_finch_sandbox_connection(
    request: FinchSandboxConnectRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Mint a Finch **sandbox** connection and store its token — no OAuth redirect.

    Finch Sandbox doesn't support the Connect redirect flow, so testing goes through
    POST /sandbox/connections (HTTP Basic auth with client_id:client_secret). The
    returned access_token works directly against /employer/* and lets `/hris/sync`
    pull Finch's mock employees to validate FinchHRISService field paths.
    """
    if not (FINCH_CLIENT_ID and FINCH_CLIENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Finch is not configured (missing FINCH_CLIENT_ID / FINCH_CLIENT_SECRET)",
        )
    company_id = await get_client_company_id(current_user)

    basic = base64.b64encode(f"{FINCH_CLIENT_ID}:{FINCH_CLIENT_SECRET}".encode()).decode()
    products = await _finch_products_for_company(company_id)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{FINCH_API_BASE_URL}/sandbox/connections",
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
                json={
                    "provider_id": request.provider_id,
                    "products": products,
                    "employee_size": request.employee_size,
                },
            )
            if resp.status_code not in (200, 201):
                logger.error(f"[Finch Sandbox] {resp.status_code}: {resp.text[:300]}")
                raise HTTPException(status_code=400, detail=f"Finch sandbox connection failed: {resp.status_code}")
            data = resp.json()
            access_token = data["access_token"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Finch sandbox error: {str(e)}")

    config = {
        "mode": "finch",
        "finch_connection_id": data.get("connection_id"),
        "finch_account_id": data.get("account_id"),
        "finch_company_id": data.get("company_id"),
        "finch_provider_id": data.get("provider_id") or request.provider_id,
        "finch_products": data.get("products") or products,
        "finch_sandbox": True,
    }
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO integration_connections
                (company_id, provider, status, config, secrets, last_tested_at, created_by, updated_by)
            VALUES ($1, $2, 'connected', $3::jsonb, $4::jsonb, NOW(), $5, $5)
            ON CONFLICT (company_id, provider) DO UPDATE SET
                status = 'connected',
                config = EXCLUDED.config,
                secrets = EXCLUDED.secrets,
                last_tested_at = NOW(),
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            RETURNING *
            """,
            company_id,
            PROVIDER_HRIS,
            json.dumps(config),
            json.dumps({"access_token": encrypt_secret(access_token)}),
            current_user.id,
        )

    return _hris_connection_status_payload(row)
# ---------------------------------------------------------------------------
# Finch benefits / deductions WRITE
#
# Matcha -> Finch -> payroll provider. Only providers Finch supports for
# deductions-write expose these (QuickBooks, Gusto, ADP, …). Square Payroll does
# NOT. Writes are async — POST returns a job_id; poll the job endpoint.
# ---------------------------------------------------------------------------
async def _load_finch_for_benefits(company_id):
    """Load the company's HRIS connection for a benefits write; return (config, secrets, service).

    Raises 404 if not connected, 400 if the connection isn't a Finch connection
    (benefits write is routed through Finch's Deductions product only).
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT config, secrets FROM integration_connections WHERE company_id = $1 AND provider = $2",
            company_id, PROVIDER_HRIS,
        )
    if not row:
        raise HTTPException(status_code=404, detail="HRIS is not connected for this company")

    config = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"])
    if config.get("mode") != "finch":
        raise HTTPException(
            status_code=400,
            detail="Benefits write is available only on Finch-connected HRIS.",
        )
    secrets_raw = row["secrets"] if isinstance(row["secrets"], dict) else json.loads(row["secrets"] or "{}")
    secrets = {}
    for key, value in secrets_raw.items():
        try:
            secrets[key] = decrypt_secret(value)
        except Exception:
            secrets[key] = value

    from app.matcha.services.finch_service import FinchHRISService
    return config, secrets, FinchHRISService()
@router.get("/hris/benefits/meta",
            dependencies=[Depends(require_feature("hris_deductions"))])
async def get_hris_benefit_meta(current_user: CurrentUser = Depends(require_admin_or_client)):
    """List the benefit/deduction types the connected provider supports (the write schema)."""
    company_id = await get_client_company_id(current_user)
    config, secrets, service = await _load_finch_for_benefits(company_id)
    try:
        return await service.get_benefit_meta(config, secrets)
    except HRISProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/hris/benefits",
            dependencies=[Depends(require_feature("hris_deductions"))])
async def list_hris_benefits(current_user: CurrentUser = Depends(require_admin_or_client)):
    """List company-level benefits already configured in the connected provider."""
    company_id = await get_client_company_id(current_user)
    config, secrets, service = await _load_finch_for_benefits(company_id)
    try:
        return await service.list_benefits(config, secrets)
    except HRISProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.post("/hris/benefits",
             dependencies=[Depends(require_feature("hris_deductions"))])
async def create_hris_benefit(
    request: BenefitCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a company-level benefit/deduction in the provider via Finch.

    Async: returns {benefit_id, job_id}. Poll GET /hris/benefits/job/{job_id}
    until complete; the benefit is then readable via GET /hris/benefits.
    """
    company_id = await get_client_company_id(current_user)
    config, secrets, service = await _load_finch_for_benefits(company_id)
    try:
        result = await service.create_benefit(
            config, secrets,
            benefit_type=request.type, description=request.description, frequency=request.frequency,
        )
    except HRISProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
@router.get("/hris/benefits/job/{job_id}",
            dependencies=[Depends(require_feature("hris_deductions"))])
async def get_hris_benefit_job(
    job_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Poll an async Finch benefits-write job."""
    company_id = await get_client_company_id(current_user)
    config, secrets, service = await _load_finch_for_benefits(company_id)
    try:
        return await service.get_job(config, secrets, job_id)
    except HRISProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/hris/finch/callback")
async def finch_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle the Finch Connect callback — exchange the code for an access token."""
    _require_finch_oauth_config()

    async with get_connection() as conn:
        oauth_state = await conn.fetchrow(
            "SELECT company_id FROM oauth_states WHERE state = $1 AND created_at > NOW() - INTERVAL '10 minutes'",
            state,
        )
        if not oauth_state:
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        company_id = oauth_state["company_id"]

        # Exchange the authorization code. Finch's /auth/token takes a JSON body
        # with the client credentials inline (no Basic auth, unlike Gusto).
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    FINCH_TOKEN_URL,
                    json={
                        "client_id": FINCH_CLIENT_ID,
                        "client_secret": FINCH_CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": FINCH_OAUTH_REDIRECT_URI,
                    },
                )
                if resp.status_code != 200:
                    logger.error(f"[Finch Token] {resp.status_code}: {resp.text[:300]}")
                    raise HTTPException(status_code=400, detail=f"Finch token exchange failed: {resp.status_code}")
                token_data = resp.json()
                access_token = token_data["access_token"]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Finch token exchange error: {str(e)}")

        # Finch tokens are per-connection — the token itself scopes to one employer,
        # so no company UUID lookup is needed (unlike Gusto). Persist provider/account
        # identifiers from the token response for traceability.
        config = {
            "mode": "finch",
            "finch_connection_id": token_data.get("connection_id"),
            "finch_account_id": token_data.get("account_id"),
            "finch_company_id": token_data.get("company_id"),
            "finch_provider_id": token_data.get("provider_id"),
            "finch_products": token_data.get("products"),
        }
        secrets_payload = {
            "access_token": encrypt_secret(access_token),
        }

        await conn.execute(
            """
            INSERT INTO integration_connections
                (company_id, provider, status, config, secrets, last_tested_at, created_by, updated_by)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, NOW(), $6, $6)
            ON CONFLICT (company_id, provider) DO UPDATE SET
                status = EXCLUDED.status,
                config = EXCLUDED.config,
                secrets = EXCLUDED.secrets,
                last_tested_at = NOW(),
                updated_at = NOW(),
                updated_by = EXCLUDED.updated_by
            """,
            company_id,
            PROVIDER_HRIS,
            "connected",
            json.dumps(config),
            json.dumps(secrets_payload),
            None,  # created_by — anonymous callback
        )

        await conn.execute("DELETE FROM oauth_states WHERE state = $1", state)

    return RedirectResponse(url="/app/employees?hris=connected")
