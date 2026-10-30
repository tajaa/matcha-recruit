"""Outreach playbooks for sales campaigns.

A campaign with no playbook is the general one: find people, research them,
draft. The consulting playbook (`CONSULTING`) is for selling advisory work
(HR, compliance, investigations, AI review) to businesses, where a cold
message lands only when it names a real, current reason to talk. So:

- every prospect is placed in a segment (`SEGMENTS`) and matched to one
  service (`SERVICES`), with its why-now `signal` (one sentence, backed by
  the prospect's sources) and a `fit` of 1-3;
- every draft is short, names that signal, asks for one thing (the
  campaign's `cta_url`), cites no number its research doesn't hold, and
  never tells a business it is breaking a law (`draft_problems`).

The assistant's drafts must pass `draft_problems`; a person's own edits are
theirs, so the review surfaces show the same checks as flags instead
(`review_flags`). Matcha's own offer (`HOUSE`) is a preset only Matcha staff
see (`house_available`); everyone else writes their own offer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CONSULTING = "consulting"
PLAYBOOKS = ("", CONSULTING)


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    buyer: str  # who to write to
    service: str  # the service that usually fits
    signals: tuple[str, ...]  # where a why-now reason shows up in public


SEGMENTS: dict[str, Segment] = {
    s.key: s
    for s in (
        Segment(
            "growing",
            "Growing, no HR lead",
            "the founder, CEO, COO or head of operations",
            "hr",
            (
                "hiring their first HR, People Operations or HR generalist role (their careers page, "
                "or their board on boards.greenhouse.io, jobs.lever.co or jobs.ashbyhq.com)",
                "many open roles at once, or open roles in several states (the locations on their job posts)",
                "a funding round, acquisition or expansion announced on their own site or in the press",
            ),
        ),
        Segment(
            "regulated",
            "Healthcare and manufacturing",
            "the owner, administrator, COO, or the compliance, quality or safety lead",
            "grc",
            (
                "an OSHA inspection on osha.gov's establishment search that names them",
                "a state survey or CMS inspection result for a clinic, home health agency or senior-living community",
                "a new facility, a new state, or a new license or accreditation they announced",
            ),
        ),
        Segment(
            "ai",
            "Adopting AI",
            "the CEO, COO, CTO or head of people",
            "ai",
            (
                "their own announcement of AI tools in hiring, HR, customer service or operations",
                "job posts for AI, automation or data roles",
                "a vendor case study or press release that names them as using an AI product",
            ),
        ),
        Segment(
            "hourly",
            "Restaurants and retail",
            "the owner, operator or director of operations",
            "hr",
            (
                "several locations on their locations page, or a new one opening",
                "hiring hourly staff at several locations at once",
                "locations in a city with its own scheduling or wage rules (name the city, never a legal conclusion)",
            ),
        ),
    )
}

SERVICES: dict[str, str] = {
    "hr": "HR consulting",
    "grc": "Governance, risk and compliance",
    "er": "Employee relations and investigations",
    "ai": "AI integration review",
}

# 3: a specific, recent signal from a primary source (their own site, a
# government record) and a named decision-maker; 2: a real signal, but older
# or second-hand, or no named person; 1: fits the segment, no current signal.
FITS = (1, 2, 3)

MAX_WORDS = 150
MAX_SUBJECT = 70

# A cold message never tells a business it is breaking a law, threatens what
# could happen, or promises an outcome: that is a legal opinion nobody asked
# for, and it reads as a scare email. Only words with no everyday meaning:
# "fine" (fine-tune) and "sue" (a name) are left out on purpose.
_LEGAL = re.compile(
    r"\b(violat\w*|illegal\w*|unlawful\w*|non-?complian\w*|out of compliance|lawsuits?|litigation|sued|"
    r"liable|liabilit\w*|penalt\w*|fined|fines|guarantee\w*)\b",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s<>()\"']+")
# A number in digits, with the scale written after it ("$2.5M", "2.5 million", "40k").
_DIGITS = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)(?:\s*(k|m|mm|bn|b|thousand|million|billion)\b)?", re.IGNORECASE,
)
_UNITS = {
    w: i for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen".split())
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {
    "hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000,
    "k": 1_000, "m": 1_000_000, "mm": 1_000_000, "b": 1_000_000_000, "bn": 1_000_000_000,
}
# Size claims with no number in them: kept only when the evidence says them too.
_SIZE_WORDS = {"dozen", "doubled", "tripled", "quadrupled", "tenfold"}
# "one" and "a" carry no claim ("one call", "a team"), so they don't start a number.
_QUIET = {"zero", "one"}


def _spelled(words: list[str]) -> float | None:
    """ "two hundred" -> 200, "twenty-five thousand" -> 25000."""
    total, current, seen = 0, 0, False
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word in ("thousand", "million", "billion"):
            total += max(current, 1) * _SCALES[word]
            current = 0
        else:
            continue
        seen = True
    return float(total + current) if seen else None


def _amounts(text: str) -> set:
    """Every amount `text` states, as values ("2.5 million" == "$2.5M" == 2500000),
    plus size words with no number ("doubled"). A link's digits aren't claims."""
    text = _URL.sub(" ", text or "")
    found: set = set()
    for digits, scale in _DIGITS.findall(text):
        try:
            value = float(digits.replace(",", ""))
        except ValueError:
            continue
        found.add(value * _SCALES.get((scale or "").lower(), 1))
    run: list[str] = []
    for word in re.findall(r"[a-z]+", re.sub(r"\d[\d,.]*\s*\w*", " ", text.lower())) + [""]:
        if word in _UNITS or word in _TENS or word in ("hundred", "thousand", "million", "billion"):
            run.append(word)
            continue
        if word == "and" and run:
            continue
        if run and not set(run) <= _QUIET:
            value = _spelled(run)
            if value is not None:
                found.add(value)
        run = []
        if word in _SIZE_WORDS:
            found.add(word)
    return found


_FAKE_THREAD = re.compile(r"^\s*(re|fwd?|fw)\s*:", re.IGNORECASE)

HOUSE = {
    "title": "Matcha consulting",
    "target": (
        "US employers of about 20 to 500 people with a public reason to need HR, compliance or AI help now: "
        "growing companies without an HR lead; healthcare and manufacturing (OSHA, CMS, state boards); "
        "companies adopting AI in hiring or operations; restaurants and retailers with several locations."
    ),
    "offer": (
        "Matcha (hey-matcha.com) is an HR and compliance consulting firm. Four services:\n"
        "- HR consulting: compensation frameworks and pay equity, multi-state handbooks, performance "
        "programs, hiring, termination and classification review, advisory retainers.\n"
        "- Governance, risk and compliance: regulatory gap analysis across every state a company operates "
        "in, compliance programs for healthcare and manufacturing, audit preparation and remediation, "
        "credential and license programs.\n"
        "- Employee relations: independent workplace investigations, mediation, separation risk review, "
        "memos counsel can use.\n"
        "- AI integration review: independent evaluation of AI tools in hiring and operations for bias, "
        "privacy and compliance risk, with a deployment playbook.\n"
        "How we work: discovery, diagnosis, design, delivery.\n"
        "The ask: a 20-minute call."
    ),
    "cta_url": "https://hey-matcha.com/services?book=1",
}


def house_available(role: str | None, email: str | None) -> bool:
    """Matcha staff: an admin account, or the platform's master admin."""
    from app.core.dependencies import _is_master_admin

    return (role or "") == "admin" or _is_master_admin(email)


