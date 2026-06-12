"""Cappe offerings tests — generalized product fulfillment, intake validation,
and the public storefront widget rendering. No DB, no app boot.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_offerings.py -q
"""
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.models.cappe import CappeProductCreate  # noqa: E402
from app.cappe.routes.public import _validate_intake  # noqa: E402
from app.cappe.services.render import render_site_html  # noqa: E402


# --- product model -----------------------------------------------------------

def test_product_defaults_physical():
    p = CappeProductCreate(name="Tee", price_cents=1500)
    assert p.fulfillment == "physical"
    assert p.digital_file_url is None
    assert p.intake_fields == []


def test_product_accepts_fulfillment():
    p = CappeProductCreate(name="HR Handbook", price_cents=4900, fulfillment="digital")
    assert p.fulfillment == "digital"
    s = CappeProductCreate(
        name="Wedding package", price_cents=120000, fulfillment="service",
        intake_fields=[{"key": "date", "label": "Event date", "type": "date", "required": True}],
    )
    assert s.intake_fields[0]["key"] == "date"


def test_product_rejects_bad_fulfillment():
    with pytest.raises(Exception):
        CappeProductCreate(name="x", price_cents=0, fulfillment="teleport")


# --- intake validation -------------------------------------------------------

INTAKE = [
    {"key": "date", "label": "Event date", "type": "date", "required": True},
    {"key": "notes", "label": "Notes", "type": "textarea", "required": False},
]


def test_intake_ok_when_required_present():
    _validate_intake(INTAKE, {"date": "2026-08-01", "notes": ""})  # no raise


def test_intake_missing_required_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_intake(INTAKE, {"notes": "hi"})
    assert exc.value.status_code == 400


def test_intake_blank_required_rejected():
    with pytest.raises(HTTPException):
        _validate_intake(INTAKE, {"date": "   "})


def test_intake_no_required_fields_passes():
    _validate_intake([{"key": "x", "label": "X", "required": False}], {})


def test_intake_oversized_rejected():
    with pytest.raises(HTTPException):
        _validate_intake([], {"k": "x" * 9000})


# --- storefront widget rendering --------------------------------------------

def _render(blocks):
    site = {"name": "Demo", "slug": "demo", "theme_config": {"mode": "dark"}, "meta_config": {}}
    page = {"title": "Home", "slug": "home", "content": {"blocks": blocks}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_store_block_wires_checkout():
    html = _render([{"type": "store", "heading": "Shop"}])
    assert "window.__CAPPE__" in html
    assert "/api/cappe/public/sites/demo" in html
    assert "RT.post('/orders'" in html


def test_booking_and_newsletter_and_contact_wired():
    html = _render([
        {"type": "booking", "heading": "Book"},
        {"type": "newsletter", "heading": "Subscribe"},
        {"type": "contact", "heading": "Contact", "formSlug": "contact", "fields": ["name", "email"]},
    ])
    assert "RT.post('/bookings'" in html
    assert "RT.post('/subscribe'" in html
    assert "RT.post('/forms/'" in html
    assert 'data-form="contact"' in html


def test_contact_form_no_longer_dead():
    html = _render([{"type": "contact", "heading": "Contact"}])
    assert "onsubmit=\"return false\"" not in html
