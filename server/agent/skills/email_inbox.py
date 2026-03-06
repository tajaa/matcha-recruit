"""Email Inbox skill — fetches unread Gmail, summarizes via Gemini, writes digest."""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def run(config, sandbox) -> str | None:
    """Fetch unread emails and generate a daily digest."""
    if sandbox.gmail is None or not sandbox.gmail.is_configured:
        logger.info("Gmail not configured, skipping email_inbox")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    output_file = f"output/email-digest-{today}.md"

    # Idempotency: skip if today's digest already exists
    existing = sandbox.fs.list_dir("output")
    if f"email-digest-{today}.md" in existing:
        logger.info(f"Email digest for {today} already exists, skipping")
        return output_file

    # Load last-checked state
    state = _load_state(sandbox)
    last_checked = state.get("last_checked")

    # Fetch unread messages
    try:
        messages = await sandbox.gmail.fetch_unread(
            max_results=config.gmail_max_emails,
            label_ids=config.gmail_label_ids,
        )
    except Exception as e:
        logger.error(f"Failed to fetch emails: {e}")
        return None

    if not messages:
        logger.info("No unread emails found")
        _save_state(sandbox)
        return None

    logger.info(f"Found {len(messages)} unread email(s)")

    # Fetch full message details
    emails = []
    for msg_stub in messages:
        try:
            email = await sandbox.gmail.get_message(msg_stub["id"])
            emails.append(email)
        except Exception as e:
            logger.error(f"Failed to fetch message {msg_stub['id']}: {e}")

    if not emails:
        logger.warning("Could not fetch any email details")
        return None

    # Build prompt for Gemini
    emails_text = "\n\n---\n\n".join(
        f"From: {e['from']}\nSubject: {e['subject']}\nDate: {e['date']}\n\n{e['body'][:2000]}"
        for e in emails
    )

    prompt = f"""Summarize these emails into a daily digest. Group by priority/topic.

Format as markdown with:
- A "Priority" section for urgent or time-sensitive items
- Grouped sections by topic (e.g., Work, Notifications, Updates)
- Each item: bold subject, sender, 1-2 sentence summary
- Action items as a checklist at the end
- Keep it concise and scannable

Emails:
{emails_text}"""

    try:
        summary = await sandbox.llm.generate(prompt)
    except Exception as e:
        logger.error(f"Gemini summarization failed: {e}")
        summary = "Gemini summarization failed. Raw email subjects below.\n\n" + "\n".join(
            f"- {e['subject']} (from {e['from']})" for e in emails
        )

    # Build final output
    now = datetime.now().strftime("%I:%M %p")
    briefing = f"""# Email Digest — {today}

Generated at {now} · {len(emails)} emails

{summary}

---
_Last checked: {last_checked or 'first run'}_
"""

    sandbox.fs.write(output_file, briefing)
    _save_state(sandbox)
    logger.info(f"Email digest written to {output_file}")
    return output_file


def _load_state(sandbox) -> dict:
    try:
        raw = sandbox.fs.read("email_state.json")
        return json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(sandbox):
    state = {"last_checked": datetime.now().isoformat()}
    sandbox.fs.write("email_state.json", json.dumps(state, indent=2))
