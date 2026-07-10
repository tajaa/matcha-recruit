"""The one canonical business-category taxonomy every legacy vocabulary maps into.

Pure module — no DB, no network, no Gemini. The `business_categories` table
(migration ``scoperg01``) is seeded from the same rows for FK integrity and
runtime-added categories; ``tests/scope_registry/test_migration_parity.py``
pins the two against drift.

Seven vocabularies already exist in this repo and do not agree
(SCOPE_REGISTRY_PLAN.md §1). This module absorbs all of them:

* ``compliance_service._INDUSTRY_ALIASES`` — now deleted; ``_resolve_industry``
  is a shim over :func:`resolve_legacy_industry`.
* ``industry_compliance_profiles.name`` ("Restaurant / Hospitality", …)
* ``compliance_categories.industry_tag`` (``healthcare:oncology`` colon tags)
* admin FE ``INDUSTRIES`` (canonical slugs since PR #25)
* signup ``INDUSTRY_OPTIONS`` (``financial_services``, ``real_estate``, …)
* ``GUIDED_INDUSTRY_PLAYBOOK`` keys (``general``, ``hospitality``, …)
* ``HEALTHCARE_SPECIALTIES`` (``oncology``, ``cardiology``, …)

Two deliberate behavior changes vs. the legacy resolver, both from the plan:

* **``warehouse`` no longer resolves to ``manufacturing``.** A warehouse is
  general industry, not a factory; scoping it as one is how CA AB 701 could
  never be scoped for it while it wrongly inherited a factory's RCRA/EPCRA
  pack. ``warehousing`` is first-class (NAICS 493) and carries **no** legacy
  industry, so the legacy shim returns ``""`` for it — under-scoping made
  visible rather than wrong-scoping made silent.
* **``logistics`` / ``distribution center`` / ``fulfillment center`` /
  ``transportation`` resolve** (previously ``""``).

One deliberate non-change: ``construction`` is first-class here (NAICS 23,
distinct from manufacturing 31–33) but its *legacy* industry stays
``manufacturing`` — the live profile is literally "Construction / Manufacturing"
and detaching it is a scoping decision for the classification layer (commit 4),
not a vocabulary shim.

NAICS caveat: ``naics_codes`` are hints, not identities. 621111 is "Offices of
Physicians" — the plan (§3) assigns it to ophthalmology as the *deepest seeded
practice category*, which over-claims for a generic physician office. Resolution
combines NAICS with the self-reported category; a missing/ambiguous NAICS
surfaces as an ``unmodeled_coordinate``, never a silent empty scope.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = [
    "BusinessCategory",
    "CATEGORIES",
    "resolve_category",
    "ancestry",
    "categories_for_naics",
    "legacy_industry_for",
    "resolve_legacy_industry",
]


@dataclass(frozen=True)
class BusinessCategory:
    """One node of the canonical taxonomy.

    ``legacy_industry`` is the value the pre-registry vocabulary used for this
    category ("healthcare", "fast food", …) — what ``compliance_service.
    _resolve_industry`` must keep returning so ``industry_tag`` / profile
    matching does not break. ``None`` means the legacy vocabulary had no word
    for this category and the shim returns ``""``.
    """

    slug: str
    label: str
    parent: Optional[str] = None
    naics_codes: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()
    # Exact-match only — excluded from the bidirectional substring fallback.
    # For generic words (devices, emergency, surgery) whose substring capture
    # would resolve non-members ("consumer devices" is not a healthcare
    # company), and for any alias where only the whole word is evidence.
    exact_aliases: Tuple[str, ...] = ()
    legacy_industry: Optional[str] = None


# Parents strictly before children (the migration seed relies on this order for
# its self-referencing FK, and the parity test asserts it).
_SEED: Tuple[BusinessCategory, ...] = (
    # ── hospitality ────────────────────────────────────────────────────────
    BusinessCategory(
        slug="hospitality",
        label="Restaurant / Hospitality",
        naics_codes=("72",),
        aliases=(
            "restaurant", "food", "hotel", "restaurant / hospitality",
            "restaurant_hospitality",
        ),
        legacy_industry="hospitality",
    ),
    BusinessCategory(
        slug="fast_food",
        label="Fast Food",
        parent="hospitality",
        naics_codes=("722513",),
        aliases=("fast food",),
        legacy_industry="fast food",
    ),
    # ── healthcare ─────────────────────────────────────────────────────────
    BusinessCategory(
        slug="healthcare",
        label="Healthcare",
        naics_codes=("62",),
        aliases=(
            "health", "medical", "clinic", "hospital", "nursing", "pharmacy",
            "dental", "physician", "outpatient", "ambulatory",
        ),
        # HEALTHCARE_SPECIALTIES (industryConstants.ts) — sub-industry tags,
        # runtime-extensible via `industry_specialties`; they resolve to their
        # parent here. Exact-only: substring capture of generic words would
        # resolve "consumer devices" or "emergency restoration services" to
        # healthcare, a behavior change the legacy resolver never had.
        exact_aliases=(
            "oncology", "primary_care", "cardiology", "pediatric",
            "behavioral_health", "telehealth", "managed_care", "devices",
            "transplant", "orthopedics", "neurology", "dermatology",
            "emergency", "surgery",
        ),
        legacy_industry="healthcare",
    ),
    BusinessCategory(
        slug="medical_offices",
        label="Medical Offices",
        parent="healthcare",
        # Offices of physicians / dentists / other practitioners only. NOT the
        # whole of 621 (Ambulatory Health Care Services) — labs (6215), home
        # health (6216), and ambulance services (6219) are healthcare, not
        # medical offices; they fall back to the 62 prefix above.
        naics_codes=("6211", "6212", "6213"),
        aliases=("medical office", "medical offices", "doctors office"),
        legacy_industry="healthcare",
    ),
    BusinessCategory(
        slug="ophthalmology",
        label="Ophthalmology",
        parent="medical_offices",
        # ≈ per plan §3: 621111 physicians / 621320 optometrists. A hint, not
        # an identity — see module docstring.
        naics_codes=("621111", "621320"),
        aliases=("ophthalmology", "optometry", "eye care"),
        legacy_industry="healthcare",
    ),
    # ── biotech ────────────────────────────────────────────────────────────
    BusinessCategory(
        slug="biotech",
        label="Biotech / Life Sciences",
        naics_codes=("3254", "5417"),
        aliases=(
            "pharma", "pharmaceutical", "pharmaceuticals", "life_sciences",
            "life sciences", "biopharma",
        ),
        legacy_industry="biotech",
    ),
    # ── retail ─────────────────────────────────────────────────────────────
    BusinessCategory(
        slug="retail",
        label="Retail",
        naics_codes=("44", "45"),
        aliases=("store", "shop"),
        legacy_industry="retail",
    ),
    # ── manufacturing / construction / warehousing / transportation ───────
    BusinessCategory(
        slug="manufacturing",
        label="Manufacturing",
        naics_codes=("31", "32", "33"),
        aliases=("industrial", "factory", "construction / manufacturing",
                 "construction_manufacturing"),
        legacy_industry="manufacturing",
    ),
    BusinessCategory(
        slug="construction",
        label="Construction",
        naics_codes=("23",),
        # No "general contractor" alias: the bidirectional substring fallback
        # would capture the input "general" (a GUIDED playbook key that must
        # stay unresolved). "contractor" still matches it as a substring.
        aliases=("contractor", "builder"),
        # Deliberate: stays on the combined legacy profile. See module docstring.
        legacy_industry="manufacturing",
    ),
    BusinessCategory(
        slug="warehousing",
        label="Warehousing & Storage",
        naics_codes=("493",),
        aliases=(
            "warehouse", "distribution center", "distribution centre",
            "fulfillment center", "fulfilment center", "logistics", "3pl",
        ),
        legacy_industry=None,  # the warehouse→manufacturing kill
    ),
    BusinessCategory(
        slug="transportation",
        label="Transportation",
        naics_codes=("48", "49"),
        aliases=("shipping", "trucking", "freight", "delivery", "transit"),
        legacy_industry=None,
    ),
    # ── technology ─────────────────────────────────────────────────────────
    BusinessCategory(
        slug="technology",
        label="Tech / Professional Services",
        naics_codes=("51", "5415"),
        aliases=(
            "software", "saas", "professional services", "consulting", "tech",
            "tech / professional services", "tech_professional",
        ),
        legacy_industry="technology",
    ),
    # ── INDUSTRY_OPTIONS completions (legacy resolver returned "" for all of
    #    these; they get taxonomy homes so signup vocab round-trips, but no
    #    legacy_industry — downstream industry_tag matching is unchanged) ────
    BusinessCategory(
        slug="education",
        label="Education",
        naics_codes=("61",),
        aliases=("school", "university"),
    ),
    BusinessCategory(
        slug="legal",
        label="Legal Services",
        naics_codes=("5411",),
        aliases=("law firm", "attorney"),
    ),
    BusinessCategory(
        slug="financial_services",
        label="Financial Services",
        naics_codes=("52",),
        aliases=("finance", "banking", "insurance"),
    ),
    BusinessCategory(
        slug="real_estate",
        label="Real Estate",
        naics_codes=("53",),
        aliases=("realty", "property management"),
    ),
    BusinessCategory(
        slug="nonprofit",
        label="Nonprofit",
        naics_codes=("813",),
        aliases=("non-profit", "not for profit", "charity"),
    ),
)

# Built incrementally so the parent check genuinely enforces declaration
# order (a completed-dict check would only catch unknown parents — the
# migration's self-FK seed relies on parents-first order).
CATEGORIES: Dict[str, BusinessCategory] = {}
for _c in _SEED:
    if _c.parent is not None and _c.parent not in CATEGORIES:
        raise RuntimeError(
            f"business category {_c.slug!r} declares unknown or later-declared "
            f"parent {_c.parent!r} — parents must be seeded before children"
        )
    CATEGORIES[_c.slug] = _c


def _normalize(raw: str) -> str:
    # Underscores fold to spaces so "primary_care" (tag form) and
    # "Primary Care" (display form) land on the same key.
    return " ".join(raw.lower().replace("_", " ").strip().split())


# Exact-match lookup: every slug + every alias (both kinds) → slug. Built in
# seed order so overlapping aliases resolve deterministically (first
# definition wins), which also preserves the legacy dict-order semantics for
# fuzzy inputs. The substring fallback pool deliberately excludes
# exact_aliases — see BusinessCategory.
_ALIAS_TO_SLUG: Dict[str, str] = {}
_SUBSTRING_POOL: Dict[str, str] = {}
for _c in _SEED:
    for _name in (_c.slug, *_c.aliases):
        _ALIAS_TO_SLUG.setdefault(_normalize(_name), _c.slug)
        _SUBSTRING_POOL.setdefault(_normalize(_name), _c.slug)
    for _name in _c.exact_aliases:
        _ALIAS_TO_SLUG.setdefault(_normalize(_name), _c.slug)


def resolve_category(raw: Optional[str]) -> Optional[str]:
    """Resolve a free-text industry/category string to a canonical slug.

    ``None`` means the string names no category we model — callers must treat
    that as an unmodeled coordinate, never as "no obligations".

    Colon tags (``healthcare:oncology``) resolve on their prefix: the suffix is
    a runtime specialty (`industry_specialties`), not a taxonomy node.
    """
    if not raw:
        return None

    normalized = _normalize(raw)
    if ":" in normalized:
        normalized = normalized.split(":", 1)[0].strip()
    if not normalized:
        # Whitespace-only must not reach the substring loop, where the empty
        # string is a substring of every alias. (The legacy resolver had this
        # bug — "   " resolved to hospitality.)
        return None

    hit = _ALIAS_TO_SLUG.get(normalized)
    if hit:
        return hit

    # Substring fallback, preserving the legacy resolver's bidirectional
    # semantics ("healthcare provider" → healthcare; "tech" → technology).
    # exact_aliases are not in this pool.
    for alias, slug in _SUBSTRING_POOL.items():
        if alias in normalized or normalized in alias:
            return slug

    return None


def ancestry(slug: str) -> List[str]:
    """Category chain from ``slug`` up to its root, inclusive.

    ``ophthalmology`` → ``["ophthalmology", "medical_offices", "healthcare"]``.
    Unknown slug → ``[]`` (an unmodeled coordinate, not an error).
    """
    if slug not in CATEGORIES:
        return []
    chain: List[str] = []
    current: Optional[str] = slug
    while current is not None:
        cat = CATEGORIES[current]  # parents guaranteed present by import check
        chain.append(cat.slug)
        current = cat.parent
    return chain


def categories_for_naics(naics: Optional[str]) -> List[str]:
    """Ancestry chain of the deepest category whose NAICS prefix matches.

    ``"621111"`` → ophthalmology chain; ``"493110"`` → ``["warehousing"]``
    (**not** manufacturing); ``"332710"`` → ``["manufacturing"]``. Longest
    prefix wins, so 493 (warehousing) beats 49 (transportation). No match →
    ``[]`` — an unmodeled coordinate for the caller to surface.
    """
    if not naics:
        return []
    code = "".join(ch for ch in str(naics) if ch.isdigit())
    if not code:
        return []

    best: Optional[BusinessCategory] = None
    best_len = 0
    for cat in _SEED:
        for prefix in cat.naics_codes:
            if code.startswith(prefix) and len(prefix) > best_len:
                best, best_len = cat, len(prefix)
    return ancestry(best.slug) if best else []


def legacy_industry_for(slug: str) -> str:
    """Nearest ``legacy_industry`` walking up the ancestry chain, else ``""``."""
    for node in ancestry(slug):
        legacy = CATEGORIES[node].legacy_industry
        if legacy is not None:
            return legacy
    return ""


def resolve_legacy_industry(raw: Optional[str]) -> str:
    """Drop-in body for ``compliance_service._resolve_industry``.

    Same outputs as the deleted ``_INDUSTRY_ALIASES`` resolver for every legacy
    input, except ``warehouse`` (now ``""``). New vocabulary (warehousing,
    transportation, education, …) also returns ``""`` here — legacy consumers
    match on ``industry_tag`` values, which don't exist for those yet.
    """
    slug = resolve_category(raw)
    return legacy_industry_for(slug) if slug else ""
