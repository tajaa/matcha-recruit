"""What did the person want when they typed "@huume ..." in a channel?

Pure and DB-free, like `categories`. Deterministic on purpose — the same
reasoning as `services/pilots/hr_pilot_escalation.classify_message`: this
runs BEFORE any model call, decides whether a message becomes a permanent
`ems_events` row, and its failure mode has to be auditable rather than
probabilistic.

**Bias to LOG. Always.** The product invariant is that documentation
survives everything (a Gemini outage still logs the event as
`uncategorized` — see event_intake's module docstring). An event silently
swallowed because a regex read it as small talk is unrecoverable: nobody
re-types it. A question mistakenly logged is visible, editable and
dismissable in the Events tab. So an unmatched message is a LOG, and the
patterns below are deliberately narrow — they match phrasings that cannot
plausibly be a report of something that happened.

That asymmetry is why RECALL patterns are anchored at the START of the
message: "here's what happened — Julia slipped" is a report that contains
the words "what happened", and only the anchor tells it apart from
"what happened at the store last week?".
"""

import re

LOG = "log"
ASK = "ask"
HELP = "help"
LINK = "link"
SCHEDULE = "schedule"

# Leading "@huume" / "@Huume:" the sender typed to address the bot. Stripped
# before matching so every pattern below can anchor on ^.
_MENTION_PREFIX = re.compile(r"^\s*@\s*huume\b[\s,:;\-—]*", re.IGNORECASE)

_HELP_PATTERNS = (
    r"^help\b",
    r"^what can (?:you|u) do\b",
    r"^what (?:else )?can (?:you|u) help\b",
    r"^what do (?:you|u) do\b",
    r"^what are (?:you|your|ur) (?:for|capabilities)\b",
    r"^commands?\b",
    r"^how do (?:i|you) (?:use|work)\b",
    r"^how does this work\b",
    r"^\?+$",
)

# Unambiguous recall phrasings — no question mark required, because people
# type "@huume what happened last week" without one. Every entry has to be
# a phrasing nobody would use to REPORT an event.
_RECALL_PATTERNS = (
    r"^what happened\b",
    r"^what went on\b",
    r"^what was going on\b",
    r"^what(?:'s| has| have)? been (?:logged|reported|going on|happening)\b",
    r"^what(?:'s| is| are)? (?:the )?(?:events?|incidents?|logs?)\b",
    r"^(?:show|list|recap|remind|tell|give) (?:me|us)\b",
    r"^(?:show|list|recap)\b",
    r"^summar(?:y|ize|ise)\b",
    r"^catch (?:me|us) up\b",
    r"^(?:pull|look) up\b",
    r"^any(?:thing|)? (?:logged|reported|else logged)\b",
    r"^anyone (?:log|report)(?:ed)?\b",
    r"^any (?:events?|incidents?|reports?)\b",
    r"^(?:did|have|has) (?:we|you|anyone|any ?one|somebody|someone)\b",
    r"^do we have (?:any|anything)\b",
    r"^can (?:you|u) (?:show|list|tell|remind|summar|recap|find|pull|look)\w*\b",
)

# Weaker signal: only counts as a question when the message actually ends
# in a question mark, which "@huume what's broken: the ice machine" does
# not.
_INTERROGATIVE_LEAD = re.compile(
    r"^(?:what|when|who|whom|whose|where|why|how|which|is|are|was|were|do|does|"
    r"did|has|have|had|can|could|should|would|will|any)\b",
    re.IGNORECASE,
)

# The reporting-link ask. Narrow on purpose, same bias-to-LOG reasoning as
# the recall patterns: "the link to the vendor portal is broken" or "here's
# the report I mentioned, link's below" must still LOG, so every pattern
# requires an explicit report/intake noun immediately next to "link", or an
# imperative send/share verb leading straight into one.
_LINK_PATTERNS = (
    r"\b(?:report(?:ing)?|anonymous|confidential|magic|intake)\s+link\b",
    r"^(?:send|share|post|drop|get|give)\b(?:\s+\w+){0,3}\s+link\b",
    r"\blink\s+(?:to|for)\s+(?:the\s+)?report\b",
)

# The "build me a schedule" ask. Bias-to-LOG stands here too: every pattern
# requires BOTH a request verb (need/want/schedule/add/...) AND a shift-noun,
# and every pattern is start-anchored. \bneed\b / \bwant\b deliberately do
# NOT match "needed"/"wanted" (word-boundary + exact tense), so a past-tense
# report — "we needed more staff last night and someone got hurt" — still
# LOGs. The negative lookahead in the first pattern keeps "I need to report
# an incident" / "we need to talk about what happened" in LOG too: those are
# requests, but not requests FOR a shift.
_SHIFT_NOUN = (
    r"(?:opener|closer|opening|closing|shift|shifts|cover(?:age)?|"
    r"schedule|scheduled|staff(?:ed|ing)?|on the schedule)"
)
_SCHEDULE_PATTERNS = (
    rf"^(?:i|we)(?:'ll|'d| will| would)? (?:need|want|gotta|have to|need to get)\b"
    rf"(?:(?!\bto (?:report|log|file|talk|discuss|flag)\b).)*?\b{_SHIFT_NOUN}\b",
    r"^(?:can|could|will|would) (?:you|u) (?:schedule|staff|book|add|set ?up|put)\b",
    r"^schedule\b",
    rf"^(?:add|set ?up|create|build|make|book)\b(?:\s+\S+){{0,6}}\s+{_SHIFT_NOUN}\b",
)

_HELP_RE = tuple(re.compile(p, re.IGNORECASE) for p in _HELP_PATTERNS)
_RECALL_RE = tuple(re.compile(p, re.IGNORECASE) for p in _RECALL_PATTERNS)
_LINK_RE = tuple(re.compile(p, re.IGNORECASE) for p in _LINK_PATTERNS)
_SCHEDULE_RE = tuple(re.compile(p, re.IGNORECASE) for p in _SCHEDULE_PATTERNS)


def strip_mention(content: str) -> str:
    """The message with a leading "@huume" address removed — what the
    person actually said. Also what the ask path feeds the model as the
    question, so it isn't answering "@huume" as if it were a word."""
    return _MENTION_PREFIX.sub("", content or "").strip()


def classify_intent(content: str) -> str:
    """LOG (default), ASK (recall question about what's on file), HELP (what
    can you do), LINK (share the anonymous reporting link), or SCHEDULE
    (build/change the shift schedule). See the module docstring for why LOG
    wins ties. HELP is checked first so a capability probe never falls into
    ASK/LINK/SCHEDULE on a shared word ("what can you do" reads as
    interrogative too). SCHEDULE is checked before RECALL so "can you
    schedule two people for Saturday" never lands in ASK — RECALL's
    show/list/tell/remind/summarize/recap/find/pull/look verb set doesn't
    overlap schedule/staff/book/add."""
    text = strip_mention(content)
    if not text:
        return HELP  # a bare "@huume" is someone poking it to see what it is

    for pattern in _HELP_RE:
        if pattern.search(text):
            return HELP

    for pattern in _LINK_RE:
        if pattern.search(text):
            return LINK

    for pattern in _SCHEDULE_RE:
        if pattern.search(text):
            return SCHEDULE

    for pattern in _RECALL_RE:
        if pattern.search(text):
            return ASK

    if text.endswith("?") and _INTERROGATIVE_LEAD.match(text):
        return ASK

    return LOG
