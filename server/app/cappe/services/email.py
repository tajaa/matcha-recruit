"""Cappe transactional email — reuses the platform email service.

Cappe is its own product but shares matcha's Gmail/MailerSend sender (and its
reserved-domain guard, so sends to @example.com / *.test are skipped). Called
as a FastAPI background task so account creation never blocks on SMTP.
"""
import logging
import os
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from ...core.services.email import _is_reserved_test_domain
from ...core.services.email.client import get_email_service

logger = logging.getLogger(__name__)

# Cappe shares Matcha's sender address but not its brand: without this every
# Gummfit email arrives signed with Matcha's display name.
_FROM_NAME = "Gummfit"


async def send_cappe_shopper_code_email(to_email: str, site_name: str, code: str):
    html = _email_shell(
        f"Sign in to {escape(site_name)}",
        f"<p>Your sign-in code is <strong>{escape(code)}</strong>.</p>"
        "<p>It expires in 10 minutes. If you did not request this code, ignore this email.</p>",
        footer=site_name,
    )
    await _send(to_email, None, f"Your sign-in code — {site_name}", html,
                f"Your code: {code}. Expires in 10 minutes.", label="shopper sign-in")


def _base_url() -> str:
    return f"https://{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}"


_DASHBOARD_URL = f"{_base_url()}/cappe"


def app_origin() -> str:
    """Scheme + host the Cappe SPA is served from (no path)."""
    return _base_url()


def dashboard_url(path: str = "") -> str:
    """Absolute creator-dashboard URL, e.g. dashboard_url(f"/sites/{id}/orders")."""
    return f"{_DASHBOARD_URL}{path}"


def booking_manage_url(token: str) -> str:
    """Customer-facing self-serve link for a booking (view/cancel/reschedule)."""
    return f"{_base_url()}/cappe/booking/{token}"


def thread_url(token: str) -> str:
    """Client-facing link to the public message thread page."""
    return f"{_base_url()}/cappe/thread/{token}"


def suggestion_access_url(origin: str, token: str) -> str:
    """Tenant-host URL with the secret in the fragment, never sent in a request."""
    return f"{origin.rstrip('/')}/__cappe/booking-suggestions/access#{token}"


async def send_cappe_booking_suggestion_access_email(
    to_email: str,
    to_name: str | None,
    site_name: str,
    access_url: str,
) -> None:
    """Send a short-lived link that unlocks AI suggestions for an existing client."""
    name = (to_name or "there").strip()
    greeting = f"Hi {name}," if to_name else "Hi there,"
    e_site = escape(site_name or "this site")
    html = _email_shell(
        f"Find a time with {e_site}",
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#a1a1aa;">'
        f"{escape(greeting)} We found your client record. Use this link to ask for AI-matched open times.</p>"
        f'<p style="margin:0;font-size:12px;line-height:1.6;color:#71717a;">'
        "The link expires in 15 minutes and works once.</p>",
        cta_label="Find open times",
        cta_url=access_url,
        footer=site_name or "Cappe",
    )
    text = (
        f"{greeting}\n\nUse this link to ask for AI-matched open times at {site_name}:\n"
        f"{access_url}\n\nThis link expires in 15 minutes and works once."
    )
    await _send(
        to_email,
        to_name,
        f"Your booking access link — {site_name}",
        html,
        text,
        label="booking suggestion access",
    )

_CCY_SYMBOL = {"USD": "$", "CAD": "$", "AUD": "$", "EUR": "€", "GBP": "£"}


# ── pure helpers (unit-tested in tests/cappe/test_cappe_email_payloads.py) ────

def fmt_money(cents: int | None, currency: str = "USD") -> str:
    """Display a cent amount, e.g. 4000 → "$40.00". Unknown currencies get the
    ISO code suffix instead of a symbol."""
    ccy = (currency or "USD").upper()
    val = f"{(cents or 0) / 100:,.2f}"
    sym = _CCY_SYMBOL.get(ccy)
    return f"{sym}{val}" if sym else f"{val} {ccy}"


def build_order_items_summary(items) -> str:
    """One-line "2× Print, 1× Session" summary from order line dicts
    ({title, quantity})."""
    parts = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        qty = it.get("quantity") or 1
        title = (it.get("title") or "Item").strip()
        parts.append(f"{qty}× {title}")
    return ", ".join(parts)


def format_when(dt: datetime, tz_name: str | None) -> str:
    """Friendly local time with its zone, e.g. "Mon, Jun 15 · 4:00 PM EDT",
    rendered in the booking's timezone (falls back to the datetime's own zone
    if tz is bad/missing).

    The zone is part of the text because a time without one is ambiguous to
    anyone not standing in the shop — and because a site still on its default
    UTC says so, instead of quietly showing a customer the wrong hour."""
    try:
        if tz_name:
            dt = dt.astimezone(ZoneInfo(tz_name))
    except Exception:  # bad tz string → leave dt as-is
        pass
    return dt.strftime("%a, %b %d · %-I:%M %p %Z").strip()


# ── shared email shell ───────────────────────────────────────────────────────

