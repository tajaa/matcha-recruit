"""External legal research for Legal Pilot — CourtListener case search +
grounded-Gemini guidance synthesis.

Informational only, never legal advice: case-law hits are search-relevance
results, not vetted precedent, and the Gemini synthesis is a public-guidance
summary, not an assessment of the company's position. Only CourtListener API
rows become citable evidence (``case:<cluster_id>`` cids minted from rows
persisted here) — the Gemini guidance text is never cited, per
``legal_defense.validate_citations``'s index-membership invariant.

Because persisted rows become citable, retrieval precision is a correctness
concern, not a UX one. Two axes must hold, and they fail independently:

*Jurisdiction* — the matter's state selects a ``court`` filter
(``_STATE_COURTS``) rather than a free-text state name.

*Subject* — the matter's resolved theory (``legal_defense.resolve_matter_theory``,
the same one that scopes the evidence corpus) anchors EVERY query-ladder tier to
that theory's legal concepts, and gates the returned cases against their own text
afterwards. Jurisdiction alone is not relevance: a San Diego gunshot-wrongful-death
opinion is validly inside a California wage-and-hour matter's court set, and
before the subject axis existed it was retrieved for one — its opinion mentions
employees who "worked", took "breaks", and were "unpaid". ``_filter_rank``'s BM25
floor cannot catch that: it compares hits against each other within one query, so
a uniformly off-subject field survives intact.
"""

import asyncio
import json
import logging
import re

import httpx
from google.genai import types

from app.config import get_settings
from app.core.services.genai_client import get_genai_client
from app.core.services.rate_limiter import get_rate_limiter
from app.database import get_connection

from .legal_defense import MODEL as _GEMINI_MODEL
from .legal_defense import _hum, _matches_other_subject, _parse_json, resolve_matter_theory

logger = logging.getLogger(__name__)

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"
_CL_TIMEOUT = 20.0
_MAX_CASES = 8
_GUIDANCE_TIMEOUT = 90

# A hit must score at least this fraction of the reference BM25 to survive.
# RELATIVE, not absolute: BM25 is query-scale dependent — probing the live API
# showed a top score of 40.7 on one query and 7.5 on another, so any fixed
# threshold would pass junk on rich queries and reject everything on thin ones.
_RELEVANCE_FLOOR_RATIO = 0.35

# ...and the reference is the MEDIAN of the top 3 scores, not the top score.
# BM25 spikes when a query term appears in the case caption: a live probe of the
# class-action tier scored "In re NJOY Consumer Class Action Litigation" at
# 192.9 against a ~30 field, which with a top-anchored floor discarded all seven
# genuine hits. The median of the top 3 ignores one such outlier.
_FLOOR_REFERENCE_SAMPLE = 3

# Copied from compliance_service._CODE_TO_STATE_NAME — kept local since this
# module only needs it to enrich the CourtListener query / Gemini prompt with
# a human-readable jurisdiction, not for any DB lookup.
_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District Of Columbia",
}

