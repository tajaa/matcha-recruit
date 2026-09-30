"""Shared WeasyPrint helpers with an SSRF-safe URL fetcher.

WeasyPrint's default URL fetcher will resolve ANY scheme referenced in the HTML
it renders — including `file:///etc/passwd` (local-file disclosure into the PDF)
and `http://169.254.169.254/...` (cloud-metadata / IAM-credential SSRF). Several
PDF endpoints render user- or AI-authored HTML (project sections, handbooks,
offer letters, ER/IR/discipline docs), so any `<img src=...>` / `<link href=...>`
the author controls becomes a server-side fetch.

`SafeURLFetcher` refuses every remote/file scheme and allows only inline
`data:` URIs. Images are base64-inlined as `data:` *before* render in the paths
that need them, so legitimate assets are unaffected. This mirrors the original
one-off guard in `matcha/services/benefits_eligibility.py`.
"""

import asyncio

from weasyprint import HTML
from weasyprint.urls import URLFetcher

# Why a URLFetcher subclass and not a plain function: WeasyPrint 70 removed
# `default_url_fetcher` (from `weasyprint.urls` too, not only the top-level
# re-export), and its internal `fetch()` now reads `url_fetcher._fail_on_errors`
# when a fetch raises — a plain function has no such attribute, so the first
# blocked URL would crash the whole render instead of being skipped. A
# `URLFetcher` subclass works identically on 69 and 70.


class SafeURLFetcher(URLFetcher):
    """WeasyPrint fetcher that allows only inline `data:` URIs.

    Refuses `file://`, `http(s)://` (incl. cloud metadata at 169.254.169.254
    and RFC-1918 hosts), `ftp://`, etc. — to prevent SSRF and local-file
    disclosure when rendering attacker-influenced HTML. The refusal is a
    ValueError, which WeasyPrint catches: the resource is skipped with a
    warning and the rest of the document still renders.
    """

    def __init__(self):
        # WeasyPrint's own protocol allow-list is a second, independent guard;
        # no redirects, and a short timeout in case either is ever widened.
        super().__init__(allowed_protocols={"data"}, allow_redirects=False, timeout=5)

    def fetch(self, url, headers=None):
        if not str(url).startswith("data:"):
            raise ValueError(f"Blocked non-data URL in PDF render: {str(url)[:80]}")
        return super().fetch(url, headers)


def safe_url_fetcher(url: str):
    """Fetch `url` through a fresh `SafeURLFetcher` (only `data:` passes).

    A new instance per call: URLFetcher is a urllib OpenerDirector and keeps
    per-request state, and renders run concurrently on worker threads.
    """
    return SafeURLFetcher().fetch(url)


def render_pdf(html_string: str, **write_pdf_kwargs) -> bytes:
    """Render HTML to PDF bytes with the SSRF-safe fetcher applied.

    Drop-in replacement for `HTML(string=html).write_pdf()`. Extra kwargs
    (e.g. `stylesheets=[...]`) are forwarded to `write_pdf`.
    """
    return HTML(string=html_string, url_fetcher=SafeURLFetcher()).write_pdf(
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
