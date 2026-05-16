"""TrainingEmailMixin email-send methods.

Extracted from `email.py` during the 2026-05-16 package split. Mixed
into `EmailService` (see `client.py`) via multiple inheritance. Method
bodies call `self.send_email(...)` / `self.is_configured()` / etc. —
`self` is the composed `EmailService` at runtime.
"""
import logging
import os
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


class TrainingEmailMixin:
    async def send_training_assignment_email(
        self,
        to_email: str,
        to_name: Optional[str],
        training_title: str,
        due_date: Optional[date],
        login_url: str,
    ) -> bool:
        """Notify an employee they've been assigned a training (CA SB 1343 et al)."""
        title_safe = html.escape(training_title)
        due_label = due_date.strftime("%B %-d, %Y") if due_date else "as soon as possible"
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f2937; background: #f8fafc; margin: 0; padding: 24px; }}
  .container {{ max-width: 560px; margin: 0 auto; background: white; border-radius: 8px; padding: 28px; }}
  .logo {{ color: #16a34a; font-weight: bold; letter-spacing: 2px; font-size: 18px; }}
  h1 {{ font-size: 20px; margin: 16px 0; }}
  .btn {{ display: inline-block; background: #16a34a; color: white; padding: 12px 22px;
          text-decoration: none; border-radius: 6px; font-weight: 600; margin-top: 16px; }}
  .meta {{ background: #f1f5f9; border-left: 3px solid #16a34a; padding: 12px 16px;
           border-radius: 6px; margin: 16px 0; font-size: 14px; }}
  .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; }}
</style></head>
<body>
  <div class="container">
    <div class="logo">MATCHA</div>
    <h1>Required training assigned</h1>
    <p>Hi {html.escape(to_name or '')},</p>
    <p>You've been assigned a required training: <strong>{title_safe}</strong>.</p>
    <div class="meta">
      <div><strong>Complete by:</strong> {due_label}</div>
    </div>
    <p>This training is required by California SB 1343. It must be completed
    fully — there's a minimum seat-time requirement, followed by a short
    quiz and an attestation.</p>
    <p><a class="btn" href="{login_url}">Start training</a></p>
    <div class="footer">If you have questions, reply to this email or contact your HR administrator.</div>
  </div>
</body></html>"""
        text_content = (
            f"Required training assigned: {training_title}\n\n"
            f"Complete by: {due_label}\n\n"
            f"Start at: {login_url}\n"
        )
        return await self._send_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=f"Required training: {training_title}",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_training_completion_email(
        self,
        to_email: str,
        to_name: Optional[str],
        training_title: str,
        score_percent: float,
        expiration_date: Optional[date],
        pdf_bytes: bytes,
    ) -> bool:
        """Send completion confirmation with PDF cert attached."""
        title_safe = html.escape(training_title)
        valid_until = expiration_date.strftime("%B %-d, %Y") if expiration_date else "—"
        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f2937; background: #f8fafc; margin: 0; padding: 24px; }}
  .container {{ max-width: 560px; margin: 0 auto; background: white; border-radius: 8px; padding: 28px; }}
  .logo {{ color: #16a34a; font-weight: bold; letter-spacing: 2px; font-size: 18px; }}
  h1 {{ font-size: 20px; margin: 16px 0; }}
  .meta {{ background: #ecfdf5; border-left: 3px solid #16a34a; padding: 12px 16px;
           border-radius: 6px; margin: 16px 0; font-size: 14px; }}
  .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; }}
</style></head>
<body>
  <div class="container">
    <div class="logo">MATCHA</div>
    <h1>Training completed</h1>
    <p>Hi {html.escape(to_name or '')},</p>
    <p>You completed <strong>{title_safe}</strong>. Your certificate is attached
    to this email.</p>
    <div class="meta">
      <div><strong>Score:</strong> {score_percent:.1f}%</div>
      <div><strong>Valid until:</strong> {valid_until}</div>
    </div>
    <p>Save this certificate for your records. Your employer also retains a
    copy. You'll be notified when renewal is due.</p>
    <div class="footer">California SB 1343 / Gov. Code §12950.1</div>
  </div>
</body></html>"""
        text_content = (
            f"Training completed: {training_title}\n"
            f"Score: {score_percent:.1f}%\n"
            f"Valid until: {valid_until}\n"
        )
        attachment = {
            "filename": "training_certificate.pdf",
            "content": base64.b64encode(pdf_bytes).decode(),
            "disposition": "attachment",
        }
        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Training certificate: {training_title}",
            html_content=html_content,
            text_content=text_content,
            attachments=[attachment],
        )