# CourtListener court IDs whose rulings actually bind a matter in each state:
# state high court + intermediate appellate court(s) + the federal district
# court(s) sitting in the state + the governing federal circuit. Employment
# claims (Title VII, FLSA, ADA) are mostly federal, so the district/circuit
# entries are load-bearing, not decoration.
#
# These go to the search endpoint's ``court`` param. The state name is NEVER
# put in ``q``: CourtListener ANDs free-text terms, so "Nevada" matched any
# opinion mentioning the word — including a *Texas* case captioned "Nevada v.
# U.S. Dep't of Labor" and California's "Sierra Nevada Memorial-Miners
# Hospital". A party name is not a jurisdiction.
#
# SCOTUS is deliberately absent: its opinions bind everywhere (never
# jurisdictionally wrong) but score high on generic employment terms and would
# crowd the 8-case cap with landmarks counsel already knows.
#
# CourtListener SILENTLY IGNORES an unknown court id — no 400, just a quietly
# narrower filter. A typo here degrades results without any error surfacing, so
# every id below is verified to exist and be in_use against
# ``/api/rest/v4/courts/``; ``test_state_courts_*`` guards the shape. Ids do not
# follow a predictable pattern (Nevada's appellate court is ``nevapp``, not
# ``nevctapp``) — look them up, never infer them.
_STATE_COURTS: dict[str, tuple[str, ...]] = {
    "AL": ("ala", "alacivapp", "alacrimapp", "almd", "alnd", "alsd", "ca11"),
    "AK": ("alaska", "alaskactapp", "akd", "ca9"),
    "AZ": ("ariz", "arizctapp", "azd", "ca9"),
    "AR": ("ark", "arkctapp", "ared", "arwd", "ca8"),
    "CA": ("cal", "calctapp", "cacd", "caed", "cand", "casd", "ca9"),
    "CO": ("colo", "coloctapp", "cod", "ca10"),
    "CT": ("conn", "connappct", "ctd", "ca2"),
    "DE": ("del", "ded", "ca3"),
    "DC": ("dc", "dcd", "cadc"),
    "FL": ("fla", "fladistctapp", "flmd", "flnd", "flsd", "ca11"),
    "GA": ("ga", "gactapp", "gamd", "gand", "gasd", "ca11"),
    "HI": ("haw", "hawapp", "hid", "ca9"),
    "ID": ("idaho", "idahoctapp", "idd", "ca9"),
    "IL": ("ill", "illappct", "ilcd", "ilnd", "ilsd", "ca7"),
    "IN": ("ind", "indctapp", "innd", "insd", "ca7"),
    "IA": ("iowa", "iowactapp", "iand", "iasd", "ca8"),
    "KS": ("kan", "kanctapp", "ksd", "ca10"),
    "KY": ("ky", "kyctapp", "kyed", "kywd", "ca6"),
    "LA": ("la", "lactapp", "laed", "lamd", "lawd", "ca5"),
    "ME": ("me", "med", "ca1"),
    "MD": ("md", "mdctspecapp", "mdd", "ca4"),
    "MA": ("mass", "massappct", "mad", "ca1"),
    "MI": ("mich", "michctapp", "mied", "miwd", "ca6"),
    "MN": ("minn", "minnctapp", "mnd", "ca8"),
    "MS": ("miss", "missctapp", "msnd", "mssd", "ca5"),
    "MO": ("mo", "moctapp", "moed", "mowd", "ca8"),
    "MT": ("mont", "mtd", "ca9"),
    "NE": ("neb", "nebctapp", "ned", "ca8"),
    "NV": ("nev", "nevapp", "nvd", "ca9"),
    "NH": ("nh", "nhd", "ca1"),
    "NJ": ("nj", "njsuperctappdiv", "njd", "ca3"),
    "NM": ("nm", "nmctapp", "nmd", "ca10"),
    "NY": ("ny", "nyappdiv", "nyed", "nynd", "nysd", "nywd", "ca2"),
    "NC": ("nc", "ncctapp", "nced", "ncmd", "ncwd", "ca4"),
    "ND": ("nd", "ndd", "ca8"),
    "OH": ("ohio", "ohioctapp", "ohnd", "ohsd", "ca6"),
    "OK": ("okla", "oklacivapp", "oklacrimapp", "oked", "oknd", "okwd", "ca10"),
    "OR": ("or", "orctapp", "ord", "ca9"),
    "PA": ("pa", "pasuperct", "pacommwct", "paed", "pamd", "pawd", "ca3"),
    "RI": ("ri", "rid", "ca1"),
    "SC": ("sc", "scctapp", "scd", "ca4"),
    "SD": ("sd", "sdd", "ca8"),
    "TN": ("tenn", "tennctapp", "tned", "tnmd", "tnwd", "ca6"),
    "TX": ("tex", "texapp", "texcrimapp", "txed", "txnd", "txsd", "txwd", "ca5"),
    "UT": ("utah", "utahctapp", "utd", "ca10"),
    "VT": ("vt", "vtd", "ca2"),
    "VA": ("va", "vactapp", "vaed", "vawd", "ca4"),
    "WA": ("wash", "washctapp", "waed", "wawd", "ca9"),
    "WV": ("wva", "wvnd", "wvsd", "ca4"),
    "WI": ("wis", "wisctapp", "wied", "wiwd", "ca7"),
    "WY": ("wyo", "wyd", "ca10"),
}

