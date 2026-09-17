"""CloudFront distribution tenants — the custom-domain TLS path.

A tenant's own domain can't ride the `*.gummfit.com` wildcard certificate, so
each gets a CloudFront distribution tenant with a CloudFront-managed ACM
certificate. Until this landed, a domain a tenant *bought through us* pointed an
A record straight at the EC2 and every visitor got a certificate-name mismatch
interstitial followed by the Gummfit marketing SPA (audit O4).

No AWS: the boto3 client is injected.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_cloudfront_tenants.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.services import cloudfront_tenants as mod  # noqa: E402
from app.cappe.services.cloudfront_tenants import (  # noqa: E402
    CappeEdgeError,
    CappeEdgeNotFound,
    CloudFrontTenants,
    apex_of,
)


class FakeClientError(Exception):
    """Stand-in for botocore.exceptions.ClientError (duck-typed by _error_code)."""

    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeClient:
    """Records calls; each operation returns a queued response or raises."""

    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def _do(self, op, **kwargs):
        self.calls.append((op, kwargs))
        value = self.responses.get(op)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(**kwargs)
        return value or {}

    def __getattr__(self, name):
        def _op(**kwargs):
            return self._do(name, **kwargs)

        return _op


@pytest.fixture
def settings(monkeypatch):
    class S:
        cappe_cf_tenant_distribution_id = "E_TENANT"
        cappe_cf_connection_group_id = "cg-1"
        cappe_cf_routing_endpoint = "d123.cloudfront.net"
        cappe_cloudfront_access_key_id = None
        cappe_cloudfront_secret_access_key = None

    monkeypatch.setattr(mod, "get_settings", lambda: S)
    return S


# ── apex normalization ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("example.com", "example.com"),
    ("  Example.COM  ", "example.com"),
    ("www.example.com", "example.com"),
    ("example.com.", "example.com"),
    ("WWW.Example.com.", "example.com"),
    ("", ""),
])
def test_apex_normalization(raw, expected):
    assert apex_of(raw) == expected


def test_tenant_name_is_a_safe_slug():
    assert mod._tenant_name("my-shop.example.com") == "cappe-my-shop-example-com"
    assert len(mod._tenant_name("x" * 200)) <= 64


# ── create ───────────────────────────────────────────────────────────────────

def test_create_attaches_apex_and_www_and_requests_a_managed_cert(settings):
    client = FakeClient(create_distribution_tenant={"DistributionTenant": {"Id": "dt-1"}})
    tenant = asyncio.run(CloudFrontTenants(client).create_tenant("www.Example.com"))

    assert tenant.tenant_id == "dt-1"
    assert tenant.routing_endpoint == "d123.cloudfront.net"

    op, kwargs = client.calls[0]
    assert op == "create_distribution_tenant"
    assert kwargs["DistributionId"] == "E_TENANT"
    assert kwargs["ConnectionGroupId"] == "cg-1"
    # Both hostnames: the renderer answers on apex and www alike.
    assert kwargs["Domains"] == [{"Domain": "example.com"}, {"Domain": "www.example.com"}]
    cert = kwargs["ManagedCertificateRequest"]
    assert cert["PrimaryDomainName"] == "example.com"
    assert cert["ValidationTokenHost"] == "cloudfront"


def test_create_without_a_configured_distribution_is_refused(settings, monkeypatch):
    settings.cappe_cf_tenant_distribution_id = ""
    client = FakeClient()
    with pytest.raises(CappeEdgeError, match="CAPPE_CF_TENANT_DISTRIBUTION_ID"):
        asyncio.run(CloudFrontTenants(client).create_tenant("example.com"))
    assert client.calls == []


def test_create_with_an_empty_domain_is_refused(settings):
    client = FakeClient()
    with pytest.raises(CappeEdgeError):
        asyncio.run(CloudFrontTenants(client).create_tenant("   "))


def test_create_without_an_id_in_the_response_is_an_error(settings):
    client = FakeClient(create_distribution_tenant={"DistributionTenant": {}})
    with pytest.raises(CappeEdgeError, match="no Id"):
        asyncio.run(CloudFrontTenants(client).create_tenant("example.com"))


def test_aws_failure_surfaces_as_an_edge_error(settings):
    client = FakeClient(create_distribution_tenant=FakeClientError("AccessDenied"))
    with pytest.raises(CappeEdgeError, match="AccessDenied"):
        asyncio.run(CloudFrontTenants(client).create_tenant("example.com"))


# ── status mapping ───────────────────────────────────────────────────────────

def _status(tenant, cert=None, cert_exc=None):
    client = FakeClient(
        get_distribution_tenant={"DistributionTenant": tenant},
        get_managed_certificate_details=(
            cert_exc if cert_exc else {"ManagedCertificateDetails": {"CertificateStatus": cert}}
        ),
    )
    return asyncio.run(CloudFrontTenants(client).tenant_status("dt-1"))


DEPLOYED = {"Status": "Deployed", "Domains": [{"Status": "active"}, {"Status": "active"}]}
DEPLOYING = {"Status": "InProgress", "Domains": [{"Status": "active"}]}


def test_issued_cert_on_a_deployed_tenant_is_live():
    assert _status(DEPLOYED, cert="issued") == ("live", "")


def test_pending_validation_means_waiting_on_the_tenant_s_dns():
    """The resting state right after creation — the certificate cannot validate
    until the owner points their DNS at the routing endpoint."""
    state, detail = _status(DEPLOYED, cert="pending-validation")
    assert state == "pending_dns"
    assert "DNS" in detail


@pytest.mark.parametrize("cert", ["failed", "validation-timed-out", "revoked", "expired"])
def test_dead_certificate_states_are_failed(cert):
    state, detail = _status(DEPLOYED, cert=cert)
    assert state == "failed"
    assert cert in detail


def test_issued_cert_but_still_deploying_is_provisioning():
    state, _ = _status(DEPLOYING, cert="issued")
    assert state == "provisioning"


def test_inactive_domain_keeps_it_out_of_live():
    state, _ = _status({"Status": "Deployed", "Domains": [{"Status": "pending"}]}, cert="issued")
    assert state == "provisioning"


def test_tenant_without_a_managed_certificate_falls_back_to_its_own_state():
    """A tenant carrying a supplied certificate (or created outside this code
    path) has no managed-certificate record; polling it forever would strand the
    domain, so the tenant's own deployment state decides."""
    missing = FakeClientError("EntityNotFound")
    assert _status(DEPLOYED, cert_exc=missing)[0] == "live"
    assert _status(DEPLOYING, cert_exc=missing)[0] == "provisioning"