def guide() -> dict:
    """The consulting playbook as data, for the assistant and the review pages."""
    return {
        "key": CONSULTING,
        "label": "Consulting outreach",
        "segments": [
            {"key": s.key, "label": s.label, "buyer": s.buyer, "service": s.service, "signals": list(s.signals)}
            for s in SEGMENTS.values()
        ],
        "services": [{"key": k, "label": v} for k, v in SERVICES.items()],
        "max_words": MAX_WORDS,
    }


def _shown(value) -> str:
    if isinstance(value, float):
        return f"{value:,.0f}" if value == int(value) else f"{value:,}"
    return str(value)


def draft_problems(subject: str, body: str, *, cta_url: str, signal: str, evidence: str) -> list[str]:
    """What keeps a consulting draft from going out as written. `evidence` is
    everything a number may come from: the prospect's research and signal,
    and the campaign's offer."""
    subject, body = subject or "", body or ""
    problems = []
    if not (signal or "").strip():
        problems.append("Save the prospect's why-now signal (with its sources) before drafting.")
    if len(subject) > MAX_SUBJECT:
        problems.append(f"Keep the subject under {MAX_SUBJECT} characters.")
    if _FAKE_THREAD.match(subject):
        problems.append("Don't start the subject with Re: or Fwd: on a first message.")
    words = len(re.findall(r"\S+", _URL.sub("", body)))
    if words > MAX_WORDS:
        problems.append(f"Keep the message under {MAX_WORDS} words (it has {words}).")
    links = {u.rstrip(".,;:!?") for u in _URL.findall(body)}
    if not cta_url:
        problems.append("Add the campaign's booking link before drafting: every message asks for it.")
    elif cta_url not in links:
        problems.append(f"Ask for one thing: include the booking link {cta_url}.")
    if links - {cta_url}:
        problems.append("Include no link but the booking link.")
    unsupported = sorted(_amounts(subject + "\n" + body) - _amounts(evidence), key=str)
    if unsupported:
        problems.append(
            "Cite no number or result the research and offer don't state: "
            + ", ".join(_shown(v) for v in unsupported[:5]) + "."
        )
    legal = sorted({m.group(0).lower() for m in _LEGAL.finditer(subject + "\n" + body)})
    if legal:
        problems.append(
            "Don't tell them they're breaking a law, warn of penalties or promise outcomes ("
            + ", ".join(legal[:4]) + "). Name the signal and offer a conversation."
        )
    return problems


def review_flags(campaign, prospect) -> list[str]:
    """The same checks on a saved draft, for the person reviewing it."""
    if (campaign.get("playbook") or "") != CONSULTING or not (prospect.get("subject") or prospect.get("body")):
        return []
    return draft_problems(
        prospect.get("subject") or "",
        prospect.get("body") or "",
        cta_url=campaign.get("cta_url") or "",
        signal=prospect.get("signal") or "",
        evidence="\n".join(
            [prospect.get("research") or "", prospect.get("signal") or "", campaign.get("offer") or ""]
        ),
    )