def _email_shell(
    heading: str, body_html: str, *, cta_label: str | None = None,
    cta_url: str | None = None, accent: str = "#c6f16b", footer: str = "Gummfit",
) -> str:
    """Full HTML document matching the existing Cappe transactional style.
    `heading` and `body_html` MUST already be escaped by the caller; `cta_url`
    is escaped here for the href."""
    cta = ""
    if cta_label and cta_url:
        cta = (
            f'<a href="{escape(cta_url, quote=True)}" style="display:inline-block;'
            f"background:{accent};color:#10120a;text-decoration:none;font-weight:600;"
            f'font-size:14px;padding:12px 22px;border-radius:10px;margin-top:8px;">{escape(cta_label)}</a>'
        )
    return f"""\
<!doctype html>
<html>
<body style="margin:0;background:#0b0b0d;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:40px 24px;">
    <div style="background:#18181b;border:1px solid #27272a;border-radius:16px;padding:32px;color:#e4e4e7;">
      <h1 style="margin:0 0 16px;font-size:20px;color:#fafafa;">{heading}</h1>
      {body_html}
      {cta}
    </div>
    <p style="text-align:center;margin:20px 0 0;font-size:12px;color:#52525b;">{escape(footer)}</p>
  </div>
</body>
</html>"""


async def _send(
    to_email: str, to_name: str | None, subject: str, html: str, text: str, *,
    label: str, log_recipient: bool = True, critical: bool = False,
) -> bool:
    """Best-effort send — logs and swallows so it's safe in a background task.

    Returns whether the message was actually handed to a provider.
    `send_email_with_fallback` reports failure by returning False (both
    providers down, or a blocked recipient), not by raising, so a caller that
    needs to retry or count failures must read this value. `log_recipient=False`
    keeps the address out of the log for callers that log by row id instead.

    `critical=True` is for mail the recipient is stranded without (the
    confirmation link): an undelivered one is logged at ERROR so it lands in
    `server_error_reports` instead of vanishing. Reserved test domains are
    skipped by design and are not a failure.
    """
    who = to_email if log_recipient else "<recipient>"
    try:
        ok = await get_email_service().send_email_with_fallback(
            to_email=to_email, to_name=to_name, subject=subject,
            html_content=html, text_content=text, from_name=_FROM_NAME,
        )
    except Exception:
        logger.exception("Cappe %s email failed for %s", label, who)
        return False
    if not ok and critical and not _is_reserved_test_domain(to_email):
        logger.error("Cappe %s email was not delivered to %s (no provider accepted it)", label, who)
    return bool(ok)


async def send_cappe_verification_email(to_email: str, to_name: str | None, token: str) -> None:
    """Send the email-confirmation link. This is the anti-spam gate — the
    account can't be used until the recipient clicks through, so a bogus or
    unreachable address never becomes a live account. Best-effort: logs and
    swallows failures (the user can request a resend)."""
    verify_url = f"{_base_url()}/cappe/verify?token={token}"
    greeting = f"Hi {to_name}," if to_name else "Welcome!"  # plaintext
    greeting_html = f"Hi {escape(to_name)}," if to_name else "Welcome!"  # name is user-controlled
    html = f"""\
<!doctype html>
<html>
<body style="margin:0;background:#0b0b0d;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:40px 24px;">
    <div style="text-align:center;margin-bottom:28px;">
      <span style="display:inline-block;width:44px;height:44px;line-height:44px;border-radius:12px;
                   background:linear-gradient(135deg,#bef264,#84cc16);color:#10120a;font-size:20px;
                   font-weight:700;text-align:center;">G</span>
    </div>
    <div style="background:#18181b;border:1px solid #27272a;border-radius:16px;padding:32px;color:#e4e4e7;">
      <h1 style="margin:0 0 12px;font-size:22px;color:#fafafa;">Confirm your email</h1>
      <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#a1a1aa;">{greeting_html}</p>
      <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#a1a1aa;">
        One click and your Gummfit account is live — then you can build your site, add what you
        sell, and publish.
      </p>
      <a href="{verify_url}" style="display:inline-block;background:#c6f16b;color:#10120a;
         text-decoration:none;font-weight:600;font-size:14px;padding:12px 22px;border-radius:10px;">
        Confirm my email
      </a>
      <p style="margin:20px 0 0;font-size:12px;line-height:1.6;color:#71717a;">
        Or paste this link into your browser:<br>
        <span style="color:#a1a1aa;word-break:break-all;">{verify_url}</span>
      </p>
      <p style="margin:16px 0 0;font-size:12px;line-height:1.6;color:#71717a;">
        This link expires in 24 hours. If you didn't sign up, ignore this email.
      </p>
    </div>
    <p style="text-align:center;margin:20px 0 0;font-size:12px;color:#52525b;">Gummfit</p>
  </div>
</body>
</html>"""
    text = (
        f"{greeting}\n\nConfirm your email to activate your Gummfit account:\n{verify_url}\n\n"
        "This link expires in 24 hours. If you didn't sign up, ignore this email."
    )
    await _send(to_email, to_name, "Confirm your email for Gummfit", html, text,
                label="verification", critical=True)


