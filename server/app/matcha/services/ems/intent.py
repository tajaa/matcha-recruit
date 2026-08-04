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
INVENTORY = "inventory"

# Leading "@huume" / "@Huume:" the sender typed to address the bot. Stripped
# before matching so every pattern below can anchor on ^.
_MENTION_PREFIX = re.compile(r"^\s*@\s*huume\b[\s,:;\-—]*", re.IGNORECASE)

# "Hey @huume ...", "ok @huume ...", "good morning @huume ..." — the sender
# is still ADDRESSING the bot; the greeting defeats the position-0 mention
# strip and with it every ^-anchored pattern below, so everything becomes a
# LOG (the "weekly recap logged as an event" bug). A mention deeper in a
# sentence ("tell @huume about it") is being talked ABOUT, not addressed —
# only greeting words may precede a strippable mention.
_GREETING_PREFIX = re.compile(
    r"^(?:hey|hi|hello|yo|hiya|howdy|ok|okay|please|pls|morning|"
    r"good (?:morning|afternoon|evening))\b[\s,!.:;\-—]*",
    re.IGNORECASE,
)

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
    r"^what(?:'?s| has| have)? been (?:logged|reported|going on|happening)\b",
    r"^what(?:'?s| is| are)? (?:the )?(?:events?|incidents?|logs?|reports?|(?:status )?updates?)\b",
    r"^(?:show|list|recap|remind|tell|give) (?:me|us)\b",
    r"^(?:show|list|recap)\b",
    r"^summar(?:y|ize|ise)\b",
    r"^catch (?:me|us) up\b",
    r"^(?:pull|look) up\b",
    r"^any(?:thing|)? (?:logged|reported|else logged)\b",
    r"^anyone (?:log|report)(?:ed)?\b",
    r"^any (?:events?|incidents?|reports?|(?:status )?updates?)\b",
    r"^(?:did|have|has) (?:we|you|anyone|any ?one|somebody|someone)\b",
    r"^do we have (?:any|anything)\b",
    # Recall-specific verbs that aren't ordinary report phrasing regardless
    # of object ("can you list/summarize/recap/find/pull up/look up ...").
    r"^(?:can|could|would|will) (?:you|u) (?:please )?(?:list|summar\w*|recap\w*|find|pull up|look up)\b",
    # Ambiguous verbs ("show/tell/give/get/send") ARE ordinary report
    # phrasing too — "can you send someone, the sink is leaking" or "can
    # you tell everyone the walk-in flooded" must still LOG. Only count
    # these as a recall ask when the object is "me"/"us" — a report never
    # phrases itself that way.
    r"^(?:can|could|would|will) (?:you|u) (?:please )?(?:show|tell|give|get|send)\s+(?:me|us)\b",
    r"^(?:can|could) i (?:get|have|see)\s+(?:a |the |an )?(?:recap|summary|rundown|roundup|update|events?|incidents?|logs?|reports?)\b",
    # Modifier-tolerant recap noun — "weekly recap of...", "quick recap of
    # the week please" — a plain leading noun beats a hardcoded verb-first
    # anchor. Subsumes bare "^recap" above but that entry stays for the
    # show/list/recap group's shared phrasing.
    r"^(?:(?:a|the|my|our|quick|short|full|daily|weekly|monthly)\s+)*(?:recap|summary|rundown|roundup)\b",
    r"^(?:i|we)(?:'d| would)? (?:need|want|would like)\b(?:\s+\w+){0,2}?\s+(?:a |the )?(?:recap|summary|rundown|roundup)\b",
    # Ops grounding asks — schedule/inventory questions phrased as questions,
    # not requests (a request to BUILD/ASSIGN a shift is caught by
    # _SCHEDULE_PATTERNS first, checked before RECALL; a report of stock
    # running out needs a we/i lead per _INVENTORY_PATTERNS, checked before
    # RECALL too, so neither fork is stolen by these).
    r"^who(?:'s| is| are)? (?:working|scheduled|on (?:the )?schedule|on shift|opening|closing)\b",
    r"^(?:what|when)(?:'s| is| are)? (?:my|the|our) (?:next )?(?:shifts?|schedule)\b",
    r"^how (?:much|many)\b(?=.*\b(?:in stock|stock|inventory|on hand|left|remaining)\b)",
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
    # The leading lookahead excludes a recap/summary noun ANYWHERE in the
    # rest of the message — not just before the shift noun is reached —
    # so "I need a shift recap" (recap noun AFTER the shift noun) is a
    # recall ask (see _RECALL_PATTERNS), not a staffing request, the same
    # as "I need a weekly recap of the schedule" (recap noun before it).
    rf"(?:^|[.!?]\s+)(?:i|we)(?:'ll|'d| will| would)? (?:need|want|gotta|have to|need to get)\b"
    rf"(?!.*\b(?:recap|summary|rundown|roundup)\b)"
    rf"(?:(?!\bto (?:report|log|file|talk|discuss|flag)\b).)*?\b{_SHIFT_NOUN}\b",
    r"^(?:can|could|will|would) (?:you|u) (?:schedule|staff|book|add|set ?up|put)\b",
    r"^schedule\b",
    rf"(?:^|[.!?]\s+)(?:add|set ?up|create|build|make|book)\b(?:\s+\S+){{0,6}}\s+{_SHIFT_NOUN}\b",
    # push/assign only count when the sentence reaches a shift noun —
    # "can you push the meeting notes" must stay LOG. ass?i(?:gn|ng)
    # additionally absorbs the real-world typo "assing". The lead-in
    # allows a short throwaway clause before the verb ("how about now,
    # can you...") without opening this up to mid-message false hits —
    # bounded to a few words, not a bare .search() over the whole text.
    rf"(?:^|^.{{0,20}}?,\s*)(?:can|could|will|would) (?:you|u) "
    rf"(?:push|re-?ass?i(?:gn|ng)|ass?i(?:gn|ng))\b"
    rf"(?:(?!\bto (?:report|log|file)\b).)*?\b{_SHIFT_NOUN}\b",
)

