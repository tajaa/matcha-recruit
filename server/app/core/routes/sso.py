"""SAML 2.0 SSO routes for enterprise single sign-on."""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from typing import Optional

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

from ...config import get_settings
from ...database import get_connection
from ..services.auth import create_access_token, create_refresh_token
from ..dependencies import require_admin
from ...matcha.dependencies import require_admin_or_client

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Pydantic models ─────────────────────────────────────────────────────────

class SSOConfigCreate(BaseModel):
    idp_entity_id: str
    idp_sso_url: str
    idp_x509_cert: str
    email_domain: str
    default_role: str = "employee"
    auto_provision: bool = True
    enabled: bool = False


class SSOConfigFromMetadata(BaseModel):
    metadata_url: str
    email_domain: str
    default_role: str = "employee"
    auto_provision: bool = True
    enabled: bool = False


class SSOConfigResponse(BaseModel):
    id: UUID
    company_id: UUID
    enabled: bool
    idp_entity_id: str
    idp_sso_url: str
    email_domain: str
    default_role: str
    auto_provision: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _prepare_saml_request(request: Request) -> dict:
    """Convert FastAPI request to the dict format python3-saml expects."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "http")
    server_port = request.url.port or (443 if forwarded_proto == "https" else 80)

    return {
        "https": "on" if forwarded_proto == "https" else "off",
        "http_host": request.headers.get("host", request.url.hostname),
        "server_port": server_port,
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": {},
    }


def _build_saml_settings(idp_entity_id: str, idp_sso_url: str, idp_x509_cert: str) -> dict:
    """Build the settings dict for python3-saml from stored config + app settings."""
    settings = get_settings()

    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": settings.saml_sp_entity_id,
            "assertionConsumerService": {
                "url": settings.saml_sp_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": idp_entity_id,
            "singleSignOnService": {
                "url": idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": idp_x509_cert,
        },
        "security": {
            "authnRequestsSigned": False,
            "wantAssertionsSigned": True,
            "wantNameIdEncrypted": False,
        },
    }


async def _get_sso_config_by_domain(domain: str):
    """Look up an enabled SSO config by email domain."""
    async with get_connection() as conn:
        return await conn.fetchrow(
            """SELECT c.*, co.name as company_name
               FROM company_sso_configs c
               JOIN companies co ON co.id = c.company_id
               WHERE c.email_domain = $1 AND c.enabled = true""",
            domain.lower(),
        )


# ── Public SSO endpoints ────────────────────────────────────────────────────

@router.get("/metadata")
async def sp_metadata():
    """Return SAML Service Provider metadata XML.

    Hand this URL to clients so they can configure their IdP (Okta, Azure AD, etc.).
    """
    settings = get_settings()

    saml_settings = _build_saml_settings(
        idp_entity_id="placeholder",
        idp_sso_url="placeholder",
        idp_x509_cert="placeholder",
    )

    # python3-saml can generate SP metadata even without valid IdP config
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    saml = OneLogin_Saml2_Settings(saml_settings, sp_validation_only=True)
    metadata = saml.get_sp_metadata()
    errors = saml.validate_metadata(metadata)

    if errors:
        logger.error("SP metadata validation errors: %s", errors)
        raise HTTPException(status_code=500, detail="Failed to generate SP metadata")

    return Response(content=metadata, media_type="application/xml")


@router.get("/login")
async def sso_login(request: Request, email: str):
    """Initiate SAML login.

    Looks up the company SSO config by email domain and redirects to the IdP.
    """
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email format")

    domain = email.split("@")[1].lower()
    config = await _get_sso_config_by_domain(domain)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="SSO is not configured for this email domain",
        )

    saml_settings = _build_saml_settings(
        idp_entity_id=config["idp_entity_id"],
        idp_sso_url=config["idp_sso_url"],
        idp_x509_cert=config["idp_x509_cert"],
    )

    req = _prepare_saml_request(request)
    auth = OneLogin_Saml2_Auth(req, saml_settings)
    redirect_url = auth.login()

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/acs")
async def assertion_consumer_service(request: Request):
    """SAML Assertion Consumer Service.

    The IdP posts the SAML response here after the user authenticates.
    We validate it, find or create the user, issue JWTs, and redirect to the frontend.
    """
    settings = get_settings()
    form_data = await request.form()
    saml_response = form_data.get("SAMLResponse")

    if not saml_response:
        raise HTTPException(status_code=400, detail="Missing SAMLResponse")

    # We need to figure out which IdP config to use. The SAMLResponse contains
    # the IdP entity ID in the Issuer element, so we look it up.
    # First, decode enough to get the issuer without full validation.
    from onelogin.saml2.response import OneLogin_Saml2_Response
    from onelogin.saml2.xml_utils import OneLogin_Saml2_XML
    import base64

    try:
        raw_xml = base64.b64decode(saml_response)
        doc = OneLogin_Saml2_XML.to_etree(raw_xml)
        ns = {"saml": "urn:oasis:names:tc:SAML:2.0:assertion"}
        issuer_el = doc.find(".//saml:Issuer", ns)
        issuer = issuer_el.text if issuer_el is not None else None
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SAML response")

    if not issuer:
        raise HTTPException(status_code=400, detail="No Issuer in SAML response")

    # Look up the SSO config by IdP entity ID
    async with get_connection() as conn:
        config = await conn.fetchrow(
            """SELECT c.*, co.name as company_name
               FROM company_sso_configs c
               JOIN companies co ON co.id = c.company_id
               WHERE c.idp_entity_id = $1 AND c.enabled = true""",
            issuer,
        )

    if not config:
        raise HTTPException(status_code=403, detail="Unknown or disabled IdP")

    # Now validate the full SAML response
    saml_settings = _build_saml_settings(
        idp_entity_id=config["idp_entity_id"],
        idp_sso_url=config["idp_sso_url"],
        idp_x509_cert=config["idp_x509_cert"],
    )

    req = _prepare_saml_request(request)
    req["post_data"] = {"SAMLResponse": saml_response}
    relay_state = form_data.get("RelayState")
    if relay_state:
        req["post_data"]["RelayState"] = relay_state

    auth = OneLogin_Saml2_Auth(req, saml_settings)
    auth.process_response()

    errors = auth.get_errors()
    if errors:
        logger.error("SAML validation errors: %s, reason: %s", errors, auth.get_last_error_reason())
        raise HTTPException(status_code=403, detail="SAML validation failed")

    if not auth.is_authenticated():
        raise HTTPException(status_code=403, detail="Authentication failed")

    # Extract user info from SAML attributes
    nameid = auth.get_nameid()  # Usually the email
    attributes = auth.get_attributes()

    email = nameid
    # Some IdPs put email in attributes instead of NameID
    if not email or "@" not in email:
        email = (
            attributes.get("email", [None])[0]
            or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", [None])[0]
        )

    if not email:
        raise HTTPException(status_code=400, detail="No email in SAML response")

    email = email.lower().strip()

    # Extract name if available
    first_name = (
        attributes.get("firstName", [None])[0]
        or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname", [None])[0]
        or "SSO"
    )
    last_name = (
        attributes.get("lastName", [None])[0]
        or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname", [None])[0]
        or "User"
    )

    # Find or create the user
    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, role, is_active FROM users WHERE lower(email) = $1",
            email,
        )

        if user and not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account is disabled")

        if not user:
            if not config["auto_provision"]:
                raise HTTPException(
                    status_code=403,
                    detail="Account not found. Contact your administrator to be provisioned.",
                )

            # Auto-provision: create user with the configured default role
            role = config["default_role"]
            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role, is_active)
                   VALUES ($1, $2, $3, true)
                   RETURNING id, email, role, is_active""",
                email,
                "__SSO_NO_PASSWORD__",  # SSO users don't have passwords
                role,
            )

            # If role is employee or client, link to the company
            if role == "employee":
                await conn.execute(
                    """INSERT INTO employees (user_id, company_id, first_name, last_name, email, status)
                       VALUES ($1, $2, $3, $4, $5, 'active')
                       ON CONFLICT DO NOTHING""",
                    user["id"], config["company_id"], first_name, last_name, email,
                )
            elif role == "client":
                await conn.execute(
                    """INSERT INTO clients (user_id, company_id, first_name, last_name)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT DO NOTHING""",
                    user["id"], config["company_id"], first_name, last_name,
                )

            logger.info("SSO auto-provisioned user %s as %s for company %s",
                        email, role, config["company_name"])

    # Issue JWTs — same tokens as normal login
    access_token = create_access_token(user["id"], user["email"], user["role"])
    refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

    # Redirect to frontend with tokens in URL fragment (not query params, for security)
    frontend_url = settings.app_base_url
    redirect_url = f"{frontend_url}/sso/callback#access_token={access_token}&refresh_token={refresh_token}"

    return RedirectResponse(url=redirect_url, status_code=302)