# The broadest ladder tier. These replace the humanized ``matter_type`` enum
# label, which is a UI string, not a search term: ANDed as free text it made
# "Eeoc Charge" require the literal tokens "eeoc" and "charge", and "Other"
# matched everything — a live probe of ``q="Other Nevada"`` returned 84,621
# hits topped by a death-penalty case. Expressions are code-authored, so they
# reach CourtListener's query parser verbatim (quotes and OR intact) rather
# than through ``_sanitize_query``, which exists to defang free text.
#
# Every expression is ANDed with an employment anchor. A procedural posture is
# not a subject: unanchored, ``"class action" OR "collective action"`` returned
# a consumer vape class action as its top hit, and ``"motion to quash"`` reaches
# grand-jury practice. The anchor keeps the broadest tier inside employment law,
# which is the only corpus a Legal Pilot matter is ever about.
_EMPLOYMENT_ANCHOR = '(employment OR employee OR "wage and hour")'
_MATTER_TYPE_TERMS: dict[str, str] = {
    "class_action": f'("class action" OR "collective action") AND {_EMPLOYMENT_ANCHOR}',
    "eeoc_charge": f'(discrimination OR retaliation OR "hostile work environment") AND {_EMPLOYMENT_ANCHOR}',
    "single_plaintiff": f'("wrongful termination" OR retaliation) AND {_EMPLOYMENT_ANCHOR}',
    "subpoena": f'("motion to quash" OR "subpoena duces tecum") AND {_EMPLOYMENT_ANCHOR}',
    "audit": f'("wage and hour" OR "records inspection") AND {_EMPLOYMENT_ANCHOR}',
    "other": f'("employment discrimination" OR "wrongful termination") AND {_EMPLOYMENT_ANCHOR}',
}
_DEFAULT_MATTER_TERMS = _MATTER_TYPE_TERMS["other"]

# The SUBJECT anchor, keyed by ``legal_defense`` theory slug. Where
# _EMPLOYMENT_ANCHOR only keeps the broadest tier inside employment law, these
# keep every tier inside the matter's own subject — the allegation keywords alone
# never did. "Nurses were required to work through meal breaks off the clock"
# reduces to tokens (nurses required work meal breaks clock) that a
# wrongful-death opinion satisfies as readily as a wage opinion.
#
# Code-authored like _MATTER_TYPE_TERMS: quotes and OR reach CourtListener's
# parser verbatim (``sanitize=False``). Keyword tiers are alphabetic by
# construction (``_WORD_RE``), so ANDing them onto an anchor stays parser-safe.
_THEORY_ANCHORS: dict[str, str] = {
    "wage_hour": ('("wage and hour" OR overtime OR "meal period" OR "meal break" '
                  'OR "off the clock" OR "unpaid wages")'),
    "eeo": '(discrimination OR harassment OR retaliation OR "hostile work environment")',
    "safety": '(OSHA OR "workplace safety" OR "workplace injury" OR "workers compensation")',
}


_RESERVED_QUERY_CHARS_RE = re.compile(r'[\[\]{}()"~^:/&|]')

# CourtListener's v4 search effectively ANDs free-text terms: feeding the raw
# 300-char allegation in returns zero (or one irrelevant) hit — confirmed by
# probing the live API (full-sentence EEOC allegation + "Nevada" → count:0;
# "class action overtime wages Nevada" → count:425). So the query is built
# from KEYWORDS, and run_research broadens through a ladder until something
# matches.
#
# Tokens are alphabetic by construction (``_WORD_RE``), so keyword tiers carry
# no query-parser metacharacters and need no sanitizing — which is what lets
# the curated broadest tier keep its quotes and OR operators.
_QUERY_STOPWORDS = frozenset("""
a about after all also an and any are as at be because been before being but
by can could did do does during each for from had has have he her hers him his
how i if in into is it its just may me might most must my no nor not of on or
our ours out over she should so some such than that the their theirs them then
there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your yours
""".split())
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]+")

