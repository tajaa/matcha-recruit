"""What each model phase must hand back, and how it is checked. Pure: no I/O.

The model never writes to the database. Each phase ends with one `finish`
call; its arguments go through a `normalize_*` here, and the orchestrator
persists only what survives. A ValueError gets the model one repair.

  plan       the titles to search and what to rank on, from the ask (and résumé)
  discover   links to current postings found on the web (code reads each one)
  screen     relevant or not, and a 0-5 fit, for a batch of jobs by short id
  approach   per job: how to approach, drafts, answers to the real questions
  tailor     one job: the person's résumé rewritten for it (`tailor.py`)

Checks that matter:
  * a posting's link must be one this run's searches or page loads returned
  * ids must be ones the batch showed (short ids like J3, mapped back here)
  * a contact must be named on a page fetched in this run
  * an email must be printed on a fetched page or typed by the person
  * an answer must be to one of the posting's open questions; file,
    authorization and demographic questions are never answered
  * every link must be one this run's searches or page loads returned
  * a tailored résumé line must quote the résumé lines it rewrites (from its
    own role), word for word, and be made of them: its numbers exactly, its
    names whole, most of its words; a role's title, employer and dates must
    be written together in the résumé, and a skill as a whole word
"""
from __future__ import annotations

import re
from typing import Any

from app.matcha.services.matcha_work.agent_runtime import finish

from . import ats, normalize
from .comp import _norm, amounts_in, verify_quote

# Titles a plan searches for: what they typed, then kept directions, then the
# plan's own (`phases.search_titles` says how many the searches take).
MAX_TITLES = 10
# Roles beyond the person's own title that their résumé supports, suggested
# by the plan: at most this many, each among the first titles searched.
MAX_DIRECTIONS = 3
APPROACH_CHANNELS = ("referral", "hiring_manager", "recruiter", "apply_portal", "search_firm")
_EMAIL = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")
# Addresses in the person's own words: a typed address is itself, never a
# suffix of one ("doe@acme.com" is not "jane.doe@acme.com").
_EMAIL_IN = re.compile(r"[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"'.]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Words a model sends for "no deal-breaker" when it doesn't send null.
_NO_BREAKER = {"", "none", "null", "nil", "n/a", "na", "no", "nothing", "-", "—", "false"}


def _text(value: Any, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).strip()[:limit]


def titles_in(titles: Any) -> list[str]:
    """Titles as a plan keeps them: trimmed, two letters or more, once each
    (case aside), at most `MAX_TITLES`."""
    out: dict[str, str] = {}
    for title in titles if isinstance(titles, list) else []:
        text = " ".join(_text(title, 400).split())[:80]
        if len(text) >= 2:
            out.setdefault(text.lower(), text)
    return list(out.values())[:MAX_TITLES]


def _texts(values: Any, *, items: int, limit: int) -> list[str]:
    out = []
    for value in values if isinstance(values, list) else []:
        text = _text(value, limit)
        if text:
            out.append(text)
        if len(out) >= items:
            break
    return out


# ── plan ─────────────────────────────────────────────────────────────────────

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {
            "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_TITLES,
            "description": "Job titles to search for, as postings write them, most wanted first: "
                           "theirs, then real synonyms at that level",
        },
        "deal_breakers": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "profile_summary": {"type": "string", "description": "Two or three sentences on who is looking, from the ask and résumé"},
        "directions": {
            "type": "array", "maxItems": MAX_DIRECTIONS,
            "description": "Only with a résumé: roles beyond the titles they asked for that their résumé supports",
            "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "A job title to search, e.g. 'Solutions Architect'"},
                "why": {"type": "string", "description": "One or two sentences to them: what in their résumé fits it"},
                "evidence": {"type": "string", "description": "Words copied exactly from their résumé that show it"},
            }, "required": ["title", "why", "evidence"]},
        },
        "weights": {
            "type": ["object", "null"],
            "description": "How much base, bonus, equity and fit matter to this person (0-1 each), from the ask",
            "properties": {k: {"type": "number"} for k in ("base", "bonus", "equity", "fit")},
        },
    },
    "required": ["titles", "deal_breakers", "profile_summary", "weights"],
}
PLAN_FINISH = finish.tool("Planned the search", "Finish with the search plan.", PLAN_SCHEMA)


