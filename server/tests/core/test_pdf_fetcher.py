"""`app/core/services/pdf.py` — the SSRF guard on every PDF render.

Nine modules render PDFs through this helper, several of them over user- or
AI-authored HTML (handbooks, offer letters, ER/IR/discipline docs), so an
`<img src="file:///etc/passwd">` an author controls becomes a server-side
fetch unless `safe_url_fetcher` refuses it.

This file also pins the import and a real render. WeasyPrint 70 removed
`default_url_fetcher` altogether (fetchers became `URLFetcher` objects), and
the 2026-09-30 backend image crash-looped the worker at import. `pdf.py` now
works on 69 and 70; the render test below also catches the quieter 70 break,
where a function fetcher that refuses a URL crashes the render.

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


class TestRealRender:
    def test_blocked_links_are_skipped_and_inline_images_render(self):
        # A 1x1 PNG, inlined the way the PDF paths inline their images.
        png = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGNgYPj/HwADAgH/eL9GtQAAAABJRU5ErkJggg=="
        )
        html = (
            f'<p>ok</p><img src="{png}">'
            '<img src="file:///etc/passwd"><img src="http://169.254.169.254/x">'
            '<link rel="stylesheet" href="http://evil.test/x.css">'
        )
        out = pdf.render_pdf(html)
        assert out.startswith(b"%PDF")
        assert b"root:" not in out


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
            pdf, "default_url_fetcher", lambda url: seen.setdefault("url", url)
        )
        tiny_png = "data:image/png;base64,iVBORw0KGgo="
        pdf.safe_url_fetcher(tiny_png)
        assert seen["url"] == tiny_png

    def test_scheme_check_is_not_a_substring_match(self):
        # "data:" has to START the URL; a remote URL that merely mentions it
        # must not slip through.
        with pytest.raises(ValueError):
            pdf.safe_url_fetcher("http://evil.test/redirect?to=data:image/png;base64,AAAA")


class TestBothWeasyPrintMajors:
    """CI installs one WeasyPrint; this loads pdf.py against the other API too."""

    def _load_with(self, monkeypatch, urls_module):
        import importlib.util
        import sys

        monkeypatch.setitem(sys.modules, "weasyprint.urls", urls_module)
        spec = importlib.util.spec_from_file_location("_pdf_under_test", pdf.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_69_uses_plain_function_fetchers(self, monkeypatch):
        import types

        seen = []
        urls = types.ModuleType("weasyprint.urls")
        urls.default_url_fetcher = lambda url: seen.append(url) or {"string": b""}
        module = self._load_with(monkeypatch, urls)
        assert module.URLFetcher is None
        assert module.safe_url_fetcher is module._fetch_data_only
        module.safe_url_fetcher("data:,x")
        assert seen == ["data:,x"]
        with pytest.raises(ValueError):
            module.safe_url_fetcher("file:///etc/passwd")

    def test_70_uses_a_url_fetcher_object(self, monkeypatch):
        import types

        class FakeURLFetcher:
            def __init__(self, allowed_protocols=None, **_kw):
                self.allowed_protocols = allowed_protocols

            def __call__(self, url):
                return self.fetch(url)

            def fetch(self, url, headers=None):
                return ("fetched", url)

        urls = types.ModuleType("weasyprint.urls")
        urls.URLFetcher = FakeURLFetcher
        module = self._load_with(monkeypatch, urls)
        assert isinstance(module.safe_url_fetcher, FakeURLFetcher)
        assert module.default_url_fetcher.allowed_protocols == {"data"}
        assert module.safe_url_fetcher("data:,x") == ("fetched", "data:,x")
        with pytest.raises(ValueError):
            module.safe_url_fetcher("http://169.254.169.254/")
