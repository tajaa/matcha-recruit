"""AuthEmailMixin email-send methods.

Extracted from `email.py` during the 2026-05-16 package split. Mixed
into `EmailService` (see `client.py`) via multiple inheritance. Method
bodies call `self.send_email(...)` / `self.is_configured()` / etc. —
`self` is the composed `EmailService` at runtime.
"""
import html
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class AuthEmailMixin:
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
            logger.warning("Gmail not configured, skipping email send")
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

        subject = f"{broker_name} invited you to activate {company_name} on Matcha"

        if not self.api_key:
            # Fall back to Gmail API if MailerSend not configured
            return await self.send_email(
                to_email=to_email, to_name=to_name, subject=subject,
                html_content=html_content, text_content=text_content,
            )

        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

    async def send_broker_welcome_email(
        self,
        to_email: str,
        to_name: str,
        broker_name: str,
        broker_slug: str,
        password: str,
    ) -> bool:
        """Send a welcome email to a newly created broker owner with their login credentials."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        login_url = f"{app_base_url}/login/{broker_slug}"
        safe_name = html.escape(to_name)
        safe_broker = html.escape(broker_name)
        safe_email = html.escape(to_email)
        safe_password = html.escape(password)

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
        .card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .card-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
        .card-value {{ font-size: 16px; font-weight: 600; color: #111; }}
        .card-value.mono {{ font-family: 'SF Mono', Monaco, Consolas, monospace; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; }}
        .security-note {{ background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 4px; padding: 12px 16px; margin: 20px 0; font-size: 14px; color: #92400e; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {safe_name},</p>

            <p>Your broker account <strong>{safe_broker}</strong> has been created on Matcha. Here are your login credentials:</p>

            <div class="card">
                <div style="margin-bottom: 16px;">
                    <div class="card-label">Email</div>
                    <div class="card-value">{safe_email}</div>
                </div>
                <div>
                    <div class="card-label">Password</div>
                    <div class="card-value mono">{safe_password}</div>
                </div>
            </div>

            <p style="text-align: center; margin-top: 24px;">
                <a href="{login_url}" class="btn">Log In to Your Dashboard</a>
            </p>

            <div class="security-note">
                For security, please change your password after your first login.
            </div>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi {to_name},

Your broker account "{broker_name}" has been created on Matcha.

Your login credentials:
  Email: {to_email}
  Password: {password}

Log in at: {login_url}

For security, please change your password after your first login.

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Welcome to Matcha — Your {broker_name} broker account is ready",
            html_content=html_content,
            text_content=text_content,
        )

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
            logger.warning("Gmail not configured, skipping email send")
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

        _subject = f"Registration Pending: {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_resources_free_welcome_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
    ) -> bool:
        """Welcome email for resources_free signups.

        Different copy from `send_business_approved_email` — free-tier accounts
        only unlock templates, calculators, JDs, glossary, and the compliance
        audit. They explicitly do NOT get the full platform.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        app_base_url = self.settings.app_base_url
        resources_url = f"{app_base_url}/app/resources"

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
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 15px; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        ul {{ padding-left: 20px; }}
        li {{ margin: 6px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>
            <p>Your free Matcha Resources account for <strong>{company_name}</strong> is ready.</p>
            <p>You now have access to:</p>
            <ul>
                <li>14 editable HR document templates (DOCX)</li>
                <li>62 ready-to-use job description templates (DOCX)</li>
                <li>HR calculators (PTO, overtime, turnover cost, total comp)</li>
                <li>Compliance audit — emailed gap report tailored to your business</li>
                <li>HR glossary covering FLSA, FMLA, ACA, and the rest</li>
            </ul>
            <p style="text-align: center;">
                <a href="{resources_url}" class="btn">Open Resources →</a>
            </p>
            <p style="color: #6b7280; font-size: 13px;">
                Need incident reporting, employee records, or progressive discipline?
                You can upgrade to Matcha Lite anytime from inside your account.
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Your free Matcha Resources account for {company_name} is ready.

You now have access to:
- 14 editable HR document templates (DOCX)
- 62 ready-to-use job description templates (DOCX)
- HR calculators (PTO, overtime, turnover cost, total comp)
- Compliance audit — emailed gap report tailored to your business
- HR glossary covering FLSA, FMLA, ACA, and the rest

Open Resources: {resources_url}

Need incident reporting, employee records, or progressive discipline?
You can upgrade to Matcha Lite anytime from inside your account.

- Matcha
"""

        _subject = f"Your Matcha Resources account is ready"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_email_verification_email(
        self,
        to_email: str,
        to_name: str,
        verification_url: str,
    ) -> bool:
        """Single-click email verification for resources_free signups.

        Sent BEFORE the user/company row exists. The link carries a JWT that
        the verify endpoint exchanges for the actual account. If the user
        never clicks, nothing is persisted.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
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
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 20px 0; font-size: 15px; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
        .small {{ color: #6b7280; font-size: 13px; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {to_name},</p>
            <p>Confirm your email to finish creating your free Matcha Resources account.</p>
            <p style="text-align: center;">
                <a href="{verification_url}" class="btn">Confirm email →</a>
            </p>
            <p class="small">Or paste this link into your browser:<br>{verification_url}</p>
            <p class="small">This link expires in 1 hour. If you didn't request this, you can ignore this email — no account is created until you click.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Confirm your email to finish creating your free Matcha Resources account.

Confirm email: {verification_url}

This link expires in 1 hour. If you didn't request this, ignore this email — no account is created until you click.

- Matcha
"""

        _subject = "Confirm your email — Matcha Resources"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

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
            logger.warning("Gmail not configured, skipping email send")
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

        _subject = f"Welcome to Matcha! {company_name} is Approved"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_lite_payment_pending_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        headcount: int,
    ) -> bool:
        """Sent at registration time for business-pays Matcha Lite signups.

        The account exists but Matcha Lite features are gated until the
        Stripe subscription completes. CTA points back at the app where
        MatchaLitePendingSidebar surfaces the resume-checkout button.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
            return False

        import math
        price_dollars = math.ceil(max(headcount, 1) / 10) * 100
        app_base_url = self.settings.app_base_url
        dashboard_url = f"{app_base_url}/app"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 2px solid #d7ba7d; }}
        .logo {{ color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }}
        .content {{ padding: 30px 0; }}
        .status-card {{ background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border-radius: 12px; padding: 30px; margin: 20px 0; text-align: center; border-left: 4px solid #d7ba7d; }}
        .status-icon {{ font-size: 48px; margin-bottom: 10px; }}
        .company-name {{ font-size: 24px; font-weight: 700; color: #111; margin-bottom: 8px; }}
        .price {{ font-size: 18px; color: #92400e; margin-top: 8px; }}
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

            <p>Your account for <strong>{company_name}</strong> is created. One last step: complete your subscription to activate Matcha Lite.</p>

            <div class="status-card">
                <div class="status-icon">⏳</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #92400e; margin: 0;">Payment required</p>
                <p class="price">${price_dollars}/month for {headcount} employee{'s' if headcount != 1 else ''}</p>
            </div>

            <p>Sign in and click <strong>Subscribe</strong> in the sidebar to finish checkout. Your incident reporting, HR resources, and compliance tools unlock the moment payment clears.</p>

            <p style="text-align: center;">
                <a href="{dashboard_url}" class="btn">Complete subscription</a>
            </p>

            <p style="font-size: 13px; color: #6b7280;">If you signed up by mistake, no action is required — the account stays inactive until paid.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Your account for {company_name} is created. One last step: complete your subscription to activate Matcha Lite.

Pricing: ${price_dollars}/month for {headcount} employee{'s' if headcount != 1 else ''}.

Sign in and click Subscribe in the sidebar to finish checkout:
{dashboard_url}

Your incident reporting, HR resources, and compliance tools unlock the moment payment clears.

If you signed up by mistake, no action is required.

- Matcha
"""

        _subject = f"Complete your Matcha Lite subscription — {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_lite_subscription_active_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
    ) -> bool:
        """Sent by the Stripe webhook when checkout.session.completed fires
        for a Matcha Lite subscription. Confirms activation and points back
        to the dashboard."""
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping email send")
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

            <p>Payment confirmed. Matcha Lite is active for <strong>{company_name}</strong>.</p>

            <div class="status-card">
                <div class="status-icon">✅</div>
                <div class="company-name">{company_name}</div>
                <p style="color: #166534; margin: 0;">Matcha Lite Active</p>
            </div>

            <p>You now have access to:</p>
            <ul>
                <li>Incident reporting + AI summaries</li>
                <li>State-by-state HR compliance guides</li>
                <li>Templates, calculators, and the compliance audit</li>
            </ul>

            <p style="text-align: center;">
                <a href="{dashboard_url}" class="btn">Open Matcha Lite</a>
            </p>

            <p>Welcome aboard.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

Payment confirmed. Matcha Lite is active for {company_name}.

You now have access to:
- Incident reporting + AI summaries
- State-by-state HR compliance guides
- Templates, calculators, and the compliance audit

Open Matcha Lite: {dashboard_url}

Welcome aboard.

- Matcha
"""

        _subject = f"Matcha Lite is active — {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

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
            logger.warning("Gmail not configured, skipping email send")
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

        _subject = f"Registration Update: {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)


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
            logger.warning("Gmail not configured, skipping email send")
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

        _subject = f"You're a top candidate: {position_title} at {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)


