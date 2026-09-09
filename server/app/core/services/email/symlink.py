"""Sym-link emails: the recipient invite and the sender's completion notice.

Both take a prebuilt ``link`` (same shape as ``send_ir_info_request_email``)
so the route owns URL construction. The weekly passcode is deliberately NOT a
parameter — it must never ride in the same email as the link.
"""
import html
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_STYLE = """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; padding: 20px 0; border-bottom: 2px solid #22c55e; }
        .logo { color: #22c55e; font-size: 24px; font-weight: bold; letter-spacing: 2px; }
        .content { padding: 30px 0; }
        .btn { display: inline-block; background: #22c55e; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 10px 5px 10px 0; }
        .footer { text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }
        .highlight { background: #ecfdf5; border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0; }
"""


class SymlinkEmailMixin:
    async def send_symlink_invite_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        requested_by_name: str,
        title: str,
        instructions: Optional[str],
        link: str,
        expires_text: Optional[str] = None,
        *,
        reminder: bool = False,
    ) -> bool:
        """Send (or re-send) a sym-link to its recipient. Returns True on success."""
        if not self.is_configured():
            logger.warning("Email not configured, skipping sym-link invite")
            return False

        to_name_esc = html.escape(to_name) if to_name else None
        by_esc = html.escape(requested_by_name)
        company_esc = html.escape(company_name)
        title_esc = html.escape(title)
        instr_esc = html.escape(instructions) if instructions else None
        instr_section = f'<div class="highlight"><p style="margin:0">{instr_esc}</p></div>' if instr_esc else ""
        instr_text = f"{instructions}\n\n" if instructions else ""
        expiry_html = f"<p style=\"color:#6b7280;font-size:14px;\">This link expires {html.escape(expires_text)}.</p>" if expires_text else ""
        expiry_text = f"This link expires {expires_text}.\n" if expires_text else ""
        lead = "Just a reminder — " if reminder else ""

        html_content = f"""
<!DOCTYPE html>
<html>
<head><style>{_STYLE}</style></head>
<body>
    <div class="container">
        <div class="header"><div class="logo">MATCHA</div></div>
        <div class="content">
            <p>Hi{' ' + to_name_esc if to_name_esc else ''},</p>
            <p>{lead}{by_esc} at {company_esc} needs something from you: <strong>{title_esc}</strong>.</p>
            {instr_section}
            <p>Open the link below and a short guided chat will walk you through exactly what's needed.
            You'll be asked for your company's current passcode first — {by_esc} or your manager can give it to you.</p>
            <p><a href="{link}" class="btn">Get started</a></p>
            {expiry_html}
            <p style="color:#6b7280;font-size:14px;">This link is unique to you. Please don't forward it.</p>
        </div>
        <div class="footer"><p>Sent on behalf of {company_esc} via Matcha</p></div>
    </div>
</body>
</html>
"""
        text_content = f"""Hi{' ' + to_name if to_name else ''},

{lead}{requested_by_name} at {company_name} needs something from you: {title}.

{instr_text}Open the link below and a short guided chat will walk you through what's needed.
You'll be asked for your company's current passcode first — {requested_by_name} or your manager can give it to you.

{link}

{expiry_text}This link is unique to you. Please don't forward it.

Sent on behalf of {company_name} via Matcha
"""
        subject = f"{'Reminder: ' if reminder else ''}{company_name} needs: {title}"
        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)

    async def send_symlink_submitted_email(
        self,
        to_email: str,
        to_name: Optional[str],
        company_name: str,
        recipient_name: str,
        title: str,
        review_link: str,
    ) -> bool:
        """Tell the sender a recipient finished and the submission awaits review."""
        if not self.is_configured():
            logger.warning("Email not configured, skipping sym-link submitted notice")
            return False

        to_name_esc = html.escape(to_name) if to_name else None
        recipient_esc = html.escape(recipient_name)
        title_esc = html.escape(title)
        company_esc = html.escape(company_name)

        html_content = f"""
<!DOCTYPE html>
<html>
<head><style>{_STYLE}</style></head>
<body>
    <div class="container">
        <div class="header"><div class="logo">MATCHA</div></div>
        <div class="content">
            <p>Hi{' ' + to_name_esc if to_name_esc else ''},</p>
            <p><strong>{recipient_esc}</strong> completed <strong>{title_esc}</strong>. Nothing has been applied yet — review it and confirm.</p>
            <p><a href="{review_link}" class="btn">Review submission</a></p>
        </div>
        <div class="footer"><p>{company_esc} · Matcha</p></div>
    </div>
</body>
</html>
"""
        text_content = f"""Hi{' ' + to_name if to_name else ''},

{recipient_name} completed "{title}". Nothing has been applied yet — review it and confirm:

{review_link}

{company_name} · Matcha
"""
        subject = f"Sym-link completed: {title}"
        return await self._send_with_fallback(to_email, to_name, subject, html_content, text_content)