# Sentence-ish boundaries: a capital right after one of these says nothing about
# whether the word is a name.
_SENTENCE_END = frozenset(".!?;:")
# ALL-CAPS acronyms are real search terms (FLSA, OSHA, ADA, EEOC), never names.
_ACRONYM_MAX = 5


def _proper_nouns(text: str) -> set[str]:
    """Lowercased tokens that read as proper nouns in ``text`` — party and
    employer names. Pure.

    An allegation names its parties first ("Jim Jones, a nurse, is claiming
    World Health denied breaks"), so the leading keywords are exactly the words
    that identify nobody's legal subject. CourtListener ANDs free text, so
    "jim jones nurse" retrieves opinions that merely have a party named Jones —
    a criminal appeal, in the case that prompted this.

    A token is a name when EVERY occurrence is capitalized and at least one sits
    mid-sentence (where capitalization carries information). A sentence-initial
    capital is ambiguous — "Employees were required..." is not a name — so it
    only counts when the NEXT token is itself a name, which is how "Jim" in
    "Jim Jones" is caught without catching "Employees" in "Employees were"."""
    occurrences: list[tuple[str, bool, bool]] = []   # (lower, capitalized, sentence_initial)
    for m in _WORD_RE.finditer(text or ""):
        tok = m.group()
        before = (text[:m.start()].rstrip() or "")
        sentence_initial = not before or before[-1] in _SENTENCE_END
        occurrences.append((tok.lower(), tok[0].isupper(), sentence_initial))
        if tok.isupper() and len(tok) <= _ACRONYM_MAX:
            occurrences[-1] = (tok.lower(), False, sentence_initial)   # acronym, not a name

    always_cap = {low for low, cap, _ in occurrences if cap}
    always_cap -= {low for low, cap, _ in occurrences if not cap}
    names = {low for low, cap, si in occurrences if cap and not si and low in always_cap}

    # "Jim" is sentence-initial, but it precedes the name "Jones".
    for i, (low, cap, si) in enumerate(occurrences):
        if cap and si and low in always_cap and i + 1 < len(occurrences):
            if occurrences[i + 1][0] in names:
                names.add(low)
    return names


def _keywords(text: str, limit: int) -> list[str]:
    """Significant search terms from free text: alphabetic tokens, stopwords,
    1-char fragments and proper nouns dropped, order preserved, deduped. Pure."""
    out: list[str] = []
    seen: set[str] = set()
    names = _proper_nouns(text or "")
    for tok in _WORD_RE.findall(text or ""):
        low = tok.lower()
        if low in _QUERY_STOPWORDS or len(low) < 2 or low in seen or low in names:
            continue
        seen.add(low)
        out.append(low)
        if len(out) >= limit:
            break
    return out


def build_query_ladder(matter_type: str | None, allegation: str | None,
                       theory: str | None = None) -> list[str]:
    """Ordered narrow→broad CourtListener queries: 6 allegation keywords, then
    3, then a curated legal-concept expression. Distinct, never empty. Pure
    (unit-tested).

    The matter-type label is deliberately absent from the keyword tiers — ANDed
    into free text it constrained on UI wording ("Eeoc Charge") rather than on
    law. Matter-type meaning enters only through the curated bottom tier, and
    jurisdiction only through the ``court`` filter.

    ``theory`` (a ``legal_defense`` slug) ANDs the matter's SUBJECT onto every
    tier, including the bottom one, where it outranks the matter-type concept —
    a "class action" is a posture, ``wage_hour`` is what the case is about. Every
    tier of an anchored ladder therefore stays on-subject: broadening can widen
    the terms but never leave the theory. Without a theory (broad matters:
    subpoena / audit / other, or an ambiguous allegation) the ladder is unchanged
    — a records subpoena must reach whatever the records are about."""
    anchor = _THEORY_ANCHORS.get(theory or "")
    kws = _keywords(allegation or "", 6)
    ladder: list[str] = []
    for n in (6, 3):
        q = " ".join(kws[:n]).strip()
        if q:
            q = f"{q} AND {anchor}" if anchor else q
            if q not in ladder:
                ladder.append(q)
    concept = (f"{anchor} AND {_EMPLOYMENT_ANCHOR}" if anchor
               else _MATTER_TYPE_TERMS.get((matter_type or "").lower(), _DEFAULT_MATTER_TERMS))
    if concept not in ladder:
        ladder.append(concept)
    return ladder


