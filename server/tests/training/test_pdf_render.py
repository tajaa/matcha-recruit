"""Unit test — training_pdf.render_certificate_pdf produces valid PDF bytes."""

import asyncio
from datetime import date, datetime
from uuid import uuid4

import pytest


@pytest.mark.skipif(
    "weasyprint" not in __import__("sys").modules.get("__main__", object()).__dict__
    and not __import__("importlib").util.find_spec("weasyprint"),
    reason="weasyprint not installed",
)
def test_render_certificate_returns_pdf_bytes():
    from app.matcha.services.training_pdf import render_certificate_pdf

    pdf_bytes = asyncio.run(
        render_certificate_pdf(
            employee_first="Jane",
            employee_last="Doe",
            company_name="Acme Co",
            training_title="California Harassment Prevention — Employee (1 hour)",
            variant_label="Employee (1 hour)",
            completed_date=date(2026, 5, 6),
            score_percent=92.5,
            required_minutes=60,
            expiration_date=date(2028, 5, 6),
            attested_at=datetime(2026, 5, 6, 14, 30),
            attestation_ip="203.0.113.1",
            certificate_id=uuid4(),
        )
    )
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_html_template_includes_required_strings():
    """Quick smoke test on the HTML template layer (no PDF rendering)."""
    from app.matcha.services.training_pdf import _build_html

    cert_id = uuid4()
    html = _build_html(
        employee_first="Jane",
        employee_last="Doe",
        company_name="Acme Co",
        training_title="CA Harassment Prevention",
        variant_label="Supervisor (2 hours)",
        completed_date=date(2026, 5, 6),
        score_percent=92.5,
        required_minutes=120,
        expiration_date=date(2028, 5, 6),
        attested_at=datetime(2026, 5, 6, 14, 30),
        attestation_ip="203.0.113.1",
        certificate_id=cert_id,
    )
    assert "Jane Doe" in html
    assert "Acme Co" in html
    assert "California SB 1343" in html
    assert "92.5%" in html
    assert "Supervisor (2 hours)" in html
    assert str(cert_id) in html
    assert "203.0.113.1" in html
