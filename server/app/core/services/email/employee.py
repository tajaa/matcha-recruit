"""EmployeeEmailMixin email-send methods.

Extracted from `email.py` during the 2026-05-16 package split. Mixed
into `EmailService` (see `client.py`) via multiple inheritance. Method
bodies call `self.send_email(...)` / `self.is_configured()` / etc. —
`self` is the composed `EmailService` at runtime.
"""
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


class EmployeeEmailMixin:
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
            logger.warning("Gmail not configured, skipping employee invitation email")
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

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Welcome to {company_name} - Set Up Your Account",
            html_content=html_content,
            text_content=text_content,
        )


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
            logger.warning("Gmail not configured, skipping employee welcome email")
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

Questions? Contact your HR administrator.

- Matcha Recruit / {company_name}
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"You're all set — welcome to {company_name}",
            html_content=html_content,
            text_content=text_content,
        )

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
            logger.warning("MailerSend not configured, skipping onboarding reminder email")
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

        _subject = f"Onboarding reminder: {task_title}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_task_completion_notification(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        employee_name: str,
        task_title: str,
    ) -> bool:
        """Send a notification email when an onboarding task is completed."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping task completion notification")
            return False

        app_base_url = self.settings.app_base_url
        portal_url = f"{app_base_url}/app/onboarding"

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
        .card {{ background: #f0fdf4; border-radius: 10px; padding: 20px; margin: 20px 0; border-left: 4px solid #22c55e; }}
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
            <p><strong>{employee_name}</strong> has completed an onboarding task.</p>

            <div class="card">
                <p style="margin: 0;"><strong>Task:</strong> {task_title}</p>
                <p style="margin: 8px 0 0 0;">Status: Completed</p>
            </div>

            <p>
                <a href="{portal_url}" class="btn">View Onboarding Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit &mdash; {company_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Hi {to_name},

{employee_name} has completed an onboarding task.

Task: {task_title}
Status: Completed

View onboarding dashboard: {portal_url}

- Matcha Recruit / {company_name}
"""

        _subject = f"[{company_name}] Onboarding task completed \u2014 {employee_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

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
            logger.warning("MailerSend not configured, skipping onboarding escalation email")
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

        _subject = f"Onboarding escalation ({escalation_label}): {task_title}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)

    async def send_manager_onboarding_summary(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        summary_lines: list[str],
    ) -> bool:
        """Send a weekly manager summary of onboarding items."""
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping manager onboarding summary email")
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

        _subject = f"Weekly onboarding summary — {company_name}"
        return await self._send_with_fallback(to_email, to_name, _subject, html_content, text_content)


    async def send_provisioning_welcome_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        work_email: Optional[str] = None,
        temp_password: Optional[str] = None,
        slack_workspace_name: Optional[str] = None,
        slack_invite_link: Optional[str] = None,
    ) -> bool:
        """Send a welcome email to a new employee with their provisioned credentials.

        Sent to the employee's personal email with their new work email,
        temporary password, and Slack invite info.
        """
        if not self.is_configured():
            logger.warning("MailerSend not configured, skipping provisioning welcome email")
            return False

        # Build credential sections
        google_section_html = ""
        google_section_text = ""
        if work_email:
            password_html = ""
            password_text = ""
            if temp_password:
                password_html = f"""
                    <div style="margin-top: 12px;">
                        <div style="font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Temporary Password</div>
                        <div style="margin-top: 4px; font-family: monospace; font-size: 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 4px; padding: 8px 12px; display: inline-block;">{temp_password}</div>
                        <div style="margin-top: 8px; color: #dc2626; font-size: 13px;">You will be asked to change this password on your first login.</div>
                    </div>"""
                password_text = f"\nTemporary Password: {temp_password}\n(You will be asked to change this on first login.)"

            google_section_html = f"""
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 12px 0; color: #166534;">Google Workspace Account</h3>
                <div>
                    <div style="font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Work Email</div>
                    <div style="margin-top: 4px; font-size: 16px; color: #111;">{work_email}</div>
                </div>{password_html}
                <div style="margin-top: 16px;">
                    <a href="https://accounts.google.com" style="display: inline-block; background: #22c55e; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">Sign in to Google Workspace</a>
                </div>
            </div>"""
            google_section_text = f"""
Google Workspace Account
------------------------
Work Email: {work_email}{password_text}
Sign in: https://accounts.google.com
"""

        slack_section_html = ""
        slack_section_text = ""
        if slack_workspace_name and slack_invite_link:
            slack_section_html = f"""
            <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 12px 0; color: #7c3aed;">Slack Workspace</h3>
                <div>
                    <div style="font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Workspace</div>
                    <div style="margin-top: 4px; font-size: 16px; color: #111;">{slack_workspace_name}</div>
                </div>
                <div style="margin-top: 16px;">
                    <a href="{slack_invite_link}" style="display: inline-block; background: #7c3aed; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">Join Slack Workspace</a>
                </div>
            </div>"""
            slack_section_text = f"""
Slack Workspace
---------------
Workspace: {slack_workspace_name}
Join here: {slack_invite_link}
"""

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

            <p>Welcome to <strong>{company_name}</strong>! Your accounts have been set up and are ready to go.</p>

            {google_section_html}
            {slack_section_html}

            <p style="color: #6b7280; font-size: 14px; margin-top: 24px;">If you have any questions about getting started, reach out to your manager or HR team.</p>
        </div>
        <div class="footer">
            <p>Sent via Matcha Recruit</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Hi {to_name},

Welcome to {company_name}! Your accounts have been set up and are ready to go.
{google_section_text}{slack_section_text}
If you have any questions about getting started, reach out to your manager or HR team.

- Matcha Recruit
"""

        return await self.send_email(
            to_email=to_email,
            to_name=to_name,
            subject=f"Welcome to {company_name} — Your account credentials",
            html_content=html_content,
            text_content=text_content,
        )