def gate_cases_to_subject(cases: list[dict], theory: str | None) -> list[dict]:
    """Drop hits whose own text is plainly about another subject. Pure.

    The anchors constrain what CourtListener is ASKED for; this constrains what
    it RETURNS. Both are needed: an opinion can satisfy a boolean anchor in a
    passing citation ("...unlike the plaintiff's wage and hour claim...") while
    being about something else entirely, and these rows become citable ``case:``
    evidence in an attorney-facing packet.

    Reuses ``legal_defense._matches_other_subject``, so an unclassifiable case —
    no snippet, or a snippet naming no subject — is KEPT, exactly as an
    unclassifiable internal record is. Under-retrieval is the failure mode this
    module can't detect; over-retrieval is the one the reviewer can."""
    if not theory:
        return list(cases)
    return [c for c in cases
            if not _matches_other_subject(
                f"{c.get('case_name') or ''} {c.get('snippet') or ''}", theory)]


def _sanitize_query(query: str) -> str:
    """Neutralize CourtListener/Lucene query-syntax reserved characters that
    crash v4 search (500) or are rejected (400) — confirmed via direct
    probing of the live API. Replaces with a space (never deletes, so word
    boundaries survive) then collapses whitespace. Pure, no I/O.

    This is for FREE TEXT, which must never reach the query parser as
    operators. The curated ``_MATTER_TYPE_TERMS`` expressions do use that
    syntax deliberately and bypass this via ``search_case_law(sanitize=False)``."""
    cleaned = _RESERVED_QUERY_CHARS_RE.sub(" ", query or "")
    return " ".join(cleaned.split())


# A sovereign as the FIRST party is a criminal prosecution. Anchored to the start
# of the caption so an employer named "People's Bank" or a case captioned
# "Villas v. State Farm" is untouched — only the plaintiff position matters. The
# "of <sovereign>" forms ("State of Nevada v. U.S. Dep't of Labor") are civil and
# deliberately excluded by requiring the "v." right after the sovereign.
_CRIMINAL_CAPTION_RE = re.compile(
    r"^(the\s+)?(people|state|commonwealth|united\s+states)\s+vs?[.\s]", re.IGNORECASE)


def _bm25(row: dict) -> float | None:
    """CourtListener's Elasticsearch relevance score, ``meta.score.bm25``.
    Returns None when absent or non-numeric — callers treat that as "unscored"
    and keep the row, so a response-shape change degrades to today's behavior
    instead of silently emptying the panel."""
    meta = row.get("meta")
    score = meta.get("score") if isinstance(meta, dict) else None
    bm25 = score.get("bm25") if isinstance(score, dict) else None
    return float(bm25) if isinstance(bm25, (int, float)) and not isinstance(bm25, bool) else None


def _parse_search_results(payload: dict, limit: int | None = None) -> list[dict]:
    """Map CourtListener v4 ``type=o`` search results to compact case dicts.

    Parses the whole page by default — ``_filter_rank`` applies the relevance
    floor and the ``_MAX_CASES`` cap afterwards, so truncating here would throw
    away candidates that outrank the ones kept.

    Pure, never raises — tolerates missing keys / an unexpected payload shape.
    """
    out: list[dict] = []
    try:
        results = (payload or {}).get("results") or []
    except AttributeError:
        return out
    for r in results if limit is None else results[:limit]:
        try:
            if not isinstance(r, dict):
                continue
            cid = str(r.get("cluster_id") or r.get("id") or "")
            case_name = r.get("caseName") or r.get("caseNameFull") or ""
            if not cid or not case_name:
                continue
            citation = r.get("citation")
            citation = citation[0] if isinstance(citation, list) and citation else None
            opinions = r.get("opinions") or []
            snippet = r.get("snippet") or (
                opinions[0].get("snippet") if opinions and isinstance(opinions[0], dict) else None
            )
            out.append({
                "id": cid,
                "case_name": case_name,
                "citation": citation,
                "court": r.get("court") or "",
                "court_id": r.get("court_id") or "",
                "date_filed": r.get("dateFiled"),
                "url": "https://www.courtlistener.com" + (r.get("absolute_url") or ""),
                "snippet": snippet,
                "score": _bm25(r),
            })
        except Exception:  # noqa: BLE001 — one bad row never drops the rest
            continue
    return out


