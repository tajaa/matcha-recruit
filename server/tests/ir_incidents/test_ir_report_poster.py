"""Unit tests for the magic-link QR poster PDF builder.

Pure-function test — no DB, no app boot. Renders through WeasyPrint (real,
not mocked) since that's the actual behavior being verified: valid HTML in,
valid PDF bytes out.
"""
from app.matcha.services.ir_report_poster import (
    DEFAULT_BRANDING,
    _text_on,
    build_report_poster_pdf,
    resolve_branding,
)


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


def test_build_report_poster_pdf_with_custom_branding():
    pdf = build_report_poster_pdf(
        "https://hey-matcha.com/report/demo-token",
        branding={"primary": "#123456", "secondary": "#abcdef"},
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 500


def test_resolve_branding_merges_onto_defaults():
    assert resolve_branding({"primary": "#111111"}) == {
        "primary": "#111111",
        "secondary": DEFAULT_BRANDING["secondary"],
    }
    assert resolve_branding(None) == DEFAULT_BRANDING
    assert resolve_branding({}) == DEFAULT_BRANDING


def test_resolve_branding_rejects_invalid_hex():
    # Malformed/non-hex values must fall back to the Matcha default, never
    # pass through raw — these strings are interpolated straight into CSS.
    assert resolve_branding({"primary": "red", "secondary": "javascript:alert(1)"}) == DEFAULT_BRANDING
    assert resolve_branding({"primary": "#12345"}) == DEFAULT_BRANDING  # too short
    assert resolve_branding({"primary": "#gggggg"}) == DEFAULT_BRANDING  # non-hex chars


def test_text_on_picks_higher_contrast_foreground():
    # Dark primary -> light text; light primary -> dark text.
    assert _text_on("#111111") == "#ffffff"
    assert _text_on("#ffffff") == "#0c1f16"