def normalize_plan(args: dict, _state=None) -> tuple[dict, list[str]]:
    result = finish.answer(args)
    titles = titles_in(result.get("titles"))
    if not titles:
        raise ValueError("give at least one job title to search for")
    weights = result.get("weights") if isinstance(result.get("weights"), dict) else None
    plan = {
        "titles": titles,
        "deal_breakers": _texts(result.get("deal_breakers"), items=10, limit=160),
        "profile_summary": _text(result.get("profile_summary"), 800),
        "source": "model",
    }
    directions = _directions(result.get("directions"))
    if directions:
        plan["directions"] = directions
    if weights:
        plan["weights"] = {k: weights[k] for k in ("base", "bonus", "equity", "fit")
                           if isinstance(weights.get(k), (int, float))}
    return plan, []


def _directions(raw: Any) -> list[dict]:
    """The plan's suggested directions, shaped; not yet checked (that needs
    the résumé: `check_directions`)."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        direction = {"title": " ".join(_text(item.get("title"), 80).split()),
                     "why": " ".join(_text(item.get("why"), 300).split()),
                     "evidence": " ".join(_text(item.get("evidence"), 240).split())}
        if direction["title"] and direction["why"] and direction["evidence"]:
            out.append(direction)
    return out[:MAX_DIRECTIONS]


def check_directions(directions: list[dict], resume: str | None, taken: list[str]) -> list[dict]:
    """Keep a direction only when its evidence is in the résumé word for word
    (a model can't tell someone they have experience they don't) and it is a
    role beyond the titles already searched or asked for. Without a résumé,
    none: the suggestions are its to support."""
    if not resume:
        return []
    kept, seen = [], {t.strip().lower() for t in taken if t}
    for direction in directions:
        title = direction["title"]
        if title.lower() in seen or any(normalize.same_title(title, t) for t in taken if t):
            continue
        if not verify_quote(direction["evidence"], resume):
            continue
        seen.add(title.lower())
        kept.append(direction)
    return kept


def direction_of(title: str, directions: list[dict], own_titles: list[str]) -> str | None:
    """The suggested direction a found job is, if it is one: squarely that
    title (`normalize.title_covers`) and not the same job as one they asked
    for (`normalize.same_title`)."""
    if any(normalize.same_title(title, own) for own in own_titles if own):
        return None
    for direction in directions:
        if normalize.title_covers(title, direction.get("title") or ""):
            return direction["title"]
    return None


# ── discover ─────────────────────────────────────────────────────────────────

MAX_POSTINGS = 40
DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "postings": {
            "type": "array", "maxItems": MAX_POSTINGS,
            "items": {"type": "object", "properties": {
                "url": {"type": "string",
                        "description": "The posting's own page, exactly as a search or page load returned it"},
                "title": {"type": "string", "description": "As the posting shows it"},
                "company": {"type": "string"},
                "location": {"type": "string"},
            }, "required": ["url", "title", "company", "location"]},
        },
    },
    "required": ["postings"],
}
DISCOVER_FINISH = finish.tool("Found postings", "Finish with the postings you found.", DISCOVER_SCHEMA)


def normalize_postings(args: dict, *, citable: set[str]) -> tuple[dict, list[str]]:
    """The postings whose links this run's searches or page loads returned,
    once each. None at all is a fine answer (nothing current fits); some, and
    not one of them traceable, gets the model one repair."""
    result = finish.answer(args)
    postings: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    given = untraceable = 0
    for item in finish.items(result, "postings"):
        if not isinstance(item, dict):
            continue
        given += 1
        url = str(item.get("url") or "").strip()
        if url not in citable or not url.startswith(("https://", "http://")):
            untraceable += 1
            warnings.append(f"Dropped {url[:80]!r}: not a link this run's searches or page loads returned")
            continue
        if url in seen:
            continue
        seen.add(url)
        # A posting with no title is still read: code takes the title from the
        # posting itself, and the ATS has it whatever the model left out.
        postings.append({"url": url, "title": _text(item.get("title"), 200),
                         "company": _text(item.get("company"), 200), "location": _text(item.get("location"), 200)})
        if len(postings) >= MAX_POSTINGS:
            break
    if given and untraceable == given:
        raise ValueError("give each posting's url exactly as a search or page load in this run returned it")
    return {"postings": postings}, warnings


# ── screen ───────────────────────────────────────────────────────────────────

SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "The job's short id, e.g. J3"},
                "relevant": {"type": "boolean"},
                "fit": {"type": "integer", "minimum": 0, "maximum": 5},
                "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                "deal_breaker": {"type": ["string", "null"]},
            }, "required": ["id", "relevant", "fit", "reasons", "deal_breaker"]},
        },
    },
    "required": ["verdicts"],
}
SCREEN_FINISH = finish.tool("Screened the jobs", "Finish with one verdict per job shown.", SCREEN_SCHEMA)
SCREEN_MISSING_TOLERANCE = 0.2


def normalize_screen(args: dict, batch: dict[str, str]) -> tuple[dict[str, dict], list[str]]:
    """`batch`: short id -> lead id. Returns lead id -> verdict."""
    result = finish.answer(args)
    verdicts: dict[str, dict] = {}
    warnings = []
    for item in finish.items(result, "verdicts"):
        if not isinstance(item, dict):
            continue
        short = str(item.get("id") or "").strip().upper()
        lead_id = batch.get(short)
        if lead_id is None:
            warnings.append(f"Ignored a verdict for an unknown job {short[:12]!r}")
            continue
        fit = item.get("fit")
        fit = max(0, min(5, int(fit))) if isinstance(fit, (int, float)) and not isinstance(fit, bool) else None
        breaker = _text(item.get("deal_breaker"), 160)
        # "None", "N/A" and the like are no deal-breaker, whatever the schema asked for.
        breaker = None if breaker.strip(" .").lower() in _NO_BREAKER else breaker
        relevant = bool(item.get("relevant")) and breaker is None
        verdicts[lead_id] = {
            "relevant": relevant,
            "fit": fit,
            "reasons": _texts(item.get("reasons"), items=3, limit=200),
            "reason": breaker or ("" if relevant else "; ".join(_texts(item.get("reasons"), items=1, limit=200))),
        }
    missing = len(batch) - len(verdicts)
    if batch and missing > len(batch) * SCREEN_MISSING_TOLERANCE:
        raise ValueError(f"give a verdict for every job: {missing} of {len(batch)} are missing")
    return verdicts, warnings


# ── approach ─────────────────────────────────────────────────────────────────

APPROACH_SCHEMA = {
    "type": "object",
    "properties": {
        "approaches": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "The job's short id, e.g. J1"},
                "summary": {"type": "string", "description": "Two sentences: the best way in and why"},
                "channel": {"type": "string", "enum": list(APPROACH_CHANNELS)},
                "steps": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                "talking_points": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                "negotiation": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                "contacts": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "source_url": {"type": "string", "description": "A page you loaded with fetch_page that names them"},
                }, "required": ["name", "role", "source_url"]}},
                "outreach": {"type": "object", "properties": {
                    "to_email": {"type": ["string", "null"],
                                 "description": "Only an address printed on a page you loaded, else null"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                }, "required": ["to_email", "subject", "body"]},
                "answers": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
                    "question_key": {"type": ["string", "null"],
                                     "description": "The key of one of the posting's questions, or null for a likely question"},
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                }, "required": ["question_key", "question", "answer"]}},
                "cover_letter": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            }, "required": ["id", "summary", "channel", "steps", "talking_points", "negotiation",
                            "contacts", "outreach", "answers", "cover_letter", "sources"]},
        },
    },
    "required": ["approaches"],
}
APPROACH_FINISH = finish.tool("Drafted approaches", "Finish with one approach per job shown.", APPROACH_SCHEMA)
MAX_LIKELY_ANSWERS = 4


def _name_on_page(name: str, page_text: str) -> bool:
    """The name as a phrase on the page, or each of its words as a whole
    word: "John Smith" is not on a page naming Johnathan Doe and Sarah
    Smithers."""
    words = [w for w in re.split(r"\s+", name.strip()) if len(w) > 1]
    if not words:
        return False
    hay = " ".join(page_text.split()).casefold()
    if " ".join(words).casefold() in hay:
        return True
    return all(re.search(rf"(?<![\w'’]){re.escape(w.casefold())}(?![\w'’])", hay) for w in words)


def _field(item: dict, key: str, short: str):
    """An approach's list or object field, read as itself when it was sent as
    JSON text; refused (one repair) when it is text that isn't JSON. Haiku
    sends nested fields as text now and then; iterated as characters, an
    approach was stored `done` with no contacts, no answers and no outreach."""
    value = finish.unquoted(item.get(key))
    if isinstance(value, str) and value.strip():
        raise ValueError(f"`{key}` of {short} came as text: send it as JSON (a list or an object), not a string")
    return value


def _answerable(question: dict) -> bool:
    return question.get("kind") == "open"


def normalize_approaches(
    args: dict,
    *,
    batch: dict[str, str],
    questions: dict[str, list[dict]],
    citable: set[str],
    pages: dict[str, str],
    observed_emails: set[str],
    user_text: str,
) -> tuple[dict[str, dict], list[str]]:
    """`batch`: short id -> lead id; `questions`: lead id -> its ATS questions;
    `citable`: links this run may cite; `pages`: url -> text fetched this run."""
    result = finish.answer(args)
    out: dict[str, dict] = {}
    warnings: list[str] = []
    typed_addresses = {m.lower() for m in _EMAIL_IN.findall(user_text or "")}
    for item in finish.items(result, "approaches"):
        if not isinstance(item, dict):
            continue
        short = str(item.get("id") or "").strip().upper()
        lead_id = batch.get(short)
        if lead_id is None or lead_id in out:
            continue
        contacts = []
        for contact in _field(item, "contacts", short) or []:
            if not isinstance(contact, dict):
                continue
            name = _text(contact.get("name"), 120)
            url = str(contact.get("source_url") or "").strip()
            page = pages.get(url)
            if name and page is not None and _name_on_page(name, page):
                contacts.append({"name": name, "role": _text(contact.get("role"), 120), "source_url": url})
            elif name:
                warnings.append(f"Dropped contact {name[:40]!r}: not named on a page loaded in this run")
        outreach = _field(item, "outreach", short)
        outreach = outreach if isinstance(outreach, dict) else {}
        to_email = str(outreach.get("to_email") or "").strip().lower() or None
        if to_email and not (_EMAIL.match(to_email) and (to_email in observed_emails or to_email in typed_addresses)):
            warnings.append(f"Dropped address {to_email[:60]!r}: not printed on a page loaded in this run")
            to_email = None
        posting_questions = {q["key"]: q for q in questions.get(lead_id, []) if isinstance(q, dict) and q.get("key")}
        answers, likely = [], 0
        for answer in _field(item, "answers", short) or []:
            if not isinstance(answer, dict):
                continue
            text = _text(answer.get("answer"), 3000)
            if not text:
                continue
            key = answer.get("question_key")
            if key:
                question = posting_questions.get(str(key))
                if question is None or not _answerable(question):
                    continue
                answers.append({"question_key": question["key"], "question": question["label"],
                                "answer": text, "likely": False})
                continue
            label = _text(answer.get("question"), 300)
            if posting_questions or not label or likely >= MAX_LIKELY_ANSWERS:
                continue  # with the real questions known, only those are answered
            if ats._AUTHORIZATION.search(label) or ats._DEMOGRAPHIC.search(label):
                continue
            likely += 1
            answers.append({"question_key": None, "question": label, "answer": text, "likely": True})
        sources = []
        for url in _field(item, "sources", short) or []:
            url = str(url or "").strip()
            if url in citable and url not in sources:
                sources.append(url)
        channel = item.get("channel") if item.get("channel") in APPROACH_CHANNELS else "apply_portal"
        out[lead_id] = {
            "summary": _text(item.get("summary"), 600),
            "channel": channel,
            "steps": _texts(_field(item, "steps", short), items=6, limit=300),
            "talking_points": _texts(_field(item, "talking_points", short), items=6, limit=300),
            "negotiation": _texts(_field(item, "negotiation", short), items=4, limit=300),
            "contacts": contacts,
            "outreach": {"to_email": to_email, "subject": _text(outreach.get("subject"), 200),
                         "body": _text(outreach.get("body"), 4000)},
            "answers": answers,
            "unanswered": [
                {"question_key": q["key"], "question": q["label"], "kind": q.get("kind")}
                for q in posting_questions.values()
                if q.get("kind") in ("file", "authorization", "demographic")
            ],
            "cover_letter": _text(item.get("cover_letter"), 6000),
            "sources": sources[:8],
        }
    if not out:
        raise ValueError(f"give an approach for each job shown, by its short id: {', '.join(batch)}")
    return out, warnings


# ── tailored résumé ──────────────────────────────────────────────────────────

MAX_TAILORED_ROLES = 12
MAX_ROLE_BULLETS = 8
MAX_TAILORED_SKILLS = 30
MAX_EXTRA_SECTIONS = 4
MAX_SECTION_LINES = 8
MAX_LINE_SOURCES = 3

_LINE = {"type": "object", "properties": {
    "text": {"type": "string", "description": "The line as it should read for this job"},
    "sources": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_LINE_SOURCES,
                "description": "The résumé lines it rewrites, each copied exactly from the résumé"},
}, "required": ["text", "sources"]}

TAILOR_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Two to four sentences: who they are, for this job"},
            "sources": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_LINE_SOURCES,
                        "description": "Résumé lines it rests on, each copied exactly"},
        }, "required": ["text", "sources"]},
        "experience": {
            "type": "array", "maxItems": MAX_TAILORED_ROLES,
            "description": "Their roles, most relevant to this job first within the résumé's own order",
            "items": {"type": "object", "properties": {
                "role": {"type": "string", "description": "The title exactly as the résumé writes it"},
                "organization": {"type": "string", "description": "The employer exactly as the résumé writes it"},
                "dates": {"type": "string", "description": "The dates exactly as the résumé writes them, or ''"},
                "bullets": {"type": "array", "items": _LINE, "maxItems": MAX_ROLE_BULLETS},
            }, "required": ["role", "organization", "dates", "bullets"]},
        },
        "skills": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_TAILORED_SKILLS,
                   "description": "Skills from the résumé this job asks for first, each as the résumé writes it"},
        "sections": {
            "type": "array", "maxItems": MAX_EXTRA_SECTIONS,
            "description": "Education, certifications and the like, from the résumé",
            "items": {"type": "object", "properties": {
                "heading": {"type": "string"},
                "lines": {"type": "array", "items": _LINE, "maxItems": MAX_SECTION_LINES},
            }, "required": ["heading", "lines"]},
        },
        "changes": {"type": "array", "items": {"type": "string"}, "maxItems": 6,
                    "description": "What you changed for this job and why, one short sentence each"},
        "gaps": {"type": "array", "items": {"type": "string"}, "maxItems": 6,
                 "description": "What the posting asks for that the résumé doesn't show"},
    },
    "required": ["summary", "experience", "skills", "sections", "changes", "gaps"],
}
TAILOR_FINISH = finish.tool("Tailored the résumé", "Finish with the résumé tailored to this job.", TAILOR_SCHEMA)


# A source shorter than this can be found in almost any résumé ("managed the").
MIN_SOURCE_WORDS = 3
# Of a line's own words (four letters or more), at least this share must be in
# its sources: rewording for the posting is fine, writing new work isn't.
MIN_SHARED_WORDS = 0.5
# Spelled-out amounts, checked like digits ("five regions" needs a 5 or a "five").
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "dozen": 12,
    "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000,
}
# Claims of size that no digit carries: kept only when the sources say them too.
_SCALE_WORDS = {"doubled", "doubling", "tripled", "tripling", "quadrupled", "tenfold", "decade", "decades"}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&+#'.-]*")
_STOP = {"with", "from", "that", "this", "their", "they", "into", "over", "across", "while", "within",
         "through", "including", "using", "which", "where", "when", "also", "each", "every", "more"}


def _words(text: str) -> list[str]:
    return [w.rstrip(".-'") for w in _WORD.findall(text or "") if w.rstrip(".-'")]


def _written_in(value: str, text_norm: str) -> bool:
    """`value` written in `text_norm` as whole words (case and spacing aside):
    "Excel" isn't in "excellent", nor "AWS" in "laws"."""
    return len(_norm(value)) >= 2 and _has_word(value, text_norm)


