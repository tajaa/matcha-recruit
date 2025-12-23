"""Email service using MailerSend."""
import httpx
from typing import Optional

from ..config import get_settings


class EmailService:
    """Service for sending emails via MailerSend API."""

    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.mailersend_api_key
        self.from_email = self.settings.mailersend_from_email
        self.from_name = self.settings.mailersend_from_name
        self.base_url = "https://api.mailersend.com/v1"

    def is_configured(self) -> bool:
        """Check if email service is properly configured."""
        return bool(self.api_key)

    async def send_outreach_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        position_title: str,
        location: Optional[str],
        salary_range: Optional[str],
        outreach_token: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send an outreach email to a candidate.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        outreach_url = f"{app_base_url}/outreach/{outreach_token}"

        # Build email HTML
        location_text = f" in {location}" if location else ""
        salary_text = f"\n<p><strong>Compensation:</strong> {salary_range}</p>" if salary_range else ""

        custom_section = ""
        if custom_message:
            custom_section = f"<p>{custom_message}</p><br>"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .role-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 10px 5px 10px 0; }}
        .btn-secondary {{ background: #6b7280; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + to_name if to_name else ''},</p>

            {custom_section}

            <p>We came across your profile and think you might be a great fit for an exciting opportunity:</p>

            <div class="role-card">
                <h2 style="margin-top: 0; color: #111;">{position_title}</h2>
                <p><strong>Company:</strong> {company_name}{location_text}</p>
                {salary_text}
            </div>

            <p>If you're interested in learning more, click the button below to express your interest. You'll then have the opportunity to complete a brief screening conversation.</p>

            <p>
                <a href="{outreach_url}" class="btn">I'm Interested</a>
                <a href="{outreach_url}?decline=true" class="btn btn-secondary">Not for me</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">This link is unique to you and will expire in 14 days.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi{' ' + to_name if to_name else ''},

{custom_message + chr(10) + chr(10) if custom_message else ''}We came across your profile and think you might be a great fit for an exciting opportunity:

{position_title} at {company_name}{location_text}
{('Compensation: ' + salary_range + chr(10)) if salary_range else ''}
If you're interested, visit this link: {outreach_url}

Not interested? Let us know: {outreach_url}?decline=true

This link is unique to you and will expire in 14 days.

- Matcha Recruit
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name or to_email,
                }
            ],
            "subject": f"Opportunity: {position_title} at {company_name}",
            "html": html_content,
            "text": text_content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201, 202):
                    print(f"[Email] Sent outreach email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
