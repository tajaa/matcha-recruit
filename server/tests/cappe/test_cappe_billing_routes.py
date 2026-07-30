"""Cappe billing route wiring: auth, the platform-admin gate, webhook signature.

These are behavioural, not structural, on purpose. FastAPI 0.141 resolves
`include_router` lazily into `_IncludedRouter` wrappers, so introspecting
`router.routes` for a mount-level dependency silently finds nothing and any
"all routes are gated" assertion built that way passes VACUOUSLY. Driving real
requests is the only check that can actually fail.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_billing_routes.py -q
"""
import os
import uuid

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.dependencies import require_cappe_account  # noqa: E402
from app.cappe.models.cappe import CappeAccount  # noqa: E402
from app.cappe.routes import cappe_router  # noqa: E402

ADMIN_ENDPOINTS = [
    ("GET", "/api/cappe/admin/billing/products"),
    ("GET", "/api/cappe/admin/billing/accounts"),
    ("GET", "/api/cappe/admin/billing/subscriptions"),
    ("GET", "/api/cappe/admin/billing/events"),
    ("POST", "/api/cappe/admin/billing/products"),
]

TENANT_ENDPOINTS = [
    ("GET", "/api/cappe/billing/catalog"),
    ("GET", "/api/cappe/billing/subscription"),
    ("POST", "/api/cappe/billing/checkout"),
    ("POST", "/api/cappe/billing/portal"),
    ("POST", "/api/cappe/billing/addons"),
    ("POST", "/api/cappe/billing/change-plan"),
    ("POST", "/api/cappe/billing/cancel"),
]


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(cappe_router, prefix="/api/cappe")
    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _account(is_platform_admin: bool) -> CappeAccount:
    return CappeAccount(
        id=uuid.uuid4(),
        email="staff@example.com",
        plan="free",
        status="active",
        account_type="business",
        is_platform_admin=is_platform_admin,
    )


class TestBillingRoutesAreRegistered:
    def test_every_billing_endpoint_is_mounted(self, app):
        """Guards against a router that silently never got included."""
        paths = set(app.openapi()["paths"])
        for _method, path in ADMIN_ENDPOINTS + TENANT_ENDPOINTS:
            assert path in paths, f"{path} is not mounted"


class TestAnonymousAccess:
    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS + TENANT_ENDPOINTS)
    def test_rejects_anonymous(self, client, method, path):
        resp = client.request(method, path, json={})
        assert resp.status_code in (401, 403), (
            f"{method} {path} returned {resp.status_code} to an anonymous caller"
        )


class TestPlatformAdminGate:
    """The admin gate is applied at the MOUNT, so a new endpoint added to
    admin_billing.py cannot ship ungated. These assert it both blocks and
    admits — a gate that rejects everyone would pass a blocks-only test."""

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_authenticated_non_admin_is_forbidden(self, app, client, method, path):
        app.dependency_overrides[require_cappe_account] = lambda: _account(False)
        try:
            resp = client.request(method, path, json={})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_platform_admin_passes_the_gate(self, app, client, method, path):
        """A platform admin must get PAST the gate. There is no database in
        this test, so the handler fails afterwards — anything other than 403 is
        the signal that authorization succeeded."""
        app.dependency_overrides[require_cappe_account] = lambda: _account(True)
        try:
            resp = client.request(method, path, json={})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code != 403

    def test_tenant_billing_does_not_require_platform_admin(self, app, client):
        """A normal paying tenant must reach their own billing page."""
        app.dependency_overrides[require_cappe_account] = lambda: _account(False)
        try:
            resp = client.get("/api/cappe/billing/catalog")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code != 403


class TestPlatformWebhook:
    def test_webhook_is_public_but_signature_gated(self, client):
        """Stripe posts unauthenticated; the signature IS the authentication.
        An unsigned body must 400 rather than 401 (which would mean we put an
        auth dependency on it and Stripe could never deliver)."""
        resp = client.post(
            "/api/cappe/domains/webhook",
            content=b"{}",
            headers={"stripe-signature": "definitely-not-a-valid-signature"},
        )
        assert resp.status_code == 400

    def test_webhook_rejects_missing_signature(self, client):
        resp = client.post("/api/cappe/domains/webhook", content=b"{}")
        assert resp.status_code == 400
