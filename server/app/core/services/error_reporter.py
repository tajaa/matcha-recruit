"""Server-side error reporter — captures exceptions, HTTP 5xx, Celery failures,
background task errors, and explicit logger.error/exception calls from anywhere
in the app. Persists to server_error_reports with dedup + occurrence counting.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
import sys
import threading
import traceback as tb_module
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("matcha.error_reporter")
logger.propagate = False

_HOSTNAME = socket.gethostname()

_REDACT_KEYS = {
    "password", "passwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "authorization", "cookie", "session", "ssn", "credit_card",
    "card_number", "cvv", "stripe_secret", "gemini_api_key", "jwt_secret",
    "private_key", "client_secret",
}

# Contextvar-based recursion guard. Async-safe (unlike threading.local).
_reporting: ContextVar[bool] = ContextVar("error_reporting_active", default=False)

# Dedup window bucket — fingerprint includes current day so recurrences after
# a day create a new row (fix #8).
_DEDUP_BUCKET_HOURS = 24


def _redact(obj: Any, _depth: int = 0) -> Any:
    """Recursive redaction that handles dicts, lists, tuples, sets, and
    arbitrary objects with __dict__ (Pydantic, dataclass, etc.)."""
    if _depth > 6:
        return "[DEPTH_LIMIT]"
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() in _REDACT_KEYS else _redact(v, _depth + 1))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple, set)):
        return [_redact(x, _depth + 1) for x in obj]
    if hasattr(obj, "model_dump"):
        try:
            return _redact(obj.model_dump(), _depth + 1)
        except Exception:
            return repr(obj)[:500]
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        try:
            return _redact(vars(obj), _depth + 1)
        except Exception:
            return repr(obj)[:500]
    return obj


def _current_bucket() -> str:
    """Day bucket for dedup. Two errors with same fingerprint in the same day
    merge; a new day starts a fresh row so we can see recurrence after a fix."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d") if _DEDUP_BUCKET_HOURS == 24 else now.strftime("%Y-%m-%d-%H")


def _fingerprint(kind: str, exc_type: Optional[str], message: str, traceback_str: Optional[str]) -> str:
    top_frame = ""
    if traceback_str:
        for line in traceback_str.splitlines():
            stripped = line.strip()
            if stripped.startswith("File "):
                top_frame = stripped
                break
    head = (message or "")[:200]
    fp_input = f"{_current_bucket()}|{kind}|{exc_type or ''}|{head}|{top_frame}"
    return hashlib.sha1(fp_input.encode()).hexdigest()


# ── DB writes ────────────────────────────────────────────────────────────────

_INSERT_SQL = """
INSERT INTO server_error_reports (
    fingerprint, kind, level, logger_name, message,
    exception_type, traceback, source, hostname,
    request_method, request_path, request_status,
    user_id, user_email, context, occurrences, first_seen, last_seen
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9,
    $10, $11, $12, $13, $14, $15::jsonb, 1, NOW(), NOW()
)
ON CONFLICT (fingerprint) WHERE resolved_at IS NULL
DO UPDATE SET
    occurrences = server_error_reports.occurrences + 1,
    last_seen = NOW(),
    message = EXCLUDED.message,
    traceback = COALESCE(EXCLUDED.traceback, server_error_reports.traceback),
    context = COALESCE(EXCLUDED.context, server_error_reports.context),
    request_path = COALESCE(EXCLUDED.request_path, server_error_reports.request_path),
    request_method = COALESCE(EXCLUDED.request_method, server_error_reports.request_method)
"""


def _row_args(row: dict) -> tuple:
    return (
        row["fingerprint"], row["kind"], row["level"], row["logger_name"], row["message"],
        row["exception_type"], row["traceback"], row["source"], row["hostname"],
        row["request_method"], row["request_path"], row["request_status"],
        row["user_id"], row["user_email"], row["context_json"],
    )


async def _upsert_async(row: dict) -> None:
    from ...database import get_connection  # lazy: avoid circular import at module load
    async with get_connection() as conn:
        await conn.execute(_INSERT_SQL, *_row_args(row))


