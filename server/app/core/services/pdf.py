"""Shared WeasyPrint helpers with an SSRF-safe URL fetcher.

WeasyPrint's default URL fetcher will resolve ANY scheme referenced in the HTML
it renders — including `file:///etc/passwd` (local-file disclosure into the PDF)
and `http://169.254.169.254/...` (cloud-metadata / IAM-credential SSRF). Several
PDF endpoints render user- or AI-authored HTML (project sections, handbooks,
offer letters, ER/IR/discipline docs), so any `<img src=...>` / `<link href=...>`
the author controls becomes a server-side fetch.

`safe_url_fetcher` refuses every remote/file scheme and allows only inline
`data:` URIs. Images are base64-inlined as `data:` *before* render in the paths
that need them, so legitimate assets are unaffected. This mirrors the original
one-off guard in `matcha/services/benefits_eligibility.py`.
"""

import asyncio

from weasyprint import HTML, default_url_fetcher


def safe_url_fetcher(url: str):
    """URL fetcher for WeasyPrint that blocks all non-`data:` schemes.

    Allows inline `data:` URIs (e.g. base64 images we inlined ourselves) and
    refuses everything else — `file://`, `http(s)://` (incl. cloud metadata at
    169.254.169.254 and RFC-1918 hosts), `ftp://`, etc. — to prevent SSRF and
    local-file disclosure when rendering attacker-influenced HTML.
    """
    if url.startswith("data:"):
        return default_url_fetcher(url)
    raise ValueError(f"Blocked non-data URL in PDF render: {url[:80]}")


def render_pdf(html_string: str, **write_pdf_kwargs) -> bytes:
    """Render HTML to PDF bytes with the SSRF-safe fetcher applied.

    Drop-in replacement for `HTML(string=html).write_pdf()`. Extra kwargs
    (e.g. `stylesheets=[...]`) are forwarded to `write_pdf`.
    """
    return HTML(string=html_string, url_fetcher=safe_url_fetcher).write_pdf(
        **write_pdf_kwargs
    )


async def render_pdf_async(html_string: str, **write_pdf_kwargs) -> bytes:
    """`render_pdf` off the event loop.

    WeasyPrint render is CPU-bound and blocking; the desktop client awaits the
    bytes inline (see the root CLAUDE.md note on why PDF render stays in the
    request path), so every async caller wrapped it in `asyncio.to_thread`. This
    folds that wrapper — and the SSRF-safe fetcher — into one call.
    """
    return await asyncio.to_thread(render_pdf, html_string, **write_pdf_kwargs)
