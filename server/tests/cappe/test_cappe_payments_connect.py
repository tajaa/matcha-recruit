"""Caller-supplied Stripe redirect URLs are bounded to our own origins.

Stripe renders `return_url` / `refresh_url` as links on its hosted, Stripe-
branded Connect onboarding page, and `success_url` / `cancel_url` on Checkout.
Forwarding a client-supplied address there makes Stripe a phishing springboard
with real Stripe branding in front of it (audit F4 / B7).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_payments_connect.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

import app.config as app_config  # noqa: E402
from app.cappe.routes.payments import _own_dashboard_url  # noqa: E402
from app.cappe.services.common import (  # noqa: E402
    receipt_filename,
    site_origins,
    url_within_origins,
)
from app.cappe.services.email import dashboard_url  # noqa: E402


@pytest.fixture
def base_domain(monkeypatch):
    """Pin the Cappe base domain for this module only.

    `CAPPE_BASE_DOMAIN` must NOT be set via os.environ here: the environment is
    process-global, so an import-time setdefault silently re-homes every other
    test module in the same run (it broke tests/cappe/test_cappe_hosting.py).
    `site_origins` reads settings first and only falls back to the env, so
    patching the settings object is both accurate and contained.
    """
    real = app_config.get_settings()

    class S:
        def __getattr__(self, name):
            return getattr(real, name)

        cappe_base_domain = "gummfit.com"

    monkeypatch.setattr(app_config, "get_settings", lambda: S())
    return "gummfit.com"


# ── url_within_origins ───────────────────────────────────────────────────────

ORIGINS = ["https://shop.gummfit.com", "https://example-store.com"]


@pytest.mark.parametrize("url", [
    "https://shop.gummfit.com",
    "https://shop.gummfit.com/",
    "https://shop.gummfit.com/thanks",
    "https://shop.gummfit.com?order=1",
    "https://shop.gummfit.com#done",
    "https://example-store.com/receipt",
    "HTTPS://SHOP.GUMMFIT.COM/thanks",   # scheme/host are case-insensitive
])
def test_own_origin_is_accepted(url):
    assert url_within_origins(url, ORIGINS) == url


@pytest.mark.parametrize("url", [
    "https://evil.test/phish",
    "https://shop.gummfit.com.evil.test/",     # prefix match without a boundary
    "https://shop.gummfit.comevil.test",
    "http://shop.gummfit.com/thanks",          # scheme downgrade
    "//shop.gummfit.com/thanks",               # protocol-relative
    "javascript:alert(1)",
    "",
    None,
])
def test_foreign_or_malformed_url_is_rejected(url):
    assert url_within_origins(url, ORIGINS) is None


def test_no_origins_accepts_nothing():
    assert url_within_origins("https://shop.gummfit.com", []) is None


# ── site_origins ─────────────────────────────────────────────────────────────

def test_site_origins_covers_canonical_host_and_custom_domain(base_domain):
    origins = site_origins({"subdomain": "shop", "custom_domain": "example-store.com"})
    assert origins == [
        "https://shop.gummfit.com",
        "https://example-store.com",
        "https://www.example-store.com",   # the renderer accepts www. too
    ]


def test_site_origins_without_a_custom_domain(base_domain):
    assert site_origins({"subdomain": "shop", "custom_domain": None}) == [
        "https://shop.gummfit.com"
    ]


def test_site_origins_is_case_and_dot_insensitive(base_domain):
    assert site_origins({"subdomain": "SHOP", "custom_domain": "Example-Store.COM."}) == [
        "https://shop.gummfit.com",
        "https://example-store.com",
        "https://www.example-store.com",
    ]


def test_site_with_neither_host_yields_no_origins(base_domain):
    """An empty origin list means every caller-supplied URL is refused, which is
    the safe direction — never an accidental allow-all."""
    assert site_origins({"subdomain": "", "custom_domain": ""}) == []


# ── _own_dashboard_url ───────────────────────────────────────────────────────

def test_dashboard_url_on_our_own_origin_is_kept():
    ours = dashboard_url("/sites/abc/orders")
    assert _own_dashboard_url(ours) == ours


@pytest.mark.parametrize("url", [
    "https://evil.test/onboarding-done",
    "https://gummfit.com.evil.test/",
    None,
    "",
])
def test_foreign_dashboard_url_is_dropped(url):
    assert _own_dashboard_url(url) is None


# ── receipt_filename ─────────────────────────────────────────────────────────

def test_receipt_filename_keeps_a_normal_receipt_number():
    assert receipt_filename("INV-00042") == "INV-00042.pdf"


def test_receipt_filename_strips_a_quote_that_would_add_header_directives():
    """`receipt_prefix` is now charset-constrained, but rows written before that
    are not, and the value lands inside a quoted Content-Disposition."""
    assert '"' not in receipt_filename('a"; filename="evil')
    assert receipt_filename('a"; filename="evil') == "afilenameevil.pdf"


@pytest.mark.parametrize("value,expected", [
    (None, "receipt.pdf"),
    ("", "receipt.pdf"),
    ("///", "receipt.pdf"),          # nothing survives the strip
    ("a\r\nb", "ab.pdf"),            # CR/LF never reach the header
])
def test_receipt_filename_falls_back_when_nothing_usable_remains(value, expected):
    assert receipt_filename(value) == expected


def test_receipt_filename_is_length_capped():
    assert len(receipt_filename("X" * 500)) == 64 + len(".pdf")