async def send_cappe_message_email(
    to_email: str, to_name: str | None, site_name: str, snippet: str, link: str, from_label: str
) -> None:
    """Notify a recipient (client or creator) of a new message in a thread, with
    a link to read + reply. Best-effort."""
    raw = (snippet or "").strip()
    if len(raw) > 240:
        raw = raw[:240] + "…"
    # All four values are user-controlled (message body, site/sender names, and
    # a DB-derived link) → escape before embedding in the HTML email body.
    safe = escape(raw)
    e_from = escape(from_label or "")
    e_site = escape(site_name or "")
    e_link = escape(link or "", quote=True)  # sits inside a double-quoted href
    html = f"""\
<!doctype html>
<html>
<body style="margin:0;background:#0b0b0d;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:40px 24px;">
    <div style="background:#18181b;border:1px solid #27272a;border-radius:16px;padding:32px;color:#e4e4e7;">
      <p style="margin:0 0 6px;font-size:13px;color:#a1a1aa;">New message from {e_from}</p>
      <h1 style="margin:0 0 16px;font-size:20px;color:#fafafa;">{e_site}</h1>
      <div style="border-left:3px solid #c6f16b;padding:8px 0 8px 14px;margin:0 0 20px;color:#d4d4d8;font-size:15px;line-height:1.6;">
        {safe}
      </div>
      <a href="{e_link}" style="display:inline-block;background:#c6f16b;color:#10120a;
         text-decoration:none;font-weight:600;font-size:14px;padding:12px 22px;border-radius:10px;">
        Read &amp; reply
      </a>
    </div>
    <p style="text-align:center;margin:20px 0 0;font-size:12px;color:#52525b;">Gummfit</p>
  </div>
</body>
</html>"""
    text = f"New message from {from_label} ({site_name}):\n\n{raw}\n\nRead & reply: {link}"
    await _send(to_email, to_name, f"New message — {site_name}", html, text, label="message")


async def send_cappe_welcome_email(to_email: str, to_name: str | None) -> None:
    """Send the signup confirmation / welcome email. Best-effort: logs and
    swallows failures so it's safe to fire from a background task."""
    greeting = f"Hi {to_name}," if to_name else "Welcome!"  # plaintext
    greeting_html = f"Hi {escape(to_name)}," if to_name else "Welcome!"  # name is user-controlled
    html = f"""\
<!doctype html>
<html>
<body style="margin:0;background:#0b0b0d;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:40px 24px;">
    <div style="text-align:center;margin-bottom:28px;">
      <span style="display:inline-block;width:44px;height:44px;line-height:44px;border-radius:12px;
                   background:linear-gradient(135deg,#34d399,#059669);color:#0b0b0d;font-size:20px;
                   font-weight:700;text-align:center;">C</span>
    </div>
    <div style="background:#18181b;border:1px solid #27272a;border-radius:16px;padding:32px;color:#e4e4e7;">
      <h1 style="margin:0 0 12px;font-size:22px;color:#fafafa;">Your Cappe account is ready</h1>
      <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#a1a1aa;">{greeting_html}</p>
      <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#a1a1aa;">
        Thanks for signing up for Cappe — the simplest way to build, design, and launch your website.
        Pick a template, customize it in the editor, and publish when you're ready.
      </p>
      <a href="{_DASHBOARD_URL}" style="display:inline-block;background:#10b981;color:#0b0b0d;
         text-decoration:none;font-weight:600;font-size:14px;padding:12px 22px;border-radius:10px;">
        Open your dashboard
      </a>
      <p style="margin:24px 0 0;font-size:12px;line-height:1.6;color:#71717a;">
        If you didn't create this account, you can safely ignore this email.
      </p>
    </div>
    <p style="text-align:center;margin:20px 0 0;font-size:12px;color:#52525b;">Built with Cappe</p>
  </div>
</body>
</html>"""
    text = (
        f"{greeting}\n\nYour Cappe account is ready. Pick a template, customize it, and "
        f"publish your website.\n\nOpen your dashboard: {_DASHBOARD_URL}\n\n"
        "If you didn't create this account, you can safely ignore this email."
    )
    await _send(to_email, to_name, "Welcome to Cappe — your account is ready", html, text,
                label="welcome")


# ── transactional: orders ────────────────────────────────────────────────────

async def send_cappe_order_receipt_email(
    to_email: str, to_name: str | None, site_name: str, items_summary: str,
    total_cents: int, currency: str, requires_approval: bool,
) -> None:
    """Self-contained order confirmation / receipt for the customer (no external
    page needed — the email is the receipt). Best-effort."""
    e_site, e_items, total = escape(site_name or ""), escape(items_summary or ""), fmt_money(total_cents, currency)
    next_line = (
        "The seller will review your order and confirm by email."
        if requires_approval else "Your order is confirmed — you'll hear from the seller with next steps."
    )
    body = (
        f'<p style="margin:0 0 6px;font-size:13px;color:#a1a1aa;">Thanks for your order from {e_site}.</p>'
        f'<div style="border:1px solid #27272a;border-radius:10px;padding:14px 16px;margin:14px 0;color:#d4d4d8;font-size:15px;">'
        f'<div style="margin-bottom:8px;">{e_items}</div>'
        f'<div style="font-weight:700;color:#fafafa;font-size:17px;">Total: {escape(total)}</div></div>'
        f'<p style="margin:0;font-size:13px;line-height:1.6;color:#a1a1aa;">{next_line}</p>'
    )
    html = _email_shell(f"Order received — {e_site}", body, accent="#10b981")
    text = f"Thanks for your order from {site_name}.\n\n{items_summary}\nTotal: {total}\n\n{next_line}"
    await _send(to_email, to_name, f"Your order — {site_name}", html, text, label="order receipt")


async def send_cappe_order_alert_email(
    to_email: str, to_name: str | None, site_name: str, customer_name: str | None,
    total_cents: int, currency: str, dashboard_url: str,
) -> None:
    """'New order' alert to the creator. Best-effort."""
    e_site, who, total = escape(site_name or ""), escape((customer_name or "A customer").strip() or "A customer"), fmt_money(total_cents, currency)
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{who}</b> placed an order for <b style="color:#fafafa;">{escape(total)}</b> on {e_site}.</p>'
        f'<p style="margin:14px 0 0;font-size:13px;color:#a1a1aa;">Open your dashboard to review and fulfill it.</p>'
    )
    html = _email_shell(f"New order — {e_site}", body, cta_label="View order", cta_url=dashboard_url)
    text = f"{customer_name or 'A customer'} placed an order for {total} on {site_name}.\n\nReview it: {dashboard_url}"
    await _send(to_email, to_name, f"New order — {site_name}", html, text, label="order alert")


