"""Matter theory — subject-matter scoping of the evidence corpus."""

import re
from typing import NamedTuple, get_args

from app.core.compliance_registry import CATEGORY_KEYS
from app.matcha.models.er_case import ERCaseCategory
from app.matcha.models.ir_incident import IRIncidentType

from ...discipline.discipline_engine import DEFAULT_INFRACTION_TYPES
from ._shared import _hum


# --------------------------------------------------------------------------- #
# Matter theory — subject-matter scoping of the evidence corpus.
#
# Location/state scoping (below) answers "whose records?"; it says nothing about
# "which records?". Without a subject filter a meal-break matter pulls every
# slip-and-fall and medication-error incident the company ever logged, which
# buries the relevant record and poisons the AI's grounding corpus.
#
# The theory is derived, never asked for: the allegation text decides when it
# speaks clearly, and ``matter_type`` is the fallback. Types that carry no
# subject signal (subpoena / audit / other) resolve to the broad theory — no
# filtering at all, today's behavior — which doubles as the escape hatch when
# the derivation gets it wrong.
# --------------------------------------------------------------------------- #

_WAGE_HOUR = ["minimum_wage", "overtime", "meal_breaks", "pay_frequency", "final_pay",
              "scheduling_reporting", "sick_leave", "leave", "employee_classification",
              "equal_pay", "pay_transparency"]
_EEO = ["anti_discrimination", "equal_pay", "pregnancy_accommodation", "eeo_reporting",
        "background_checks", "pay_transparency", "whistleblower"]
_SAFETY = ["workplace_safety", "workers_comp", "industrial_hygiene", "machine_safety",
           "chemical_safety", "environmental_safety", "emergency_preparedness",
           "radiation_safety", "process_safety", "clinical_safety"]

# Vocabularies the topic filter knows, DERIVED from their sources of truth so a
# new incident type / ER category / infraction can't silently change filter
# semantics by looking "company-defined". A slug outside these lists really is
# company-defined (discipline infraction types are per-company configurable,
# er_cases.category has no CHECK constraint, and the Specialization Research
# Wizard mints compliance categories outside the registry).
#
# Such a slug still passes the SQL allowlist — silently dropping an unrecognized
# record from a legal corpus is the one failure mode worse than over-inclusion —
# but it is no longer passed UNCONDITIONALLY. A category that carries no usable
# subject signal (company-defined slug, NULL, or a generic bucket like ER's
# "other") is classified from the record's own TEXT instead, and dropped only
# when that text speaks clearly for a DIFFERENT subject: see
# ``_matches_other_subject`` and the per-source demotion below. 720 Behavioral's
# `hipaa` discipline infractions were the reported failure — unknown to
# _INFRACTIONS, so every one of them surfaced in a wage-and-hour matter.
_INCIDENT_TYPES = list(get_args(IRIncidentType))
_ER_CATEGORIES = list(get_args(ERCaseCategory))
_INFRACTIONS = [d["infraction_type"] for d in DEFAULT_INFRACTION_TYPES]
_COMPLIANCE_CATEGORIES = sorted(CATEGORY_KEYS)

# Values that exist in a source's closed vocabulary but say nothing about
# subject — a human picking "other" or "policy violation" for an FMLA-interference
# complaint has not told us the case is about FMLA; the title has. Each vocabulary
# names its own generic buckets HERE, next to nothing: leaving one out means those
# records read as explicit human categorizations and are never text-classified —
# the exact cross-subject leak the demotion pass exists to close.
_GENERIC_ER_CATEGORIES = frozenset({"other", "policy_violation"})
_GENERIC_INFRACTIONS = frozenset({"policy_violation"})


class _Topic(NamedTuple):
    """Per-source allowlists for one theory. ``None`` = don't filter that source.
    An EMPTY list is meaningful and different: no value in that source's
    vocabulary relates to the theory, so the source drops out entirely (a
    wage-and-hour claim has no relevant IR/OSHA incident type).

    ``slug`` is the theory's own key (``None`` on the broad topic). Sources need
    it to know which keyword probes are "the matter's own" when they fall back
    to classifying a signal-less record by its text."""
    label: str
    compliance: list[str] | None
    incidents: list[str] | None
    er: list[str] | None
    discipline: list[str] | None
    slug: str | None = None


_BROAD = _Topic("all records", None, None, None, None)

