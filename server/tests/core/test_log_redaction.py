"""API keys some providers take in the query string never reach a log line."""
import logging
from pathlib import Path

import httpx
import pytest

from app.core import log_redaction

KEY = "not-a-real-key-0123456789"


@pytest.mark.parametrize("text, expected", [
    (f"GET https://www.searchapi.io/api/v1/search?engine=google_jobs&api_key={KEY}&q=COO",
     "GET https://www.searchapi.io/api/v1/search?engine=google_jobs&api_key=***&q=COO"),
    (f"https://serpapi.com/search.json?api_key={KEY}", "https://serpapi.com/search.json?api_key=***"),
    (f"https://maps.googleapis.com/x?KEY={KEY}&input=cafe", "https://maps.googleapis.com/x?KEY=***&input=cafe"),
    (f'GET https://a.test/?access_token={KEY} "HTTP/1.1 200 OK"', 'GET https://a.test/?access_token=*** "HTTP/1.1 200 OK"'),
    (f"https://b.s3.amazonaws.com/f?X-Amz-Credential={KEY}&X-Amz-Signature={KEY}",
     "https://b.s3.amazonaws.com/f?X-Amz-Credential=***&X-Amz-Signature=***"),
    # Meta's token exchange: the short-lived user token rides as `fb_exchange_token`.
    (f"https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=1"
     f"&client_secret={KEY}&fb_exchange_token={KEY}",
     "https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=1"
     "&client_secret=***&fb_exchange_token=***"),
    (f"https://a.test/?refresh_token={KEY}&id_token={KEY}", "https://a.test/?refresh_token=***&id_token=***"),
    # Not a secret parameter, or not a query parameter at all: left as it is.
    ("https://a.test/search?q=api_key&monkey=1", "https://a.test/search?q=api_key&monkey=1"),
    ("the api_key=abc was refused", "the api_key=abc was refused"),
])
def test_redact(text, expected):
    assert log_redaction.redact(text) == expected


def test_httpx_request_lines_are_redacted(caplog):
    log_redaction.install()
    log_redaction.install()  # once is enough, twice changes nothing
    logger = logging.getLogger("httpx")
    assert sum(isinstance(f, log_redaction.RedactSecretsFilter) for f in logger.filters) == 1
    url = httpx.URL("https://www.searchapi.io/api/v1/search", params={"api_key": KEY, "q": "COO"})
    with caplog.at_level(logging.INFO, logger="httpx"):
        # httpx's own call: `logger.info('HTTP Request: %s %s "%s %d %s"', ...)`
        logger.info('HTTP Request: %s %s "%s %d %s"', "GET", url, "HTTP/1.1", 429, "Too Many Requests")
        logger.info("no url here %s", "at all")
    assert KEY not in caplog.text
    assert "api_key=***&q=COO" in caplog.text and "no url here at all" in caplog.text


def test_a_malformed_record_is_passed_on():
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, "%d", ("not a number",), None)
    assert log_redaction.RedactSecretsFilter().filter(record) is True


def test_the_api_and_the_workers_install_it():
    app_dir = Path(__file__).resolve().parents[2] / "app"
    for module in ("main.py", "workers/celery_app.py"):
        assert "\nlog_redaction.install()\n" in (app_dir / module).read_text(), module