def test_missing_tenant_raises_not_found():
    client = FakeClient(get_distribution_tenant=FakeClientError("EntityNotFound"))
    with pytest.raises(CappeEdgeNotFound):
        asyncio.run(CloudFrontTenants(client).tenant_status("dt-gone"))


# ── delete ───────────────────────────────────────────────────────────────────

def test_delete_disables_before_removing():
    """CloudFront refuses to delete an enabled tenant, and the ETag from the
    disable call is the one the delete must carry."""
    client = FakeClient(
        get_distribution_tenant={"DistributionTenant": {"Id": "dt-1", "Enabled": True}, "ETag": "e1"},
        update_distribution_tenant={"ETag": "e2"},
        delete_distribution_tenant={},
    )
    asyncio.run(CloudFrontTenants(client).delete_tenant("dt-1"))

    ops = [c[0] for c in client.calls]
    assert ops == [
        "get_distribution_tenant",
        "update_distribution_tenant",
        "delete_distribution_tenant",
    ]
    assert client.calls[1][1]["Enabled"] is False
    assert client.calls[2][1]["IfMatch"] == "e2"


def test_delete_of_an_already_disabled_tenant_skips_the_update():
    client = FakeClient(
        get_distribution_tenant={"DistributionTenant": {"Id": "dt-1", "Enabled": False}, "ETag": "e1"},
        delete_distribution_tenant={},
    )
    asyncio.run(CloudFrontTenants(client).delete_tenant("dt-1"))
    assert [c[0] for c in client.calls] == ["get_distribution_tenant", "delete_distribution_tenant"]


def test_delete_of_a_missing_tenant_is_a_no_op():
    """The sweeper re-runs; a tenant someone already removed must not raise."""
    client = FakeClient(get_distribution_tenant=FakeClientError("EntityNotFound"))
    asyncio.run(CloudFrontTenants(client).delete_tenant("dt-gone"))
    assert [c[0] for c in client.calls] == ["get_distribution_tenant"]


def test_delete_tolerates_the_tenant_disappearing_mid_flight():
    client = FakeClient(
        get_distribution_tenant={"DistributionTenant": {"Id": "dt-1", "Enabled": True}, "ETag": "e1"},
        update_distribution_tenant=FakeClientError("NoSuchResource"),
    )
    asyncio.run(CloudFrontTenants(client).delete_tenant("dt-1"))


# ── importing never needs credentials ────────────────────────────────────────

def test_injected_client_is_used_without_building_a_boto3_client(monkeypatch):
    def _boom():
        raise AssertionError("must not build a real boto3 client")

    monkeypatch.setattr(mod, "_build_client", _boom)
    client = FakeClient(get_distribution_tenant=FakeClientError("EntityNotFound"))
    asyncio.run(mod.get_cloudfront_tenants(client).delete_tenant("dt-1"))
