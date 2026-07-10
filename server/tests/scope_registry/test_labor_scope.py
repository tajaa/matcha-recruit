"""labor_scope pure pieces — labor-domain filter, core spine, registry bucketing,
exhaustiveness. No DB: the orchestrator is one chain lookup + queries feeding
these functions; verified live in the plan's verification section."""
from app.core.services.scope_registry.labor_scope import (
    CURATED_NOTE,
    ENUMERATED_NOTE,
    NO_INDEX_NOTE,
    build_exhaustiveness,
    bucket_registry,
    core_spine,
    is_labor_index,
)
from app.core.services.scope_registry.authority_sources import (
    CURATED_INDEXES,
    FEDERAL_ECFR_PARTS,
)
from app.core.services.compliance_evals.industry_keysets import CORE_LABOR_KEYS


# ── 1. labor-domain filter over the real catalog ─────────────────────────────

def test_is_labor_index_over_the_catalog():
    by_slug = {p.slug: p.domain_categories for p in FEDERAL_ECFR_PARTS}
    by_slug.update({c.slug: c.domain_categories for c in CURATED_INDEXES})

    # OSHA general industry, recordkeeping, FMLA, FLSA, CA labor + Cal/OSHA = labor.
    for slug in ("ecfr-29-1910", "ecfr-29-1904", "ecfr-29-825",
                 "us-flsa", "ca-labor-code", "ca-title-8"):
        assert is_labor_index(slug, by_slug[slug]), slug
    # RCRA hazardous waste + professional-licensing board = NOT labor.
    for slug in ("ecfr-40-260", "ecfr-40-261", "ecfr-40-262", "ca-title-16"):
        assert not is_labor_index(slug, by_slug[slug]), slug


def test_every_catalog_index_domain_is_recognized():
    """A future index whose domain label is neither labor nor a known non-labor
    domain would silently drop out of the labor view — pin the domain vocabulary
    so adding one forces a decision here."""
    known = {
        "all_industry", "general_industry", "all_ca_employers",   # labor
        "hazardous_waste_generators", "licensed_professions",     # non-labor
    }
    for spec in list(FEDERAL_ECFR_PARTS) + list(CURATED_INDEXES):
        unknown = set(spec.domain_categories or []) - known
        assert not unknown, f"{spec.slug} has unrecognized domain(s): {unknown}"


# ── 2. core spine (industry-agnostic checklist) ──────────────────────────────

def _req(category, key, level, requirement_key=None):
    return {"category": category, "regulation_key": key,
            "requirement_key": requirement_key, "level": level, "country_code": "US"}


def test_core_spine_has_exactly_the_labor_keys():
    spine = core_spine([])
    total = sum(len(v) for v in CORE_LABOR_KEYS.values())
    assert spine["total"] == total
    assert spine["present"] == 0
    assert spine["complete"] is False


def test_core_spine_present_and_governing_level():
    rows = [
        _req("minimum_wage", "state_minimum_wage", "state"),
        _req("workers_comp", "mandatory_coverage", "state"),
    ]
    spine = core_spine(rows)
    got = {(i["category"], i["key"]): i for i in spine["items"]}
    assert got[("minimum_wage", "state_minimum_wage")]["present"] is True
    assert got[("minimum_wage", "state_minimum_wage")]["level"] == "state"
    assert got[("workers_comp", "mandatory_coverage")]["present"] is True
    # a key we didn't supply stays missing
    assert got[("overtime", "daily_weekly_overtime")]["present"] is False
    assert got[("overtime", "daily_weekly_overtime")]["level"] is None
    assert spine["present"] == 2


def test_core_spine_city_beats_state_for_governing_level():
    rows = [
        _req("sick_leave", "state_paid_sick_leave", "state"),
        _req("sick_leave", "state_paid_sick_leave", "city"),
    ]
    got = {(i["category"], i["key"]): i for i in core_spine(rows)["items"]}
    assert got[("sick_leave", "state_paid_sick_leave")]["level"] == "city"


def test_core_spine_counts_legacy_requirement_key_row():
    # older rows have only requirement_key = "category:key"
    rows = [_req("final_pay", None, "state", requirement_key="final_pay:final_pay_termination")]
    got = {(i["category"], i["key"]): i for i in core_spine(rows)["items"]}
    assert got[("final_pay", "final_pay_termination")]["present"] is True


def test_core_spine_federal_general_minwage_does_not_satisfy_state_key():
    # normalize_key maps a federal-level 'general' minimum wage to
    # national_minimum_wage, so it must NOT satisfy state_minimum_wage.
    rows = [_req("minimum_wage", "general", "federal")]
    got = {(i["category"], i["key"]): i for i in core_spine(rows)["items"]}
    assert got[("minimum_wage", "state_minimum_wage")]["present"] is False


# ── 3. registry bucketing by level ───────────────────────────────────────────

def _cls(level, key, citation="X", index="ix"):
    return {"level": level, "regulation_key": key, "citation": citation,
            "heading": "h", "source_url": "u", "index_slug": index,
            "disposition": "universal_in_domain"}


def test_bucket_registry_codified_vs_uncodified_by_level():
    applicable = [
        _cls("federal", "national_minimum_wage", "29 USC 206"),   # codified below
        _cls("state", "meal_break", "Lab 512"),                   # named key, no req row
        _cls("state", None, "Lab 226"),                           # NULL key
        _cls("county", "local_sick_leave", "Ord 1"),              # county → city bucket
    ]
    reqs = {"national_minimum_wage": {"regulation_key": "national_minimum_wage", "title": "Fed min wage"}}
    levels = bucket_registry(applicable, reqs)

    assert len(levels["federal"]["codified"]) == 1
    assert levels["federal"]["codified"][0]["requirement"]["title"] == "Fed min wage"
    # named-key-miss and NULL-key both land uncodified
    assert {e["citation"] for e in levels["state"]["uncodified"]} == {"Lab 512", "Lab 226"}
    assert not levels["state"]["codified"]
    # county folds into the city bucket
    assert levels["city"]["uncodified"][0]["citation"] == "Ord 1"


# ── 4. exhaustiveness basis ──────────────────────────────────────────────────

def _ix(slug, level, enumerable, item_count=10, unclassified=0, name=None):
    return {"slug": slug, "name": name or slug, "level": level,
            "enumerable": enumerable, "item_count": item_count,
            "unclassified_count": unclassified}


def test_build_exhaustiveness_federal_enumerated_state_curated():
    rows = [
        _ix("ecfr-29-1910", "federal", True, 209, 207),   # enumerable
        _ix("us-flsa", "federal", False, 4, 0),           # curated supplement
        _ix("ca-labor-code", "state", False, 19, 0),      # curated
    ]
    ex = build_exhaustiveness(rows)
    assert ex["federal"]["basis"] == "enumerated"
    assert ex["federal"]["note"] == ENUMERATED_NOTE
    assert {ix["slug"] for ix in ex["federal"]["indexes"]} == {"ecfr-29-1910", "us-flsa"}
    assert ex["state"]["basis"] == "curated"
    assert ex["state"]["note"] == CURATED_NOTE
    # nothing at city → 'none'
    assert ex["city"]["basis"] == "none"
    assert ex["city"]["note"] == NO_INDEX_NOTE
