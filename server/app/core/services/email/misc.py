"""MiscEmailMixin email-send methods.

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


class MiscEmailMixin:
    async def send_contact_form_email(
        self,
        sender_name: str,
        sender_email: str,
        company_name: str,
        message: str,
        preferred_date: str | None = None,
        preferred_time: str | None = None,
    ) -> bool:
        """Send a contact form submission to the admin email.

        Returns True if sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping contact form email")
            return False

        contact_email = self.settings.contact_email

        is_consultation = preferred_date is not None or preferred_time is not None
        subject_prefix = "Consultation Request" if is_consultation else "Contact Form"

        schedule_html = ""
        schedule_text = ""
        if is_consultation:
            date_str = preferred_date or "Not specified"
            time_str = preferred_time or "Not specified"
            schedule_html = f"""
                <div style="margin-bottom: 16px;">
                    <div class="label">Requested Date</div>
                    <div class="value">{date_str}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Requested Time (ET)</div>
                    <div class="value">{time_str}</div>
                </div>"""
            schedule_text = f"\nRequested Date: {date_str}\nRequested Time (ET): {time_str}"

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
            <h2 style="margin-top: 0;">{'New Consultation Request' if is_consultation else 'New Contact Form Submission'}</h2>

            <div class="info-card">
                <div style="margin-bottom: 16px;">
                    <div class="label">Company</div>
                    <div class="value">{company_name}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Contact Name</div>
                    <div class="value">{sender_name}</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div class="label">Email</div>
                    <div class="value"><a href="mailto:{sender_email}">{sender_email}</a></div>
                </div>{schedule_html}
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
{'New Consultation Request' if is_consultation else 'New Contact Form Submission'}

Company: {company_name}
Contact: {sender_name}
Email: {sender_email}{schedule_text}

Message:
{message}

---
Sent from Matcha Recruit contact form
"""

        return await self.send_email(
            to_email=contact_email,
            to_name="Matcha Team",
            subject=f"{subject_prefix}: {company_name} - {sender_name}",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_blog_comment_pending_notification(
        self,
        to_email: str,
        post_title: str,
        post_slug: str,
        author_label: str,
        comment_excerpt: str,
        comment_id: str,
    ) -> bool:
        """Notify a platform admin that a blog comment is awaiting review."""
        if not self.is_configured():
            logger.warning("Email not configured, skipping blog comment notification")
            return False

        app_base_url = (self.settings.app_base_url or "").rstrip("/")
        post_url = f"{app_base_url}/blog/{post_slug}" if app_base_url else f"/blog/{post_slug}"
        admin_url = f"{app_base_url}/admin/blogs?tab=comments" if app_base_url else "/admin/blogs?tab=comments"

        post_title_safe = html.escape(post_title)
        author_safe = html.escape(author_label)
        excerpt_safe = html.escape(comment_excerpt)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .logo {{ color: #22c55e; font-size: 22px; font-weight: bold; letter-spacing: 2px; }}
        .card {{ background: #f8fafc; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .quote {{ background: #f9fafb; border-radius: 6px; padding: 12px 14px; font-style: italic; color: #444; margin: 12px 0; white-space: pre-wrap; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; margin-top: 24px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">MATCHA</div>
        <h2 style="font-size:18px;color:#111;">New blog comment awaiting review</h2>
        <div class="card">
            <p style="margin:0 0 4px 0;"><strong>Post:</strong> <a href="{post_url}">{post_title_safe}</a></p>
            <p style="margin:0;"><strong>From:</strong> {author_safe}</p>
        </div>
        <div class="quote">{excerpt_safe}</div>
        <p style="text-align:center;">
            <a href="{admin_url}" class="btn">Review &amp; moderate</a>
        </p>
        <div class="footer">Sent via Matcha Recruit · comment id {comment_id}</div>
    </div>
</body>
</html>
"""
        text_content = (
            f"New blog comment awaiting review\n\n"
            f"Post: {post_title}\n{post_url}\n\n"
            f"From: {author_label}\n\n"
            f"\"{comment_excerpt}\"\n\n"
            f"Review & moderate: {admin_url}\n"
        )

        return await self.send_email(
            to_email=to_email,
            subject=f"[Matcha] New blog comment on \"{post_title}\" awaiting review",
            html_content=html_content,
            text_content=text_content,
        )

    async def send_channel_invite_email(
        self,
        to_email: str,
        channel_name: str,
        inviter_name: str,
        join_url: str,
    ) -> bool:
        """Invite a non-user to a channel via a free-signup link.

        Sent when a channel owner/moderator invites someone by email who does
        not have an account yet. `join_url` lands on the public join page,
        which creates a free personal workspace and drops them into the
        channel. Returns True if sent, False otherwise (incl. reserved-domain
        guard skips).
        """
        if not self.is_configured():
            logger.warning("Gmail not configured, skipping channel invite email")
            return False

        channel_safe = html.escape(channel_name)
        inviter_safe = html.escape(inviter_name)

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .logo {{ color: #22c55e; font-size: 22px; font-weight: bold; letter-spacing: 2px; }}
        .card {{ background: #f8fafc; border-left: 4px solid #22c55e; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .btn {{ display: inline-block; background: #22c55e; color: white; padding: 12px 22px; text-decoration: none; border-radius: 6px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; margin-top: 24px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">MATCHA</div>
        <h2 style="font-size:18px;color:#111;">You're invited to a channel</h2>
        <div class="card">
            <p style="margin:0;"><strong>{inviter_safe}</strong> invited you to join the channel
            <strong>#{channel_safe}</strong>.</p>
        </div>
        <p>Create a free account and you'll be dropped straight into the conversation.</p>
        <p style="text-align:center;">
            <a href="{join_url}" class="btn">Join #{channel_safe}</a>
        </p>
        <p style="font-size:12px;color:#6b7280;">Or paste this link into your browser:<br>{join_url}</p>
        <div class="footer">If you weren't expecting this invitation, you can ignore this email.</div>
    </div>
</body>
</html>
"""
        text_content = (
            f"{inviter_name} invited you to join the channel #{channel_name}.\n\n"
            f"Create a free account and you'll be dropped straight into the conversation:\n"
            f"{join_url}\n\n"
            f"If you weren't expecting this invitation, you can ignore this email.\n"
        )

        return await self.send_email(
            to_email=to_email,
            to_name=None,
            subject=f"{inviter_name} invited you to #{channel_name}",
            html_content=html_content,
            text_content=text_content,
        )
