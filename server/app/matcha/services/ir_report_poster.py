"""Branded print poster for an anonymous-reporting magic link.

Renders a printable "SUBMIT AN INCIDENT" poster around a QR code pointing at
a company-wide `/report/{token}` or per-location `/intake/{token}` link.
QR is generated server-side from the link (never trusts a client-rendered
SVG) with ``segno``, inlined as a base64 ``data:`` PNG so it survives
WeasyPrint's SSRF-safe fetcher (``app.core.services.pdf.safe_url_fetcher``
only allows ``data:`` URIs).
"""

import base64
import html
import io

import segno

from app.core.services.pdf import render_pdf

_GREEN = "#4f9d72"
_ORANGE = "#f5a623"
_DARK = "#111111"


def _qr_data_uri(link: str) -> str:
    qr = segno.make(link, error="m")
    buf = io.BytesIO()
    # border=4 = the QR-spec quiet zone (in modules). Transparent (light=None) so
    # the poster's green shows through — still high-contrast against dark modules.
    qr.save(buf, kind="png", scale=10, dark=_DARK, light=None, border=4)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_report_poster_pdf(link: str, *, subtitle: str | None = None) -> bytes:
    """Render a branded, print-ready PDF poster for the given magic link.

    ``subtitle`` (e.g. a location label) prints under the title when given —
    used for per-location links so a printed poster identifies its site.
    """
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
            background: {_GREEN};
            font-family: Georgia, 'Times New Roman', serif;
            color: #0c1f16;
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
            width: 3.6in;
            height: 3.6in;
            padding: 0.25in;
        }}
        .qr-frame img {{
            width: 100%;
            height: 100%;
        }}
        .corner {{
            position: absolute;
            width: 0.9in;
            height: 0.9in;
            border: 0.06in solid {_ORANGE};
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
                <img src="{qr_src}" alt="QR code" />
            </div>
            <div>
                <p class="scan-me">SCAN ME</p>
                <p class="domain">HEY-MATCHA.COM</p>
            </div>
        </div>
    </body>
    </html>
    """
    return render_pdf(doc)