def _has_word(value: str, text_norm: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_norm(value))}(?!\w)", text_norm) is not None


def _numbers_exact(text: str, sources: str) -> bool:
    """Every number in `text` is written in `sources` exactly: no rounding a
    year or a headcount, and a spelled-out amount counts as a number."""
    stated = set(amounts_in(sources))
    source_words = set(re.findall(r"[a-z]+", sources.casefold()))
    if any(value not in stated for value in amounts_in(text)):
        return False
    for word in re.findall(r"[a-z]+", text.casefold()):  # "forty-five" is two words here
        if word in _NUMBER_WORDS and word not in source_words and _NUMBER_WORDS[word] not in stated:
            return False
        if word in _SCALE_WORDS and word not in source_words:
            return False
    return True


def _check(text: str, sources: list[str], within: str, *, facts_from: str | None = None, shared: bool = True) -> str:
    """Why `text` can't be traced to `sources` within `within`, or ''. Its
    numbers and names must be in `facts_from` (its sources, unless given)."""
    if not sources:
        return "it names no résumé line it comes from"
    if any(len(_words(s)) < MIN_SOURCE_WORDS or not verify_quote(s, within) for s in sources):
        return "its sources aren't in the résumé word for word"
    joined = " ".join(sources)
    facts = joined if facts_from is None else facts_from
    if not _numbers_exact(text, facts):
        return "a number in it isn't in its sources"
    facts_norm = _norm(facts)
    # A name, product or acronym ("Snowflake", "AWS", "P&L") has to come from
    # the sources; a capital that only starts a sentence doesn't count.
    for match in _WORD.finditer(text):
        word = match.group().rstrip(".-'")
        starts = not text[:match.start()].rstrip() or text[:match.start()].rstrip()[-1] in ".!?:;"
        named = any(c.isupper() for c in word[1:]) or any(c.isdigit() for c in word) \
            or (word[:1].isupper() and not starts)
        if word and named and not _has_word(word, facts_norm):
            return f"{word!r} isn't in its sources"
    words = _words(text)
    if shared:
        own = [w.casefold() for w in words if len(w) >= 4 and w.casefold() not in _STOP]
        stems = {w.casefold()[:5] for w in _words(joined)}
        if own and sum(w[:5] in stems for w in own) < MIN_SHARED_WORDS * len(own):
            return "most of its words aren't in its sources"
    return ""


