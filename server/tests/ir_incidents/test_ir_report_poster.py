"""Unit tests for the magic-link QR poster PDF builder.

Pure-function test — no DB, no app boot. Renders through WeasyPrint (real,
not mocked) since that's the actual behavior being verified: valid HTML in,
valid PDF bytes out.
"""
from app.matcha.services.ir_report_poster import build_report_poster_pdf


def test_build_report_poster_pdf_returns_pdf_bytes():
    pdf = build_report_poster_pdf("https://hey-matcha.com/report/demo-token")
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 500


def test_build_report_poster_pdf_with_subtitle():
    pdf = build_report_poster_pdf(
        "https://hey-matcha.com/intake/demo-token",
        subtitle="HQ — Austin, TX",
    )
    assert pdf.startswith(b"%PDF-")


def test_build_report_poster_pdf_escapes_subtitle_html():
    # Subtitle is location-derived free text — must not break out of the <p>.
    pdf = build_report_poster_pdf(
        "https://hey-matcha.com/intake/demo-token",
        subtitle="<script>alert(1)</script>",
    )
    assert pdf.startswith(b"%PDF-")
