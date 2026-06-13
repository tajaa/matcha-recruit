"""Cappe transactional email — reuses the platform email service.

Cappe is its own product but shares matcha's Gmail/MailerSend sender (and its
reserved-domain guard, so sends to @example.com / *.test are skipped). Called
as a FastAPI background task so account creation never blocks on SMTP.
"""
import logging
import os
from html import escape

from ...core.services.email.client import get_email_service

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return f"https://{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}"


_DASHBOARD_URL = f"{_base_url()}/cappe"


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