def _sources(item: dict) -> list[str]:
    raw = item.get("sources")
    return [s for s in (_text(v, 600) for v in raw[:MAX_LINE_SOURCES]) if s] if isinstance(raw, list) else []


def _line(item: Any, within: str) -> tuple[dict | None, str]:
    """A rewritten line, kept only when it traces to résumé text in `within`
    (its role's part of the résumé, or all of it). (line, why not)."""
    if not isinstance(item, dict):
        return None, "not a line"
    text = _text(item.get("text"), 400)
    if not text:
        return None, "empty"
    sources = _sources(item)
    why = _check(text, sources, within)
    if why:
        return None, f"{text[:60]!r}: {why}"
    return {"text": text, "sources": sources}, ""


def _header(fields: dict[str, str], lines: list[str]) -> tuple[int | None, set[str]]:
    """Where in the résumé this role is written: the first run of up to three
    lines, starting on one that names it, naming the most of its title,
    employer and dates together. (line index, the fields found there)."""
    best: tuple[int | None, set[str]] = (None, set())
    for i in range(len(lines)):
        if not any(v and _written_in(v, lines[i]) for v in fields.values()):
            continue
        window = " ".join(lines[i:i + 3])
        found = {k for k, v in fields.items() if v and _written_in(v, window)}
        if len(found) > len(best[1]):
            best = (i, found)
    return best