_THEORIES: dict[str, _Topic] = {
    slug: topic._replace(slug=slug)   # slug mirrors the key; derived so they can't diverge
    for slug, topic in {
        "wage_hour": _Topic(
            label="wage-and-hour",
            compliance=_WAGE_HOUR,
            incidents=[],  # no IR/OSHA incident type describes a pay practice
            er=["wage_hour", "retaliation", "policy_violation", "other"],
            discipline=["attendance", "performance", "policy_violation"],
        ),
        "eeo": _Topic(
            label="discrimination / EEO",
            compliance=_EEO,
            incidents=["behavioral", "other"],
            er=["harassment", "discrimination", "retaliation", "misconduct",
                "policy_violation", "other"],
            discipline=["harassment", "gross_misconduct", "policy_violation", "performance"],
        ),
        "safety": _Topic(
            label="workplace-safety",
            compliance=_SAFETY,
            incidents=["safety", "near_miss", "property", "other"],
            er=["safety", "policy_violation", "other"],
            discipline=["safety", "policy_violation", "gross_misconduct"],
        ),
    }.items()
}

# Word-boundary probes against the matter's title + allegation, lowercased.
# A trailing ``*`` marks a stem ("discriminat*" matches discriminates,
# discrimination) so tense/plural never costs a hit; everything else must match
# a whole word. Bare-substring matching was wrong in both directions: "ada "
# fired inside "Nevada", and "ppe" inside "happened" — each flipping a matter
# onto a theory that then filtered out its own core records.
_THEORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "wage_hour": ("wage*", "overtime", "meal break*", "meal period*", "rest break*",
                  "off the clock", "off-the-clock", "timecard*", "time card*", "unpaid",
                  "minimum wage", "misclassif*", "exempt", "tip credit", "payroll",
                  "final pay", "paystub*", "pay stub*", "flsa", "hours worked",
                  "donning", "rounding", "wage theft"),
    "eeo": ("discriminat*", "harass*", "retaliat*", "hostile work", "title vii", "adea",
            "eeoc", "pregnan*", "accommodat*", "wrongful termination", "fmla",
            "disparate", "hostile environment", "ada"),
    "safety": ("osha", "injur*", "slip", "trip and fall", "safety", "accident*",
               "near miss", "workers comp*", "workers' comp*", "hazard*", "ergonomic*",
               "ppe", "lockout", "exposure"),
}


def _compile_probes(kws: tuple[str, ...]) -> list[re.Pattern]:
    """``foo*`` → ``\\bfoo`` (stem, matches any suffix); ``foo`` → ``\\bfoo\\b``."""
    out = []
    for kw in kws:
        if kw.endswith("*"):
            out.append(re.compile(r"\b" + re.escape(kw[:-1])))
        else:
            out.append(re.compile(r"\b" + re.escape(kw) + r"\b"))
    return out


_THEORY_PROBES: dict[str, list[re.Pattern]] = {
    slug: _compile_probes(kws) for slug, kws in _THEORY_KEYWORDS.items()
}

# Vocabulary for CLASSIFYING a record (or a case-law hit) whose category carries
# no subject signal — a separate JOB from deriving a matter's theory, with its
# own precision needs, so it gets its own adjustments in BOTH directions rather
# than edits to the shared _THEORY_KEYWORDS (where a change silently re-themes
# whole matters — resolve_matter_theory scores on those words).
#
# _CLASSIFY_ONLY_KEYWORDS adds words that name a subject without arguing for it:
# a wrongful-death opinion is a safety record, but "gunshot" in an allegation
# must not retheme the matter; "retaliation" names a subject wage_hour's own ER
# allowlist claims, so it must never be the sole reason a wage record is demoted
# — but one stray "retaliated" shouldn't derive a wage theory either.
#
# _CLASSIFY_EXCLUDE_KEYWORDS removes derivation words that are modifiers, not
# subjects, at record granularity: an "unpaid suspension" is a discipline record
# and "unpaid leave" is a leave record, and either one, read as a wage keyword,
# keeps an off-subject record in a wage corpus by short-circuiting
# _matches_other_subject. Derivation keeps bare "unpaid" — an allegation is ABOUT
# nonpayment in a way a discipline write-up is not.
#
# ``privacy`` is a subject a RECORD can be about while no MATTER can — a HIPAA
# write-up would otherwise classify as "no subject detected" and fail open into
# a wage-and-hour corpus. That was the reported bug (a behavioral-health tenant's
# `hipaa` infraction type).
#
# Every probe here can only ever cause a record to be EXCLUDED, so a loose word
# ("confidential", "records", "assault") would silently shrink a legal corpus —
# "sexual assault" is an EEO record, not a safety one. Add a word only when the
# word alone names the subject.
_CLASSIFY_ONLY_KEYWORDS: dict[str, tuple[str, ...]] = {
    # the "unpaid X" phrases restore the wage readings the bare-"unpaid"
    # exclusion below would otherwise cost ("unpaid wages"/"unpaid overtime"
    # already score on their second word)
    "wage_hour": ("retaliat*", "unpaid work*", "unpaid time"),
    "safety": ("wrongful death", "gunshot", "gun shot", "shooting", "homicide",
               "decedent", "fatalit*", "fatally"),
}
_CLASSIFY_EXCLUDE_KEYWORDS: dict[str, frozenset] = {
    "wage_hour": frozenset({"unpaid"}),
}
_OFF_THEORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    # "hippa" is not a typo here: it is THE typo — these probes read text users
    # type into case titles, where that misspelling is common enough to name the
    # subject as unambiguously as the correct spelling.
    "privacy": ("hipaa", "hippa", "phi", "patient privacy", "patient record*",
                "medical record*", "data breach", "protected health"),
    # A healthcare tenant's records are mostly ABOUT care delivery. Without this
    # group an "Oncology Incident" ER case reads as "no subject detected" and
    # fails open into every matter's corpus, wage-and-hour included.
    "clinical": ("oncolog*", "patient care", "medication error*", "clinical care",
                 "patient treatment", "infection control", "patient fall*"),
}

