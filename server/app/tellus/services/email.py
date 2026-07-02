"""Tell-Us transactional email — reuses the platform email service.

Tell-Us is its own product but shares matcha's Gmail/MailerSend sender (and its
reserved-domain guard, so sends to @example.com / *.test are skipped). Called as
FastAPI background tasks so requests never block on SMTP. All best-effort: log
and swallow so email never surfaces to the caller.
"""
import logging
import os
from html import escape

from ...core.services.email.client import get_email_service

logger = logging.getLogger(__name__)

_ACCENT = "#f97316"  # tell-us orange


def _base_url() -> str:
    return f"https://{os.getenv('TELLUS_BASE_DOMAIN', 'hey-matcha.com')}"


def app_url(path: str = "") -> str:
    """Absolute Tell-Us app URL, e.g. app_url('/rewards')."""
    return f"{_base_url()}/tellus{path}"


def _shell(heading: str, body_html: str, *, cta_label: str | None = None, cta_url: str | None = None) -> str:
    """Full HTML document in the Tell-Us transactional style. `heading` and
    `body_html` MUST already be escaped by the caller; `cta_url` escaped here."""
    cta = ""
    if cta_label and cta_url:
        cta = (
            f'<a href="{escape(cta_url, quote=True)}" style="display:inline-block;'
            f"background:{_ACCENT};color:#1a0f00;text-decoration:none;font-weight:600;"
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
    <p style="text-align:center;margin:20px 0 0;font-size:12px;color:#52525b;">Tell-Us</p>
  </div>
</body>
</html>"""


async def _send(to_email: str, to_name: str | None, subject: str, html: str, text: str, *, label: str) -> None:
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email, to_name=to_name, subject=subject,
            html_content=html, text_content=text,
        )
    except Exception:
        logger.exception("Tell-Us %s email failed for %s", label, to_email)


async def send_tellus_verification_email(to_email: str, to_name: str | None, token: str) -> None:
    """Email-confirmation link — the anti-spam gate. Best-effort."""
    verify_url = f"{_base_url()}/tellus/verify?token={token}"
    greeting = f"Hi {to_name}," if to_name else "Welcome!"
    greeting_html = f"Hi {escape(to_name)}," if to_name else "Welcome!"
    body = (
        f'<p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#a1a1aa;">{greeting_html}</p>'
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#a1a1aa;">'
        f'Confirm your email to activate your Tell-Us account — then start earning points for '
        f'useful feedback and redeeming rewards in your city.</p>'
        f'<p style="margin:16px 0 0;font-size:12px;line-height:1.6;color:#71717a;">'
        f'Or paste this link:<br><span style="color:#a1a1aa;word-break:break-all;">{escape(verify_url)}</span></p>'
        f'<p style="margin:12px 0 0;font-size:12px;color:#71717a;">This link expires in 24 hours.</p>'
    )
    html = _shell("Confirm your email", body, cta_label="Confirm my email", cta_url=verify_url)
    text = (
        f"{greeting}\n\nConfirm your email to activate your Tell-Us account:\n{verify_url}\n\n"
        "This link expires in 24 hours. If you didn't sign up, ignore this email."
    )
    await _send(to_email, to_name, "Confirm your email for Tell-Us", html, text, label="verification")


async def send_tellus_points_email(
    to_email: str, to_name: str | None, points: int, reason_label: str, balance: int
) -> None:
    """Notify a consumer they earned points. Best-effort."""
    body = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'You just earned <b style="color:{_ACCENT};">+{int(points)} points</b> for {escape(reason_label)}.</p>'
        f'<p style="margin:0;font-size:14px;color:#a1a1aa;">New balance: '
        f'<b style="color:#fafafa;">{int(balance)} points</b>.</p>'
    )
    html = _shell("You earned points", body, cta_label="See rewards", cta_url=app_url("/rewards"))
    text = f"You earned +{points} points for {reason_label}. New balance: {balance} points.\n\n{app_url('/rewards')}"
    await _send(to_email, to_name, f"+{points} points on Tell-Us", html, text, label="points")


async def send_tellus_redemption_email(
    to_email: str, to_name: str | None, listing_title: str, code: str | None
) -> None:
    """Send the consumer their redemption code. Best-effort."""
    code_html = (
        f'<div style="border:1px dashed #3f3f46;border-radius:10px;padding:14px 16px;margin:14px 0;'
        f'text-align:center;font-size:22px;letter-spacing:3px;color:#fafafa;font-weight:700;">'
        f'{escape(code)}</div>' if code else ""
    )
    body = (
        f'<p style="margin:0 0 6px;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'You redeemed <b style="color:#fafafa;">{escape(listing_title)}</b>.</p>{code_html}'
        f'<p style="margin:0;font-size:13px;color:#a1a1aa;">Show this at the store to claim your reward.</p>'
    )
    html = _shell("Reward redeemed", body, cta_label="My redemptions", cta_url=app_url("/redemptions"))
    text = f"You redeemed {listing_title}." + (f"\nCode: {code}" if code else "") + f"\n\n{app_url('/redemptions')}"
    await _send(to_email, to_name, f"Your reward — {listing_title}", html, text, label="redemption")


async def send_tellus_feedback_alert_email(
    to_email: str, to_name: str | None, brand_name: str, store_name: str | None, sentiment: str
) -> None:
    """Alert a brand to new feedback. Content NOT echoed (untrusted UGC) — the
    brand opens the dashboard to read it. Best-effort."""
    where = f" at {escape(store_name)}" if store_name else ""
    body = (
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#d4d4d8;">'
        f'New <b style="color:#fafafa;">{escape(sentiment)}</b> feedback for '
        f'<b style="color:#fafafa;">{escape(brand_name)}</b>{where}.</p>'
    )
    html = _shell("New feedback", body, cta_label="View feedback", cta_url=app_url("/brand/feedback"))
    text = f"New {sentiment} feedback for {brand_name}{(' at ' + store_name) if store_name else ''}.\n\n{app_url('/brand/feedback')}"
    await _send(to_email, to_name, f"New feedback — {brand_name}", html, text, label="feedback alert")
