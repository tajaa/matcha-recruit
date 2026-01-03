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

    async def send_screening_invite_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        position_title: str,
        location: Optional[str],
        salary_range: Optional[str],
        screening_token: str,
        custom_message: Optional[str] = None,
    ) -> bool:
        """Send a direct screening interview invitation to a candidate.

        Unlike outreach emails, this goes directly to the screening interview
        (requires candidate to have an account to access).

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        screening_url = f"{app_base_url}/screening/{screening_token}"

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
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; }}
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

            <p>You've been invited to complete a screening interview for an exciting opportunity:</p>

            <div class="role-card">
                <h2 style="margin-top: 0; color: #111;">{position_title}</h2>
                <p><strong>Company:</strong> {company_name}{location_text}</p>
                {salary_text}
            </div>

            <div class="highlight">
                <strong>What to expect:</strong> A brief voice conversation (about 5-10 minutes) to learn more about your background and interests.
            </div>

            <p>Click below to start your screening interview:</p>

            <p>
                <a href="{screening_url}" class="btn">Start Screening Interview</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">You'll need to log in or create an account to access the interview. This link is unique to you.</p>
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

{custom_message + chr(10) + chr(10) if custom_message else ''}You've been invited to complete a screening interview for an exciting opportunity:

{position_title} at {company_name}{location_text}
{('Compensation: ' + salary_range + chr(10)) if salary_range else ''}
What to expect: A brief voice conversation (about 5-10 minutes) to learn more about your background and interests.

Start your screening interview here: {screening_url}

You'll need to log in or create an account to access the interview.

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
            "subject": f"Screening Interview: {position_title} at {company_name}",
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
                    print(f"[Email] Sent screening invite to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_contact_form_email(
        self,
        sender_name: str,
        sender_email: str,
        company_name: str,
        message: str,
    ) -> bool:
        """Send a contact form submission to the admin email.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        contact_email = self.settings.contact_email

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
        .info-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .label {{ font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
        .value {{ margin-top: 4px; color: #111; }}
        .message {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-top: 20px; white-space: pre-wrap; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <h2 style="margin-top: 0;">New Contact Form Submission</h2>

            <div class="info-card">
                <div style="margin-bottom: 16px;">
                    <div class="label">Company</div>
                    <div class="value">{company_name}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Contact Name</div>
                    <div class="value">{sender_name}</div>
                </div>
                <div>
                    <div class="label">Email</div>
                    <div class="value"><a href="mailto:{sender_email}">{sender_email}</a></div>
                </div>
            </div>

            <div class="label">Message</div>
            <div class="message">{message}</div>
        </div>
        <div class="footer">
            <p>Sent from Matcha Recruit contact form</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
New Contact Form Submission

Company: {company_name}
Contact: {sender_name}
Email: {sender_email}

Message:
{message}

---
Sent from Matcha Recruit contact form
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": contact_email,
                    "name": "Matcha Team",
                }
            ],
            "reply_to": {
                "email": sender_email,
                "name": sender_name,
            },
            "subject": f"Contact Form: {company_name} - {sender_name}",
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
                    print(f"[Email] Sent contact form email from {sender_email}")
                    return True
                else:
                    print(f"[Email] Failed to send contact form: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending contact form: {e}")
            return False

    async def send_policy_signature_email(
        self,
        to_email: str,
        to_name: str,
        policy_title: str,
        policy_version: str,
        token: str,
        expires_at,
        company_name: Optional[str] = None,
    ) -> bool:
        """Send a policy signature request email.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        signature_url = f"{app_base_url}/sign/{token}"

        company_section = f"<p><strong>From:</strong> {company_name}</p>" if company_name else ""
        version_section = f"<p><strong>Version:</strong> {policy_version}</p>" if policy_version else ""

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
        .policy-card {{ background: #f8f9fa; border-left: 4px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; text-align: center; }}
        .btn:hover {{ background: #16a34a; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>

            <p>You have been asked to sign the following policy document:</p>

            <div class="policy-card">
                <h2 style="margin-top: 0; color: #111;">{policy_title}</h2>
                {company_section}
                {version_section}
            </div>

            <p>Please review the policy and click the button below to sign it electronically.</p>

            <p>
                <a href="{signature_url}" class="btn">Sign Policy</a>
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                This link will expire on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                If you have questions about this policy, please contact your administrator.
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

You have been asked to sign the following policy document:

{policy_title}
{company_name if company_name else ''}
{('Version: ' + policy_version) if policy_version else ''}

Please review the policy and sign it using the link below:

{signature_url}

This link will expire on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.

If you have questions, please contact your administrator.

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
                    "name": to_name,
                }
            ],
            "subject": f"Action Required: Please sign {policy_title}",
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
                    print(f"[Email] Sent policy signature email to {to_email}")
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
