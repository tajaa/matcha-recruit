"""Urgent-event fan-out helpers. Pure — no DB/Gemini.

    cd server && ./venv/bin/python -m pytest tests/ems/test_urgent_notify.py -q
"""

from app.matcha.services.ems.urgent_notify import build_urgent_email, resolve_email_recipients

_ADMINS = [
    {"id": "u1", "email": "admin1@x.com", "name": "Admin One"},
    {"id": "u2", "email": "admin2@x.com", "name": "Admin Two"},
]


class TestResolveEmailRecipients:
    def test_notify_all_admins_false_uses_explicit_only(self):
        protocol_row = {"notify_emails": ["hr@x.com"], "notify_all_admins": False}
        recipients = resolve_email_recipients(protocol_row, _ADMINS)
        assert [r["email"] for r in recipients] == ["hr@x.com"]

    def test_notify_all_admins_true_unions_and_dedupes_case_insensitively(self):
        protocol_row = {"notify_emails": ["Admin1@X.com"], "notify_all_admins": True}
        recipients = resolve_email_recipients(protocol_row, _ADMINS)
        emails = {r["email"].lower() for r in recipients}
        assert emails == {"admin1@x.com", "admin2@x.com"}
        assert len(recipients) == 2  # no duplicate for admin1

    def test_empty_explicit_and_all_admins_false_falls_back_to_admins(self):
        protocol_row = {"notify_emails": [], "notify_all_admins": False}
        recipients = resolve_email_recipients(protocol_row, _ADMINS)
        assert len(recipients) == 2  # never empty while admin_contacts is non-empty

    def test_no_protocol_row_falls_back_to_all_admins(self):
        recipients = resolve_email_recipients(None, _ADMINS)
        assert len(recipients) == 2


class TestBuildUrgentEmail:
    def test_osha_variant_content(self):
        subject, html = build_urgent_email(
            urgency="osha", company_name="Acme", title="Someone was hospitalized",
            category_label="Safety", channel_name="front-desk", link="/work/events/123",
        )
        assert "OSHA-reportable" in subject
        assert "8 hours" in html
        assert "1-800-321-6742" in html
        assert "/work/events/123" in html
        assert "Someone was hospitalized" not in subject  # title lives in the body, not subject

    def test_severe_variant_subject(self):
        subject, _ = build_urgent_email(
            urgency="severe", company_name="Acme", title="t",
            category_label="Behavioral", channel_name="ch", link="/x",
        )
        assert "severe" in subject.lower()

    def test_html_special_chars_in_interpolated_fields_are_escaped(self):
        # title/channel_name/company_name trace back to user-typed channel
        # content — a title like `<script>alert(1)</script>` must render as
        # inert text, not execute in a mail client that renders HTML.
        _, html = build_urgent_email(
            urgency="severe",
            company_name='Acme & <b>Co</b>',
            title="<script>alert(1)</script>",
            category_label="Safety",
            channel_name='front-desk"><img src=x onerror=alert(1)>',
            link="/x",
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        # The raw `<img ...>` tag must not survive — escaping `<`/`>` is
        # what makes it inert; the word "onerror=" surviving as plain text
        # inside an escaped, non-executing tag is fine.
        assert "<img" not in html
        assert "&lt;img" in html

    def test_no_narrative_leaks_into_email(self):
        # Only title/category/channel/link — never the narrative string.
        subject, html = build_urgent_email(
            urgency="severe", company_name="Acme", title="Fight broke out",
            category_label="Behavioral", channel_name="ch",
            link="/x",
        )
        sentinel = "the exact narrative sentence nobody should see"
        assert sentinel not in subject
        assert sentinel not in html

    def test_absolute_link_renders_as_a_real_href(self):
        # send_urgent_event_notifications must pass an absolute
        # app_base_url-prefixed link here — a bare relative path is a dead
        # CTA in a mail client. This only pins build_urgent_email's own
        # pass-through; the absolute-vs-relative decision lives in
        # send_urgent_event_notifications.
        _, html = build_urgent_email(
            urgency="osha", company_name="Acme", title="t",
            category_label="Safety", channel_name="ch",
            link="https://hey-matcha.com/work/events/123",
        )
        assert 'href="https://hey-matcha.com/work/events/123"' in html