def _filter_rank(cases: list[dict], limit: int = _MAX_CASES) -> list[dict]:
    """Dedupe, drop criminal prosecutions and weak hits, cap. Pure (unit-tested).

    Four passes, in order:

    1. **Dedupe** by cluster id, then by (case name, filing date) — the live API
       returns the same opinion twice under sibling cluster ids (probing showed
       both "Martel v. HG Staffing" and "NEVILLE, JR. VS. DIST. CT."
       duplicated), and duplicates otherwise consume the cap.
    2. **Criminal captions** (``_CRIMINAL_CAPTION_RE``) — a sovereign as
       plaintiff is a prosecution, never employment precedent. Neither the
       subject anchor nor the subject gate can catch these: "People v. Von
       Villas" is a murder appeal whose opinion discusses police *overtime*, so
       it satisfies a wage-and-hour anchor AND carries a wage keyword that makes
       the gate read it as on-subject. It was retrieved for a real nurse
       meal-break matter. The caption is the only reliable signal.
    3. **Relevance floor** at ``_RELEVANCE_FLOOR_RATIO`` of a reference BM25 —
       the median of the top ``_FLOOR_REFERENCE_SAMPLE`` scores, so one
       caption-match outlier cannot raise the bar past the whole field. The
       ``court`` filter fixes jurisdiction but not strength of match: the tail
       of a result page can match on one incidental term and still fill a slot.
       Unscored rows always survive (see ``_bm25``).
    4. **Cap** at ``limit`` after sorting by score, unscored last.
    """
    seen_ids: set[str] = set()
    seen_names: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for c in cases:
        name = str(c.get("case_name") or "").strip()
        name_key = (name.lower(), str(c.get("date_filed") or ""))
        if c["id"] in seen_ids or name_key in seen_names:
            continue
        if _CRIMINAL_CAPTION_RE.match(name):
            continue
        seen_ids.add(c["id"])
        seen_names.add(name_key)
        deduped.append(c)

    scores = sorted((c["score"] for c in deduped if c.get("score") is not None), reverse=True)
    if scores:
        sample = scores[:_FLOOR_REFERENCE_SAMPLE]
        # Median once the sample is full; below that a spike is indistinguishable
        # from a strong field, so the top score stays the reference.
        reference = sample[len(sample) // 2] if len(sample) == _FLOOR_REFERENCE_SAMPLE else sample[0]
        floor = reference * _RELEVANCE_FLOOR_RATIO
        deduped = [c for c in deduped if c.get("score") is None or c["score"] >= floor]

    deduped.sort(key=lambda c: c["score"] if c.get("score") is not None else float("-inf"), reverse=True)
    return deduped[:limit]


async def search_case_law(
    query: str,
    state: str | None = None,
    limit: int = _MAX_CASES,
    sanitize: bool = True,
) -> list[dict]:
    """GET CourtListener opinion search, restricted to the courts that bind
    ``state``, deduped and relevance-floored. Raises on transport/HTTP failure —
    callers isolate this (see ``run_research``).

    ``sanitize=False`` passes ``query`` to CourtListener's parser verbatim, for
    the trusted, code-authored expressions in ``_MATTER_TYPE_TERMS`` whose
    quotes and OR operators ``_sanitize_query`` would strip. Free text must
    always go through the default."""
    q = _sanitize_query(query) if sanitize else " ".join((query or "").split())
    params = {"q": q, "type": "o", "order_by": "score desc"}

    courts = _STATE_COURTS.get((state or "").upper())
    if courts:
        params["court"] = " ".join(courts)
    elif state:
        # Unmapped state (territory, bad data): fall back to the old
        # name-in-query behavior rather than searching the whole country.
        state_name = _STATE_NAMES.get(state.upper())
        if state_name:
            params["q"] = f"{q} {state_name}"

    headers = {}
    token = get_settings().courtlistener_api_token
    if token:
        headers["Authorization"] = f"Token {token}"

    async with httpx.AsyncClient(timeout=_CL_TIMEOUT) as client:
        resp = await client.get(
            f"{COURTLISTENER_BASE}/search/",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return _filter_rank(_parse_search_results(resp.json()), limit)


async def synthesize_guidance(matter: dict, juris_display: str | None, cases: list[dict],
                              subject: str | None = None) -> dict:
    """Grounded-Gemini public-guidance briefing. Raises on failure — callers
    isolate this (see ``run_research``).

    ``subject`` is the matter's theory label. A matter type is a posture, not a
    subject: "Class Action" alone sends the model looking for class-certification
    guidance for a meal-break case. ``None`` (a broad matter — subpoena / audit /
    ambiguous allegation) omits the subject constraint entirely: telling the
    model to stay on an "unspecified" subject would suppress exactly the
    whole-landscape overview a broad matter is supposed to get."""
    label = _hum(matter.get("matter_type")) or "Employment matter"
    allegation = (matter.get("allegation") or "")[:300]
    case_names = ", ".join(c["case_name"] for c in cases[:5]) or "(none located)"

    subject_field = f". Subject: {subject}" if subject else ""
    subject_rule = (
        "relevant to this matter's SUBJECT (EEOC enforcement guidance, DOL opinion letters, "
        "state agency rules), each with its source URL. Stay on that subject: guidance about "
        "any other area of employment law is out of scope, even if it is about this matter type. "
    ) if subject else (
        "relevant to this matter type (EEOC enforcement guidance, DOL opinion letters, "
        "state agency rules), each with its source URL. "
    )
    prompt = (
        "You are compiling an INFORMATIONAL briefing of the public legal landscape "
        "for outside counsel. Matter type: " + label + subject_field + ". Jurisdiction: "
        + (juris_display or "unspecified") + ". Allegation summary: " + allegation
        + ". Cases already located (do not re-verify): " + case_names
        + ". Using web search, summarize current federal and state agency guidance "
        + subject_rule +
        "Do NOT give legal advice, do NOT "
        "assess the company's position, do NOT invent case citations. Return STRICT JSON: "
        '{"summary": "<neutral 2-4 paragraph overview>", "key_authorities": '
        '[{"name","url","publisher","relevance"}]}'
    )

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("gemini_compliance", "legal_research")
    resp = await asyncio.wait_for(
        get_genai_client().aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        ),
        timeout=_GUIDANCE_TIMEOUT,
    )
    await rate_limiter.record_call("gemini_compliance", "legal_research")

    data = _parse_json(getattr(resp, "text", "") or "")
    return {
        "summary": str(data.get("summary") or "").strip(),
        "key_authorities": [a for a in (data.get("key_authorities") or []) if isinstance(a, dict)],
    }


def parse_research_row(row: dict) -> dict:
    """asyncpg returns jsonb columns as raw text (no codec registered on the
    pool) — decode ``cases``/``guidance`` back into Python objects. Shared by
    every caller that reads ``legal_matter_research`` rows directly."""
    row = dict(row)
    for key in ("cases", "guidance"):
        v = row.get(key)
        if isinstance(v, str):
            try:
                row[key] = json.loads(v)
            except Exception:
                row[key] = None
    return row


async def _resolve_state(conn, matter: dict) -> str | None:
    """Location-first (company-scoped), then the explicit state override —
    the SAME precedence ``legal_defense.resolve_matter_jurisdiction`` applies,
    so the CourtListener search can never target a different state than the
    governing-law chain shown alongside it."""
    if matter.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
            matter["location_id"], matter["company_id"],
        )
        if loc and loc["state"]:
            return loc["state"].upper()
    return (matter.get("jurisdiction_state") or "").upper() or None


