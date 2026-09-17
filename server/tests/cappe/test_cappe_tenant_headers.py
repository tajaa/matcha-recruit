"""Security headers on tenant-rendered pages, pinned.

The policy is asserted whole rather than by feature: a directive silently
dropped (or `default-src` quietly widened) is the failure mode this guards, and
it is invisible in a diff of the rendered HTML. The map block is the live
example — the OpenStreetMap iframe fell back to `default-src 'self'` and every
published map rendered blank, while the editor preview (a sandboxed srcdoc with
no CSP at all) kept showing it, so the owner never saw the break (audit R1).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_tenant_headers.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.routes.render import TENANT_CSP, tenant_security_headers  # noqa: E402

EXPECTED_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "media-src 'self' https:; "
    "connect-src 'self'; "
    "frame-src 'self' https://www.openstreetmap.org; "
    "frame-ancestors 'self'"
)


def test_tenant_csp_is_exactly_the_reviewed_policy():
    assert TENANT_CSP == EXPECTED_CSP


def test_map_block_iframe_origin_is_allowed():
    """services/render/blocks.py embeds this origin when the owner supplies
    lat/lng; without frame-src it inherits default-src 'self' and is blocked."""
    assert "frame-src 'self' https://www.openstreetmap.org" in TENANT_CSP


def test_hero_video_media_origin_is_allowed():
    """The same class of bug, fixed earlier: an external CloudFront <video> was
    blocked on published pages while the preview kept showing it."""
    assert "media-src 'self' https:" in TENANT_CSP


@pytest.mark.parametrize("directive", [
    "default-src 'self'",
    "object-src",     # absent by design — default-src 'self' covers it
])
def test_policy_never_widens_to_a_wildcard_default(directive):
    assert "default-src *" not in TENANT_CSP
    assert "script-src *" not in TENANT_CSP


def test_tenant_headers_carry_the_policy_and_framing_guards():
    headers = tenant_security_headers()
    assert headers["Content-Security-Policy"] == EXPECTED_CSP
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["Cache-Control"] == "public, max-age=60"
