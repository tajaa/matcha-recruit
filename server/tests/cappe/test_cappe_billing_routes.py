"""Cappe billing route wiring: auth, the platform-admin gate, webhook signature.

These are behavioural, not structural, on purpose. FastAPI 0.141 resolves
`include_router` lazily into `_IncludedRouter` wrappers, so introspecting
`router.routes` for a mount-level dependency silently finds nothing and any
"all routes are gated" assertion built that way passes VACUOUSLY. Driving real
requests is the only check that can actually fail.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_billing_routes.py -q
"""
import os
import pathlib
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


class TestBillingReturnUrl:
    """Stripe renders these on its own pages, so anything off our origin is
    replaced; the replacement is the billing page, which re-checks the plan."""

    def test_a_foreign_return_url_falls_back_to_the_billing_page(self):
        from app.cappe.routes import billing

        url = billing._billing_return_url("https://evil.test/phish")
        assert "evil.test" not in url
        assert url.endswith("/cappe/billing?checkout=return")

    def test_a_url_on_our_origin_is_kept(self):
        from app.cappe.routes import billing
        from app.cappe.services.email import app_origin

        own = f"{app_origin()}/cappe/billing?checkout=success"
        assert billing._billing_return_url(own) == own


class TestPlanCheckoutBody:
    def test_plan_checkout_validates_the_plan_body_not_the_cart_body(self, app, client):
        """`/billing/checkout` once received the storefront's cart model
        (same class name, shadowed through the models.cappe shim), so the
        billing page's body 422'd for want of `items` and `customer_email`
        and no plan could be bought. Past validation, the handler fails on
        the missing database instead — anything but 422 is the pass."""
        app.dependency_overrides[require_cappe_account] = lambda: _account(False)
        try:
            resp = client.post("/api/cappe/billing/checkout", json={
                "plan_code": "business", "interval": "month",
                "success_url": "https://gummfit.com/cappe/billing?checkout=success",
                "cancel_url": "https://gummfit.com/cappe/billing?checkout=cancelled",
            })
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code != 422, resp.text

    def test_no_two_model_modules_export_the_same_name(self):
        """The shim star-imports every module, so a repeated name silently
        resolves to whichever module is imported last."""
        import importlib

        from app.cappe.models import cappe as shim

        owners: dict[str, list[str]] = {}
        for line in pathlib.Path(shim.__file__).read_text().splitlines():
            if line.startswith("from .") and "import *" in line:
                name = line.split()[1].lstrip(".")
                module = importlib.import_module(f"app.cappe.models.{name}")
                for exported in getattr(module, "__all__", []):
                    owners.setdefault(exported, []).append(name)
        assert {n: m for n, m in owners.items() if len(m) > 1} == {}