async def run_research(matter: dict, created_by, include_guidance: bool = True) -> dict:
    """Orchestrate one research run: persist a row, gather cases + (optionally)
    guidance, each isolated, finalize status. Never raises on partial failure —
    the row is only marked ``failed`` when nothing attempted succeeded (case
    search failed, and guidance either wasn't attempted or also failed).

    ``include_guidance=False`` skips the ~90s grounded-Gemini synthesis call
    entirely — just the CourtListener case search — for callers who only
    want a fast case-law refresh.

    Acquires its own short-lived pool connections around the DB phases so
    that NO pooled connection is held across the external CourtListener +
    Gemini calls (~110s worst case) — the same discipline the chat endpoint
    applies before its long Gemini call."""
    async with get_connection() as conn:
        state = await _resolve_state(conn, matter)
        allegation = (matter.get("allegation") or "")[:300]
        # The SAME theory that scopes the evidence corpus, resolved the same way
        # (stored override > matter_type > keywords). Persisted alongside the
        # results so _gather_case_law can tell a run made under this matter's
        # current subject from a stale one made under another — a re-themed
        # matter must not keep citing the old subject's case law.
        theory, _topic = resolve_matter_theory(matter)
        ladder = build_query_ladder(matter.get("matter_type"), allegation, theory)
        query = ladder[0]
        row = await conn.fetchrow(
            """INSERT INTO legal_matter_research
                   (matter_id, company_id, query, created_by, jurisdiction_state, theory)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            matter["id"], matter["company_id"], query, created_by, state, theory,
        )
        research_id = row["id"]

    cases: list[dict] = []
    case_err: str | None = None
    try:
        # Broaden until something matches: a specific allegation can AND the
        # free-text search down to zero hits. A transport/HTTP failure aborts
        # the whole ladder — retrying broader terms won't fix a dead API.
        #
        # "Matches" means survives the relevance floor, not merely returns rows:
        # a tier whose every hit is weak should broaden rather than persist junk
        # that would become citable ``case:`` evidence downstream.
        #
        # ``sanitize=False``: every tier is built from alphabetic keywords or a
        # curated constant (see build_query_ladder), never raw user text.
        #
        # The subject gate runs INSIDE the loop, so a tier whose every hit is
        # off-subject broadens like an empty one rather than persisting cases
        # that would become citable ``case:`` evidence — the same reasoning the
        # relevance floor already applies to weak hits.
        for q in ladder:
            cases = gate_cases_to_subject(
                await search_case_law(q, state=state, sanitize=False), theory)
            query = q
            if cases:
                break
    except Exception as e:  # noqa: BLE001 — isolation is the point
        logger.warning("legal_research: case search failed: %s", e)
        case_err = str(e)

    guidance: dict | None = None
    guid_err: str | None = None
    if include_guidance:
        try:
            juris_display = _STATE_NAMES.get(state) if state else None
            guidance = await synthesize_guidance(
                matter, juris_display, cases, subject=_topic.label if theory else None)
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_research: guidance synthesis failed: %s", e)
            guid_err = str(e)

    async with get_connection() as conn:
        nothing_succeeded = bool(case_err) and (not include_guidance or bool(guid_err))
        if nothing_succeeded:
            error = f"Case search failed: {case_err}"
            if include_guidance:
                error += f"; guidance synthesis failed: {guid_err}"
            await conn.execute(
                "UPDATE legal_matter_research SET status='failed', error=$1, completed_at=NOW() WHERE id=$2",
                error, research_id,
            )
        else:
            error = None
            if case_err:
                error = f"Case search unavailable: {case_err}"
            elif include_guidance and guid_err:
                error = f"Guidance synthesis unavailable: {guid_err}"
            await conn.execute(
                """UPDATE legal_matter_research
                       SET status='complete', cases=$1::jsonb, guidance=$2::jsonb,
                           error=$3, query=$4, completed_at=NOW()
                     WHERE id=$5""",
                json.dumps(cases), json.dumps(guidance) if guidance else None, error,
                query, research_id,  # query = the ladder tier actually used
            )

        result = await conn.fetchrow("SELECT * FROM legal_matter_research WHERE id = $1", research_id)
    return parse_research_row(dict(result))
