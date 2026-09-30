"""`app/core/services/pdf.py` — the SSRF guard on every PDF render.

Nine modules render PDFs through this helper, several of them over user- or
AI-authored HTML (handbooks, offer letters, ER/IR/discipline docs), so an
`<img src="file:///etc/passwd">` an author controls becomes a server-side
fetch unless `safe_url_fetcher` refuses it.

This file also pins the fetcher's SHAPE. WeasyPrint 70.0 removed
`default_url_fetcher` (from `weasyprint.urls` as well as the top-level
package), and its internal fetch loop reads `url_fetcher._fail_on_errors` when
a fetch raises — so a plain function both fails to import and would crash a
render on the first blocked URL. The guard is a `URLFetcher` subclass, which
works on 69 and 70 alike.

    cd server && ./venv/bin/python -m pytest tests/core/test_pdf_fetcher.py -q
"""

import pytest

from app.core.services import pdf


class TestImportContract:
    def test_fetcher_is_a_weasyprint_url_fetcher(self):
        # WeasyPrint 70 calls `url_fetcher(url)` and reads `._fail_on_errors`
        # on failure: only a URLFetcher instance satisfies both.
        from weasyprint.urls import URLFetcher

        fetcher = pdf.SafeURLFetcher()
        assert isinstance(fetcher, URLFetcher)
        assert fetcher._fail_on_errors is False
        assert callable(fetcher)

    def test_render_helpers_are_exported(self):
        assert callable(pdf.render_pdf)
        assert callable(pdf.safe_url_fetcher)


class TestSafeUrlFetcher:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "file:///Users/finch/.aws/credentials",
            # Cloud metadata — the credential-theft case.
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            "https://169.254.169.254/computeMetadata/v1/",
            # Ordinary SSRF into the private network.
            "http://127.0.0.1:8001/api/admin/companies",
            "http://10.0.0.5/",
            "https://example.com/tracker.png",
            "ftp://example.com/x",
        ],
    )
    def test_every_non_data_scheme_is_refused(self, url):
        with pytest.raises(ValueError) as excinfo:
            pdf.safe_url_fetcher(url)
        assert "Blocked non-data URL" in str(excinfo.value)

    def test_the_refusal_does_not_echo_an_unbounded_url(self):
        # The message is truncated so a huge data-bearing URL cannot be
        # smuggled wholesale into logs.
        with pytest.raises(ValueError) as excinfo:
            pdf.safe_url_fetcher("http://evil.test/" + "A" * 5000)
        assert len(str(excinfo.value)) < 200

    def test_inline_data_uris_are_allowed(self):
        # Images are base64-inlined before render, so `data:` must be fetched
        # for real — that is the one scheme the guard permits.
        tiny_png = "data:image/png;base64,iVBORw0KGgo="
        response = pdf.safe_url_fetcher(tiny_png)
        assert response.read() == b"\x89PNG\r\n\x1a\n"

    def test_weasyprint_allow_list_is_a_second_guard(self):
        # Even calling the base-class fetch directly (bypassing our prefix
        # check) refuses non-data schemes, via WeasyPrint's allowed_protocols.
        from weasyprint.urls import URLFetcher

        with pytest.raises(ValueError):
            URLFetcher.fetch(pdf.SafeURLFetcher(), "file:///etc/passwd")

    def test_scheme_check_is_not_a_substring_match(self):
        # "data:" has to START the URL; a remote URL that merely mentions it
        # must not slip through.
        with pytest.raises(ValueError):
            pdf.safe_url_fetcher("http://evil.test/redirect?to=data:image/png;base64,AAAA")


class TestRender:
    def test_blocked_resources_are_skipped_not_fatal(self):
        # The refusal is swallowed by WeasyPrint (resource skipped, warning
        # logged); the document still renders.
        html = (
            '<p>Letter <img src="http://169.254.169.254/latest/meta-data/">'
            '<img src="file:///etc/passwd"></p>'
        )
        assert pdf.render_pdf(html).startswith(b"%PDF")

    def test_each_render_gets_its_own_fetcher(self, monkeypatch):
        seen = []
        real = pdf.HTML

        def spy(*args, **kwargs):
            seen.append(kwargs["url_fetcher"])
            return real(*args, **kwargs)
        monkeypatch.setattr(pdf, "HTML", spy)
        pdf.render_pdf("<p>a</p>")
        pdf.render_pdf("<p>b</p>")
        assert len(seen) == 2 and seen[0] is not seen[1]
        assert all(isinstance(f, pdf.SafeURLFetcher) for f in seen)