def _upsert_sync_celery(row: dict) -> None:
    """Sync path for Celery workers — create a dedicated short-lived loop.
    Runs completely outside any running loop so it's safe for sync contexts."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_upsert_async(row))
    finally:
        loop.close()


async def _safe_async_upsert(row: dict) -> None:
    try:
        await _upsert_async(row)
    except Exception as e:
        # Last-resort: print to stderr so startup / DB-down errors aren't lost.
        sys.stderr.write(f"[error_reporter] failed to persist: {e}\n")


# ── Public API ───────────────────────────────────────────────────────────────


def report_server_error(
    *,
    kind: str,
    message: str,
    exception: Optional[BaseException] = None,
    traceback_str: Optional[str] = None,
    source: str = "api",
    level: str = "ERROR",
    logger_name: Optional[str] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    request_status: Optional[int] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    context: Optional[dict] = None,
) -> None:
    """Fire-and-forget error report. Never raises."""
    if _reporting.get():
        return
    token = _reporting.set(True)
    try:
        if exception is not None and not traceback_str:
            traceback_str = "".join(
                tb_module.format_exception(type(exception), exception, exception.__traceback__)
            )
        exc_type_name = type(exception).__name__ if exception is not None else None
        fp = _fingerprint(kind, exc_type_name, message, traceback_str)

        context_json: Optional[str] = None
        if context:
            try:
                serialized = json.dumps(_redact(context), default=str)
                if len(serialized) > 10_000:
                    serialized = json.dumps({"_truncated": True, "_bytes": len(serialized)})
                context_json = serialized
            except Exception:
                context_json = None

        row = {
            "fingerprint": fp,
            "kind": kind,
            "level": level,
            "logger_name": logger_name,
            "message": (message or "")[:4000],
            "exception_type": exc_type_name,
            "traceback": traceback_str[:20000] if traceback_str else None,
            "source": source,
            "hostname": _HOSTNAME,
            "request_method": request_method,
            "request_path": request_path,
            "request_status": request_status,
            "user_id": user_id,
            "user_email": user_email,
            "context_json": context_json,
        }

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # On the event loop: schedule fire-and-forget
            loop.create_task(_safe_async_upsert(row))
        else:
            # No running loop (Celery worker, sync CLI): short-lived loop
            try:
                _upsert_sync_celery(row)
            except Exception as e:
                sys.stderr.write(f"[error_reporter] sync persist failed: {e}\n")
    except Exception as e:
        sys.stderr.write(f"[error_reporter] report_server_error crashed: {e}\n")
    finally:
        _reporting.reset(token)


# ── Logging handler ──────────────────────────────────────────────────────────


_IGNORED_LOGGERS = {
    "uvicorn.access",
    "watchfiles.main",
    "watchfiles",
    "matcha.error_reporter",
}


def _classify_kind(logger_name: str, message: str, exc_type: Optional[str], source: str) -> str:
    lname = (logger_name or "").lower()
    et = (exc_type or "").lower()
    msg_low = (message or "").lower()

    if source == "celery" or "celery" in lname:
        return "celery_task"
    if "postgres" in et or "asyncpg" in lname or "asyncpg" in et or "integrityerror" in et:
        return "db_error"
    if "startup" in lname or "lifespan" in lname:
        return "startup"
    if "worker" in lname or "background" in lname or "scheduler" in lname:
        return "background_task"
    if "http" in lname and "5" in msg_low:
        return "http_error"
    if exc_type:
        return "exception"
    return "unhandled"


class ServerErrorDBHandler(logging.Handler):
    """Captures ERROR+ log records and persists them. Attach to root logger."""

    def __init__(self, source: str = "api"):
        super().__init__(level=logging.ERROR)
        self.source = source

    def emit(self, record: logging.LogRecord) -> None:
        if record.name in _IGNORED_LOGGERS:
            return
        if record.name.startswith("matcha.error_reporter"):
            return
        try:
            message = record.getMessage()
            traceback_str = None
            exception = None
            exc_type_name = None
            if record.exc_info:
                exc_type, exc_val, exc_tb = record.exc_info
                exception = exc_val
                exc_type_name = exc_type.__name__ if exc_type else None
                traceback_str = "".join(tb_module.format_exception(exc_type, exc_val, exc_tb))

            kind = _classify_kind(record.name, message, exc_type_name, self.source)
            report_server_error(
                kind=kind,
                message=message,
                exception=exception,
                traceback_str=traceback_str,
                source=self.source,
                level=record.levelname,
                logger_name=record.name,
            )
        except Exception:
            pass


def install_error_logging(source: str = "api") -> ServerErrorDBHandler:
    """Attach the DB handler to the root logger. Idempotent."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, ServerErrorDBHandler):
            return h
    handler = ServerErrorDBHandler(source=source)
    root.addHandler(handler)
    return handler