_CLASSIFY_PROBES: dict[str, list[re.Pattern]] = {
    **{slug: _compile_probes(
           tuple(k for k in kws if k not in _CLASSIFY_EXCLUDE_KEYWORDS.get(slug, frozenset()))
           + _CLASSIFY_ONLY_KEYWORDS.get(slug, ()))
       for slug, kws in _THEORY_KEYWORDS.items()},
    **{slug: _compile_probes(kws) for slug, kws in _OFF_THEORY_KEYWORDS.items()},
}


_OFF_THEORY_PROBES: list[re.Pattern] = [
    p for slug in _OFF_THEORY_KEYWORDS for p in _CLASSIFY_PROBES[slug]
]


def _names_unmodeled_subject(text: str) -> bool:
    """Does ``text`` name a subject no theory models (privacy, clinical care)?

    Used only to VETO a matter_type prior that scored no keywords of its own —
    never to assert a theory, because there is no theory to assert. Silence and
    a named-but-unmodeled subject are different states, and only the first one
    should inherit ``_MATTER_TYPE_THEORY``'s guess about the modal suit."""
    t = (text or "").lower()
    return any(p.search(t) for p in _OFF_THEORY_PROBES)


def _is_signalless(value, vocabulary, generic=frozenset()) -> bool:
    """Does this category/type value tell us the record's subject? NULL doesn't;
    a slug outside the source's known vocabulary doesn't (it is company-defined —
    ``hipaa``, ``cardiac_catheterization_safety`` — and the allowlist was written
    without it); a generic in-vocabulary bucket doesn't either. Anything else is
    a human's explicit categorization and is never second-guessed by text."""
    return not value or value in generic or value not in vocabulary


def _matches_other_subject(text: str, theory_slug: str | None) -> bool:
    """True only when ``text`` speaks clearly for a subject OTHER than the
    matter's, and carries none of the matter's own keywords.

    This is the single condition under which a signal-less record — company-
    defined slug, NULL category, or a generic bucket — is dropped instead of
    failing open. Both halves are load-bearing: the own-keyword short-circuit
    keeps "off-the-clock work; FMLA retaliation" in a wage matter (it IS a wage
    record, whatever else it mentions), and requiring a positive hit on another
    subject keeps an unclassifiable record ("telehealth licensure renewal") in
    every corpus. Ambiguity resolves to inclusion, always."""
    if not theory_slug:
        return False
    t = (text or "").lower()
    if any(p.search(t) for p in _CLASSIFY_PROBES[theory_slug]):
        return False
    return any(p.search(t)
               for slug, probes in _CLASSIFY_PROBES.items() if slug != theory_slug
               for p in probes)


def _demote_off_subject(rows, slug: str | None, allowlist, vocabulary, cat_col: str,
                        *text_cols: str, generic=frozenset()) -> list:
    """Second pass over a themed source's rows: drop the ones whose category
    couldn't be filtered in SQL and whose text is plainly about another subject.

    Inert on the broad topic (``slug is None``) and on sources this theory
    doesn't filter (``allowlist is None``), so it can never narrow a corpus the
    SQL didn't already intend to narrow. The category is humanized into the
    classified text — ``hipaa`` and ``cardiac_catheterization_safety`` name
    their own subject, which is the only signal a company-defined slug carries."""
    if not slug or allowlist is None:
        return list(rows)
    vocab = frozenset(vocabulary)   # rows × in-list scans → rows × O(1)
    kept = []
    for r in rows:
        if _is_signalless(r[cat_col], vocab, generic):
            text = " ".join([_hum(r[cat_col])] + [str(r[c] or "") for c in text_cols])
            if _matches_other_subject(text, slug):
                continue
        kept.append(r)
    return kept

