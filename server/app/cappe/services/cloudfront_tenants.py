"""CloudFront distribution tenants — TLS + edge routing for Cappe custom domains.

A custom domain (bought through us or BYO-connected) cannot use the
`*.gummfit.com` wildcard certificate, and standing up one distribution per
domain would burn a 5-10 minute deploy and a slot in the 200-distribution
quota each time. Instead every custom domain becomes a **distribution tenant**
of ONE tenant-only distribution that carries the shared origin
(`origin.gummfit.com`), the `X-Cappe-Origin-Verify` custom header and the
`cappe-public-edge` WAF ACL. CloudFront issues AND renews the per-tenant
certificate itself, so nothing here ever touches ACM directly.

Validation is `ValidationTokenHost: "cloudfront"`, which means AWS validates by
following the domain once it resolves to the connection group's routing
endpoint. So a freshly created tenant sits at `pending_dns` until the tenant's
DNS is pointed, then flips to `live` on its own — which is what
`workers/tasks/cappe_edge_sync.py` polls for.

boto3 field names used here, verified against the installed boto3 1.43.6
service model (`service_model.operation_model(...).input_shape.members`):

    CreateDistributionTenant(DistributionId, Name, Domains=[{"Domain": str}],
        ConnectionGroupId, Enabled,
        ManagedCertificateRequest={ValidationTokenHost, PrimaryDomainName,
                                   CertificateTransparencyLoggingPreference})
        -> {"DistributionTenant": {...}, "ETag": str}
    GetDistributionTenant(Identifier)
        -> {"DistributionTenant": {"Id", "Status", "Enabled",
                                   "Domains": [{"Domain", "Status"}], ...},
            "ETag": str}
    UpdateDistributionTenant(Id, IfMatch, Enabled) -> {"DistributionTenant", "ETag"}
    DeleteDistributionTenant(Id, IfMatch) -> (no output)
    GetManagedCertificateDetails(Identifier)
        -> {"ManagedCertificateDetails": {"CertificateArn", "CertificateStatus",
              "ValidationTokenHost", "ValidationTokenDetails": [...]}}

`DomainResult.Status` is `active|inactive`; `CertificateStatus` is one of
`pending-validation|issued|inactive|expired|validation-timed-out|revoked|failed`.
The connection group's `RoutingEndpoint` is NOT on the tenant — it comes from
`settings.cappe_cf_routing_endpoint` (recorded once at setup).

Error codes we special-case: `EntityNotFound` (treated as "gone", so deletes are
idempotent) and `ResourceNotDisabled` (a tenant must be disabled before it can
be deleted — `delete_tenant` disables first).

All calls are sync SDK calls run through `asyncio.to_thread`, like
`services/stripe_connect.py`.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from ...config import get_settings

logger = logging.getLogger("cappe.cloudfront_tenants")

# CloudFront region for distribution/tenant/certificate APIs (global service).
_REGION = "us-east-1"

# Terminal certificate states — an operator has to intervene, polling won't help.
_CERT_FAILED = {"failed", "validation-timed-out", "revoked", "expired", "inactive"}
# Error codes that mean "this tenant does not exist" rather than "call failed".
_NOT_FOUND_CODES = {"EntityNotFound", "NoSuchResource", "NoSuchDistribution"}


class CappeEdgeError(Exception):
    """A CloudFront tenant call failed, or the edge is not configured."""


class CappeEdgeNotFound(CappeEdgeError):
    """The tenant (or its certificate) no longer exists at the edge."""


@dataclass(frozen=True)
class CfTenant:
    """A created distribution tenant plus the endpoint its DNS must point at."""

    tenant_id: str
    routing_endpoint: Optional[str]


def apex_of(domain: str) -> str:
    """Normalize to the apex we attach as the tenant's primary domain."""
    host = (domain or "").strip().lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _tenant_name(apex: str) -> str:
    """CloudFront tenant names are not hostnames — hyphenate and clamp."""
    slug = re.sub(r"[^a-z0-9-]+", "-", apex).strip("-")
    return f"cappe-{slug}"[:64]


