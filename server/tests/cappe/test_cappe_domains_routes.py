"""Domain routes — the feature gate and the DNS-management guards.

`domains.py` is the money path with the widest blast radius (it spends at
Porkbun, charges on our own platform account, and proxies a registrar API), and
before the 2026-09 audit it had no route-level tests at all.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_domains_routes.py -q
"""
import asyncio
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.cappe.routes import domains as mod  # noqa: E402
from tests._helpers.routes import iter_api_routes  # noqa: E402


class Settings:
    cappe_custom_domains_enabled = False
    cappe_cf_routing_endpoint = "d123.cloudfront.net"


@pytest.fixture
def settings(monkeypatch):
    s = Settings()
    monkeypatch.setattr(mod, "get_settings", lambda: s)
    return s


# ── the feature gate ─────────────────────────────────────────────────────────

def test_gate_is_closed_by_default(settings):
    """A domain bought while the edge is unconfigured resolves to a certificate
    error, so the whole create surface stays dark until it is set up."""
    with pytest.raises(HTTPException) as exc:
        mod._require_custom_domains_enabled()
    assert exc.value.status_code == 503
    assert "not available yet" in exc.value.detail


def test_gate_opens_when_configured(settings):
    settings.cappe_custom_domains_enabled = True
    assert mod._require_custom_domains_enabled() is None


def test_every_domain_creating_route_is_gated():
    """search / purchase / connect / verify all lead to a live custom domain."""
    source = mod.__file__
    with open(source) as fh:
        text = fh.read()
    assert text.count("_require_custom_domains_enabled()") >= 4


def test_config_hides_the_endpoint_while_disabled(settings):
    out = asyncio.run(mod.domains_config(account=None))
    assert out == {"enabled": False, "routing_endpoint": None}


def test_config_exposes_the_endpoint_once_enabled(settings):
    settings.cappe_custom_domains_enabled = True
    out = asyncio.run(mod.domains_config(account=None))
    assert out == {"enabled": True, "routing_endpoint": "d123.cloudfront.net"}


# ── DNS management guards ────────────────────────────────────────────────────

class FakeConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, sql, *args):
        return self._row


def _owned(row):
    return asyncio.run(mod._owned_register_domain(FakeConn(row), "acct-1", "d-1"))


def test_active_registered_domain_is_manageable():
    row = {"id": "d-1", "domain": "example.com", "kind": "register", "status": "active"}
    assert _owned(row)["domain"] == "example.com"


def test_unknown_domain_is_404():
    with pytest.raises(HTTPException) as exc:
        _owned(None)
    assert exc.value.status_code == 404


def test_connected_domain_dns_stays_at_the_tenant_s_registrar():
    row = {"id": "d-1", "domain": "example.com", "kind": "connect", "status": "active"}
    with pytest.raises(HTTPException) as exc:
        _owned(row)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("status_value", ["pending", "registering", "failed", "expired"])
def test_non_active_domain_cannot_have_its_dns_edited(status_value):
    """A pending row is created before payment; writing DNS for it sends
    registrar calls for a name we do not hold."""
    row = {"id": "d-1", "domain": "example.com", "kind": "register", "status": status_value}
    with pytest.raises(HTTPException) as exc:
        _owned(row)
    assert exc.value.status_code == 409


def test_transfer_out_freezes_dns():
    """After the auth code is handed over the domain is on its way to someone
    else's account; we must not keep rewriting its records."""
    row = {"id": "d-1", "domain": "example.com", "kind": "register", "status": "transfer_requested"}
    with pytest.raises(HTTPException) as exc:
        _owned(row)
    assert exc.value.status_code == 409
    assert "transferred out" in exc.value.detail


# ── record_id is interpolated into an outbound URL ───────────────────────────

def test_record_id_is_constrained_to_digits():
    """`record_id` lands in the Porkbun request path (`/dns/delete/<d>/<id>`);
    a `..` there re-points the call at a different endpoint."""
    def _patterns(field):
        # Pydantic v2 keeps a Path(pattern=...) constraint in FieldInfo.metadata.
        out = []
        for meta in getattr(field.field_info, "metadata", None) or []:
            pattern = getattr(meta, "pattern", None)
            if pattern:
                out.append(pattern)
        return out

    checked = 0
    for route in iter_api_routes(mod.router):
        if "{record_id}" not in route.path:
            continue
        checked += 1
        record_id = [f for f in route.dependant.path_params if f.name == "record_id"]
        assert record_id, route.path
        assert r"^[0-9]{1,20}$" in _patterns(record_id[0]), route.path
    assert checked >= 2      # the PUT and the DELETE


def test_tls_authorize_endpoint_is_gone():
    """The Caddy on-demand ask-endpoint had no consumer and was an unauthenticated
    oracle for "is this domain hosted on Cappe"."""
    paths = [r.path for r in iter_api_routes(mod.router)]
    assert not any("tls/authorize" in p for p in paths)