# matter_type -> theory when the allegation text is silent or ambiguous.
# None = broad (no subject filter).
_MATTER_TYPE_THEORY: dict[str, str | None] = {
    "class_action": "wage_hour",
    "single_plaintiff": "wage_hour",
    "eeoc_charge": "eeo",
    "subpoena": None,
    "audit": None,
    "other": None,
}

# Types whose theory the type itself asserts: an EEOC charge is a discrimination
# charge by definition. One incidental word ("terminated after her workplace
# accident") must not swing it onto a safety corpus, so keywords need
# _STRONG_OVERRIDE hits to win.
#
# The others are weak priors — "class action" and "single plaintiff" describe
# procedural posture, not subject, and their wage-and-hour mapping is a guess
# about which suit is most common. Any unambiguous keyword beats a guess: a
# single_plaintiff matter titled "warehouse forklift injury" is a safety matter,
# whatever the modal class action is about.
_STRONG_TYPE_PRIORS = frozenset({"eeoc_charge"})
_STRONG_OVERRIDE = 2

# The value a user stores on ``legal_matters.subject_theory`` to force broad
# scope. NULL on that column means "derive"; this means "derive nothing".
BROAD_THEORY = "all"

# Registry-membership of the theory slugs is enforced by
# tests/legal_defense/test_legal_defense.py::test_theory_compliance_categories_are_registry_keys
# — NOT by a module-level assert: this module is imported unconditionally at
# app boot via routes/__init__.py, so an import-time assert would take down
# the entire backend on a registry rename, not just Legal Pilot.


def resolve_matter_theory(matter: dict | None) -> tuple[str | None, _Topic]:
    """(theory_slug, topic) for a matter. ``(None, _BROAD)`` = evidence unfiltered.

    Precedence, narrowest authority first:

    1. ``matter.subject_theory`` — the user's stored override. ``'all'`` forces
       broad. This is the escape hatch, and it is a real one: the matter's other
       scoping axis (jurisdiction) already works this way, and a derived-only
       subject left a misclassified matter with no recovery short of deleting it.
    2. ``matter_type`` values carrying no subject signal (subpoena / audit /
       other) → broad. A records subpoena mentioning wages must still return
       every record.
    3. Allegation/title keywords, when nothing ties them. They override a weak
       matter_type prior outright and a strong one (``_STRONG_TYPE_PRIORS``)
       only with ``_STRONG_OVERRIDE`` hits.
    4. The ``matter_type`` map.

    A tie never resolves to a theory that scored zero: two subjects arguing for
    attention is a signal to widen, not to fall back on a prior neither
    supports."""
    if not matter:
        return None, _BROAD

    stored = matter.get("subject_theory")
    if stored == BROAD_THEORY:
        return None, _BROAD
    if stored in _THEORIES:
        return stored, _THEORIES[stored]

    mt = matter.get("matter_type")
    fallback = _MATTER_TYPE_THEORY.get(mt)
    if mt in _MATTER_TYPE_THEORY and fallback is None:
        return None, _BROAD

    text = f"{matter.get('title') or ''} {matter.get('allegation') or ''}".lower()
    scores = {slug: sum(1 for p in probes if p.search(text))
              for slug, probes in _THEORY_PROBES.items()}
    best = max(scores, key=lambda k: scores[k])
    top = scores[best]
    tied = [s for s, v in scores.items() if v == top]

    if top > 0 and len(tied) == 1:
        needed = _STRONG_OVERRIDE if mt in _STRONG_TYPE_PRIORS else 1
        if best == fallback or top >= needed:
            return best, _THEORIES[best]
    elif top > 0 and fallback not in tied:
        # Tied subjects, none of them the matter_type's prior → widen rather
        # than assert a theory the text gives no support for.
        return None, _BROAD

    if top == 0 and _names_unmodeled_subject(text):
        # The text is not silent — it names a subject this system has no theory
        # for (a patient-privacy claim, a clinical-care claim). The matter_type
        # prior is a guess about the modal suit, and here the text proves the
        # guess wrong: a HIPAA matter filtered through the wage-and-hour
        # allowlist loses its own records. Broad is the only honest scope.
        return None, _BROAD

    return (fallback, _THEORIES[fallback]) if fallback else (None, _BROAD)
