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

from ...core.services.email.client import get_email_service

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return f"https://{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}"


_DASHBOARD_URL = f"{_base_url()}/cappe"


def dashboard_url(path: str = "") -> str:
    """Absolute creator-dashboard URL, e.g. dashboard_url(f"/sites/{id}/orders")."""
    return f"{_DASHBOARD_URL}{path}"


def booking_manage_url(token: str) -> str:
    """Customer-facing self-serve link for a booking (view/cancel/reschedule)."""
    return f"{_base_url()}/cappe/booking/{token}"

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
    """Friendly local time, e.g. "Mon, Jun 15 · 4:00 PM", rendered in the site's
    timezone (falls back to the datetime's own zone if tz is bad/missing)."""
    try:
        if tz_name:
            dt = dt.astimezone(ZoneInfo(tz_name))
    except Exception:  # bad tz string → leave dt as-is
        pass
    return dt.strftime("%a, %b %d · %-I:%M %p")


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


async def _send(to_email: str, to_name: str | None, subject: str, html: str, text: str, *, label: str) -> None:
    """Best-effort send — logs and swallows so it's safe in a background task."""
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email, to_name=to_name, subject=subject,
            html_content=html, text_content=text,
        )
    except Exception:
        logger.exception("Cappe %s email failed for %s", label, to_email)


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
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject="Confirm your email for Gummfit",
            html_content=html,
            text_content=text,
        )
    except Exception:  # never let email failure surface to signup
        logger.exception("Cappe verification email failed for %s", to_email)


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
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=f"New message — {site_name}",
            html_content=html,
            text_content=text,
        )
    except Exception:
        logger.exception("Cappe message email failed for %s", to_email)


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
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject="Welcome to Cappe — your account is ready",
            html_content=html,
            text_content=text,
        )
    except Exception:  # never let email failure surface to signup
        logger.exception("Cappe welcome email failed for %s", to_email)


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
) -> None:
    """24h-ahead reminder to the customer. Best-effort (fired from the worker)."""
    e_site, e_type, e_when = escape(site_name or ""), escape(type_name or "Booking"), escape(when_label or "")
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">A quick reminder of your upcoming booking with {e_site}.</p>'
        f'<div style="border-left:3px solid #c6f16b;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{e_type}</b><br><span style="color:#a1a1aa;">{e_when}</span></div>'
    )
    html = _email_shell(f"Reminder — {e_site}", body, cta_label="Manage booking" if manage_url else None, cta_url=manage_url)
    text = f"Reminder: your booking with {site_name} — {type_name}, {when_label}." + (f"\nManage: {manage_url}" if manage_url else "")
    await _send(to_email, to_name, f"Reminder: your booking with {site_name}", html, text, label="booking reminder")


async def send_cappe_booking_cancelled_email(
    to_email: str, to_name: str | None, site_name: str, customer_name: str | None,
    type_name: str, when_label: str, dashboard_url: str,
) -> None:
    """Alert the creator that a customer cancelled. Best-effort."""
    e_site, who = escape(site_name or ""), escape((customer_name or "A customer").strip() or "A customer")
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'<b style="color:#fafafa;">{who}</b> cancelled their booking on {e_site}.</p>'
        f'<div style="border-left:3px solid #71717a;padding:8px 0 8px 14px;color:#fafafa;font-size:15px;">'
        f'<b>{escape(type_name or "Booking")}</b><br><span style="color:#a1a1aa;">{escape(when_label or "")}</span></div>'
    )
    html = _email_shell(f"Booking cancelled — {e_site}", body, cta_label="View bookings", cta_url=dashboard_url)
    text = f"{customer_name or 'A customer'} cancelled {type_name} — {when_label} on {site_name}.\n\n{dashboard_url}"
    await _send(to_email, to_name, f"Booking cancelled — {site_name}", html, text, label="booking cancelled")
