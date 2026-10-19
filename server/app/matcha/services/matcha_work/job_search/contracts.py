"""What each model phase must hand back, and how it is checked. Pure: no I/O.

The model never writes to the database. Each phase ends with one `finish`
call; its arguments go through a `normalize_*` here, and the orchestrator
persists only what survives. A ValueError gets the model one repair.

  plan       the titles to search and what to rank on, from the ask (and résumé)
  discover   links to current postings found on the web (code reads each one)
  screen     relevant or not, and a 0-5 fit, for a batch of jobs by short id
  approach   per job: how to approach, drafts, answers to the real questions

Checks that matter:
  * a posting's link must be one this run's searches or page loads returned
  * ids must be ones the batch showed (short ids like J3, mapped back here)
  * a contact must be named on a page fetched in this run
  * an email must be printed on a fetched page or typed by the person
  * an answer must be to one of the posting's open questions; file,
    authorization and demographic questions are never answered
  * every link must be one this run's searches or page loads returned
"""
from __future__ import annotations

import re
from typing import Any

from app.matcha.services.matcha_work.agent_runtime import finish

from . import ats, normalize
from .comp import verify_quote

# Titles a plan searches for: what they typed, then kept directions, then the
# plan's own (`phases.search_titles` says how many the searches take).
MAX_TITLES = 10
# Roles beyond the person's own title that their résumé supports, suggested
# by the plan: at most this many, each among the first titles searched.
MAX_DIRECTIONS = 3
APPROACH_CHANNELS = ("referral", "hiring_manager", "recruiter", "apply_portal", "search_firm")
_EMAIL = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


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
    given = 0
    for item in result.get("postings") or []:
        if not isinstance(item, dict):
            continue
        given += 1
        url = str(item.get("url") or "").strip()
        title = _text(item.get("title"), 200)
        if url not in citable or not url.startswith(("https://", "http://")):
            warnings.append(f"Dropped {url[:80]!r}: not a link this run's searches or page loads returned")
            continue
        if url in seen or not title:
            continue
        seen.add(url)
        postings.append({"url": url, "title": title, "company": _text(item.get("company"), 200),
                         "location": _text(item.get("location"), 200)})
        if len(postings) >= MAX_POSTINGS:
            break
    if given and not postings:
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
    for item in result.get("verdicts") or []:
        if not isinstance(item, dict):
            continue
        short = str(item.get("id") or "").strip().upper()
        lead_id = batch.get(short)
        if lead_id is None:
            warnings.append(f"Ignored a verdict for an unknown job {short[:12]!r}")
            continue
        fit = item.get("fit")
        fit = max(0, min(5, int(fit))) if isinstance(fit, (int, float)) and not isinstance(fit, bool) else None
        breaker = _text(item.get("deal_breaker"), 160) or None
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
    words = [w for w in re.split(r"\s+", name.strip()) if len(w) > 1]
    if not words:
        return False
    hay = page_text.casefold()
    return all(w.casefold() in hay for w in words)


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
    user_lower = (user_text or "").lower()
    for item in result.get("approaches") or []:
        if not isinstance(item, dict):
            continue
        lead_id = batch.get(str(item.get("id") or "").strip().upper())
        if lead_id is None or lead_id in out:
            continue
        contacts = []
        for contact in item.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            name = _text(contact.get("name"), 120)
            url = str(contact.get("source_url") or "").strip()
            page = pages.get(url)
            if name and page is not None and _name_on_page(name, page):
                contacts.append({"name": name, "role": _text(contact.get("role"), 120), "source_url": url})
            elif name:
                warnings.append(f"Dropped contact {name[:40]!r}: not named on a page loaded in this run")
        outreach = item.get("outreach") if isinstance(item.get("outreach"), dict) else {}
        to_email = str(outreach.get("to_email") or "").strip().lower() or None
        if to_email and not (_EMAIL.match(to_email) and (to_email in observed_emails or to_email in user_lower)):
            warnings.append(f"Dropped address {to_email[:60]!r}: not printed on a page loaded in this run")
            to_email = None
        posting_questions = {q["key"]: q for q in questions.get(lead_id, []) if isinstance(q, dict) and q.get("key")}
        answers, likely = [], 0
        for answer in item.get("answers") or []:
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
        for url in item.get("sources") or []:
            url = str(url or "").strip()
            if url in citable and url not in sources:
                sources.append(url)
        channel = item.get("channel") if item.get("channel") in APPROACH_CHANNELS else "apply_portal"
        out[lead_id] = {
            "summary": _text(item.get("summary"), 600),
            "channel": channel,
            "steps": _texts(item.get("steps"), items=6, limit=300),
            "talking_points": _texts(item.get("talking_points"), items=6, limit=300),
            "negotiation": _texts(item.get("negotiation"), items=4, limit=300),
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
        raise ValueError("give an approach for each job shown, by its short id")
    return out, warnings