async def send_cappe_low_stock_email(
    to_email: str, to_name: str | None, site_name: str,
    items: list[tuple[str, int]], dashboard_url: str,
) -> None:
    """Low-stock alert to the creator after a sale drops stock to/below the
    product's threshold. `items` = [(product name, remaining)]. Best-effort."""
    e_site = escape(site_name or "")
    rows = "".join(
        f'<li style="margin:2px 0;"><b style="color:#fafafa;">{escape(str(n))}</b> — '
        f'{int(bal)} left</li>'
        for n, bal in items
    )
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;color:#d4d4d8;">A sale on {e_site} left these low on stock:</p>'
        f'<ul style="margin:8px 0 0;padding-left:18px;color:#d4d4d8;font-size:14px;">{rows}</ul>'
    )
    html = _email_shell(f"Low stock — {e_site}", body, cta_label="Manage inventory",
                        cta_url=dashboard_url, accent="#f59e0b")
    text = "Low stock on {0}:\n{1}\n\nManage: {2}".format(
        site_name, "\n".join(f"- {n}: {bal} left" for n, bal in items), dashboard_url
    )
    await _send(to_email, to_name, f"Low stock — {site_name}", html, text, label="low stock")


# ── transactional: bookings ──────────────────────────────────────────────────

async def send_cappe_booking_received_email(
    to_email: str, to_name: str | None, site_name: str, type_name: str,
    when_label: str, requires_approval: bool, manage_url: str | None = None,
) -> None:
    """Booking confirmation / 'request received' for the customer. Best-effort."""
    e_site, e_type, e_when = escape(site_name or ""), escape(type_name or "Booking"), escape(when_label or "")
    lead = (
        "Your request was received and is pending the host's approval — you'll get an email once it's confirmed."
        if requires_approval else "Your booking is confirmed. We look forward to seeing you."
    )
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">{lead}</p>'
        f'<div style="border-left:3px solid #c6f16b;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{e_type}</b><br><span style="color:#a1a1aa;">{e_when}</span></div>'
    )
    html = _email_shell(f"Booking with {e_site}", body, cta_label="Manage booking" if manage_url else None, cta_url=manage_url)
    text = f"{lead}\n\n{type_name} — {when_label}" + (f"\n\nManage: {manage_url}" if manage_url else "")
    subj = "Booking request received" if requires_approval else "Booking confirmed"
    await _send(to_email, to_name, f"{subj} — {site_name}", html, text, label="booking received")


async def send_cappe_booking_alert_email(
    to_email: str, to_name: str | None, site_name: str, customer_name: str | None,
    type_name: str, when_label: str, requires_approval: bool, dashboard_url: str,
) -> None:
    """'New booking' alert to the creator. Best-effort."""
    e_site, who = escape(site_name or ""), escape((customer_name or "Someone").strip() or "Someone")
    tail = " — needs your approval" if requires_approval else ""
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{who}</b> requested a booking on {e_site}{escape(tail)}.</p>'
        f'<div style="border-left:3px solid #c6f16b;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{escape(type_name or "Booking")}</b><br><span style="color:#a1a1aa;">{escape(when_label or "")}</span></div>'
    )
    html = _email_shell(f"New booking — {e_site}", body, cta_label="View booking", cta_url=dashboard_url)
    text = f"{customer_name or 'Someone'} requested {type_name} — {when_label} on {site_name}{tail}.\n\nReview: {dashboard_url}"
    await _send(to_email, to_name, f"New booking — {site_name}", html, text, label="booking alert")


async def send_cappe_booking_decision_email(
    to_email: str, to_name: str | None, site_name: str, approved: bool,
    when_label: str, type_name: str, decline_reason: str | None = None,
) -> None:
    """Tell the customer their pending booking was approved or declined. Best-effort."""
    e_site, e_when, e_type = escape(site_name or ""), escape(when_label or ""), escape(type_name or "Booking")
    if approved:
        body = (
            f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">Good news — your booking with {e_site} is confirmed.</p>'
            f'<div style="border-left:3px solid #10b981;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
            f'<b>{e_type}</b><br><span style="color:#a1a1aa;">{e_when}</span></div>'
        )
        subj, heading = f"Booking confirmed — {site_name}", f"Booking confirmed — {e_site}"
        text = f"Your booking with {site_name} is confirmed.\n\n{type_name} — {when_label}"
    else:
        reason = f'<p style="margin:12px 0 0;font-size:13px;color:#a1a1aa;">Reason: {escape(decline_reason)}</p>' if decline_reason else ""
        body = (
            f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
            f'Unfortunately your booking request with {e_site} ({e_type}, {e_when}) couldn\'t be confirmed.</p>{reason}'
        )
        subj, heading = f"Booking update — {site_name}", f"Booking update — {e_site}"
        text = f"Your booking request with {site_name} ({type_name}, {when_label}) couldn't be confirmed." + (f"\nReason: {decline_reason}" if decline_reason else "")
    html = _email_shell(heading, body, accent="#10b981" if approved else "#c6f16b")
    await _send(to_email, to_name, subj, html, text, label="booking decision")


# ── transactional: forms ─────────────────────────────────────────────────────