# ── Admin SSO config endpoints ──────────────────────────────────────────────

@router.get("/admin/config/{company_id}", response_model=SSOConfigResponse)
async def get_sso_config(company_id: UUID, current_user=Depends(require_admin_or_client)):
    """Get SSO configuration for a company."""
    async with get_connection() as conn:
        config = await conn.fetchrow(
            "SELECT * FROM company_sso_configs WHERE company_id = $1",
            company_id,
        )

    if not config:
        raise HTTPException(status_code=404, detail="No SSO config for this company")

    return SSOConfigResponse(
        id=config["id"],
        company_id=config["company_id"],
        enabled=config["enabled"],
        idp_entity_id=config["idp_entity_id"],
        idp_sso_url=config["idp_sso_url"],
        email_domain=config["email_domain"],
        default_role=config["default_role"],
        auto_provision=config["auto_provision"],
        created_at=str(config["created_at"]) if config["created_at"] else None,
        updated_at=str(config["updated_at"]) if config["updated_at"] else None,
    )


@router.put("/admin/config/{company_id}", response_model=SSOConfigResponse)
async def upsert_sso_config(
    company_id: UUID,
    body: SSOConfigCreate,
    current_user=Depends(require_admin_or_client),
):
    """Create or update SSO configuration for a company."""
    async with get_connection() as conn:
        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        config = await conn.fetchrow(
            """INSERT INTO company_sso_configs
               (company_id, idp_entity_id, idp_sso_url, idp_x509_cert,
                email_domain, default_role, auto_provision, enabled)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (company_id) DO UPDATE SET
                   idp_entity_id = EXCLUDED.idp_entity_id,
                   idp_sso_url = EXCLUDED.idp_sso_url,
                   idp_x509_cert = EXCLUDED.idp_x509_cert,
                   email_domain = EXCLUDED.email_domain,
                   default_role = EXCLUDED.default_role,
                   auto_provision = EXCLUDED.auto_provision,
                   enabled = EXCLUDED.enabled,
                   updated_at = NOW()
               RETURNING *""",
            company_id,
            body.idp_entity_id,
            body.idp_sso_url,
            body.idp_x509_cert,
            body.email_domain.lower(),
            body.default_role,
            body.auto_provision,
            body.enabled,
        )

    logger.info("SSO config upserted for company %s (domain: %s, enabled: %s)",
                company_id, body.email_domain, body.enabled)

    return SSOConfigResponse(
        id=config["id"],
        company_id=config["company_id"],
        enabled=config["enabled"],
        idp_entity_id=config["idp_entity_id"],
        idp_sso_url=config["idp_sso_url"],
        email_domain=config["email_domain"],
        default_role=config["default_role"],
        auto_provision=config["auto_provision"],
        created_at=str(config["created_at"]) if config["created_at"] else None,
        updated_at=str(config["updated_at"]) if config["updated_at"] else None,
    )


