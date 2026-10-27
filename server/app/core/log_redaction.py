"""Secrets out of logged request URLs.

httpx logs every request at INFO as `HTTP Request: GET <url> "HTTP/1.1 200 OK"`.
Some APIs take their key in the query string (SearchAPI's and SerpApi's
`api_key`, Google's `key`), so on prod the worker log printed a live SearchAPI
key on every job search (found 2026-10-18). `RedactSecretsFilter` rewrites a
record's message with those parameters' values blanked, and `install()` puts it
on the loggers that print request URLs. The API (`app/main.py`) and the Celery
workers (`app/workers/celery_app.py`) both call it at start.

A logger's filter sees only the records logged on that exact logger, not its
children's, so the names are the ones those libraries log on.
"""
from __future__ import annotations

import logging
import re

# Loggers that print a request's full URL: httpx at INFO, urllib3 at DEBUG.
LOGGERS = ("httpx", "urllib3.connectionpool")

# `\w*_?token` covers every `…token` parameter: `access_token`, `refresh_token`
# and Meta's `fb_exchange_token`, which carries a live user token on every
# Gummfit social Connect.
_SECRET_PARAM = re.compile(
    r"(?i)([?&](?:api[_-]?key|key|\w*_?token|client_secret|secret|password|"
    r"sig|signature|x-amz-signature|x-amz-credential|x-amz-security-token)=)[^&\s\"'#]+"
)
REDACTED = "***"


def redact(text: str) -> str:
    """`text` with the value of every secret-bearing query parameter blanked."""
    return _SECRET_PARAM.sub(lambda match: match.group(1) + REDACTED, text)


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a malformed record is the logging module's to report
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def install() -> None:
    """Put the filter on `LOGGERS`, once each."""
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSecretsFilter) for f in logger.filters):
            logger.addFilter(RedactSecretsFilter())