async def send_cappe_form_alert_email(
    to_email: str, to_name: str | None, site_name: str, form_name: str, dashboard_url: str,
) -> None:
    """'New form submission' alert to the creator. The submission content is NOT
    echoed (untrusted) — the creator opens the dashboard to read it. Best-effort."""
    e_site, e_form = escape(site_name or ""), escape(form_name or "your form")
    body = (
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'You have a new submission to <b style="color:#fafafa;">{e_form}</b> on {e_site}.</p>'
    )
    html = _email_shell(f"New submission — {e_site}", body, cta_label="View submission", cta_url=dashboard_url)
    text = f"New submission to {form_name} on {site_name}.\n\nView it: {dashboard_url}"
    await _send(to_email, to_name, f"New form submission — {site_name}", html, text, label="form alert")


async def send_cappe_booking_reminder_email(
    to_email: str, to_name: str | None, site_name: str, type_name: str,
    when_label: str, manage_url: str | None = None,
) -> bool:
    """24h-ahead reminder to the customer. Returns whether a provider took it,
    so the worker can give the reminder back for another try when none did."""
    e_site, e_type, e_when = escape(site_name or ""), escape(type_name or "Booking"), escape(when_label or "")
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">A quick reminder of your upcoming booking with {e_site}.</p>'
        f'<div style="border-left:3px solid #c6f16b;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{e_type}</b><br><span style="color:#a1a1aa;">{e_when}</span></div>'
    )
    html = _email_shell(f"Reminder — {e_site}", body, cta_label="Manage booking" if manage_url else None, cta_url=manage_url)
    text = f"Reminder: your booking with {site_name} — {type_name}, {when_label}." + (f"\nManage: {manage_url}" if manage_url else "")
    return await _send(to_email, to_name, f"Reminder: your booking with {site_name}", html, text, label="booking reminder")


_PAID_BOOKING_NOTE = (
    "This booking was paid for in your shop. Cancelling it did not refund the "
    "customer — refund the order from Orders if your policy allows."
)


async def send_cappe_booking_cancelled_email(
    to_email: str, to_name: str | None, site_name: str, customer_name: str | None,
    type_name: str, when_label: str, dashboard_url: str, paid: bool = False,
) -> None:
    """Alert the creator that a customer cancelled. `paid` adds that the
    booking's order took money and has not been refunded. Best-effort."""
    e_site, who = escape(site_name or ""), escape((customer_name or "A customer").strip() or "A customer")
    note = (
        f'<p style="margin:14px 0 0;font-size:13px;line-height:1.6;color:#fbbf24;">{escape(_PAID_BOOKING_NOTE)}</p>'
        if paid else ""
    )
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{who}</b> cancelled their booking on {e_site}.</p>'
        f'<div style="border-left:3px solid #71717a;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{escape(type_name or "Booking")}</b><br><span style="color:#a1a1aa;">{escape(when_label or "")}</span></div>'
        f"{note}"
    )
    html = _email_shell(f"Booking cancelled — {e_site}", body, cta_label="View bookings", cta_url=dashboard_url)
    text = (
        f"{customer_name or 'A customer'} cancelled {type_name} — {when_label} on {site_name}."
        + (f"\n\n{_PAID_BOOKING_NOTE}" if paid else "")
        + f"\n\n{dashboard_url}"
    )
    await _send(to_email, to_name, f"Booking cancelled — {site_name}", html, text, label="booking cancelled")


async def send_cappe_booking_cancelled_by_host_email(
    to_email: str, to_name: str | None, site_name: str, type_name: str, when_label: str,
) -> None:
    """Tell the customer the BUSINESS cancelled their booking. There was no
    email for this at all: the slot vanished and the customer turned up.
    Best-effort."""
    e_site, e_type, e_when = escape(site_name or ""), escape(type_name or "Booking"), escape(when_label or "")
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f"{e_site} has cancelled your booking.</p>"
        f'<div style="border-left:3px solid #71717a;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{e_type}</b><br><span style="color:#a1a1aa;">{e_when}</span></div>'
        f'<p style="margin:14px 0 0;font-size:13px;color:#a1a1aa;">If you have questions, reply to the business directly.</p>'
    )
    html = _email_shell(f"Booking cancelled — {e_site}", body)
    text = f"{site_name} has cancelled your booking: {type_name} — {when_label}."
    await _send(to_email, to_name, f"Your booking was cancelled — {site_name}", html, text, label="booking cancelled by host")


async def send_cappe_booking_rescheduled_email(
    to_email: str, to_name: str | None, site_name: str, type_name: str,
    old_when: str, new_when: str, *, for_owner: bool, needs_approval: bool,
    link: str | None, customer_name: str | None = None,
) -> None:
    """A booking moved to a new time — to the customer (with their manage
    link) or to the owner (with the dashboard). A reschedule used to tell
    nobody, so the owner learned of it when the customer turned up at the new
    time. Best-effort."""
    e_site, e_type = escape(site_name or ""), escape(type_name or "Booking")
    if for_owner:
        who = escape((customer_name or "A customer").strip() or "A customer")
        lead = f'<b style="color:#fafafa;">{who}</b> moved their booking on {e_site}.'
        if needs_approval:
            lead += " It needs your approval again."
        subject, cta = f"Booking moved — {site_name}", "View bookings"
    else:
        lead = f"Your booking with {e_site} has moved."
        if needs_approval:
            lead += " The new time is waiting for the host's approval — you'll get an email once it's confirmed."
        subject, cta = f"Booking moved — {site_name}", "Manage booking"
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">{lead}</p>'
        f'<div style="border-left:3px solid #c6f16b;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{e_type}</b><br><span style="color:#a1a1aa;text-decoration:line-through;">{escape(old_when or "")}</span>'
        f'<br><span style="color:#fafafa;">{escape(new_when or "")}</span></div>'
    )
    html = _email_shell(f"Booking moved — {e_site}", body, cta_label=cta if link else None, cta_url=link)
    plain_lead = (
        f"{customer_name or 'A customer'} moved their booking on {site_name}." if for_owner
        else f"Your booking with {site_name} has moved."
    )
    if needs_approval:
        plain_lead += " It needs approval again." if for_owner else " The new time is waiting for the host's approval."
    text = f"{plain_lead}\n\n{type_name}: {old_when} → {new_when}" + (f"\n\n{link}" if link else "")
    await _send(to_email, to_name, subject, html, text, label="booking rescheduled")


