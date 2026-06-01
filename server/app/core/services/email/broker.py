"""BrokerEmailMixin email-send methods.

Mixed into `EmailService` (see `client.py`) via multiple inheritance. Method
bodies call `self._send_with_fallback(...)` / `self.is_configured()` — `self`
is the composed `EmailService` at runtime.

Holds broker-portfolio notifications. The risk-trend digest is sent by the
`broker_risk_alerts` Celery task (one email per broker per cycle).
"""
import html
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BrokerEmailMixin:
    async def send_broker_risk_alert_digest(
        self,
        to_email: str,
        to_name: Optional[str],
        broker_name: str,
        alerts: list[dict],
        portfolio_url: Optional[str] = None,
    ) -> bool:
        """Notify a broker that their portal has new risk-trend flags.

        Deliberately minimal — no client names, metrics, values, or trend
        details. Those are privileged and live behind auth in the portal.
        Email is a pointer, not a report.

        `alerts` is accepted for signature compatibility with the worker; only
        its truthiness is used (we won't send a "you have alerts" email with
        zero alerts).
        """
        if not self.is_configured():
            logger.warning("Email service not configured, skipping broker risk digest")
            return False
        if not alerts:
            return False

        subject = "New risk-trend flags in your portfolio"
        greeting = html.escape(to_name or broker_name or "there")
        link = html.escape(portfolio_url) if portfolio_url else None

        cta_html = (
            f'<p style="margin:24px 0;"><a class="btn" href="{link}">View portal</a></p>'
            if link else ""
        )
        cta_text = f"\nView portal: {portfolio_url}\n" if portfolio_url else ""

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
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {greeting},</p>
            <p>There are new risk-trend flags to review in your broker portal.
               Sign in to see which clients are affected and the underlying metrics.</p>
            {cta_html}
            <p style="color:#6b7280;font-size:13px;">Details are kept inside the portal
               for confidentiality — this email is just a heads-up.</p>
        </div>
        <div class="footer">
            Matcha — broker portfolio monitoring
        </div>
    </div>
</body>
</html>
"""

        text_content = (
            f"Hi {to_name or broker_name or 'there'},\n\n"
            "There are new risk-trend flags to review in your broker portal. "
            "Sign in to see which clients are affected and the underlying metrics.\n"
            + cta_text
            + "\nDetails are kept inside the portal for confidentiality — "
              "this email is just a heads-up.\n"
        )

        return await self._send_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    async def send_benefit_eligibility_nudge_email(
        self,
        to_email: str,
        to_name: Optional[str],
        broker_name: str,
        company_name: str,
        employee_name: str,
        exception_type: str,
        days_remaining: Optional[int] = None,
    ) -> bool:
        """'Ping Client HR' nudge — a broker asks a client's HR contact to act on
        a benefits eligibility exception (a new-hire enrollment gap or a
        terminated employee still carrying active health deductions)."""
        if not self.is_configured():
            logger.warning("Email service not configured, skipping benefit eligibility nudge")
            return False

        greeting = html.escape(to_name or "there")
        emp = html.escape(employee_name or "an employee")
        broker = html.escape(broker_name or "Your broker")
        company = html.escape(company_name or "your company")

        if exception_type == "termination_premium_leak":
            subject = f"Action needed: terminated employee still has active benefit deductions ({company})"
            headline = (
                f"{emp} appears to be terminated but is still listed with active health-insurance "
                "deductions. Please confirm the termination in payroll and stop the benefit "
                "deductions to avoid paying premiums for someone no longer covered."
            )
        else:
            window = (
                f"about {days_remaining} day(s) left"
                if isinstance(days_remaining, int) and days_remaining > 0
                else "the enrollment window is closing"
            )
            subject = f"Action needed: new hire not yet enrolled in benefits ({company})"
            headline = (
                f"{emp} was recently hired and has not completed benefits enrollment — {window} "
                "to enroll. Please remind them to make their elections before the deadline."
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
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><div class="logo">MATCHA</div></div>
        <div class="content">
            <p>Hi {greeting},</p>
            <p>{headline}</p>
            <p style="color:#6b7280;font-size:13px;">Flagged by {broker} via Matcha's benefits
               eligibility monitoring.</p>
        </div>
        <div class="footer">Matcha — benefits eligibility monitoring</div>
    </div>
</body>
</html>
"""
        text_content = (
            f"Hi {to_name or 'there'},\n\n{headline}\n\n"
            f"Flagged by {broker_name or 'your broker'} via Matcha's benefits eligibility monitoring.\n"
        )

        return await self._send_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
