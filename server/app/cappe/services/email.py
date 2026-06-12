"""Cappe transactional email — reuses the platform email service.

Cappe is its own product but shares matcha's Gmail/MailerSend sender (and its
reserved-domain guard, so sends to @example.com / *.test are skipped). Called
as a FastAPI background task so account creation never blocks on SMTP.
"""
import logging

from ...core.services.email.client import get_email_service

logger = logging.getLogger(__name__)

_DASHBOARD_URL = "https://hey-matcha.com/cappe"


async def send_cappe_welcome_email(to_email: str, to_name: str | None) -> None:
    """Send the signup confirmation / welcome email. Best-effort: logs and
    swallows failures so it's safe to fire from a background task."""
    greeting = f"Hi {to_name}," if to_name else "Welcome!"
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
      <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#a1a1aa;">{greeting}</p>
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
