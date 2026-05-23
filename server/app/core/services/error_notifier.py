"""Real-time email alerts for new server/client errors.

Hooked off the error reporters (`error_reporter.report_server_error` and
`routes/client_errors.report_client_error`). Sends to
`settings.error_alert_email` (empty disables alerts).

Spam control, three layers:
  1. Server errors only alert on a genuinely NEW fingerprint row (the
     reporter's daily-bucket fingerprint already means one alert per
     distinct error per day; repeat occurrences just bump a counter).
  2. Client errors have no DB dedup, so this module dedups in-process by a
     computed fingerprint with a 6h TTL.
  3. A global rolling-hour cap (`_MAX_PER_HOUR`) guards against a burst of
     distinct errors flooding the inbox during an incident.

Recursion safety: the email send sets the reporter's `_reporting` guard so a
failed send (which logs via the email client's own logger) can't create a new
server_error row that loops back into another alert. This module's own logger
is namespaced under `matcha.error_reporter.*`, which `ServerErrorDBHandler.emit`
already skips.
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import time
from typing import Optional

logger = logging.getLogger("matcha.error_reporter.notifier")
logger.propagate = False

# In-process dedup: fingerprint -> last-sent monotonic seconds.
_seen: dict[str, float] = {}
_DEDUP_TTL = 6 * 3600  # don't re-alert the same fingerprint within 6h

# Global flood guard: cap alert emails per rolling hour.
_sent_times: list[float] = []
_MAX_PER_HOUR = 10

# Hold refs to fire-and-forget send tasks so they aren't GC'd mid-flight.
_pending: set = set()

# Client API-error statuses that are normal user behavior, not bugs — never alert.
_USER_ERROR_STATUSES = {400, 401, 403, 404, 409, 422, 429}


def _should_send(fingerprint: str) -> bool:
    """Dedup + global rate cap. Returns True at most once per fingerprint per
    TTL, and never more than _MAX_PER_HOUR times per rolling hour."""
    now = time.monotonic()
    last = _seen.get(fingerprint)
    if last is not None and now - last < _DEDUP_TTL:
        return False
    cutoff = now - 3600
    _sent_times[:] = [t for t in _sent_times if t >= cutoff]
    if len(_sent_times) >= _MAX_PER_HOUR:
        logger.warning("error alert hourly cap (%d) hit; suppressing", _MAX_PER_HOUR)
        return False
    _seen[fingerprint] = now
    _sent_times.append(now)
    if len(_seen) > 500:  # opportunistic cleanup
        for k in [k for k, t in _seen.items() if now - t > _DEDUP_TTL]:
            _seen.pop(k, None)
    return True


def _admin_link() -> tuple[str, str]:
    from app.config import get_settings
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/admin/server-errors", f"{base}/admin/client-errors"


async def _send(subject: str, html_body: str, text_body: str) -> None:
    from app.config import get_settings
    to_email = (getattr(get_settings(), "error_alert_email", "") or "").strip()
    if not to_email:
        return
    # Recursion guard — suppress error reporting during the send.
    from .error_reporter import _reporting
    token = _reporting.set(True)
    try:
        from .email import get_email_service
        await get_email_service().send_email_with_fallback(
            to_email=to_email,
            to_name="Matcha Alerts",
            subject=subject,
            html_content=html_body,
            text_content=text_body,
        )
    except Exception as e:
        logger.warning("error alert send failed: %s", e)
    finally:
        _reporting.reset(token)


def _wrap_html(heading: str, rows: list[tuple[str, str]], body_text: str, link: str) -> str:
    cells = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#71717a;font-size:12px;'
        f'vertical-align:top;white-space:nowrap">{_html.escape(k)}</td>'
        f'<td style="padding:4px 0;color:#18181b;font-size:13px;'
        f'font-family:monospace;word-break:break-word">{_html.escape(v)}</td></tr>'
        for k, v in rows if v
    )
    body_block = ""
    if body_text:
        body_block = (
            '<pre style="background:#fafafa;border:1px solid #e4e4e7;border-radius:6px;'
            'padding:12px;font-size:11px;color:#3f3f46;overflow-x:auto;white-space:pre-wrap;'
            f'max-height:320px">{_html.escape(body_text[:4000])}</pre>'
        )
    return (
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px;margin:0 auto">'
        f'<h2 style="color:#dc2626;font-size:16px;margin:0 0 12px">⚠️ {_html.escape(heading)}</h2>'
        f'<table style="width:100%;border-collapse:collapse;margin-bottom:12px">{cells}</table>'
        f'{body_block}'
        f'<p style="margin-top:16px"><a href="{_html.escape(link)}" '
        'style="color:#059669;font-size:13px">Open in admin →</a></p>'
        '</div>'
    )


async def notify_server_error(row: dict) -> None:
    """Alert on a newly-inserted server_error_reports row."""
    fp = row.get("fingerprint") or ""
    if not _should_send(f"srv|{fp}"):
        return
    server_link, _ = _admin_link()
    exc = row.get("exception_type")
    msg = row.get("message") or ""
    heading = f"Server error: {row.get('kind') or 'error'}"
    subject = f"[Matcha] {(exc + ': ') if exc else ''}{msg}".strip()[:140]
    method = row.get("request_method") or ""
    path = row.get("request_path") or ""
    rows = [
        ("Kind", row.get("kind") or ""),
        ("Level", row.get("level") or ""),
        ("Type", exc or ""),
        ("Message", msg),
        ("Request", f"{method} {path}".strip()),
        ("Logger", row.get("logger_name") or ""),
        ("Source", row.get("source") or ""),
        ("Host", row.get("hostname") or ""),
        ("User", row.get("user_email") or row.get("user_id") or ""),
    ]
    html_body = _wrap_html(heading, rows, row.get("traceback") or "", server_link)
    text_body = f"{heading}\n{subject}\n{method} {path}\n\n{(row.get('traceback') or '')[:2000]}\n\n{server_link}"
    await _send(subject, html_body, text_body)


def notify_client_error(
    *,
    kind: str,
    message: str,
    url: Optional[str],
    api_endpoint: Optional[str],
    api_status_code: Optional[int],
    user_email: Optional[str],
) -> None:
    """Schedule an alert for a client error. Fire-and-forget; filters out
    expected user-facing errors (4xx API responses) so only real bugs page."""
    # Noise filter: skip expected user-facing API errors (login fails, 404s, etc.)
    if kind == "api_error" and api_status_code in _USER_ERROR_STATUSES:
        return
    fp = f"cli|{kind}|{(message or '')[:160]}|{api_endpoint or ''}|{api_status_code or ''}"
    if not _should_send(fp):
        return
    _, client_link = _admin_link()
    heading = f"Client error: {kind}"
    subject = f"[Matcha] Client {kind}: {message}".strip()[:140]
    rows = [
        ("Kind", kind),
        ("Message", message or ""),
        ("Page", url or ""),
        ("API", f"{api_endpoint or ''} ({api_status_code})" if api_endpoint else ""),
        ("User", user_email or ""),
    ]
    html_body = _wrap_html(heading, rows, "", client_link)
    text_body = f"{heading}\n{subject}\n{url or ''}\n{api_endpoint or ''} {api_status_code or ''}\n\n{client_link}"

    async def _run():
        await _send(subject, html_body, text_body)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_run())
        _pending.add(task)
        task.add_done_callback(_pending.discard)
    except RuntimeError:
        pass  # no running loop (shouldn't happen in the FastAPI request path)
