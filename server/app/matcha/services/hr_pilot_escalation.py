"""HR Pilot escalation gate — decides when a question must go to corporate HR
instead of getting AI-drafted guidance.

Serves TWO surfaces: the supervisor-facing HR Pilot thread mode, and the
employee-facing Ask HR portal (`services/ask_hr.py`). The four categories are
the same either way, but the *phrasing* is not, and the pattern sets are
therefore split — see `_EMPLOYEE_EXTRA_PATTERNS` for why mixing them breaks the
supervisor tool. `classify_message(text, surface=...)` picks the set; the
default is the supervisor set, so existing callers are unaffected.

The split exists because of a real gap: the original patterns were written in
supervisor vocabulary — third-person and procedural ("a harassment complaint",
"workers comp", "OSHA recordable") — and an employee describing the identical
event in the first person uses none of those words. "He keeps making comments
about my body" and "I slipped and hurt my wrist on shift" both sailed through as
ordinary questions. When adding a category or a surface, test the phrasing the
actual person would type, not the term of art for it — and test it against the
OTHER surface too, because the same words mean different things there ("fell
behind on targets" is not an injury).

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

# Additional patterns applied ONLY to the employee surface (Ask HR).
#
# These exist because an employee describing an event in the first person uses
# none of the vocabulary above — "he keeps making comments about my body" and
# "I slipped and hurt my wrist on shift" matched nothing at all.
#
# They are deliberately NOT in the shared tuples: several of them collide head-on
# with ordinary supervisor phrasing, and a supervisor tool that hard-stops its
# own core questions is broken. Specifically, on the supervisor surface —
#   "employee fell behind on targets"   → would trip workplace_safety
#   "the team is burned out"            → would trip workplace_safety
#   "inappropriate clothing / dress code" → would trip harassment
#   "employee threatened to quit"       → would trip harassment
# — all of which are exactly what HR Pilot is for. So the asymmetry is
# intentional: over-trigger for the employee (they get a human, which is always
# safe), stay precise for the supervisor.
#
# Even here, the two loosest verbs are anchored to an object/preposition so they
# describe a body and not a metric: "slipped ON the wet floor" and "burned MY
# hand" match, "fell behind" and "burned out" do not.
_EMPLOYEE_EXTRA_PATTERNS: dict[str, tuple[str, ...]] = {
    "harassment_discrimination": (
        r"\btouch(?:ed|ing|es) me\b",
        r"\bcomments? about my\b",
        r"\bunwanted\b",
        r"\binappropriate(?:ly)?\b",
        r"\bmade me (?:feel )?uncomfortable\b",
        r"\bcreep(?:y|ed)\b",
        r"\bbull(?:y|ied|ying)\b",
        r"\bthreaten(?:ed|ing)?\b",
    ),
    "workplace_safety": (
        r"\b(?:slipped|tripped|fell)\s+(?:on|off|down|over|at|into|and)\b",
        r"\bhurt (?:my|myself)\b",
        r"\bgot hurt\b",
        r"\bburn(?:ed|t)\s+(?:my|his|her|their)\b",
        r"\bcut my\b",
        r"\bunsafe\b",
        r"\bnear[- ]miss\b",
    ),
    "leave_and_medical": (
        r"\bsurgery\b",
        r"\bdoctor'?s? note\b",
        r"\bchemo(?:therapy)?\b",
        r"\bdiagnos(?:ed|is)\b",
    ),
}

SUPERVISOR = "supervisor"
EMPLOYEE = "employee"


def _compile(surface: str):
    return tuple(
        (
            category,
            notice,
            tuple(
                re.compile(p, re.IGNORECASE)
                for p in (
                    patterns + (_EMPLOYEE_EXTRA_PATTERNS.get(category, ())
                                if surface == EMPLOYEE else ())
                )
            ),
        )
        for category, notice, patterns in _HARD_STOP_CATEGORIES
    )


_COMPILED_BY_SURFACE = {
    SUPERVISOR: _compile(SUPERVISOR),
    EMPLOYEE: _compile(EMPLOYEE),
}

# Back-compat alias — the supervisor set is what `_COMPILED` always meant.
_COMPILED = _COMPILED_BY_SURFACE[SUPERVISOR]


@dataclass(frozen=True)
class EscalationVerdict:
    hard_stop: bool
    category: str | None = None
    notice: str | None = None
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


def classify_message(text: str, *, surface: str = SUPERVISOR) -> EscalationVerdict:
    """Classify a message against the hard-stop categories. Pure, DB-free,
    deterministic.

    Returns the first (most severe) category with a match. A message can
    trip multiple categories; only the highest-severity one is reported —
    the notice always says "call corporate HR", so which category matched
    first doesn't change the action taken.

    `surface` selects the pattern set: `SUPERVISOR` (default, HR Pilot thread
    mode) or `EMPLOYEE` (Ask HR portal), which adds the first-person patterns in
    `_EMPLOYEE_EXTRA_PATTERNS`. The default keeps every existing caller on the
    supervisor set unchanged.
    """
    if not text or not text.strip():
        return EscalationVerdict(hard_stop=False)

    compiled = _COMPILED_BY_SURFACE.get(surface, _COMPILED_BY_SURFACE[SUPERVISOR])
    for category, notice, patterns in compiled:
        matched = tuple(p.pattern for p in patterns if p.search(text))
        if matched:
            return EscalationVerdict(
                hard_stop=True,
                category=category,
                notice=notice,
                matched_terms=matched,
            )

    return EscalationVerdict(hard_stop=False)
