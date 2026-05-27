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

# Human labels for the metric_key values the worker emits.
_METRIC_LABELS = {
    "trir": "TRIR (recordable incident rate)",
    "dart": "DART rate (days away / restricted / transferred)",
    "lost_days": "Lost workdays",
    "claim_free_broken": "Claim-free streak broken",
    "premium_increase": "Estimated premium impact",
}

_SEVERITY_COLOR = {"critical": "#dc2626", "warning": "#d97706"}


class BrokerEmailMixin:
    async def send_broker_risk_alert_digest(
        self,
        to_email: str,
        to_name: Optional[str],
        broker_name: str,
        alerts: list[dict],
        portfolio_url: Optional[str] = None,
    ) -> bool:
        """Send a broker a digest of clients whose WC/safety metrics worsened.

        `alerts` is a list of dicts, each with keys:
          company_name, metric_key, severity, message
          (and optionally current_value / prior_value / delta_pct).
        Returns True on successful send, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Email service not configured, skipping broker risk digest")
            return False
        if not alerts:
            return False

        count = len(alerts)
        subject = (
            f"Risk alert: {count} client{'s' if count != 1 else ''} trending negative"
        )

        rows_html = []
        rows_text = []
        for a in alerts:
            company = html.escape(str(a.get("company_name") or "Client"))
            metric = html.escape(_METRIC_LABELS.get(a.get("metric_key"), str(a.get("metric_key") or "Metric")))
            message = html.escape(str(a.get("message") or ""))
            severity = a.get("severity") or "warning"
            color = _SEVERITY_COLOR.get(severity, "#d97706")
            rows_html.append(f"""
            <tr>
                <td style="padding:12px 14px;border-bottom:1px solid #e5e7eb;vertical-align:top;">
                    <div style="font-weight:600;color:#111827;">{company}</div>
                    <div style="color:#6b7280;font-size:13px;margin-top:2px;">{metric}</div>
                </td>
                <td style="padding:12px 14px;border-bottom:1px solid #e5e7eb;vertical-align:top;">
                    <span style="display:inline-block;padding:2px 8px;border-radius:999px;background:{color};color:#fff;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">{html.escape(severity)}</span>
                    <div style="color:#374151;font-size:13px;margin-top:6px;">{message}</div>
                </td>
            </tr>""")
            rows_text.append(f"- [{severity.upper()}] {company} — {metric}: {message}")

        link_block_html = (
            f'<p style="margin:24px 0;"><a class="btn" href="{html.escape(portfolio_url)}">View portfolio</a></p>'
            if portfolio_url
            else ""
        )
        link_block_text = f"\nView portfolio: {portfolio_url}\n" if portfolio_url else ""

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
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">MATCHA</div>
        </div>
        <div class="content">
            <p>Hi {html.escape(to_name or broker_name or "there")},</p>
            <p>The following client{'s' if count != 1 else ''} in your portfolio
               show a negative safety/Workers&nbsp;Comp trend over the trailing 12 months
               compared to the prior 12 months:</p>
            <table>
                <tbody>{''.join(rows_html)}</tbody>
            </table>
            {link_block_html}
            <p style="color:#6b7280;font-size:13px;">Trends are computed from OSHA-recordable
               incidents. Premium impact is a directional estimate, not a quote.</p>
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
            f"The following client(s) in your portfolio show a negative safety/Workers Comp "
            f"trend over the trailing 12 months vs the prior 12 months:\n\n"
            + "\n".join(rows_text)
            + "\n"
            + link_block_text
            + "\nTrends are computed from OSHA-recordable incidents. "
            "Premium impact is a directional estimate, not a quote.\n"
        )

        return await self._send_with_fallback(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