def normalize_tailored(args: dict, *, resume: str) -> tuple[dict, list[str]]:
    """What survives of a tailored résumé: every line traced to the résumé.
    A line that isn't is dropped (and counted, so the page can say so). A
    role's title, employer and dates are kept only where the résumé writes
    them together, and its lines only from that role's part of the résumé; a
    role with neither title nor employer is dropped. Nothing left at all gets
    the model one repair."""
    result = finish.answer(args)
    resume_norm = _norm(resume)
    lines_norm = [_norm(line) for line in resume.splitlines() if line.strip()]
    warnings: list[str] = []
    dropped = 0

    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    summary_text = _text(summary.get("text"), 1200)
    summary_sources = _sources(summary)
    # A summary draws on the whole résumé: its names and numbers must be in it,
    # and it must still name the lines it rests on.
    why = _check(summary_text, summary_sources, resume, facts_from=resume, shared=False) if summary_text else ""
    if why:
        warnings.append(f"Dropped the summary: {why}")
        summary_text, summary_sources, dropped = "", [], dropped + 1

    roles = []
    for role in finish.items(result, "experience")[:MAX_TAILORED_ROLES]:
        if not isinstance(role, dict):
            continue
        fields = {key: _text(role.get(key), limit) for key, limit in (("role", 160), ("organization", 160), ("dates", 80))}
        at, found = _header(fields, lines_norm)
        for key, value in fields.items():
            if value and key not in found:
                warnings.append(f"Left out {key} {value[:40]!r}: not written with this role in the résumé")
                fields[key] = ""
        roles.append((role, fields, at))

    # A role's part of the résumé runs from where it is written to where the
    # next role starts, so a line can't be moved under another job.
    starts = sorted({at for _, _, at in roles if at is not None})
    experience = []
    for role, fields, at in roles:
        if at is None:
            within = resume
        else:
            end = next((s for s in starts if s > at), len(lines_norm))
            within = " ".join(lines_norm[at:end])
        bullets = []
        for item in (role.get("bullets") or [])[:MAX_ROLE_BULLETS] if isinstance(role.get("bullets"), list) else []:
            line, why = _line(item, within)
            if line:
                bullets.append(line)
            else:
                dropped += 1
                warnings.append(f"Dropped a line: {why}")
        if not (fields["role"] or fields["organization"]):
            dropped += len(bullets)
            continue
        experience.append({**fields, "bullets": bullets})

    skills: dict[str, str] = {}
    for skill in result.get("skills") if isinstance(result.get("skills"), list) else []:
        value = _text(skill, 80)
        if value and _written_in(value, resume_norm):
            skills.setdefault(value.casefold(), value)
        elif value:
            warnings.append(f"Left out skill {value[:40]!r}: not in the résumé")
    sections = []
    for section in finish.items(result, "sections")[:MAX_EXTRA_SECTIONS]:
        if not isinstance(section, dict):
            continue
        heading = _text(section.get("heading"), 60)
        lines = []
        for item in (section.get("lines") or [])[:MAX_SECTION_LINES] if isinstance(section.get("lines"), list) else []:
            line, why = _line(item, resume)
            if line:
                lines.append(line)
            else:
                dropped += 1
                warnings.append(f"Dropped a line: {why}")
        if heading and lines:
            sections.append({"heading": heading, "lines": lines})

    if not any(role["bullets"] for role in experience):
        raise ValueError(
            "no experience line could be traced to the résumé: give each line `sources` copied "
            "exactly from that role's part of the résumé (whole lines, not a few words), keep its "
            "names and numbers as they are there, and put nothing in it they don't say"
        )
    return {
        "summary": {"text": summary_text, "sources": summary_sources},
        "experience": experience,
        "skills": list(skills.values())[:MAX_TAILORED_SKILLS],
        "sections": sections,
        "changes": _texts(result.get("changes"), items=6, limit=240),
        "gaps": _texts(result.get("gaps"), items=6, limit=240),
        "dropped": dropped,
    }, warnings