# ── transactional: creator marketplace collabs ───────────────────────────────

async def send_cappe_offer_received_email(
    to_email: str, to_name: str | None, brand_name: str, offer_title: str, link: str,
) -> None:
    """New brand offer, to the creator. Best-effort."""
    e_brand, e_title = escape(brand_name or "A brand"), escape(offer_title)
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_brand}</b> sent you a collab offer: <b style="color:#fafafa;">{e_title}</b>.</p>'
    )
    html = _email_shell(f"New brand offer: {e_title}", body, cta_label="View offer", cta_url=link)
    text = f"{brand_name} sent you a collab offer: {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"New brand offer: {offer_title}", html, text, label="offer received")


async def send_cappe_offer_counter_email(
    to_email: str, to_name: str | None, counterpart_name: str, offer_title: str, link: str,
) -> None:
    """New terms proposed by the other side. Best-effort."""
    e_who, e_title = escape(counterpart_name or "The other side"), escape(offer_title)
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_who}</b> proposed new terms on <b style="color:#fafafa;">{e_title}</b>.</p>'
    )
    html = _email_shell(f"New terms proposed on {e_title}", body, cta_label="Review terms", cta_url=link)
    text = f"{counterpart_name} proposed new terms on {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"New terms proposed on {offer_title}", html, text, label="offer counter")


async def send_cappe_offer_accepted_email(
    to_email: str, to_name: str | None, offer_title: str, link: str, *, funding_due: bool,
) -> None:
    """Offer accepted. `funding_due=True` (brand copy) appends the fund-now nudge."""
    e_title = escape(offer_title)
    extra = (
        '<p style="margin:14px 0 0;font-size:13px;color:#a1a1aa;">The first installment is now due.</p>'
        if funding_due else ""
    )
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'Terms are locked on <b style="color:#fafafa;">{e_title}</b>.</p>{extra}'
    )
    cta_label = "Fund now" if funding_due else "View collab"
    html = _email_shell(f"Offer accepted: {e_title}", body, cta_label=cta_label, cta_url=link, accent="#10b981")
    text = f"Offer accepted: {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"Offer accepted: {offer_title}", html, text, label="offer accepted")


async def send_cappe_offer_closed_email(
    to_email: str, to_name: str | None, offer_title: str, verb: str, reason: str | None, link: str,
) -> None:
    """verb in {'declined', 'withdrawn', 'cancelled'}. Best-effort."""
    e_title = escape(offer_title)
    e_reason = f'<p style="margin:8px 0 0;font-size:13px;color:#a1a1aa;">{escape(reason)}</p>' if reason else ""
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_title}</b> was {escape(verb)}.</p>{e_reason}'
    )
    html = _email_shell(f"Offer {verb}: {e_title}", body, cta_label="View offer", cta_url=link, accent="#71717a")
    text = f"Offer {verb}: {offer_title}.\n" + (f"{reason}\n" if reason else "") + f"\n{link}"
    await _send(to_email, to_name, f"Offer {verb}: {offer_title}", html, text, label="offer closed")


async def send_cappe_collab_message_email(
    to_email: str, to_name: str | None, from_name: str, offer_title: str, body_text: str, link: str,
) -> None:
    """New chat message on an offer. Best-effort."""
    e_from, e_title = escape(from_name or "The other side"), escape(offer_title)
    snippet = (body_text or "")[:300]
    e_snippet = escape(snippet)
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_from}</b> on <b style="color:#fafafa;">{e_title}</b>:</p>'
        f'<div style="border-left:3px solid #71717a;padding:8px 0 8px 14px;color:#fafafa;font-size:14px;">{e_snippet}</div>'
    )
    html = _email_shell(f"{e_from} on {e_title}", body, cta_label="Reply", cta_url=link)
    text = f"{from_name} on {offer_title}:\n{snippet}\n\n{link}"
    await _send(to_email, to_name, f"{from_name} on {offer_title}", html, text, label="collab message")


async def send_cappe_deliverable_submitted_email(
    to_email: str, to_name: str | None, offer_title: str, deliverable_label: str, link: str,
) -> None:
    """A deliverable was submitted, to the brand. Best-effort."""
    e_title, e_label = escape(offer_title), escape(deliverable_label)
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_label}</b> was submitted for review on {e_title}.</p>'
    )
    html = _email_shell(f"Deliverable submitted — {e_title}", body, cta_label="Review", cta_url=link)
    text = f"{deliverable_label} was submitted for review on {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"Deliverable submitted — {offer_title}", html, text, label="deliverable submitted")


