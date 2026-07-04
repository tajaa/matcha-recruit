"""Branded print poster for an anonymous-reporting magic link.

Renders a printable "SUBMIT AN INCIDENT" poster around a QR code pointing at
a company-wide `/report/{token}` or per-location `/intake/{token}` link.
QR is generated server-side from the link (never trusts a client-rendered
SVG) with ``segno``, inlined as a base64 ``data:`` PNG so it survives
WeasyPrint's SSRF-safe fetcher (``app.core.services.pdf.safe_url_fetcher``
only allows ``data:`` URIs).

Colors are client-customizable (``primary`` background + ``secondary`` accent),
but with three guardrails baked in so a bad palette can't break the artifact:
- every color is validated as ``#RRGGBB`` before it touches the CSS (no style/
  markup injection from client input);
- the QR always sits on a white card, so it scans regardless of ``primary``;
- title/footer text auto-picks the higher-contrast of dark/light against
  ``primary`` (WCAG), and the Matcha wordmark is always rendered.
"""

import base64
import html
import io
import re

import segno

from app.core.services.pdf import render_pdf

_GREEN = "#4f9d72"
_ORANGE = "#f5a623"
_DARK = "#111111"

# Candidate foregrounds for the auto-contrast pick over the primary background.
_TEXT_DARK = "#0c1f16"
_TEXT_LIGHT = "#ffffff"

DEFAULT_BRANDING = {"primary": _GREEN, "secondary": _ORANGE}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _sanitize_hex(value, fallback: str) -> str:
    """Return ``value`` only if it's a well-formed ``#RRGGBB`` string, else the
    brand fallback. This is the injection guard — these strings are interpolated
    straight into inline CSS, so anything non-conforming is rejected outright."""
    if isinstance(value, str) and _HEX_RE.match(value.strip()):
        return value.strip().lower()
    return fallback


def resolve_branding(raw) -> dict:
    """Merge caller-supplied branding onto the Matcha defaults and sanitize.
    Always returns a full ``{"primary", "secondary"}`` of valid hex colors."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "primary": _sanitize_hex(raw.get("primary"), DEFAULT_BRANDING["primary"]),
        "secondary": _sanitize_hex(raw.get("secondary"), DEFAULT_BRANDING["secondary"]),
    }


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of an ``#RRGGBB`` color."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _text_on(primary: str) -> str:
    """Pick whichever of dark/light foreground has the higher contrast against
    the primary background — keeps title/footer legible on any palette (and
    preserves dark-on-green for the Matcha default)."""
    return _TEXT_DARK if _contrast(primary, _TEXT_DARK) >= _contrast(primary, _TEXT_LIGHT) else _TEXT_LIGHT


def _qr_data_uri(link: str) -> str:
    qr = segno.make(link, error="m")
    buf = io.BytesIO()
    # border=4 = the QR-spec quiet zone (in modules). Transparent (light=None)
    # so the white QR card behind it shows through — always high-contrast.
    qr.save(buf, kind="png", scale=10, dark=_DARK, light=None, border=4)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_report_poster_pdf(link: str, *, subtitle: str | None = None, branding=None) -> bytes:
    """Render a branded, print-ready PDF poster for the given magic link.

    ``subtitle`` (e.g. a location label) prints under the title when given.
    ``branding`` is an optional ``{"primary", "secondary"}`` hex dict; it's
    sanitized and merged onto the Matcha defaults. Matcha's wordmark stays on
    the poster regardless of the palette.
    """
    b = resolve_branding(branding)
    primary, secondary = b["primary"], b["secondary"]
    text = _text_on(primary)
    qr_src = _qr_data_uri(link)
    subtitle_html = (
        f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else ""
    )

    doc = f"""
    <html>
    <head>
    <style>
        @page {{ size: letter; margin: 0; }}
        body {{
            margin: 0;
            width: 8.5in;
            height: 11in;
            background: {primary};
            font-family: Georgia, 'Times New Roman', serif;
            color: {text};
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .poster {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 0.5in;
        }}
        .title {{
            font-size: 46pt;
            font-weight: bold;
            letter-spacing: 2pt;
            text-align: center;
            margin: 0;
        }}
        .subtitle {{
            font-size: 16pt;
            font-weight: bold;
            letter-spacing: 1pt;
            text-align: center;
            margin: 0.2in 0 0 0;
        }}
        .qr-frame {{
            position: relative;
            width: 3.9in;
            height: 3.9in;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        /* White QR card — guarantees the code scans on any primary color. */
        .qr-card {{
            width: 3.2in;
            height: 3.2in;
            background: #ffffff;
            border-radius: 0.18in;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .qr-card img {{
            width: 2.8in;
            height: 2.8in;
        }}
        .corner {{
            position: absolute;
            width: 0.9in;
            height: 0.9in;
            border: 0.06in solid {secondary};
            border-radius: 0.15in;
        }}
        .corner.tl {{ top: 0; left: 0; border-right: none; border-bottom: none; }}
        .corner.tr {{ top: 0; right: 0; border-left: none; border-bottom: none; }}
        .corner.bl {{ bottom: 0; left: 0; border-right: none; border-top: none; }}
        .corner.br {{ bottom: 0; right: 0; border-left: none; border-top: none; }}
        .scan-me {{
            font-size: 30pt;
            font-weight: bold;
            letter-spacing: 3pt;
            margin: 0;
        }}
        .domain {{
            font-size: 14pt;
            font-weight: bold;
            letter-spacing: 1pt;
            margin: 0.2in 0 0 0;
        }}
        .powered {{
            font-size: 9pt;
            letter-spacing: 1.5pt;
            text-transform: uppercase;
            opacity: 0.7;
            margin: 0.08in 0 0 0;
        }}
    </style>
    </head>
    <body>
        <div class="poster">
            <div>
                <p class="title">SUBMIT AN INCIDENT</p>
                {subtitle_html}
            </div>
            <div class="qr-frame">
                <div class="corner tl"></div>
                <div class="corner tr"></div>
                <div class="corner bl"></div>
                <div class="corner br"></div>
                <div class="qr-card"><img src="{qr_src}" alt="QR code" /></div>
            </div>
            <div>
                <p class="scan-me">SCAN ME</p>
                <p class="domain">HEY-MATCHA.COM</p>
                <p class="powered">Powered by Matcha</p>
            </div>
        </div>
    </body>
    </html>
    """
    return render_pdf(doc)
