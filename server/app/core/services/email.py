"""Email service using MailerSend."""
import httpx
from datetime import date, datetime
from typing import Optional

from ...config import get_settings


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

    async def send_email(
        self,
        to_email: str,
        to_name: Optional[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        """Send a generic email via MailerSend.

        Attachments should match MailerSend format:
        {"filename": "...", "content": "<base64>", "disposition": "attachment"}
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

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
            "subject": subject,
            "html": html_content,
        }
        if text_content:
            payload["text"] = text_content
        if attachments:
            payload["attachments"] = attachments

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
                    print(f"[Email] Sent email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

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

    async def send_broker_client_setup_invitation_email(
        self,
        to_email: str,
        to_name: str,
        broker_name: str,
        company_name: str,
        invite_url: str,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        """Send a broker client onboarding invitation email."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        expires_text = (
            expires_at.strftime('%B %d, %Y at %I:%M %p')
            if isinstance(expires_at, datetime)
            else "in a limited time window"
        )

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
        .card {{ background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 10px; padding: 18px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 12px 0; }}
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

            <p>{broker_name} invited you to activate your compliance workspace for <strong>{company_name}</strong>.</p>

            <div class="card">
                <p style="margin: 0 0 8px 0;"><strong>What you'll do:</strong></p>
                <p style="margin: 0;">Create your account, review your preconfigured setup, and begin compliance onboarding.</p>
            </div>

            <p style="text-align: center;">
                <a href="{invite_url}" class="btn">Activate Client Workspace</a>
            </p>

            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                This invitation expires on {expires_text}.
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

{broker_name} invited you to activate your compliance workspace for {company_name}.

Use this invite link to activate your client workspace:
{invite_url}

This invitation expires on {expires_text}.

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
            "subject": f"{broker_name} invited you to activate {company_name} on Matcha",
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
                    print(f"[Email] Sent broker client invite to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_employee_invitation_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        token: str,
        expires_at,
    ) -> bool:
        """Send an employee onboarding invitation email.

        This email is sent when an admin creates an employee and wants them to set up their account.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        invitation_url = f"{app_base_url}/invite/{token}"

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
        .welcome-card {{ background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; }}
        .company-name {{ font-size: 28px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 16px; }}
        .btn:hover {{ background: #16a34a; }}
        .steps {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .step {{ display: flex; align-items: flex-start; margin-bottom: 12px; }}
        .step-number {{ background: #22c55e; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; margin-right: 12px; flex-shrink: 0; }}
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

            <p>Welcome! You've been invited to join the employee portal.</p>

            <div class="welcome-card">
                <div class="company-name">{company_name}</div>
                <p style="color: #6b7280; margin: 0;">is inviting you to set up your account</p>
            </div>

            <div class="steps">
                <div class="step">
                    <div class="step-number">1</div>
                    <div>Click the button below to get started</div>
                </div>
                <div class="step">
                    <div class="step-number">2</div>
                    <div>Create your password</div>
                </div>
                <div class="step">
                    <div class="step-number">3</div>
                    <div>Access your employee portal</div>
                </div>
            </div>

            <p style="text-align: center;">
                <a href="{invitation_url}" class="btn">Set Up My Account</a>
            </p>

            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                This invitation expires on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.
            </p>

            <p style="color: #6b7280; font-size: 14px;">
                If you weren't expecting this invitation or have questions, please contact your HR administrator.
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

Welcome! You've been invited to join the employee portal at {company_name}.

To set up your account, please visit:
{invitation_url}

This invitation expires on {expires_at.strftime('%B %d, %Y at %I:%M %p')}.

If you weren't expecting this invitation, please contact your HR administrator.

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
            "subject": f"Welcome to {company_name} - Set Up Your Account",
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
                    print(f"[Email] Sent employee invitation to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False


    async def send_employee_welcome_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        login_email: str,
    ) -> bool:
        """Send a getting-started welcome email to the employee's work email after they accept their invitation.

        Explains how to log in and what they can do in the Matcha employee portal.
        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping employee welcome email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/portal"
        login_url = f"{app_base_url}/login"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .hero {{ background: linear-gradient(135deg, #052e16 0%, #14532d 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; color: white; }}
        .hero-title {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; }}
        .hero-sub {{ font-size: 14px; color: #86efac; margin: 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white !important; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 15px; }}
        .login-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 13px; }}
        .login-box strong {{ display: block; margin-bottom: 4px; color: #111; }}
        .login-box code {{ background: #e5e7eb; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
        .features {{ margin: 24px 0; }}
        .feature-row {{ display: flex; align-items: flex-start; margin-bottom: 14px; }}
        .feature-icon {{ font-size: 20px; margin-right: 14px; flex-shrink: 0; width: 28px; text-align: center; }}
        .feature-title {{ font-weight: 600; color: #111; font-size: 14px; }}
        .feature-desc {{ color: #6b7280; font-size: 13px; margin: 2px 0 0 0; }}
        .divider {{ border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }}
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
            <p>Your account at <strong>{company_name}</strong> is ready. Here's everything you can do in your employee portal.</p>

            <div class="hero">
                <div class="hero-title">Welcome to {company_name}</div>
                <div class="hero-sub">Your employee portal is live</div>
            </div>

            <div class="login-box">
                <strong>Log in at:</strong>
                <a href="{login_url}">{login_url}</a><br><br>
                <strong>Your login email:</strong>
                <code>{login_email}</code>
            </div>

            <p style="text-align: center;">
                <a href="{portal_url}" class="btn">Open My Portal</a>
            </p>

            <hr class="divider">

            <p style="font-weight: 600; font-size: 15px; margin-bottom: 16px;">What you can do in Matcha:</p>

            <div class="features">
                <div class="feature-row">
                    <div class="feature-icon">✅</div>
                    <div>
                        <div class="feature-title">Complete your onboarding</div>
                        <p class="feature-desc">Finish any pending tasks, sign documents, and get set up from day one.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">🏖️</div>
                    <div>
                        <div class="feature-title">Request time off</div>
                        <p class="feature-desc">Submit PTO requests, view your balance, and track approvals in one place.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">📋</div>
                    <div>
                        <div class="feature-title">View company policies</div>
                        <p class="feature-desc">Read and acknowledge company policies, handbooks, and compliance docs.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">🚨</div>
                    <div>
                        <div class="feature-title">Submit incident reports</div>
                        <p class="feature-desc">Report workplace incidents or safety concerns quickly and confidentially.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">⭐</div>
                    <div>
                        <div class="feature-title">Performance reviews</div>
                        <p class="feature-desc">Complete self-assessments and view feedback from your manager.</p>
                    </div>
                </div>
                <div class="feature-row">
                    <div class="feature-icon">💬</div>
                    <div>
                        <div class="feature-title">Share feedback</div>
                        <p class="feature-desc">Participate in vibe checks and eNPS surveys — your voice matters.</p>
                    </div>
                </div>
            </div>

            <hr class="divider">

            <p style="color: #6b7280; font-size: 13px;">
                Questions? Reach out to your HR administrator or reply to this email.
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit &mdash; {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi {to_name},

Your account at {company_name} is ready. Log in to your employee portal to get started.

Log in at: {login_url}
Your login email: {login_email}

Portal: {portal_url}

What you can do in Matcha:
- Complete your onboarding tasks and sign documents
- Request time off and track your PTO balance
- View and acknowledge company policies
- Submit incident reports
- Complete performance reviews
- Share feedback via vibe checks and eNPS surveys

Questions? Contact your HR administrator.

- Matcha Recruit / {company_name}
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
            "subject": f"You're all set — welcome to {company_name}",
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
                    print(f"[Email] Sent employee welcome email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send welcome email to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending welcome email to {to_email}: {e}")
            return False

    async def send_task_reminder(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        employee_name: str,
        task_title: str,
        due_date: date,
    ) -> bool:
        """Send a standard onboarding task reminder email."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping onboarding reminder email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/portal"
        due_text = due_date.strftime("%B %d, %Y")

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
        .card {{ background: #f9fafb; border-radius: 10px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 12px 22px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
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
            <p>This is a reminder to complete an onboarding task for <strong>{employee_name}</strong>.</p>

            <div class="card">
                <p style="margin: 0;"><strong>Task:</strong> {task_title}</p>
                <p style="margin: 8px 0 0 0;"><strong>Due date:</strong> {due_text}</p>
            </div>

            <p>
                <a href="{portal_url}" class="btn">Open Onboarding Portal</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit — {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

This is a reminder to complete an onboarding task for {employee_name}.

Task: {task_title}
Due date: {due_text}

Open onboarding portal: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"Onboarding reminder: {task_title}",
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
                    print(f"[Email] Sent onboarding reminder to {to_email}")
                    return True
                print(f"[Email] Failed onboarding reminder to {to_email}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"[Email] Error sending onboarding reminder to {to_email}: {e}")
            return False

    async def send_task_escalation(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        employee_name: str,
        task_title: str,
        due_date: date,
        escalation_target: str,
        overdue_days: int,
    ) -> bool:
        """Send an onboarding escalation email for overdue tasks."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping onboarding escalation email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/onboarding"
        due_text = due_date.strftime("%B %d, %Y")
        escalation_label = "Manager" if escalation_target == "manager" else "HR"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #ef4444; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .alert {{ background: #fef2f2; border-left: 4px solid #ef4444; border-radius: 6px; padding: 16px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #ef4444; color: white; padding: 12px 22px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
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
            <p>An onboarding task for <strong>{employee_name}</strong> has been escalated to {escalation_label} follow-up.</p>

            <div class="alert">
                <p style="margin: 0;"><strong>Task:</strong> {task_title}</p>
                <p style="margin: 8px 0 0 0;"><strong>Due date:</strong> {due_text}</p>
                <p style="margin: 8px 0 0 0;"><strong>Overdue by:</strong> {overdue_days} day(s)</p>
            </div>

            <p>
                <a href="{portal_url}" class="btn">Review Onboarding Status</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit — {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

An onboarding task for {employee_name} has been escalated to {escalation_label} follow-up.

Task: {task_title}
Due date: {due_text}
Overdue by: {overdue_days} day(s)

Review onboarding status: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"Onboarding escalation ({escalation_label}): {task_title}",
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
                    print(f"[Email] Sent onboarding escalation to {to_email}")
                    return True
                print(f"[Email] Failed onboarding escalation to {to_email}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"[Email] Error sending onboarding escalation to {to_email}: {e}")
            return False

    async def send_manager_onboarding_summary(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        summary_lines: list[str],
    ) -> bool:
        """Send a weekly manager summary of onboarding items."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping manager onboarding summary email")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/onboarding"
        bullet_items = "".join([f"<li>{line}</li>" for line in summary_lines]) if summary_lines else "<li>No pending items this week.</li>"
        text_bullets = "\n".join([f"- {line}" for line in summary_lines]) if summary_lines else "- No pending items this week."

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
        .card {{ background: #f9fafb; border-radius: 10px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 12px 22px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
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
            <p>Here is your weekly onboarding summary for {company_name}.</p>
            <div class="card">
                <ul>{bullet_items}</ul>
            </div>
            <p>
                <a href="{portal_url}" class="btn">Open Onboarding Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit — {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Here is your weekly onboarding summary for {company_name}.

{text_bullets}

Open onboarding dashboard: {portal_url}

- Matcha Recruit / {company_name}
"""

        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": f"Weekly onboarding summary — {company_name}",
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
                    print(f"[Email] Sent manager onboarding summary to {to_email}")
                    return True
                print(f"[Email] Failed manager onboarding summary to {to_email}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"[Email] Error sending manager onboarding summary to {to_email}: {e}")
            return False


    async def send_enps_survey_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        survey_title: str,
        survey_description: Optional[str] = None,
        portal_url: Optional[str] = None,
    ) -> bool:
        """Send an eNPS survey invitation email to an employee.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        survey_url = portal_url or f"{app_base_url}/app/portal/enps"

        description_section = f"<p style='color: #6b7280;'>{survey_description}</p>" if survey_description else ""

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
        .survey-card {{ background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; }}
        .survey-title {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 16px; }}
        .btn:hover {{ background: #16a34a; }}
        .highlight {{ background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 15px; margin: 20px 0; border-radius: 0 8px 8px 0; }}
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

            <p>{company_name} values your feedback! You've been invited to participate in our Employee Net Promoter Score (eNPS) survey.</p>

            <div class="survey-card">
                <div class="survey-title">{survey_title}</div>
                {description_section}
            </div>

            <div class="highlight">
                <strong>Why participate?</strong><br>
                Your honest feedback helps us understand what we're doing well and where we can improve. The survey is quick (about 2 minutes) and your responses help shape our workplace culture.
            </div>

            <p style="text-align: center;">
                <a href="{survey_url}" class="btn">Take the Survey</a>
            </p>

            <p style="color: #6b7280; font-size: 14px; text-align: center;">
                Thank you for helping us build a better workplace!
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

{company_name} values your feedback! You've been invited to participate in our Employee Net Promoter Score (eNPS) survey.

Survey: {survey_title}
{survey_description or ''}

Why participate?
Your honest feedback helps us understand what we're doing well and where we can improve. The survey is quick (about 2 minutes) and your responses help shape our workplace culture.

Take the survey here: {survey_url}

Thank you for helping us build a better workplace!

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
            "subject": f"{company_name}: {survey_title} - Your Feedback Matters",
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
                    print(f"[Email] Sent eNPS survey invite to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_compliance_change_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        location_name: str,
        changed_requirements_count: int,
        jurisdictions: Optional[list[str]] = None,
    ) -> bool:
        """Send a general compliance change notification to a business admin."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        compliance_url = f"{app_base_url}/app/matcha/compliance"
        recipient_name = to_name or to_email

        requirement_word = "requirement" if changed_requirements_count == 1 else "requirements"
        requirement_verb = "has" if changed_requirements_count == 1 else "have"

        jurisdiction_lines = ""
        jurisdiction_text = ""
        if jurisdictions:
            preview = jurisdictions[:5]
            jurisdiction_items = "".join(f"<li>{name}</li>" for name in preview)
            jurisdiction_lines = f"""
            <p style="margin-top: 20px; margin-bottom: 8px;"><strong>Impacted jurisdictions:</strong></p>
            <ul style="margin-top: 0; color: #374151;">
                {jurisdiction_items}
            </ul>
            """
            jurisdiction_text = "\n".join([f"- {name}" for name in preview])

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
        .alert-card {{ background: #fff7ed; border-left: 4px solid #f97316; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <p>We detected an update to your compliance data for <strong>{location_name}</strong>.</p>

            <div class="alert-card">
                <p style="margin: 0;">
                    <strong>{changed_requirements_count}</strong> compliance {requirement_word} {requirement_verb} new information.
                </p>
            </div>

            {jurisdiction_lines}

            <p>Please log in and review the Compliance tab to see what changed and confirm any needed follow-up.</p>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{compliance_url}" class="btn">Review Compliance Updates</a>
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
Hi {recipient_name},

We detected an update to your compliance data for {location_name}.

{changed_requirements_count} compliance {requirement_word} {requirement_verb} new information.
{f"{chr(10)}Impacted jurisdictions:{chr(10)}{jurisdiction_text}{chr(10)}" if jurisdiction_text else ""}
Please log in and review the Compliance tab to see what changed:
{compliance_url}

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
                    "name": recipient_name,
                }
            ],
            "subject": f"{company_name}: Compliance update available",
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
                    print(f"[Email] Sent compliance change notification to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_ir_incident_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        incident_id: str,
        incident_number: str,
        incident_title: str,
        event_type: str,
        current_status: str,
        changed_by_email: Optional[str] = None,
        previous_status: Optional[str] = None,
        location_name: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> bool:
        """Send incident lifecycle notifications to a company admin/client."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        incident_url = f"{app_base_url}/app/ir/incidents/{incident_id}"
        recipient_name = to_name or to_email

        status_label = current_status.replace("_", " ").title() if current_status else "Unknown"
        previous_status_label = (
            previous_status.replace("_", " ").title()
            if previous_status else "Unknown"
        )
        actor = changed_by_email or "a team member"
        occurred_text = occurred_at.strftime("%B %d, %Y at %I:%M %p") if occurred_at else "Not provided"
        location_text = location_name or "Not provided"

        if event_type == "created":
            subject = f"{company_name}: New incident reported ({incident_number})"
            summary_line = "A new incident report was created."
            transition_line = f"Current status: <strong>{status_label}</strong>"
            transition_text = f"Current status: {status_label}"
        else:
            subject = f"{company_name}: Incident {incident_number} moved to {status_label}"
            summary_line = "An incident report changed stages."
            transition_line = (
                f"Status moved from <strong>{previous_status_label}</strong> "
                f"to <strong>{status_label}</strong>."
            )
            transition_text = f"Status moved from {previous_status_label} to {status_label}."

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
        .event-card {{ background: #f8fafc; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .incident-card {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <div class="event-card">
                <p style="margin: 0 0 8px 0;"><strong>{summary_line}</strong></p>
                <p style="margin: 0;">{transition_line}</p>
            </div>

            <div class="incident-card">
                <p><strong>Incident:</strong> {incident_number}</p>
                <p><strong>Title:</strong> {incident_title}</p>
                <p><strong>Occurred:</strong> {occurred_text}</p>
                <p><strong>Location:</strong> {location_text}</p>
                <p><strong>Updated by:</strong> {actor}</p>
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{incident_url}" class="btn">Open Incident</a>
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
Hi {recipient_name},

{summary_line}
{transition_text}

Incident: {incident_number}
Title: {incident_title}
Occurred: {occurred_text}
Location: {location_text}
Updated by: {actor}

Open incident:
{incident_url}

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
                    "name": recipient_name,
                }
            ],
            "subject": subject,
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
                    print(f"[Email] Sent IR notification to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_leave_request_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        employee_name: str,
        leave_type: str,
        event_type: str,
        leave_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        deadline_date: Optional[str] = None,
        deadline_type: Optional[str] = None,
    ) -> bool:
        """Send lifecycle notifications for leave requests and deadlines."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        leave_url = f"{app_base_url}/app/matcha/employees/leave/requests/{leave_id}"
        recipient_name = to_name or to_email
        leave_type_label = leave_type.replace("_", " ").upper()
        date_range = f"{start_date} to {end_date}" if end_date else start_date

        subject_map = {
            "submitted": f"{company_name}: Leave request from {employee_name}",
            "approved": f"{company_name}: Your leave request has been approved",
            "denied": f"{company_name}: Leave request update",
            "deadline_approaching": (
                f"{company_name}: Action needed — "
                f"{(deadline_type or 'deadline').replace('_', ' ').title()} due {deadline_date or 'soon'}"
            ),
            "notice_ready": f"{company_name}: Document ready for signature",
            "return_pending": f"{company_name}: Return-to-work tasks assigned",
        }
        subject = subject_map.get(event_type, f"{company_name}: Leave request update")

        if event_type == "submitted":
            summary = "A leave request was submitted and requires review."
        elif event_type == "approved":
            summary = "A leave request was approved."
        elif event_type == "denied":
            summary = "A leave request decision was recorded."
        elif event_type == "deadline_approaching":
            summary = "A leave compliance deadline is approaching."
        elif event_type == "notice_ready":
            summary = "A leave notice document is ready for review/signature."
        elif event_type == "return_pending":
            summary = "Return-to-work tasks were assigned."
        else:
            summary = "A leave request update is available."

        deadline_line = ""
        deadline_text = ""
        if deadline_type or deadline_date:
            dt_label = (deadline_type or "deadline").replace("_", " ").title()
            deadline_line = f"<p><strong>Deadline:</strong> {dt_label} ({deadline_date or 'soon'})</p>"
            deadline_text = f"Deadline: {dt_label} ({deadline_date or 'soon'})\n"

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
        .event-card {{ background: #f9fafb; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .leave-card {{ background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <div class="event-card">
                <p style="margin: 0;"><strong>{summary}</strong></p>
            </div>

            <div class="leave-card">
                <p><strong>Employee:</strong> {employee_name}</p>
                <p><strong>Leave Type:</strong> {leave_type_label}</p>
                <p><strong>Date Range:</strong> {date_range}</p>
                {deadline_line}
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{leave_url}" class="btn">Open Leave Request</a>
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
Hi {recipient_name},

{summary}

Employee: {employee_name}
Leave Type: {leave_type_label}
Date Range: {date_range}
{deadline_text}Open leave request:
{leave_url}

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
                    "name": recipient_name,
                }
            ],
            "subject": subject,
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
                    print(f"[Email] Sent leave notification to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_accommodation_notification_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        case_number: str,
        event_type: str,
        employee_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """Send lifecycle notifications for accommodation cases."""
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        accommodations_url = f"{app_base_url}/app/matcha/accommodations"
        recipient_name = to_name or to_email
        employee_line = employee_name or "Employee"

        subject_map = {
            "case_opened": f"{company_name}: Accommodation request received ({case_number})",
            "action_needed": f"{company_name}: Action needed on accommodation {case_number}",
            "determination_made": f"{company_name}: Accommodation determination for {case_number}",
            "interactive_meeting_scheduled": f"{company_name}: Interactive process update for {case_number}",
        }
        subject = subject_map.get(event_type, f"{company_name}: Accommodation case update ({case_number})")

        if event_type == "case_opened":
            summary = "A new accommodation case was opened."
        elif event_type == "action_needed":
            summary = "This accommodation case needs follow-up."
        elif event_type == "determination_made":
            summary = "A determination has been recorded for this accommodation case."
        elif event_type == "interactive_meeting_scheduled":
            summary = "An interactive process meeting update is available."
        else:
            summary = "An accommodation case update is available."

        details_line = f"<p><strong>Details:</strong> {details}</p>" if details else ""
        details_text = f"Details: {details}\n" if details else ""

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
        .event-card {{ background: #f9fafb; border-left: 4px solid #7c3aed; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .case-card {{ background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {recipient_name},</p>

            <div class="event-card">
                <p style="margin: 0;"><strong>{summary}</strong></p>
            </div>

            <div class="case-card">
                <p><strong>Case Number:</strong> {case_number}</p>
                <p><strong>Employee:</strong> {employee_line}</p>
                {details_line}
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{accommodations_url}" class="btn">Open Accommodation Cases</a>
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
Hi {recipient_name},

{summary}

Case Number: {case_number}
Employee: {employee_line}
{details_text}Open accommodation cases:
{accommodations_url}

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
                    "name": recipient_name,
                }
            ],
            "subject": subject,
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
                    print(f"[Email] Sent accommodation notification to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False


    async def send_business_registration_pending_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
    ) -> bool:
        """Send an email confirming business registration is pending review.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

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
        .status-card {{ background: linear-gradient(135deg, #fef3c7 0%, #fef9c3 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #f59e0b; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .info-box {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
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

            <p>Thank you for registering <strong>{company_name}</strong> with Matcha!</p>

            <div class="status-card">
                <div class="status-icon">⏳</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #92400e; margin: 0;">Registration Pending Review</p>
            </div>

            <div class="info-box">
                <h3 style="margin-top: 0;">What happens next?</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>Our team will review your registration within 1-2 business days</li>
                    <li>You'll receive an email once your account is approved</li>
                    <li>Once approved, you'll have full access to all Matcha features</li>
                </ul>
            </div>

            <p>In the meantime, you can log in to see your pending status. If you have any questions, feel free to reach out to our support team.</p>
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

Thank you for registering {company_name} with Matcha!

Your business registration is currently pending review.

What happens next?
- Our team will review your registration within 1-2 business days
- You'll receive an email once your account is approved
- Once approved, you'll have full access to all Matcha features

In the meantime, you can log in to see your pending status. If you have any questions, feel free to reach out to our support team.

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
            "subject": f"Registration Pending: {company_name}",
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
                    print(f"[Email] Sent business registration pending email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_business_approved_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
    ) -> bool:
        """Send an email notifying that business registration was approved.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        dashboard_url = f"{app_base_url}/app"

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
        .status-card {{ background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #22c55e; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 16px; }}
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

            <p>Great news! Your business registration has been approved.</p>

            <div class="status-card">
                <div class="status-icon">✅</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #166534; margin: 0;">Registration Approved!</p>
            </div>

            <p>You now have full access to all Matcha features:</p>
            <ul>
                <li>AI-powered candidate screening</li>
                <li>Employee management tools</li>
                <li>HR compliance features</li>
                <li>And much more!</li>
            </ul>

            <p style="text-align: center;">
                <a href="{dashboard_url}" class="btn">Go to Dashboard</a>
            </p>

            <p>Welcome to Matcha! We're excited to have you on board.</p>
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

Great news! Your business registration has been approved.

{company_name} - Registration Approved!

You now have full access to all Matcha features:
- AI-powered candidate screening
- Employee management tools
- HR compliance features
- And much more!

Go to your dashboard: {dashboard_url}

Welcome to Matcha! We're excited to have you on board.

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
            "subject": f"Welcome to Matcha! {company_name} is Approved",
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
                    print(f"[Email] Sent business approved email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_candidate_reach_out_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        from_name: str,
        from_company: str,
    ) -> bool:
        """Send a personalized meeting-request email to a candidate.

        The subject and body are admin-reviewed (possibly AI-drafted) text.
        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

        # Wrap the plain-text body in a simple HTML email
        html_body = body.replace('\n', '<br>')
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.7; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; font-size: 15px; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            {html_body}
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit on behalf of {from_company}</p>
        </div>
    </div>
</body>
</html>
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": from_name or self.from_name,
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name,
                }
            ],
            "subject": subject,
            "html": html_content,
            "text": body,
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
                    print(f"[Email] Sent reach-out email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False

    async def send_business_rejected_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        reason: str,
    ) -> bool:
        """Send an email notifying that business registration was rejected.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

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
        .status-card {{ background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #ef4444; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .reason-box {{ background: #f9fafb; border-radius: 8px; padding: 20px; margin: 20px 0; border-left: 4px solid #6b7280; }}
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

            <p>We've reviewed your business registration and unfortunately, we're unable to approve it at this time.</p>

            <div class="status-card">
                <div class="status-icon">❌</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #991b1b; margin: 0;">Registration Not Approved</p>
            </div>

            <div class="reason-box">
                <h4 style="margin-top: 0; color: #374151;">Reason:</h4>
                <p style="margin-bottom: 0;">{reason}</p>
            </div>

            <p>If you believe this was a mistake or have additional information to provide, please contact our support team at <a href="mailto:support@hey-matcha.com">support@hey-matcha.com</a>.</p>
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

We've reviewed your business registration and unfortunately, we're unable to approve it at this time.

{company_name} - Registration Not Approved

Reason:
{reason}

If you believe this was a mistake or have additional information to provide, please contact our support team at support@hey-matcha.com.

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
            "subject": f"Registration Update: {company_name}",
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
                    print(f"[Email] Sent business rejected email to {to_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {to_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {to_email}: {e}")
            return False


    async def send_admin_interview_invitation_email(
        self,
        candidate_email: str,
        candidate_name: Optional[str],
        company_name: str,
        position_title: str,
    ) -> bool:
        """Send an admin interview invitation to a top-ranked candidate.

        This email goes to the top 3 candidates after project closes and ranking is complete.
        It congratulates them and lets them know the hiring team will reach out personally.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            print("[Email] MailerSend not configured, skipping email send")
            return False

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
        .highlight {{ background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; border-radius: 0 6px 6px 0; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi{' ' + candidate_name if candidate_name else ''},</p>

            <p>Congratulations — you've been selected as a <strong>top candidate</strong> for the following role:</p>

            <div class="role-card">
                <h2 style="margin-top: 0; color: #111;">{position_title}</h2>
                <p><strong>Company:</strong> {company_name}</p>
            </div>

            <div class="highlight">
                <strong>What's next:</strong> A member of the hiring team will be reaching out to you directly to schedule a personal interview. Please keep an eye on your inbox.
            </div>

            <p>Thank you for going through our process — we were impressed by your background and look forward to speaking with you.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi{' ' + candidate_name if candidate_name else ''},

Congratulations — you've been selected as a top candidate for:

{position_title} at {company_name}

What's next: A member of the hiring team will be reaching out to you directly to schedule a personal interview. Please keep an eye on your inbox.

Thank you for going through our process — we were impressed by your background and look forward to speaking with you.

- Matcha Recruit
"""

        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {
                    "email": candidate_email,
                    "name": candidate_name or candidate_email,
                }
            ],
            "subject": f"You're a top candidate: {position_title} at {company_name}",
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
                    print(f"[Email] Sent admin interview invitation to {candidate_email}")
                    return True
                else:
                    print(f"[Email] Failed to send to {candidate_email}: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"[Email] Error sending to {candidate_email}: {e}")
            return False


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
