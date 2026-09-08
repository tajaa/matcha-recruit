"""`app/core/services/pdf.py` — the SSRF guard on every PDF render.

Nine modules render PDFs through this helper, several of them over user- or
AI-authored HTML (handbooks, offer letters, ER/IR/discipline docs), so an
`<img src="file:///etc/passwd">` an author controls becomes a server-side
fetch unless `safe_url_fetcher` refuses it.

This file also pins the import itself. `default_url_fetcher` used to be
imported from the top-level `weasyprint` package; WeasyPrint 70.0 dropped that
re-export and, because `requirements.txt` had an unbounded `weasyprint>=69.0`,
74 test modules stopped importing with no change on our side — and the next
backend image would have shipped a PDF path that raised at import. The symbol
now comes from its stable `weasyprint.urls` home, and a test that merely
imports this module is enough to catch the next move.

    cd server && ./venv/bin/python -m pytest tests/core/test_pdf_fetcher.py -q
"""

import pytest

from app.core.services import pdf


class TestImportContract:
    def test_module_exposes_a_callable_default_fetcher(self):
        # The regression that started this: an ImportError here took out 74
        # unrelated test modules at collection.
        assert callable(pdf.default_url_fetcher)

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

    def test_inline_data_uris_are_allowed(self, monkeypatch):
        # Images are base64-inlined before render, so `data:` must pass through
        # to the real fetcher — that is the one scheme the guard permits.
        seen = {}
        monkeypatch.setattr(
            pdf, "default_url_fetcher", lambda url: seen.setdefault("url", url) or {"string": b""}
        )
        tiny_png = "data:image/png;base64,iVBORw0KGgo="
        pdf.safe_url_fetcher(tiny_png)
        assert seen["url"] == tiny_png

    def test_scheme_check_is_not_a_substring_match(self):
        # "data:" has to START the URL; a remote URL that merely mentions it
        # must not slip through.
        with pytest.raises(ValueError):
            pdf.safe_url_fetcher("http://evil.test/redirect?to=data:image/png;base64,AAAA")