async def send_cappe_deliverable_decision_email(
    to_email: str, to_name: str | None, offer_title: str, deliverable_label: str,
    approved: bool, note: str | None, link: str,
) -> None:
    """Approval or revision-request decision on a deliverable, to the creator."""
    e_title, e_label = escape(offer_title), escape(deliverable_label)
    if approved:
        heading = f"Deliverable approved 🎉"
        body = f'<p style="margin:0;font-size:15px;color:#d4d4d8;"><b style="color:#fafafa;">{e_label}</b> was approved on {e_title}.</p>'
        accent = "#10b981"
    else:
        heading = "Changes requested"
        note_html = f'<p style="margin:8px 0 0;font-size:13px;color:#a1a1aa;">{escape(note)}</p>' if note else ""
        body = (
            f'<p style="margin:0;font-size:15px;color:#d4d4d8;">Changes requested on '
            f'<b style="color:#fafafa;">{e_label}</b> ({e_title}).</p>{note_html}'
        )
        accent = "#f59e0b"
    html = _email_shell(heading, body, cta_label="View collab", cta_url=link, accent=accent)
    text = f"{heading}: {deliverable_label} on {offer_title}.\n" + (f"{note}\n" if note else "") + f"\n{link}"
    await _send(to_email, to_name, f"{heading} — {offer_title}", html, text, label="deliverable decision")


async def send_cappe_collab_payment_due_email(
    to_email: str, to_name: str | None, offer_title: str, label: str, amount_cents: int, link: str,
) -> None:
    """To the BRAND: an installment is now due."""
    e_title, e_label, amount = escape(offer_title), escape(label), fmt_money(amount_cents)
    body = (
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{escape(amount)}</b> is due for <b style="color:#fafafa;">{e_label}</b> on {e_title}.</p>'
    )
    html = _email_shell(f"Payment due — {e_title}", body, cta_label="Pay now", cta_url=link, accent="#f59e0b")
    text = f"{amount} is due for {label} on {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"Payment due — {offer_title}", html, text, label="collab payment due")


async def send_cappe_collab_paid_email(
    to_email: str, to_name: str | None, offer_title: str, label: str, amount_cents: int, link: str,
) -> None:
    """To the CREATOR: an installment was paid."""
    e_title, e_label, amount = escape(offer_title), escape(label), fmt_money(amount_cents)
    body = (
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{escape(amount)}</b> for <b style="color:#fafafa;">{e_label}</b> on {e_title} just landed.</p>'
    )
    html = _email_shell(f"You got paid — {e_title}", body, cta_label="View collab", cta_url=link, accent="#10b981")
    text = f"{amount} for {label} on {offer_title} just landed.\n\n{link}"
    await _send(to_email, to_name, f"You got paid — {offer_title}", html, text, label="collab paid")


async def send_cappe_collab_completed_email(
    to_email: str, to_name: str | None, offer_title: str, link: str,
) -> None:
    """Both sides, on offer completion."""
    e_title = escape(offer_title)
    body = f'<p style="margin:0;font-size:15px;color:#d4d4d8;"><b style="color:#fafafa;">{e_title}</b> is complete — every deliverable approved, every payment settled.</p>'
    html = _email_shell(f"Collab completed: {e_title}", body, cta_label="View collab", cta_url=link, accent="#10b981")
    text = f"Collab completed: {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"Collab completed: {offer_title}", html, text, label="collab completed")


async def send_cappe_collab_payment_nudge_email(
    to_email: str, to_name: str | None, offer_title: str, label: str, amount_cents: int, link: str,
) -> None:
    """Creator-triggered reminder to the brand about an overdue installment."""
    e_title, e_label, amount = escape(offer_title), escape(label), fmt_money(amount_cents)
    body = (
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'A reminder: <b style="color:#fafafa;">{escape(amount)}</b> is still due for '
        f'<b style="color:#fafafa;">{e_label}</b> on {e_title}.</p>'
    )
    html = _email_shell(f"Reminder: payment due — {e_title}", body, cta_label="Pay now", cta_url=link, accent="#f59e0b")
    text = f"Reminder: {amount} is still due for {label} on {offer_title}.\n\n{link}"
    await _send(to_email, to_name, f"Reminder: payment due — {offer_title}", html, text, label="collab payment nudge")


# ── transactional: account + list hygiene ────────────────────────────────────

def subscribe_confirm_url(token: str) -> str:
    """Public double-opt-in confirmation link for an imported subscriber."""
    return f"{_base_url()}/api/cappe/public/subscribe/confirm/{token}"


def password_reset_url(token: str) -> str:
    """Reset link with the secret in the fragment, so it is never sent in a
    request line (and so never lands in an access log or a Referer header)."""
    return f"{_base_url()}/cappe/reset-password#token={token}"


async def send_cappe_password_reset_email(to_email: str, to_name: str | None, token: str) -> None:
    """Send the password-reset link. Critical: without it a locked-out owner
    has no way back in, so an undelivered one is logged as an error."""
    url = password_reset_url(token)
    greeting = f"Hi {to_name}," if to_name else "Hi there,"
    html = _email_shell(
        "Reset your Gummfit password",
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#a1a1aa;">'
        f"{escape(greeting)} We got a request to reset the password for this account. "
        "Choose a new one with the button below.</p>"
        '<p style="margin:0 0 16px;font-size:12px;line-height:1.6;color:#71717a;">'
        "The link works once and expires in 60 minutes. If you didn't ask for it, ignore this "
        "email and your password stays the same.</p>",
        cta_label="Choose a new password",
        cta_url=url,
    )
    text = (
        f"{greeting}\n\nWe got a request to reset the password for this Gummfit account. "
        f"Choose a new one here:\n{url}\n\n"
        "The link works once and expires in 60 minutes. If you didn't ask for it, ignore this "
        "email and your password stays the same."
    )
    await _send(to_email, to_name, "Reset your Gummfit password", html, text,
                label="password reset", critical=True)


