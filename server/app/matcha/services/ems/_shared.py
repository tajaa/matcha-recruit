"""Shared EMS pill-text helper.

Lifted out of event_intake.py (2026-07-31) so scheduling/schedule_chat.py can
clamp its own pill text without importing the EMS intake module — same lift
pattern as ems/queries.py. event_intake re-imports this under its old private
name (`_sanitize_pill_text`), so its callers and tests are unchanged.
"""
from typing import Optional


def sanitize_pill_text(value, cap: int) -> Optional[str]:
    """Clamp model-written text destined for a channel system-message pill.

    Two rendering contracts this must never violate: systemContent.tsx
    parses ONLY balanced `**bold**` pairs (a stray `*` in model text would
    mis-pair with the category emphasis _confirmation_text/update_text add
    around it), and extract_question() recovers an armed clarify question
    by scanning rendered pill text for the literal `_QUESTION_MARKER`
    (`"\n🤔 "`) — a newline in model text could fake that marker. Collapse
    whitespace to single spaces and drop `*` before anything else touches
    this string."""
    text = str(value or "")
    text = " ".join(text.split())
    text = text.replace("*", "")
    text = text.strip()[:cap]
    return text or None
