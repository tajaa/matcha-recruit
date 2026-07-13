"""HR Pilot escalation gate — decides when a supervisor's question must go to
corporate HR instead of getting AI-drafted guidance.

HR Pilot exists so an on-site supervisor has a first-line resource before
paging corporate HR. But some topics are not "first-line" at all — a
supervisor typing out how they plan to handle a harassment complaint or a
workplace injury is not a drafting exercise, it's a live legal-exposure
event, and the fastest safe answer is "stop, call HR now."

So this gate is a deterministic keyword classifier, not a model judgment
call — the same posture as `discipline_compliance.py`: a model that
"usually" catches a harassment disclosure is worse than useless. Unlike that
module's SQL-grounded statute check, there's no database record to test
here (the input is free text from a supervisor mid-conversation), so this
is necessarily a best-effort keyword match, not a certainty. That asymmetry
cuts one way: prefer over-triggering a hard stop (mildly annoying) over
missing one (a supervisor conversationally handles what should have been an
HR intake). Categories are ordered by severity; the first match wins.

`classify_message()` is pure and DB-free (mirrors `schedule_rules.py`'s
"testable without a database" pattern) so category coverage can be unit
tested directly against strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CORPORATE_HR_ESCALATION_NOTICE = (
    "This needs to go to corporate HR directly rather than being handled "
    "on-site — please contact HR now and hold off on taking action until "
    "you hear back from them."
)

# Ordered most-severe first. Each entry: (category, notice, keyword patterns).
# Patterns are intentionally broad word/phrase matches, not a strict regex
# grammar — a false-positive hard stop just tells a supervisor to call HR,
# which is always a safe outcome; a false negative is the failure mode to
# avoid.
_HARD_STOP_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "harassment_discrimination",
        "Harassment and discrimination complaints must be handled by corporate "
        "HR directly — do not investigate or respond on your own.",
        (
            r"\bharass(?:ment|ed|ing)?\b",
            r"\bsexual(?:ly)?\b",
            r"\bdiscriminat(?:e|ed|ion|ory)\b",
            r"\bhostile work\s?environment\b",
            r"\bretaliat(?:e|ed|ion|ory)\b",
            r"\bracis[mt]\b",
            r"\bslur\b",
            r"\bassault(?:ed)?\b",
            r"\bgroped?\b",
        ),
    ),
    (
        "workplace_safety",
        "Injuries and safety incidents must be routed through corporate HR / "
        "your incident-reporting process, not handled informally.",
        (
            r"\binjur(?:y|ed|ies)\b",
            r"\baccident\b",
            r"\bhospital(?:ized)?\b",
            r"\b911\b",
            r"\bbleeding\b",
            r"\bfell? off\b",
            r"\bworkers[' ]?comp(?:ensation)?\b",
            r"\bOSHA\b",
        ),
    ),
    (
        "leave_and_medical",
        "Leave requests and medical situations (FMLA, disability, pregnancy, "
        "serious illness) must be routed to corporate HR — do not approve, "
        "deny, or discuss medical details directly.",
        (
            r"\bFMLA\b",
            r"\bmedical leave\b",
            r"\bpregnan(?:t|cy)\b",
            r"\bdisabilit(?:y|ies)\b",
            r"\baccommodation\b",
            r"\bmental health\b",
            r"\bsuicid(?:e|al)\b",
        ),
    ),
    (
        "termination_or_legal",
        "Terminations and anything involving a lawyer, lawsuit, or government "
        "agency complaint must go through corporate HR before any action is "
        "taken.",
        (
            r"\bfir(?:e|ed|ing)\b",
            r"\bterminat(?:e|ed|ion)\b",
            r"\blay ?off\b",
            r"\blawsuit\b",
            r"\blawyer\b",
            r"\battorney\b",
            r"\bEEOC\b",
            r"\bunion\b",
            r"\bwhistleblow(?:er|ing)?\b",
        ),
    ),
)

_COMPILED = tuple(
    (category, notice, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for category, notice, patterns in _HARD_STOP_CATEGORIES
)


@dataclass(frozen=True)
class EscalationVerdict:
    hard_stop: bool
    category: str | None = None
    notice: str | None = None
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


def classify_message(text: str) -> EscalationVerdict:
    """Classify a supervisor's HR Pilot message. Pure, DB-free, deterministic.

    Returns the first (most severe) category with a match. A message can
    trip multiple categories; only the highest-severity one is reported —
    the notice always says "call corporate HR", so which category matched
    first doesn't change the action the supervisor takes.
    """
    if not text or not text.strip():
        return EscalationVerdict(hard_stop=False)

    for category, notice, patterns in _COMPILED:
        matched = tuple(p.pattern for p in patterns if p.search(text))
        if matched:
            return EscalationVerdict(
                hard_stop=True,
                category=category,
                notice=notice,
                matched_terms=matched,
            )

    return EscalationVerdict(hard_stop=False)