async def send_cappe_account_exists_email(to_email: str, to_name: str | None) -> None:
    """Told to whoever owns the address when a signup collides with it.

    The signup route answers a duplicate exactly like a fresh signup, so the
    endpoint stops being an oracle for "does this person have an account?".
    That only works if the real owner is the one who learns about it — which
    is what this is.
    """
    greeting = f"Hi {to_name}," if to_name else "Hi there,"
    forgot_url = f"{_base_url()}/cappe/forgot-password"
    html = _email_shell(
        "You already have a Gummfit account",
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#a1a1aa;">'
        f"{escape(greeting)} Someone just tried to sign up with this email address, "
        "and an account already exists — so we didn't create a second one.</p>"
        '<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#a1a1aa;">'
        "If that was you, sign in instead. If it wasn't, you can ignore this "
        "email — nothing changed on your account.</p>"
        '<p style="margin:0 0 16px;font-size:13px;line-height:1.6;color:#a1a1aa;">'
        f'Forgot your password? <a href="{escape(forgot_url, quote=True)}" '
        'style="color:#c6f16b;">Reset it here</a>.</p>',
        cta_label="Sign in",
        cta_url=f"{_base_url()}/cappe/login",
    )
    text = (
        f"{greeting}\n\nSomeone just tried to sign up with this email address, and an "
        f"account already exists — so we didn't create a second one.\n\n"
        f"If that was you, sign in instead: {_base_url()}/cappe/login\n"
        f"Forgot your password? Reset it: {forgot_url}\n\n"
        "If it wasn't you, ignore this email — nothing changed on your account."
    )
    await _send(to_email, to_name, "You already have a Gummfit account", html, text,
                label="account exists")


async def send_cappe_subscribe_confirm_email(
    to_email: str, to_name: str | None, site_name: str, confirm_url: str
) -> bool:
    """Double opt-in for a subscriber a business imported rather than one who
    signed up on the site themselves.

    An imported contact never asked us for email. Until this link is clicked the
    row stays `pending_confirmation`, and the campaign worker only ever selects
    `subscribed` — so an uploaded CSV can't be turned into a blast through our
    shared sender.
    """
    greeting = f"Hi {to_name}," if to_name else "Hi there,"
    e_site = escape(site_name or "this business")
    html = _email_shell(
        f"Confirm your subscription to {e_site}",
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#a1a1aa;">'
        f"{escape(greeting)} {e_site} added you to their mailing list. "
        "We won't send you anything until you confirm.</p>"
        '<p style="margin:0;font-size:12px;line-height:1.6;color:#71717a;">'
        "If you didn't expect this, just ignore it — no confirmation, no email.</p>",
        cta_label="Confirm subscription",
        cta_url=confirm_url,
        footer=site_name or "Gummfit",
    )
    text = (
        f"{greeting}\n\n{site_name} added you to their mailing list. We won't send you "
        f"anything until you confirm:\n{confirm_url}\n\n"
        "If you didn't expect this, ignore this email — no confirmation, no email."
    )
    # Returns delivery success: the worker releases its claim on a failed send so
    # the confirmation is retried instead of stranding the row pending forever.
    return await _send(to_email, to_name, f"Confirm your subscription to {site_name}", html, text,
                       label="subscribe confirm", log_recipient=False)


# ── transactional: domain renewals ───────────────────────────────────────────

async def send_cappe_domain_renewal_problem_email(
    to_email: str, to_name: str | None, domain: str, expires_on: str, reason: str, link: str,
) -> None:
    """A domain is about to lapse and we could not renew it: the card was
    refused, there is no card on file, or auto-renew is off. Sent ONCE per
    renewal cycle — before this, a failed renewal was silent right up to the
    day the domain went offline."""
    e_domain, e_date = escape(domain), escape(expires_on)
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_domain}</b> expires on <b style="color:#fafafa;">{e_date}</b> '
        f'and has not been renewed: {escape(reason)}</p>'
        '<p style="margin:0;font-size:13px;line-height:1.6;color:#a1a1aa;">'
        "Renew it from your site's domain settings to keep your address — and your site — online.</p>"
    )
    html = _email_shell(f"Action needed — renew {e_domain}", body, cta_label="Renew domain",
                        cta_url=link, accent="#f59e0b")
    text = (f"{domain} expires on {expires_on} and has not been renewed: {reason}\n\n"
            f"Renew it to keep your site online: {link}")
    await _send(to_email, to_name, f"Action needed — renew {domain}", html, text,
                label="domain renewal problem")


async def send_cappe_domain_lapsed_email(
    to_email: str, to_name: str | None, domain: str, link: str,
) -> None:
    """The domain was not renewed and has lapsed."""
    e_domain = escape(domain)
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{e_domain}</b> was not renewed and has expired. '
        "Your site is still available at its gummfit address.</p>"
        '<p style="margin:0;font-size:13px;line-height:1.6;color:#a1a1aa;">'
        "If you still want this domain, reply to this email as soon as you can — an expired "
        "domain can often be recovered for a short time.</p>"
    )
    html = _email_shell(f"{e_domain} has expired", body, cta_label="Open domain settings",
                        cta_url=link, accent="#ef4444")
    text = (f"{domain} was not renewed and has expired. Your site is still available at its "
            f"gummfit address.\n\nIf you still want this domain, reply to this email soon.\n\n{link}")
    await _send(to_email, to_name, f"{domain} has expired", html, text, label="domain lapsed")

