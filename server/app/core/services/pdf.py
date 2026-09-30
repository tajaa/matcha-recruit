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

from weasyprint import HTML

try:  # WeasyPrint 70+: fetchers are URLFetcher objects.
    from weasyprint.urls import URLFetcher
except ImportError:  # WeasyPrint 69: fetchers are plain functions.
    URLFetcher = None

if URLFetcher is None:
    from weasyprint.urls import default_url_fetcher
else:
    # 70 removed `default_url_fetcher`. This instance is the same thing, and
    # can only open `data:` even if something calls it directly.
    default_url_fetcher = URLFetcher(allowed_protocols={"data"})


def _fetch_data_only(url: str):
    """Allows inline `data:` URIs (e.g. base64 images we inlined ourselves) and
    refuses everything else — `file://`, `http(s)://` (incl. cloud metadata at
    169.254.169.254 and RFC-1918 hosts), `ftp://`, etc. — to prevent SSRF and
    local-file disclosure when rendering attacker-influenced HTML.
    """
    if url.startswith("data:"):
        return default_url_fetcher(url)
    raise ValueError(f"Blocked non-data URL in PDF render: {url[:80]}")


if URLFetcher is None:
    safe_url_fetcher = _fetch_data_only
else:

    class _DataOnlyFetcher(URLFetcher):
        """70 wants a URLFetcher, not a function: when a fetch raises it reads
        `_fail_on_errors` off the fetcher, so a bare function crashes the
        render on the first blocked URL instead of skipping it."""

        def fetch(self, url, headers=None):
            return _fetch_data_only(url)

    safe_url_fetcher = _DataOnlyFetcher(allowed_protocols={"data"})


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