@router.put("/admin/config/{company_id}/from-metadata", response_model=SSOConfigResponse)
async def upsert_sso_config_from_metadata(
    company_id: UUID,
    body: SSOConfigFromMetadata,
    current_user=Depends(require_admin_or_client),
):
    """Create or update SSO config by fetching IdP metadata from a URL.

    This is the easiest setup path — the client pastes their IdP metadata URL
    (e.g. from Okta or Azure AD) and we extract the entity ID, SSO URL, and cert.
    """
    try:
        idp_data = OneLogin_Saml2_IdPMetadataParser.parse_remote(body.metadata_url)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch/parse IdP metadata: {e}",
        )

    idp = idp_data.get("idp", {})
    entity_id = idp.get("entityId")
    sso_url = idp.get("singleSignOnService", {}).get("url")
    x509_cert = idp.get("x509cert")

    if not all([entity_id, sso_url, x509_cert]):
        raise HTTPException(
            status_code=400,
            detail="Metadata is missing required fields (entityId, SSO URL, or certificate)",
        )

    # Delegate to the standard upsert
    return await upsert_sso_config(
        company_id=company_id,
        body=SSOConfigCreate(
            idp_entity_id=entity_id,
            idp_sso_url=sso_url,
            idp_x509_cert=x509_cert,
            email_domain=body.email_domain,
            default_role=body.default_role,
            auto_provision=body.auto_provision,
            enabled=body.enabled,
        ),
        current_user=current_user,
    )


@router.delete("/admin/config/{company_id}")
async def delete_sso_config(company_id: UUID, current_user=Depends(require_admin)):
    """Delete SSO configuration for a company (admin only)."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM company_sso_configs WHERE company_id = $1", company_id
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="No SSO config for this company")

    return {"detail": "SSO config deleted"}