def _error_code(exc: BaseException) -> str:
    """botocore ClientError carries the code at response.Error.Code. Read it
    duck-typed so tests can raise a stand-in without importing botocore."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return str((response.get("Error") or {}).get("Code") or "")
    return ""


def _build_client() -> Any:
    """boto3 CloudFront client, preferring the scoped Cappe key when set."""
    import boto3  # hard dep (server/requirements.txt)

    settings = get_settings()
    kwargs: dict[str, Any] = {"region_name": _REGION}
    if settings.cappe_cloudfront_access_key_id and settings.cappe_cloudfront_secret_access_key:
        kwargs["aws_access_key_id"] = settings.cappe_cloudfront_access_key_id
        kwargs["aws_secret_access_key"] = settings.cappe_cloudfront_secret_access_key
    return boto3.client("cloudfront", **kwargs)


class CloudFrontTenants:
    """Thin async wrapper over the distribution-tenant APIs.

    `client` is injectable so tests (and any future dry-run mode) can drive the
    whole flow without AWS; when omitted the boto3 client is built lazily on
    first use, so importing this module never needs credentials.
    """

    def __init__(self, client: Any = None) -> None:
        self._client = client

    def _require_client(self) -> Any:
        if self._client is None:
            try:
                self._client = _build_client()
            except Exception as exc:  # missing boto3 / broken credentials config
                raise CappeEdgeError(f"CloudFront client unavailable: {exc}") from exc
        return self._client

    async def _call(self, operation: str, **kwargs: Any) -> dict:
        client = self._require_client()
        try:
            return await asyncio.to_thread(getattr(client, operation), **kwargs)
        except Exception as exc:
            code = _error_code(exc)
            if code in _NOT_FOUND_CODES:
                raise CappeEdgeNotFound(f"{operation}: {code}") from exc
            raise CappeEdgeError(f"{operation} failed: {code or exc}") from exc

    # ── Create ────────────────────────────────────────────────────────────
    async def create_tenant(self, domain: str, *, include_www: bool = False) -> CfTenant:
        """Attach `domain` to the tenant distribution and ask CloudFront to issue
        a managed certificate for it.

        `include_www` adds `www.<domain>` to the same certificate. CloudFront
        validates EVERY name on a managed certificate over HTTP, so a name whose
        DNS never points at the edge keeps the whole certificate
        `pending-validation` forever. It is therefore only safe when we control
        the zone and set both records ourselves (a Porkbun-registered domain).
        A connected (BYO) domain gets exactly the host the tenant connected —
        which may itself be a subdomain like `shop.example.com`, where a `www.`
        sibling makes no sense at all.
        """
        settings = get_settings()
        distribution_id = settings.cappe_cf_tenant_distribution_id
        if not distribution_id:
            raise CappeEdgeError("CAPPE_CF_TENANT_DISTRIBUTION_ID is not configured")
        apex = apex_of(domain)
        if not apex:
            raise CappeEdgeError("No domain to attach")

        params: dict[str, Any] = {
            "DistributionId": distribution_id,
            "Name": _tenant_name(apex),
            "Domains": [{"Domain": apex}] + ([{"Domain": f"www.{apex}"}] if include_www else []),
            "Enabled": True,
            "ManagedCertificateRequest": {
                "ValidationTokenHost": "cloudfront",
                "PrimaryDomainName": apex,
                "CertificateTransparencyLoggingPreference": "enabled",
            },
        }
        if settings.cappe_cf_connection_group_id:
            params["ConnectionGroupId"] = settings.cappe_cf_connection_group_id

        resp = await self._call("create_distribution_tenant", **params)
        tenant = (resp or {}).get("DistributionTenant") or {}
        tenant_id = tenant.get("Id")
        if not tenant_id:
            raise CappeEdgeError("CloudFront returned a tenant with no Id")
        logger.info("cappe edge tenant created: %s -> %s", apex, tenant_id)
        return CfTenant(tenant_id=str(tenant_id), routing_endpoint=settings.cappe_cf_routing_endpoint)

    # ── Status ────────────────────────────────────────────────────────────
    async def tenant_status(self, tenant_id: str) -> tuple[str, str]:
        """(edge_status, detail) for one tenant.

        `pending_dns` is the normal resting state right after creation: the
        managed certificate stays `pending-validation` until the domain's DNS
        actually resolves to the routing endpoint.
        """
        resp = await self._call("get_distribution_tenant", Identifier=tenant_id)
        tenant = (resp or {}).get("DistributionTenant") or {}
        deployed = str(tenant.get("Status") or "").strip().lower() == "deployed"
        domains = tenant.get("Domains") or []
        domains_active = bool(domains) and all(
            str(d.get("Status") or "").strip().lower() == "active" for d in domains
        )

        try:
            cert_resp = await self._call("get_managed_certificate_details", Identifier=tenant_id)
            cert_status = str(
                ((cert_resp or {}).get("ManagedCertificateDetails") or {}).get("CertificateStatus") or ""
            ).strip().lower()
        except CappeEdgeNotFound:
            # No managed certificate on this tenant (a supplied cert, or a
            # tenant created outside this code path). Fall back to the tenant's
            # own deployment state rather than polling forever.
            if deployed and domains_active:
                return "live", "no managed certificate on this tenant"
            return "provisioning", "certificate details not available yet"

        if cert_status in _CERT_FAILED:
            return "failed", f"certificate {cert_status}"
        if cert_status != "issued":
            return "pending_dns", "waiting for DNS to point at the routing endpoint"
        if deployed and domains_active:
            return "live", ""
        return "provisioning", f"certificate issued; tenant {tenant.get('Status') or 'deploying'}"

    # ── Delete ────────────────────────────────────────────────────────────
    async def delete_tenant(self, tenant_id: str) -> None:
        """Remove a tenant. A missing tenant is a no-op so the sweeper can run
        repeatedly; CloudFront requires the tenant be disabled first."""
        try:
            resp = await self._call("get_distribution_tenant", Identifier=tenant_id)
        except CappeEdgeNotFound:
            return
        etag = (resp or {}).get("ETag") or ""
        tenant = (resp or {}).get("DistributionTenant") or {}
        if tenant.get("Enabled"):
            try:
                disabled = await self._call(
                    "update_distribution_tenant", Id=tenant_id, IfMatch=etag, Enabled=False
                )
                etag = (disabled or {}).get("ETag") or etag
            except CappeEdgeNotFound:
                return
        try:
            await self._call("delete_distribution_tenant", Id=tenant_id, IfMatch=etag)
        except CappeEdgeNotFound:
            return
        logger.info("cappe edge tenant deleted: %s", tenant_id)


_tenants: Optional[CloudFrontTenants] = None


def get_cloudfront_tenants(client: Any = None) -> CloudFrontTenants:
    """Process-wide accessor. Passing `client` builds a throwaway instance
    around it (tests, one-off scripts) and never touches the cached one."""
    global _tenants
    if client is not None:
        return CloudFrontTenants(client)
    if _tenants is None:
        _tenants = CloudFrontTenants()
    return _tenants


__all__ = [
    "CappeEdgeError",
    "CappeEdgeNotFound",
    "CfTenant",
    "CloudFrontTenants",
    "apex_of",
    "get_cloudfront_tenants",
]
