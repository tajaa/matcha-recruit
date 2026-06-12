"""Cappe hosting tests — host→site resolution (subdomains + custom domains)
and custom-domain normalization. No DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_hosting.py -q
"""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.cappe import (  # noqa: E402
    CappeSiteUpdate,
    normalize_custom_domain,
)
from app.cappe.routes.render import (  # noqa: E402
    _custom_domain_candidates,
    subdomain_from_host,
)


# --- subdomain_from_host ------------------------------------------------------

@pytest.mark.parametrize("host,expected", [
    ("avery.cappe.hey-matcha.com", "avery"),
    ("avery.cappe.hey-matcha.com:443", "avery"),
    ("AVERY.Cappe.Hey-Matcha.com", "avery"),
    ("avery.cappe.localhost:8001", "avery"),
    ("avery.localhost", "avery"),
    ("hey-matcha.com", None),
    ("www.cappe.hey-matcha.com", None),       # reserved label
    ("api.cappe.hey-matcha.com", None),       # reserved label
    ("localhost", None),
    ("localhost:8001", None),
    ("studio-petals.com", None),              # custom domain, not a subdomain
    (None, None),
    ("", None),
])
def test_subdomain_from_host(host, expected):
    assert subdomain_from_host(host) == expected


# --- _custom_domain_candidates -------------------------------------------------

def test_custom_domain_candidates_plain():
    assert _custom_domain_candidates("studio-petals.com") == ["studio-petals.com"]


def test_custom_domain_candidates_www_matches_apex_too():
    assert _custom_domain_candidates("www.studio-petals.com") == [
        "www.studio-petals.com",
        "studio-petals.com",
    ]


def test_custom_domain_candidates_strips_port_and_case():
    assert _custom_domain_candidates("Studio-Petals.COM:443") == ["studio-petals.com"]


@pytest.mark.parametrize("host", [
    "hey-matcha.com",                 # app host
    "www.hey-matcha.com",             # app host
    "avery.cappe.hey-matcha.com",     # tenant subdomain — handled by subdomain path
    "avery.cappe.localhost",          # dev subdomain
    "avery.localhost",                # dev subdomain
    "localhost",
    "matcha-backend",
    None,
    "",
])
def test_custom_domain_candidates_excludes_non_tenants(host):
    assert _custom_domain_candidates(host) == []


# --- normalize_custom_domain ----------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("studio-petals.com", "studio-petals.com"),
    ("Studio-Petals.COM", "studio-petals.com"),
    ("  studio-petals.com  ", "studio-petals.com"),
    ("https://studio-petals.com/", "studio-petals.com"),
    ("http://studio-petals.com/about?x=1", "studio-petals.com"),
    ("www.studio-petals.com", "studio-petals.com"),   # apex stored
    ("studio-petals.com:443", "studio-petals.com"),
    ("studio-petals.com.", "studio-petals.com"),
    ("shop.studio-petals.com", "shop.studio-petals.com"),  # subdomains allowed
])
def test_normalize_custom_domain_accepts(raw, expected):
    assert normalize_custom_domain(raw) == expected


def test_normalize_custom_domain_passthrough_none_and_empty():
    # None stays None; '' passes through so the update route can map '' → NULL.
    assert normalize_custom_domain(None) is None
    assert normalize_custom_domain("") == ""
    assert normalize_custom_domain("   ") == ""


@pytest.mark.parametrize("raw", [
    "not a domain",
    "nodots",
    "-bad.com",
    "bad-.com",
    "ex_ample.com",
    "hey-matcha.com",                  # our own apex
    "cappe.hey-matcha.com",            # our infra
    "evil.cappe.hey-matcha.com",       # would shadow a tenant subdomain
    "localhost",
    "foo.localhost",
])
def test_normalize_custom_domain_rejects(raw):
    with pytest.raises(ValueError):
        normalize_custom_domain(raw)


def test_site_update_model_normalizes():
    body = CappeSiteUpdate(custom_domain="https://WWW.Studio-Petals.com/")
    assert body.custom_domain == "studio-petals.com"


def test_site_update_model_rejects_invalid():
    with pytest.raises(ValidationError):
        CappeSiteUpdate(custom_domain="not a domain")


def test_site_update_model_clear_semantics():
    # '' survives validation so routes can interpret it as "clear the domain".
    assert CappeSiteUpdate(custom_domain="").custom_domain == ""
    assert CappeSiteUpdate().custom_domain is None
