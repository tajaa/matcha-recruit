"""Pure, DB-free rules for the @huume channel-scheduling flow.

Mirrors `schedule_rules.py`'s split: DB assembly and the one Gemini parse
call live in `services/scheduling/schedule_chat.py`; every decision that
doesn't need either lives here, so it can be unit-tested without a database
or a model call — the same reason `schedule_rules.py` and
`schedule_compliance.py` are DB-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from difflib import SequenceMatcher
from typing import Literal, Optional, Union
from uuid import UUID

from .schedule_rules import sunday_indexed_weekday

# ── Authorization envelope ──────────────────────────────────────────────

ALLOWED_ROLES = frozenset({"client", "admin"})  # same pair as promote.evaluate_promote

_MANAGER_ONLY_MESSAGE = (
    "I can only build schedules for managers — if you need a shift change, "
    "file a swap or availability request from the Schedule tab in your portal."
)
_SCHEDULING_OFF_MESSAGE = (
    "Scheduling isn't turned on for this workspace — an admin can enable "
    "Employee Schedule."
)


@dataclass(frozen=True)
class ScheduleVerdict:
    kind: Literal["proceed", "refuse"]
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


def evaluate_schedule_proposal(
    *,
    role: Optional[str],
    features: dict,
    stage: Literal["propose", "confirm"],
    proposal_status: Optional[str] = None,
) -> ScheduleVerdict:
    """Pure authz envelope, mirrors `services/ems/promote.py:evaluate_promote`.

    Order: role -> `ems` flag -> `employee_schedule` flag -> (confirm stage
    only) proposal status. Called at BOTH propose time and confirm time —
    flag flips and role changes between the two chat turns are re-asserted
    on the replier, never trusted from the first check (same idiom as
    `services/huume/actions.py:evaluate_huume_action`).
    """
    if role not in ALLOWED_ROLES:
        return ScheduleVerdict("refuse", _MANAGER_ONLY_MESSAGE)
    if not features.get("ems"):
        return ScheduleVerdict("refuse", "EMS is not enabled for this company.")
    if not features.get("employee_schedule"):
        return ScheduleVerdict("refuse", _SCHEDULING_OFF_MESSAGE)
    if stage == "confirm" and proposal_status not in ("proposed", "clarifying"):
        return ScheduleVerdict("refuse", f"That proposal is already {proposal_status}.")
    return ScheduleVerdict("proceed")


# ── Week / date resolution ──────────────────────────────────────────────

@dataclass(frozen=True)
class NeedsClarify:
    question: str
    options: list = field(default_factory=list)  # ≤6, rendered as a dashed list


def resolve_week(week_hint: Optional[str], today: date) -> date:
    """The SUNDAY that starts the target week — matches
    `shift_compliance._week_window` + the schedule grid's own week-start
    convention, so a proposed shift lands in the same week an admin looking
    at the grid would expect. `'next_week'` is the Sunday strictly after
    today's own week (never today, even when today IS a Sunday);
    `'this_week'`/None is today's own week's Sunday."""
    this_sunday = today - timedelta(days=sunday_indexed_weekday(today))
    if week_hint == "next_week":
        return this_sunday + timedelta(days=7)
    return this_sunday


_WEEKDAY_NAMES = {
    "sunday": 0, "sun": 0,
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2, "tues": 2,
    "wednesday": 3, "wed": 3,
    "thursday": 4, "thu": 4, "thurs": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
}


def resolve_dates(
    spec: dict,
    week_start: date,
    today: date,
    template_days: Optional[list[int]] = None,
) -> Union[list[date], NeedsClarify]:
    """Precedence: an explicit ISO date > named weekdays (within the resolved
    week) > the matched template's own `days_of_week` mask ∩ the week >
    NeedsClarify. Any resolved date strictly before `today` is dropped —
    proposing a shift in the past is never useful.

    A bare weekday name (no explicit date, no week hint) whose every
    candidate in the resolved week already fell in the past rolls forward to
    the SAME weekday next week instead of clarifying — "I need a closer
    Monday" said on a Wednesday almost always means the next Monday, not
    "propose nothing this week." An explicit ISO date or a template-days
    fallback that's entirely in the past still clarifies — there's no
    unambiguous "next" for those. If EVERYTHING drops, that's a clarify too
    (never silently propose nothing)."""
    explicit = spec.get("date")
    if explicit:
        try:
            explicit_date = date.fromisoformat(explicit)
        except (ValueError, TypeError):
            explicit_date = None
        if explicit_date is not None:
            if explicit_date < today:
                return NeedsClarify(
                    "Which days should I schedule? Everything I found there was already in the past."
                )
            return [explicit_date]

    weekdays = spec.get("weekdays") or []
    wanted = {
        _WEEKDAY_NAMES[w.strip().lower()]
        for w in weekdays
        if isinstance(w, str) and w.strip().lower() in _WEEKDAY_NAMES
    }
    if wanted:
        dates = [week_start + timedelta(days=i) for i in range(7) if i in wanted]
        future = [d for d in dates if d >= today]
        if not future:
            rolled_start = week_start + timedelta(days=7)
            future = [rolled_start + timedelta(days=i) for i in range(7) if i in wanted]
        return future

    if template_days:
        dates = [week_start + timedelta(days=i) for i in range(7) if i in set(template_days)]
        dates = [d for d in dates if d >= today]
        if not dates:
            return NeedsClarify(
                "Which days should I schedule? Everything I found there was already in the past."
            )
        return dates

    return NeedsClarify("Which days should I schedule?")


def resolve_day_hint(hint: Optional[str], today: date) -> Optional[date]:
    """"today"/"tomorrow"/a weekday name -> the concrete date it means,
    relative to `today`. A named weekday resolves to its NEXT occurrence —
    `today` counts as a match for its own weekday (so "Wednesday" said on a
    Wednesday means today, matching how a manager would say it). Used for
    edit ops' relative day fields (target/second/new), which — unlike
    create's `weekdays`/`week_hint` — have no symbolic field at all in the
    parse prompt; the model is told never to compute a relative date, so
    something has to turn "tomorrow" into a real one deterministically.
    Returns None for anything unrecognized (an explicit `target_date` on the
    same request always wins over this, and a miss falls back to the
    existing ambiguous-listing clarify — never silently guesses)."""
    if not hint:
        return None
    h = hint.strip().lower()
    if h == "today":
        return today
    if h == "tomorrow":
        return today + timedelta(days=1)
    if h not in _WEEKDAY_NAMES:
        return None
    wanted = _WEEKDAY_NAMES[h]
    delta = (wanted - sunday_indexed_weekday(today)) % 7
    return today + timedelta(days=delta)


# ── Location / template matching ────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: Optional[str]) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


# 0.9, not 0.8: measured — 'Westwood'/'Eastwood' and 'Store 12'/'Store 13'
# both sit at 0.875 (different stores, one edit apart), while real typos of
# one name ('Willshire'->'wilshire' 0.941, 'wilshre' 0.933) clear 0.9.
_FUZZY_LOCATION_THRESHOLD = 0.9
_FUZZY_MIN_TOKEN_LEN = 5

_DIGIT_RE = re.compile(r"\d")


def match_location(hint: Optional[str], locations: list[dict]) -> list[dict]:
    """`locations` = active `business_locations` rows (id, name, address,
    city, state, zipcode). "La Jolla" must match a row NAMED "La Jolla …"
    (whose `city` column is San Diego) via name/address — a bare city match
    scores lowest on purpose, so a neighborhood name never resolves through
    the city column of some OTHER store in the same metro. Ties (score is
    equal and > 0 for more than one row) are all returned; the caller
    clarifies on 0 or >1."""
    hint_norm = (hint or "").strip().lower()
    if not hint_norm:
        return [locations[0]] if len(locations) == 1 else []

    hint_tokens = _tokens(hint_norm)
    scored: list[tuple[float, dict]] = []
    for loc in locations:
        name = (loc.get("name") or "").strip().lower()
        address = (loc.get("address") or "").strip().lower()
        city = (loc.get("city") or "").strip().lower()
        name_tokens = _tokens(name)
        score = 0.0
        if name and hint_tokens and hint_tokens <= name_tokens:
            score = 3.0
        elif name and (hint_norm in name or name in hint_norm):
            score = 2.0
        elif address and hint_norm in address:
            score = 1.0
        elif city and hint_norm == city:
            score = 0.5
        if score > 0:
            scored.append((score, loc))

    if scored:
        top = max(s for s, _ in scored)
        return [loc for s, loc in scored if s == top]

    # Nothing matched exactly/substring — try a typo-tolerant fallback
    # ("Willshire" for "Wilshire") before giving up. Only fires here (never
    # ahead of an exact/substring hit) and only returns a match when exactly
    # ONE location clears the bar — an ambiguous fuzzy hit still clarifies,
    # same as today. Scored per-token (not whole-name-string, and only
    # tokens >= 5 chars — short tokens inflate the ratio) since a real
    # location name is often multi-word ("Sunset Smile Dental — Wilshire")
    # and the typo is usually in just one word of it.
    #
    # Digit guard: a hint or name/token containing a digit skips the fuzzy
    # compare entirely. Numbered stores ("Store 12"/"Store 13") are
    # identifiers one edit apart, not typo-tolerant prose — a correct digit
    # hint already resolved through the exact/substring tiers above, so
    # this only ever prevents a WRONG numbered store from being guessed.
    if _DIGIT_RE.search(hint_norm):
        return []
    fuzzy: list[tuple[float, dict]] = []
    for loc in locations:
        name = (loc.get("name") or "").strip().lower()
        if not name:
            continue
        best = 0.0
        if not _DIGIT_RE.search(name):
            best = SequenceMatcher(None, hint_norm, name).ratio()
        for tok in _tokens(name):
            if len(tok) >= _FUZZY_MIN_TOKEN_LEN and not _DIGIT_RE.search(tok):
                best = max(best, SequenceMatcher(None, hint_norm, tok).ratio())
        if best >= _FUZZY_LOCATION_THRESHOLD:
            fuzzy.append((best, loc))
    if len(fuzzy) == 1:
        return [fuzzy[0][1]]
    return []


def apply_channel_default_location(
    matched: list[dict],
    hint: Optional[str],
    channel_location_id,
    locations: list[dict],
) -> list[dict]:
    """Channel store scope as the default: with NO explicit location hint, a
    store-scoped channel resolves to its own location — skipping the 'Which
    location?' clarify. An explicit hint ALWAYS wins, even when it names a
    DIFFERENT store ('unless asked otherwise'). A stale channel location
    (deactivated → absent from `locations`) falls through to the normal
    match/clarify path."""
    if (hint or "").strip() or not channel_location_id:
        return matched
    default = [l for l in locations if str(l.get("id")) == str(channel_location_id)]
    return default or matched


_AFFIRMATIVE_WORD = r"(?:yes|yeah|yep|sure|ok(?:ay)?|correct|that(?: one)?|the first(?: one)?|first)"
_AFFIRMATIVE_RE = re.compile(rf"{_AFFIRMATIVE_WORD}[.!\s]*", re.IGNORECASE)
_AFFIRMATIVE_LEAD_RE = re.compile(rf"^{_AFFIRMATIVE_WORD}[,.!\s]+", re.IGNORECASE)
_OPTION_CITY_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


def resolve_clarify_answer(answer: str, options: list[str]) -> str:
    """Snap a clarify reply onto one of the offered options when it
    unambiguously selects one; otherwise return the reply unchanged for
    the Gemini re-parse. Bare affirmative + exactly one option = that
    option ("Yes" answering a single-choice question — a real transcript
    burned a clarify round exactly this way). Otherwise a case-insensitive
    containment match hitting exactly one option wins. The trailing
    " (City)" that build_proposal appends to location options is stripped
    from the snapped value so it token-matches the business_locations
    name in match_location."""
    text = (answer or "").strip()
    if not options:
        return text
    snapped: Optional[str] = None
    if len(options) == 1 and _AFFIRMATIVE_RE.fullmatch(text):
        snapped = options[0]
    else:
        # Strip a leading "Yes, " so a reply that both affirms and names
        # the choice ("Yes, wilshire") still hits the containment check
        # below on its substantive remainder.
        remainder = _AFFIRMATIVE_LEAD_RE.sub("", text, count=1) or text
        low = remainder.lower()
        hits = [o for o in options if low in o.lower() or o.lower() in low]
        if len(hits) == 1:
            snapped = hits[0]
    if snapped is None:
        return text
    return _OPTION_CITY_SUFFIX.sub("", snapped).strip()


def snapped_to_option(snapped: str, options: list[str]) -> bool:
    """Did `resolve_clarify_answer` actually land on one of the offered
    options? Callers can't just test `snapped in options` — the trailing
    " (City)" is stripped off the return value, so a snapped location never
    compares equal to the raw option string it came from. A caller that
    gets this wrong silently treats a good answer as unresolved (the
    location-clarify round then re-asks the same question forever)."""
    if not snapped or not options:
        return False
    target = snapped.strip().lower()
    return any(
        _OPTION_CITY_SUFFIX.sub("", o).strip().lower() == target for o in options
    )


def _stem(word: str) -> str:
    """Naive suffix strip so "opener"/"opening"/"openers" all reduce to
    "open" and "closer"/"closing" reduce to "clos" — just enough to match a
    manager's shorthand ("opener") against a template's own name/role
    ("Opening Shift", role "Closer")."""
    w = word.lower()
    for suffix in ("ing", "ers", "er", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


def _stems(text: Optional[str]) -> set[str]:
    return {_stem(t) for t in _TOKEN_RE.findall((text or "").lower())}


def match_template(
    hint: Optional[str], label: Optional[str], templates: list[dict]
) -> Optional[dict]:
    """Precedence: exact name == hint > name-token stem overlap > role-token
    stem overlap. `hint` falls back to `label` ("opener") when the model
    didn't return a `template_hint`. Deterministic ties broken by
    (name, id)."""
    effective_hint = (hint or label or "").strip()
    if not effective_hint or not templates:
        return None
    hint_lower = effective_hint.lower()
    hint_stems = _stems(effective_hint)

    def _sort_key(t: dict):
        return (t.get("name") or "", str(t.get("id")))

    exact = [t for t in templates if (t.get("name") or "").strip().lower() == hint_lower]
    if exact:
        return sorted(exact, key=_sort_key)[0]

    name_matches = [t for t in templates if hint_stems & _stems(t.get("name"))]
    if name_matches:
        return sorted(name_matches, key=_sort_key)[0]

    role_matches = [t for t in templates if hint_stems & _stems(t.get("role"))]
    if role_matches:
        return sorted(role_matches, key=_sort_key)[0]

    return None


def build_adhoc_spec(label: str, start_time, end_time, role: Optional[str]) -> dict:
    """When no template matched but the manager (or the model's parse) gave
    explicit times. `break_minutes=0` deliberately — the §512 meal-break
    advisory then tells the truth ("scheduled with only 0 min break") rather
    than us silently inventing a break the manager never mentioned."""
    return {
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
        "role": role,
        "break_minutes": 0,
        "template_id": None,
    }


# ── Candidate ranking ────────────────────────────────────────────────────

@dataclass
class CandidateContext:
    employee_id: str
    name: str
    job_title: Optional[str]
    conflicts: list[dict]     # find_conflicts rows
    violations: list[dict]    # check_shift_compliance rows
    week_hours: float = 0.0


@dataclass
class RankResult:
    chosen: list[CandidateContext]
    alternates: list[CandidateContext]
    excluded: list[tuple[CandidateContext, str]]  # (ctx, human reason w/ verbatim violation)


def _has_block(violations: list[dict]) -> bool:
    return any(v.get("severity") == "block" for v in violations)


def _exclusion_reason(ctx: CandidateContext) -> str:
    if ctx.conflicts:
        c = ctx.conflicts[0]
        return f"{ctx.name} is already on a shift {c.get('starts_at')}–{c.get('ends_at')} that day."
    block = next((v for v in ctx.violations if v.get("severity") == "block"), None)
    if block:
        statute = f" ({block['statute']})" if block.get("statute") else ""
        return f"{block['message']}{statute}"
    return f"{ctx.name} can't be scheduled for this shift."


def _role_bonus(job_title: Optional[str], shift_role: Optional[str]) -> int:
    """0 (sorts first) when the employee's job title stem-overlaps the
    shift's role, else 1 — a light tiebreaker, not a hard filter."""
    if not job_title or not shift_role:
        return 1
    return 0 if _stems(job_title) & _stems(shift_role) else 1


def rank_candidates(
    slots_needed: int,
    candidates: list[CandidateContext],
    *,
    pinned_ids: Optional[list[str]] = None,
    shift_role: Optional[str] = None,
) -> RankResult:
    """Exclusions first: any conflict, or any `severity=='block'` violation,
    excludes the candidate outright — a hard statutory violation is never
    proposed, pinned or not (a manager naming someone doesn't override the
    law). Survivors sort: pinned first (the manager named them; advisories
    still listed on them) -> zero-advisory -> fewer advisories -> lower
    week_hours -> role-stem bonus -> name -> employee_id. Fully
    deterministic."""
    pinned = set(pinned_ids or [])
    survivors: list[CandidateContext] = []
    excluded: list[tuple[CandidateContext, str]] = []
    for ctx in candidates:
        if ctx.conflicts or _has_block(ctx.violations):
            excluded.append((ctx, _exclusion_reason(ctx)))
        else:
            survivors.append(ctx)

    def sort_key(ctx: CandidateContext):
        return (
            0 if ctx.employee_id in pinned else 1,
            len(ctx.violations),
            ctx.week_hours,
            _role_bonus(ctx.job_title, shift_role),
            ctx.name,
            ctx.employee_id,
        )

    survivors.sort(key=sort_key)
    return RankResult(
        chosen=survivors[:slots_needed],
        alternates=survivors[slots_needed:],
        excluded=excluded,
    )


# ── Confirm-reply parsing ────────────────────────────────────────────────

_THUMBS_UP = {"\U0001F44D", "\U0001F44D\U0001F3FB", "\U0001F44D\U0001F3FC",
              "\U0001F44D\U0001F3FD", "\U0001F44D\U0001F3FE", "\U0001F44D\U0001F3FF"}

_CONFIRM_RE = re.compile(
    r"^(?:confirm(?:ed)?|yes|yep|yeah|yea|sure|do it|go ahead|"
    r"approve[d]?|book it|ship it|lgtm|looks good|sounds good)[\s!.]*$",
    re.IGNORECASE,
)
_CANCEL_RE = re.compile(
    r"^(?:cancel|no|nope|nah|stop|don'?t|scrap(?: it)?|never ?mind|"
    r"forget it|kill it)[\s!.]*$",
    re.IGNORECASE,
)


def parse_confirm_reply(text: str) -> Literal["confirm", "cancel", "other"]:
    """Deterministic, no model call — a proposal's confirm/cancel gate must
    not depend on Gemini being up. Caller applies `intent.strip_mention`
    first. Both patterns are anchored start-to-end (only trailing
    punctuation/whitespace tolerated) — a bare "yes"/"confirm" is unambiguous,
    but "yes but swap Dana for Marcus" carries a modification the deterministic
    matcher can't parse, so it must NOT silently execute the unmodified
    proposal; it falls through to "other" and re-arms for a clean reply."""
    t = (text or "").strip()
    if t in _THUMBS_UP:
        return "confirm"
    if _CANCEL_RE.match(t):
        return "cancel"
    if _CONFIRM_RE.match(t):
        return "confirm"
    return "other"


# ── Shift-edit time-hint parsing ─────────────────────────────────────────

_TIME_HINT_RE = re.compile(
    r"^(?P<hour>[01]?\d|2[0-3])(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>am|pm)?$",
    re.IGNORECASE,
)

# A range hint ("9am-5pm", "9 to 5pm") narrows on its FIRST endpoint — that's
# always the shift's start time, which is what candidates differ on.
_TIME_RANGE_SPLIT_RE = re.compile(r"\s*(?:-|–|—|\bto\b|\buntil\b)\s*", re.IGNORECASE)

# A colonless 3-4 digit clock ("1230", "830") — a real transcript typed
# "Fri Aug 7 1230-18:00" and got no narrowing at all, since _TIME_HINT_RE
# requires the colon. Only 3-4 digit runs are rewritten (never 1-2 digit —
# "8" stays the deliberately-ambiguous case _TIME_HINT_RE/the has_minute
# branch below already documents) so this can't turn a genuine bare hour
# into a guessed minute.
_BARE_DIGIT_CLOCK_RE = re.compile(r"^(?P<digits>\d{3,4})\s*(?P<ampm>am|pm)?$", re.IGNORECASE)


def _normalize_bare_digit_clock(segment: str) -> str:
    m = _BARE_DIGIT_CLOCK_RE.match(segment)
    if not m:
        return segment
    digits = m.group("digits")
    hour, minute = digits[:-2], digits[-2:]
    return f"{hour}:{minute}{m.group('ampm') or ''}"


def parse_time_hint(hint: Optional[str]) -> Optional[time]:
    """Best-effort clock time out of `target_time_hint`'s free-text value
    ("8am", "8:30pm", "08:00", "20:00", "9am-5pm") — unlike `_coerce_time` in
    schedule_chat.py this ISN'T restricted to strict 24h "HH:MM", since the
    model is asked for a human hint, not a normalized field. Returns None
    on anything ambiguous (bare "8" with no am/pm and no way to tell if
    it's 24h, "morning", empty) rather than guessing — a caller uses this
    only to narrow an already-ambiguous shift match, never to schedule
    anything, so a missed parse just falls back to the existing listing."""
    if not hint:
        return None
    hint = hint.strip()
    segments = _TIME_RANGE_SPLIT_RE.split(hint, maxsplit=1)
    first = segments[0].strip()
    m = _TIME_HINT_RE.match(_normalize_bare_digit_clock(first))
    if not m:
        # "Fri Aug 7 1230-18:00" — day/date words ride in the same segment
        # as the clock, so the whole-segment match above never fires. Retry
        # on the segment's LAST whitespace token alone ("1230") before
        # giving up — anything non-clock there still fails _TIME_HINT_RE
        # ("the opener" -> "opener" -> None).
        last = first.rsplit(None, 1)[-1] if first else first
        if last and last != first:
            m = _TIME_HINT_RE.match(_normalize_bare_digit_clock(last))
    if not m:
        return None
    hour = int(m.group("hour"))
    has_minute = m.group("minute") is not None
    minute = int(m.group("minute") or 0)
    ampm = (m.group("ampm") or "").lower()
    if ampm:
        if not (1 <= hour <= 12):
            return None
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = hour if hour == 12 else hour + 12
    elif has_minute or hour > 12:
        pass  # unambiguous 24h — either an explicit "HH:MM" or a bare hour > 12
    else:
        return None  # bare "8" — no am/pm, no minute, no way to tell
    return time(hour, minute)
