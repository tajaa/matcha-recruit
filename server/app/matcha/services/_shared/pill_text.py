"""Channel system-pill text hygiene — shared by every @huume channel skill
(EMS intake/ask, schedule chat). Lives in services/_shared/ because these are
channel-pill RENDERING contracts, not EMS domain rules: systemContent.tsx
parses only balanced `**bold**` pairs, and extract_question() recovers an
armed clarify question by scanning rendered pill text for the literal
`"\n🤔 "` marker — so model-written text must never carry `*` or 🤔.
"""
from typing import Optional

# The armed-clarify marker glyph (event_intake._QUESTION_MARKER is "\n🤔 ").
QUESTION_MARKER_CHAR = "\U0001F914"


def sanitize_pill_text(value, cap: int, *, keep_newlines: bool = False) -> Optional[str]:
    """Clamp model-written text destined for a channel system-message pill.

    Default mode (intake/schedule ack lines): collapse ALL whitespace to
    single spaces — kills any "\n🤔 " a model could fake — then strip `*`
    and the 🤔 glyph, cap, and return None for empty.

    keep_newlines=True (the ask answer path — pills render with
    whitespace-pre-wrap and answers legitimately use short dashed lists):
    whitespace survives verbatim; stripping the 🤔 glyph alone is what makes
    a faked marker impossible, since the scan looks for newline+🤔+space.
    """
    text = str(value or "")
    if not keep_newlines:
        text = " ".join(text.split())
    text = text.replace("*", "").replace(QUESTION_MARKER_CHAR, "")
    text = text.strip()[:cap]
    return text or None