# The inventory ask — deduct/receive/stockout/order stock. Bias-to-LOG
# stands here too: patterns deliberately exclude bare "gave"/"used" so
# "we gave John a written warning" and "someone used the slicer and got
# hurt" still LOG.
_INVENTORY_PATTERNS = (
    # OUT — gifted/comped/donated/wasted stock, explicitly, not a bare verb.
    r"^(?:we|i)(?:'ve| have| just|'ve just| have just)? "
    r"(?:gifted|gave away|comped|donated|handed out|used up|went through|"
    r"threw (?:out|away)|tossed|wasted)\b",
    # STOCKOUT / LOW — "we ran out of salads again", "we're low on cups".
    r"^(?:we|i)(?:'re|'ve| are| have| am)?\s*(?:completely |all |totally |almost )?"
    r"(?:ran out of|run out of|out of|used the last of|have no more|"
    r"running low on|low on)\b",
    # RECEIPT — "we received the produce order", "we restocked napkins".
    r"^(?:we|i)(?: just)? (?:received|restocked|got in|"
    r"got (?:a|the|our) (?:delivery|shipment|order)(?: of)?)\b",
    # ORDER REQUEST — tense-exact like SCHEDULE's \bneed\b (never "needed").
    r"^(?:we|i)(?:'ll| will)? need to (?:order|re-?order|re-?stock|buy)\b",
)
_INVENTORY_RE = tuple(re.compile(p, re.IGNORECASE) for p in _INVENTORY_PATTERNS)

_HELP_RE = tuple(re.compile(p, re.IGNORECASE) for p in _HELP_PATTERNS)
_RECALL_RE = tuple(re.compile(p, re.IGNORECASE) for p in _RECALL_PATTERNS)
_LINK_RE = tuple(re.compile(p, re.IGNORECASE) for p in _LINK_PATTERNS)
_SCHEDULE_RE = tuple(re.compile(p, re.IGNORECASE) for p in _SCHEDULE_PATTERNS)


def strip_mention(content: str) -> str:
    """The message with a leading "@huume" address removed — what the
    person actually said. Also what the ask path feeds the model as the
    question, so it isn't answering "@huume" as if it were a word.

    A leading greeting ("hey @huume ...") is stripped along with the
    mention — see _GREETING_PREFIX. A mention that isn't at the very start
    (after any greeting) is left alone: "tell @huume about it" is a report
    ABOUT huume, not addressed TO it, and stripping it there would make an
    ordinary sentence fragment start matching ^-anchored patterns.

    Greeting words are only stripped BEFORE the mention ("hey, good
    morning @huume ..."), never after: re-applying the greeting strip once
    the mention is gone would eat real message words that happen to be
    greeting homographs ("@huume morning shift was short staffed" must
    keep "morning" — it's not filler, it's the report)."""
    text = (content or "").strip()
    for _ in range(5):  # "hey, good morning @huume ..." — bounded loop
        stripped = _GREETING_PREFIX.sub("", text)
        if stripped == text:
            break
        text = stripped
    return _MENTION_PREFIX.sub("", text).strip()


def classify_intent(content: str) -> str:
    """LOG (default), ASK (recall question about what's on file), HELP (what
    can you do), LINK (share the anonymous reporting link), or SCHEDULE
    (build/change the shift schedule). See the module docstring for why LOG
    wins ties. HELP is checked first so a capability probe never falls into
    ASK/LINK/SCHEDULE on a shared word ("what can you do" reads as
    interrogative too). SCHEDULE is checked before RECALL so "can you
    schedule two people for Saturday" never lands in ASK — RECALL's
    show/list/tell/remind/summarize/recap/find/pull/look verb set doesn't
    overlap schedule/staff/book/add. INVENTORY is checked after SCHEDULE
    and before RECALL for the same reason — its own verb set
    (gifted/ran out/received/need to order) doesn't overlap SCHEDULE's
    shift vocabulary or RECALL's show/list/tell set."""
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

    for pattern in _INVENTORY_RE:
        if pattern.search(text):
            return INVENTORY

    for pattern in _RECALL_RE:
        if pattern.search(text):
            return ASK

    if text.endswith("?") and _INTERROGATIVE_LEAD.match(text):
        return ASK

    return LOG
