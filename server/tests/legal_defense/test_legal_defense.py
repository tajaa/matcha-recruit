"""Unit tests for the Legal Defense service — pure helpers + gather isolation.

Fast, no DB / no app boot (a fake connection drives gather_evidence). The
citation gate is the security-critical bit: hallucinated IDs must never survive
into a packet.
"""
import asyncio
import io
import json
import zipfile

from app.core.compliance_registry import CATEGORY_KEYS
from app.matcha.services import legal_defense as ld


# --- citation gate (anti-hallucination) ------------------------------------

def test_validate_citations_drops_unknown_ids():
    index = {"incident:a": {}, "er_case:b": {}}
    emap = [
        {"point": "p1", "cited_ids": ["incident:a", "ghost:zzz"]},
        {"point": "p2", "cited_ids": ["er_case:b"]},
    ]
    clean, dropped = ld.validate_citations(emap, index)
    assert dropped == ["ghost:zzz"]
    assert clean[0]["cited_ids"] == ["incident:a"]   # hallucinated id stripped
    assert clean[1]["cited_ids"] == ["er_case:b"]


def test_validate_citations_accepts_new_cid_kinds():
    index = {"law:x": {}, "case:123": {}, "bill:y": {}}
    emap = [{"point": "p", "cited_ids": ["law:x", "case:123", "bill:y", "case:999"]}]
    clean, dropped = ld.validate_citations(emap, index)
    assert dropped == ["case:999"]
    assert clean[0]["cited_ids"] == ["law:x", "case:123", "bill:y"]


def test_validate_citations_tolerates_garbage():
    clean, dropped = ld.validate_citations(["not-a-dict", {"cited_ids": "x"}, {}], {"a": {}})
    # never raises; non-dict skipped, bad shapes coerced
    assert isinstance(clean, list)
    assert dropped == []


def test_cited_ids_dedupes_in_order():
    memo = {"evidence_map": [{"cited_ids": ["x", "y"]}, {"cited_ids": ["x", "z"]}]}
    assert ld._cited_ids(memo) == ["x", "y", "z"]


# --- JSON parse tolerance --------------------------------------------------

def test_parse_json_strips_fences_and_prose():
    assert ld._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ld._parse_json('here you go: {"a": 2} thanks') == {"a": 2}
    assert ld._parse_json("not json at all") == {}
    assert ld._parse_json("") == {}


# --- ZIP bundle ------------------------------------------------------------

def test_build_zip_contains_memo_manifest_and_sources():
    blob = ld._build_zip(
        b"%PDF-1.4 fake",
        [("incidents/1/photo.png", b"img-bytes")],
        ["er-cases/2/doc.pdf (download failed)"],
        {"title": "Doe v. Acme"},
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = set(z.namelist())
        assert "defense-memo.pdf" in names
        assert "manifest.txt" in names
        assert "source-documents/incidents/1/photo.png" in names
        manifest = z.read("manifest.txt").decode()
        assert "COULD NOT BE INCLUDED" in manifest
        assert "er-cases/2/doc.pdf" in manifest


# --- gather_evidence isolation ---------------------------------------------

class _FakeConn:
    """Minimal asyncpg-conn stand-in: raises for one table, returns a row for ER."""
    def __init__(self, fail_substr=None):
        self.fail = fail_substr

    async def fetch(self, sql, *args):
        if self.fail and self.fail in sql:
            raise RuntimeError("simulated source failure")
        if "er_cases" in sql:
            return [{
                "id": "11111111-1111-1111-1111-111111111111",
                "case_number": "ER-1", "title": "Complaint", "category": "harassment",
                "status": "open", "outcome": None, "created_at": None,
            }]
        return []

    async def fetchrow(self, sql, *args):
        if self.fail and self.fail in sql:
            raise RuntimeError("simulated jurisdiction failure")
        return None


_ALL_FEATURES = {
    "incidents": True, "compliance": True, "discipline": True,
    "training": True, "handbooks": True, "accommodations": True,
}


def test_gather_evidence_isolates_a_failing_source():
    corpus = asyncio.run(ld.gather_evidence(
        _FakeConn(fail_substr="ir_incidents"), "cid", None, None, _ALL_FEATURES,
    ))
    # ER survived; incidents degraded to a note, not a crash.
    assert "er_cases" in corpus["sources"]
    assert "incidents" not in corpus["sources"]
    assert any("Safety incidents" in n for n in corpus["notes"])
    # index is flat cid -> record and only holds surfaced sources
    assert "er_case:11111111-1111-1111-1111-111111111111" in corpus["index"]


def test_gather_evidence_respects_disabled_features():
    corpus = asyncio.run(ld.gather_evidence(
        _FakeConn(), "cid", None, None, {"incidents": False},
    ))
    # ER has no feature gate (always attempted); incidents off → never queried.
    assert "incidents" not in corpus["sources"]


def test_gather_evidence_without_matter_adds_no_law_source():
    # matter=None (default) — proves the new keyword stays back-compat with
    # every pre-existing 3-positional-arg caller.
    corpus = asyncio.run(ld.gather_evidence(_FakeConn(), "cid", None, None, {}))
    assert "law" not in corpus["sources"]
    assert "legislation" not in corpus["sources"]
    assert "case_law" not in corpus["sources"]
    assert corpus["legal_context"] is None


def test_gather_evidence_jurisdiction_failure_degrades():
    matter = {"id": "m1", "company_id": "cid", "matter_type": "class_action",
              "location_id": None, "jurisdiction_state": "CA"}
    corpus = asyncio.run(ld.gather_evidence(
        _FakeConn(fail_substr="jurisdictions"), "cid", None, None, {}, matter=matter,
    ))
    assert corpus["legal_context"] is None
    assert any("Jurisdiction" in n for n in corpus["notes"])
    assert "law" not in corpus["sources"]


class _FakeAlertConn:
    async def fetch(self, sql, *args):
        return [{
            "id": "a1", "title": "New law effective", "severity": "critical",
            "status": "unread", "category": "minimum_wage", "deadline": None,
            "created_at": None, "location_name": "HQ",
        }]


def test_src_compliance_alerts_shape():
    recs = asyncio.run(ld._src_compliance_alerts(_FakeAlertConn(), "cid", None, None, None, None))
    assert len(recs) == 1
    r = recs[0]
    assert r["cid"] == "compliance_alert:a1"
    assert r["ref"] == "Minimum Wage"
    assert r["summary"] == "New law effective — Critical, Unread @ HQ"


# --- matter scoping ----------------------------------------------------------

def test_scope_fragments_use_expected_placeholders():
    import re
    frag = ld._scope_direct("t.location_id", "bl.state", 4)
    assert set(re.findall(r"\$(\d+)", frag)) == {"4", "5"}
    frag2 = ld._scope_direct("cr.location_id", "bl.state", 2)
    assert set(re.findall(r"\$(\d+)", frag2)) == {"2", "3"}
    emp = ld._scope_employee(4)
    assert set(re.findall(r"\$(\d+)", emp)) == {"4", "5"}
    assert "e.work_location_id" in emp and "e.work_state" in emp
    er = ld._scope_er_involved(4)
    assert set(re.findall(r"\$(\d+)", er)) == {"4", "5"}
    # no-employees ER cases stay IN scope; malformed ids can't crash the cast
    assert "jsonb_array_length" in er
    assert "~" in er and "::uuid" in er


def test_chronology_rows_sorted_and_filtered():
    index = {
        "incident:a": {"cid": "incident:a", "summary": "s1", "when_iso": "2025-06-01"},
        "discipline:b": {"cid": "discipline:b", "summary": "s2", "when_iso": "2025-01-15T10:00:00"},
        "er_case:c": {"cid": "er_case:c", "summary": "s3", "when_iso": None},
        "compliance_req:d": {"cid": "compliance_req:d", "summary": "posture", "when_iso": "2020-01-01"},
        "law:e": {"cid": "law:e", "summary": "law", "when_iso": "2019-01-01"},
    }
    rows = ld._chronology_rows(index)
    # posture + jurisdiction context excluded; dated events oldest first; undated last
    assert [r["cid"] for r in rows] == ["discipline:b", "incident:a", "er_case:c"]


def test_chronology_html_renders_dates_and_escapes():
    index = {"incident:a": {"cid": "incident:a", "summary": "<b>x</b>", "when_iso": "2025-06-01",
                            "source_label": "Safety incidents (IR / OSHA)"}}
    html = ld._chronology_html(index)
    assert "Chronology of records" in html
    assert "2025-06-01" in html
    assert "&lt;b&gt;" in html          # summaries are escaped
    assert ld._chronology_html({}) == ""  # empty corpus renders nothing


class _ArgCountConn:
    """Records the positional-arg count of every fetch so scoping params are
    provably threaded through each source query."""
    def __init__(self):
        self.arg_counts: dict[str, int] = {}

    async def fetch(self, sql, *args):
        for tbl in ("ir_incidents", "er_cases", "compliance_requirements",
                    "progressive_discipline", "training_records",
                    "policy_signatures", "accommodation_cases", "compliance_alerts"):
            if tbl in sql:
                self.arg_counts[tbl] = len(args)
        return []

    async def fetchrow(self, sql, *args):
        return None  # jurisdiction unresolvable — state fallback path


def test_gather_evidence_scopes_sources_to_matter_location():
    conn = _ArgCountConn()
    matter = {"id": "m1", "company_id": "cid", "matter_type": "class_action",
              "location_id": "22222222-2222-2222-2222-222222222222",
              "jurisdiction_state": None}
    corpus = asyncio.run(ld.gather_evidence(
        conn, "cid", None, None, _ALL_FEATURES, matter=matter,
    ))
    # every source got the two scope params on top of company/start/end;
    # subject-bearing sources carry the topic allowlist + the known vocabulary
    assert conn.arg_counts["ir_incidents"] == 7
    assert conn.arg_counts["compliance_requirements"] == 5  # no date filter there
    assert conn.arg_counts["progressive_discipline"] == 7
    assert conn.arg_counts["training_records"] == 5         # unfiltered by design
    assert conn.arg_counts["accommodation_cases"] == 5      # unfiltered by design
    assert conn.arg_counts["compliance_alerts"] == 7
    assert any(n.startswith("Evidence scoped to") for n in corpus["notes"])


def test_gather_evidence_state_only_scope_notes():
    class _Conn(_ArgCountConn):
        async def fetchrow(self, sql, *args):
            return None  # no jurisdiction row for the state — raw override used

    corpus = asyncio.run(ld.gather_evidence(
        _Conn(), "cid", None, None, {},
        matter={"id": "m1", "company_id": "cid", "matter_type": "audit",
                "location_id": None, "jurisdiction_state": "CA"},
    ))
    assert any(n == "Evidence scoped to CA." for n in corpus["notes"])


def test_gather_evidence_unscoped_matter_has_no_scope_note():
    corpus = asyncio.run(ld.gather_evidence(
        _ArgCountConn(), "cid", None, None, {},
        matter={"id": "m1", "company_id": "cid", "matter_type": "other",
                "location_id": None, "jurisdiction_state": None},
    ))
    assert not any("Evidence scoped" in n for n in corpus["notes"])


# --- matter theory (subject-matter scoping) ----------------------------------

def test_theory_compliance_categories_are_registry_keys():
    for topic in ld._THEORIES.values():
        for c in topic.compliance or []:
            assert c in CATEGORY_KEYS


def test_vocabularies_track_their_sources_of_truth():
    """A vocabulary that drifts from its source silently changes filter
    semantics: an unlisted slug reads as 'company-defined' and passes every
    theory filter, so a new incident type would leak back into a wage-and-hour
    corpus with no test failing."""
    from typing import get_args
    from app.matcha.models.er_case import ERCaseCategory
    from app.matcha.models.ir_incident import IRIncidentType
    from app.matcha.services.discipline_engine import DEFAULT_INFRACTION_TYPES

    assert set(ld._INCIDENT_TYPES) == set(get_args(IRIncidentType))
    assert set(ld._ER_CATEGORIES) == set(get_args(ERCaseCategory))
    assert set(ld._INFRACTIONS) == {d["infraction_type"] for d in DEFAULT_INFRACTION_TYPES}
    assert set(ld._COMPLIANCE_CATEGORIES) == set(CATEGORY_KEYS)
    # _topic_filter degenerates to a no-op on an empty vocabulary
    assert ld._COMPLIANCE_CATEGORIES and ld._INCIDENT_TYPES and ld._INFRACTIONS


def test_resolve_theory_reads_the_allegation_over_the_matter_type():
    # the reported bug: a wage-and-hour class action was pulling slip-and-falls
    slug, topic = ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "Jones vs 720 Behavioral",
        "allegation": "Nurses were required to work through meal breaks off the clock.",
    })
    assert slug == "wage_hour"
    assert topic.incidents == []               # no IR incident type is about pay
    assert "meal_breaks" in topic.compliance

    # a safety class action must NOT inherit the matter_type's wage-hour default
    slug, topic = ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "Slip and fall",
        "allegation": "Employees were injured by an unmarked wet floor hazard.",
    })
    assert slug == "safety"
    assert "safety" in topic.incidents


def test_broad_matter_types_ignore_allegation_keywords():
    """A subject-less matter_type must stay broad even when the allegation is
    full of theory keywords — a records subpoena mentioning wages must not
    silently lose its safety incidents."""
    for mt in ("other", "subpoena", "audit"):
        slug, topic = ld.resolve_matter_theory({
            "matter_type": mt, "title": "Jones",
            "allegation": "missed meal breaks, unpaid overtime, wage theft",
        })
        assert slug is None, mt
        assert topic is ld._BROAD, mt


def test_stored_subject_theory_overrides_everything():
    """The real escape hatch. The derived subject is a guess; `subject_theory`
    is the user's decision and outranks both the keywords and the type."""
    base = {"matter_type": "class_action", "title": "Jones",
            "allegation": "missed meal breaks and unpaid overtime"}
    assert ld.resolve_matter_theory({**base, "subject_theory": "all"}) == (None, ld._BROAD)
    assert ld.resolve_matter_theory({**base, "subject_theory": "safety"})[0] == "safety"
    assert ld.resolve_matter_theory({**base, "subject_theory": "eeo"})[0] == "eeo"
    # null (the column default) falls through to derivation
    assert ld.resolve_matter_theory({**base, "subject_theory": None})[0] == "wage_hour"
    # an override even reaches a matter_type that short-circuits to broad
    assert ld.resolve_matter_theory(
        {"matter_type": "subpoena", "subject_theory": "safety"})[0] == "safety"


def test_theory_probes_respect_word_boundaries():
    """Bare-substring probes fired inside unrelated words and flipped matters
    onto a theory that then filtered out their own core records."""
    # "ada" inside "Nevada" must not score EEO; the injury must win
    assert ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "title": "Nevada warehouse forklift injury",
        "allegation": "Worker was injured.",
    })[0] == "safety"
    # "ppe" inside "happened" must not score safety on a tip-pooling wage claim
    assert ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "Tip pooling class action",
        "allegation": "Skimming happened across all stores",
    })[0] == "wage_hour"
    # but "ADA" as a whole word still scores EEO, including at end of text
    assert ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "title": "",
        "allegation": "Claim brought under the ADA",
    })[0] == "eeo"


def test_a_strong_matter_type_prior_resists_one_incidental_keyword():
    """An EEOC charge IS a discrimination charge. A lone stray "accident" must
    not swing it onto a safety corpus, dropping the harassment ER cases."""
    assert ld.resolve_matter_theory({
        "matter_type": "eeoc_charge", "title": "",
        "allegation": "Terminated after her workplace accident",
    })[0] == "eeo"
    # decisive safety language still wins
    assert ld.resolve_matter_theory({
        "matter_type": "eeoc_charge", "title": "",
        "allegation": "Injured by an unguarded machine; the safety hazard was reported.",
    })[0] == "safety"
    # a WEAK prior (class_action == procedural posture, not subject) yields to
    # a single unambiguous keyword
    assert ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "title": "Forklift injury",
        "allegation": "",
    })[0] == "safety"


def test_every_filtered_source_uses_the_shared_predicate():
    """One predicate, not three hand-rolled variants. Each filtered source must
    keep NULL-category rows (unattributable) and rows carrying a slug outside
    the known vocabulary (company-defined) — dropping either from a legal corpus
    is the failure mode the module calls worse than over-inclusion."""
    seen: dict[str, str] = {}

    class _Conn:
        async def fetch(self, sql, *args):
            for tbl in ("ir_incidents", "er_cases", "compliance_requirements",
                        "progressive_discipline", "compliance_alerts"):
                if tbl in sql:
                    seen[tbl] = sql
            return []

    topic = ld._THEORIES["wage_hour"]
    for fn in (ld._src_incidents, ld._src_er_cases, ld._src_compliance,
               ld._src_discipline, ld._src_compliance_alerts):
        asyncio.run(fn(_Conn(), "cid", None, None, None, None, topic))

    for tbl, col in (("ir_incidents", "i.incident_type"),
                     ("er_cases", "ec.category"),
                     ("compliance_requirements", "cr.category"),
                     ("progressive_discipline", "pd.infraction_type"),
                     ("compliance_alerts", "ca.category")):
        sql = seen[tbl]
        assert f"{col} IS NULL" in sql, tbl                  # unattributable stays in
        assert f"NOT ({col} = ANY(" in sql, tbl              # unknown slug stays in


def test_compliance_sources_pass_through_non_registry_categories():
    """compliance_service's Specialization Research Wizard mints category keys
    outside CATEGORY_KEYS and writes them onto requirements. A plain allowlist
    would silently drop a hospital's cardiac_catheterization_safety requirement
    from a safety matter."""
    captured = {}

    class _Conn:
        async def fetch(self, sql, *args):
            captured["vocab"] = args[-1]
            return []

    asyncio.run(ld._src_compliance(
        _Conn(), "cid", None, None, None, None, ld._THEORIES["safety"]))
    assert captured["vocab"] == ld._COMPLIANCE_CATEGORIES


# --- signal-less categories: classify by text, demote only on another subject --

def test_matches_other_subject_needs_a_positive_read_on_another_subject():
    # the matter's own keywords always win, whatever else the text mentions
    assert not ld._matches_other_subject("Off-the-clock work; FMLA retaliation", "wage_hour")
    # a clear other-subject read, with none of the matter's own keywords
    assert ld._matches_other_subject("FMLA interference complaint", "wage_hour")
    assert ld._matches_other_subject("HIPAA violation — patient records", "wage_hour")
    # unclassifiable text stays in every corpus (fail-open)
    assert not ld._matches_other_subject("Telehealth licensure renewal", "wage_hour")
    assert not ld._matches_other_subject("", "wage_hour")
    # the broad topic never demotes anything
    assert not ld._matches_other_subject("HIPAA violation", None)


def test_classify_probes_read_subjects_no_matter_can_carry():
    """A record can be about a subject no theory covers. Without these a HIPAA
    write-up reads as 'no subject detected' and fails open into every corpus."""
    assert ld._matches_other_subject("Gunshot wrongful death on premises", "wage_hour")
    # ...but that same record is the safety matter's own subject, not another's
    assert not ld._matches_other_subject("Gunshot wrongful death on premises", "safety")
    # classify-only words never re-theme a matter — derivation ignores them
    assert ld.resolve_matter_theory(
        {"matter_type": "class_action", "allegation": "gunshot"})[0] == "wage_hour"


def test_unpaid_is_a_modifier_not_a_subject():
    """Found against real data: a `hipaa` discipline record described as a
    '3-day unpaid suspension following confirmed HIPAA disclosure' survived a
    wage-and-hour matter, because bare 'unpaid' scored as one of the matter's own
    keywords and short-circuited the demotion."""
    assert ld._matches_other_subject(
        "Hipaa 3-day unpaid suspension following confirmed HIPAA disclosure.", "wage_hour")
    # the phrases that actually name a wage claim still score
    for t in ("unpaid wages", "unpaid overtime", "unpaid work", "unpaid time"):
        assert not ld._matches_other_subject(f"HIPAA breach and {t}", "wage_hour"), t
    # ...and derivation is unchanged: these allegations still read as wage-hour
    assert ld.resolve_matter_theory(
        {"matter_type": "class_action", "allegation": "unpaid wages"})[0] == "wage_hour"


def test_privacy_probes_read_the_common_misspelling():
    """'Potential HIPPA Violation' is a real ER case title in the tenant that
    reported this bug — its category is the generic 'policy_violation' bucket, so
    the title is the only thing naming the subject."""
    assert ld._matches_other_subject("Potential HIPPA Violation", "wage_hour")


def test_is_signalless_second_guesses_only_uninformative_categories():
    # an explicit, specific human categorization is never overridden by text
    assert not ld._is_signalless("wage_hour", ld._ER_CATEGORIES, ld._GENERIC_ER_CATEGORIES)
    # ...but a bucket, a NULL, or a company-defined slug tells us nothing
    assert ld._is_signalless("other", ld._ER_CATEGORIES, ld._GENERIC_ER_CATEGORIES)
    assert ld._is_signalless("policy_violation", ld._ER_CATEGORIES, ld._GENERIC_ER_CATEGORIES)
    assert ld._is_signalless(None, ld._ER_CATEGORIES, ld._GENERIC_ER_CATEGORIES)
    assert ld._is_signalless("hipaa", ld._INFRACTIONS)          # per-company infraction
    assert not ld._is_signalless("attendance", ld._INFRACTIONS)


class _RowConn:
    """Returns fixed rows for whichever table the query names."""
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, sql, *args):
        return self.rows


def _er_rows():
    return [
        {"id": "1", "case_number": "ER-1", "title": "FMLA interference complaint",
         "description": "Leave request denied.", "category": "other",
         "status": "open", "outcome": None, "created_at": None},
        {"id": "2", "case_number": "ER-2", "title": "Unpaid overtime dispute",
         "description": "Off-the-clock work alleged.", "category": "other",
         "status": "open", "outcome": None, "created_at": None},
        {"id": "3", "case_number": "ER-3", "title": "Meal break waiver",
         "description": None, "category": "wage_hour",
         "status": "open", "outcome": None, "created_at": None},
        {"id": "4", "case_number": "ER-4", "title": "Team conflict",
         "description": None, "category": None,
         "status": "open", "outcome": None, "created_at": None},
    ]


def test_er_generic_categories_are_classified_by_the_case_text():
    """The reported bug: 'other' and 'policy_violation' are in EVERY theory's ER
    allowlist because they might be about anything, so a HIPAA / FMLA case filed
    under one passed the SQL filter legitimately into a wage-and-hour corpus."""
    recs = asyncio.run(ld._src_er_cases(
        _RowConn(_er_rows()), "cid", None, None, None, None, ld._THEORIES["wage_hour"]))
    ids = [r["cid"] for r in recs]
    assert "er_case:1" not in ids          # 'other' + FMLA text → other subject
    assert "er_case:2" in ids              # 'other' + wage text → the matter's own
    assert "er_case:3" in ids              # explicitly categorized: never second-guessed
    assert "er_case:4" in ids              # NULL + unclassifiable → fail-open

    # the same FMLA case belongs in an EEO corpus, and in every broad one
    eeo = asyncio.run(ld._src_er_cases(
        _RowConn(_er_rows()), "cid", None, None, None, None, ld._THEORIES["eeo"]))
    assert "er_case:1" in [r["cid"] for r in eeo]
    broad = asyncio.run(ld._src_er_cases(_RowConn(_er_rows()), "cid", None, None, None, None))
    assert len(broad) == 4


def test_company_defined_infractions_are_classified_by_their_slug():
    """720 Behavioral configures `hipaa` / `patient_safety` infraction types.
    They are outside DEFAULT_INFRACTION_TYPES, so the SQL filter read them as
    'company-defined' and passed every one into a wage-and-hour corpus."""
    rows = [
        {"id": "1", "discipline_type": "written_warning", "infraction_type": "hipaa",
         "description": "Accessed a chart without cause.", "severity": "severe",
         "status": "active", "issued_date": None},
        {"id": "2", "discipline_type": "verbal_warning", "infraction_type": "attendance",
         "description": None, "severity": "minor", "status": "active", "issued_date": None},
        {"id": "3", "discipline_type": "coaching", "infraction_type": "documentation",
         "description": "Charting late.", "severity": "moderate",
         "status": "active", "issued_date": None},
    ]
    wage = asyncio.run(ld._src_discipline(
        _RowConn(rows), "cid", None, None, None, None, ld._THEORIES["wage_hour"]))
    ids = [r["cid"] for r in wage]
    assert "discipline:1" not in ids   # `hipaa` names a subject, and it isn't wages
    assert "discipline:2" in ids       # in the theory's allowlist
    assert "discipline:3" in ids       # company-defined but unclassifiable → stays

    broad = asyncio.run(ld._src_discipline(_RowConn(rows), "cid", None, None, None, None))
    assert len(broad) == 3


def test_minted_compliance_categories_land_in_the_matter_they_name():
    """A minted `cardiac_catheterization_safety` requirement belongs in a safety
    matter's corpus — the reason the passthrough arm exists. The same mechanism
    must keep a minted privacy category out of a wage-and-hour one."""
    rows = [
        {"id": "1", "title": "Annual notice of privacy practices",
         "category": "hipaa_privacy_notices", "current_value": None,
         "jurisdiction_name": None, "last_changed_at": None,
         "location_name": None, "statute_citation": None},
        {"id": "2", "title": "Cath lab sterile field protocol",
         "category": "cardiac_catheterization_safety", "current_value": None,
         "jurisdiction_name": None, "last_changed_at": None,
         "location_name": None, "statute_citation": None},
        {"id": "3", "title": "Telehealth licensure renewal",
         "category": "telehealth_licensure", "current_value": None,
         "jurisdiction_name": None, "last_changed_at": None,
         "location_name": None, "statute_citation": None},
    ]
    safety = asyncio.run(ld._src_compliance(
        _RowConn(rows), "cid", None, None, None, None, ld._THEORIES["safety"]))
    assert [r["cid"] for r in safety] == ["compliance_req:2", "compliance_req:3"]

    wage = asyncio.run(ld._src_compliance(
        _RowConn(rows), "cid", None, None, None, None, ld._THEORIES["wage_hour"]))
    # both classifiable minted keys name another subject; the third names none
    assert [r["cid"] for r in wage] == ["compliance_req:3"]


def test_demotion_is_inert_on_the_broad_topic_and_unfiltered_sources():
    """It may only ever narrow a corpus the SQL already intended to narrow —
    otherwise the packet path (apply_theory=False) would quietly lose records."""
    rows = _er_rows()
    assert ld._demote_off_subject(rows, ld._BROAD.slug, None, ld._ER_CATEGORIES, "category") == rows
    # a theory that doesn't filter this source (allowlist None) is left alone too
    topic = ld._THEORIES["wage_hour"]._replace(er=None)
    assert ld._demote_off_subject(rows, topic.slug, topic.er, ld._ER_CATEGORIES, "category") == rows


def test_generic_discipline_bucket_is_classified_by_text():
    """'policy_violation' is a real default infraction AND is in every theory's
    discipline allowlist — the same 'human picked a bucket, not a subject'
    situation as ER's 'other'. Without a generic set on the discipline source, a
    PHI-disclosure write-up filed under it rides into a wage-and-hour corpus."""
    rows = [
        {"id": "1", "discipline_type": "written_warning", "infraction_type": "policy_violation",
         "description": "Disclosed patient PHI without authorization.", "severity": "severe",
         "status": "active", "issued_date": None},
        {"id": "2", "discipline_type": "verbal_warning", "infraction_type": "policy_violation",
         "description": "Repeatedly clocked out and kept working.", "severity": "minor",
         "status": "active", "issued_date": None},
    ]
    wage = asyncio.run(ld._src_discipline(
        _RowConn(rows), "cid", None, None, None, None, ld._THEORIES["wage_hour"]))
    assert [r["cid"] for r in wage] == ["discipline:2"]


def test_retaliation_is_the_wage_matters_own_word_too():
    """wage_hour's ER allowlist claims 'retaliation' as its own category, so the
    word must never be the sole reason a generic-bucket record is demoted from a
    wage corpus — an FLSA retaliation case IS a wage case."""
    assert not ld._matches_other_subject("Retaliation after internal complaint", "wage_hour")
    # ...but one stray 'retaliated' still doesn't DERIVE a wage theory
    slug, _ = ld.resolve_matter_theory({
        "matter_type": "eeoc_charge", "allegation": "retaliation after complaint"})
    assert slug == "eeo"


def test_classification_vocab_is_decoupled_from_derivation_vocab():
    """The two jobs share a word list but not its adjustments. Removing bare
    'unpaid' from derivation flipped real tie-breaks (class_action 'unpaid PTO
    after workplace injury' went wage_hour → safety); keeping it in
    classification kept HIPAA 'unpaid suspension' write-ups in wage corpora.
    So: derivation keeps it, classification excludes it."""
    # derivation: bare 'unpaid' still scores, preserving the tie-break
    slug, _ = ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "",
        "allegation": "unpaid PTO after a workplace injury"})
    assert slug == "wage_hour"
    # classification: 'unpaid suspension' is not a wage record's own keyword
    assert ld._matches_other_subject(
        "Hipaa 3-day unpaid suspension following confirmed HIPAA disclosure.", "wage_hour")


def test_clinical_records_are_not_unclassifiable():
    """A healthcare tenant's ER cases are mostly ABOUT care delivery. Before the
    clinical group, 'Oncology Incident' (category 'Other') hit no probe at all,
    read as 'no subject detected', and failed open into a wage-and-hour corpus —
    four of them survived the round-3 fix in production."""
    rows = [
        {"id": "1", "case_number": "ER-1", "title": "Oncology Incident",
         "description": None, "category": "other",
         "status": "open", "outcome": None, "created_at": None},
        {"id": "2", "case_number": "ER-2", "title": "Medication error during unpaid overtime shift",
         "description": None, "category": "other",
         "status": "open", "outcome": None, "created_at": None},
    ]
    wage = asyncio.run(ld._src_er_cases(
        _RowConn(rows), "cid", None, None, None, None, ld._THEORIES["wage_hour"]))
    # clinical-only case drops; the one that is ALSO a wage record stays
    assert [r["cid"] for r in wage] == ["er_case:2"]
    broad = asyncio.run(ld._src_er_cases(_RowConn(rows), "cid", None, None, None, None))
    assert len(broad) == 2


def test_an_unmodeled_subject_vetoes_the_matter_type_prior():
    """'Jane Jones Vs World Health - HIPAA Claim' (a patient-privacy claim) scored
    zero on every theory and inherited single_plaintiff's wage-and-hour prior,
    filtering a privacy matter through a wage allowlist. The text is not silent —
    it names a subject no theory models — so broad is the only honest scope."""
    slug, topic = ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "title": "Jane Jones Vs World Health - HIPAA Claim",
        "allegation": "A nurse took a selfie in her room; her patient chart was visible.",
    })
    assert slug is None and topic is ld._BROAD
    # a clinical-subject matter likewise
    assert ld.resolve_matter_theory({
        "matter_type": "class_action", "allegation": "systemic medication errors"})[0] is None
    # a genuinely SILENT allegation still inherits the prior — the veto needs a
    # positive read on an unmodeled subject, not merely the absence of a theory
    assert ld.resolve_matter_theory({"matter_type": "single_plaintiff"})[0] == "wage_hour"
    assert ld.resolve_matter_theory(
        {"matter_type": "class_action", "allegation": "a dispute arose"})[0] == "wage_hour"
    # and a wage allegation that merely MENTIONS a chart is still wage
    assert ld.resolve_matter_theory({
        "matter_type": "class_action",
        "allegation": "nurses charted off the clock without overtime pay"})[0] == "wage_hour"
    # the stored override still outranks the veto
    assert ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "subject_theory": "eeo",
        "allegation": "HIPAA breach"})[0] == "eeo"


def test_classify_probe_maps_cover_every_theory():
    """_matches_other_subject indexes _CLASSIFY_PROBES[slug] bare — a theory
    added to _THEORIES without a keyword entry is a production KeyError on
    every source, invisible to a green suite without this assertion."""
    assert set(ld._THEORY_KEYWORDS) == set(ld._THEORIES)
    assert set(ld._THEORIES) <= set(ld._CLASSIFY_PROBES)
    # off-theory groups name subjects NO matter can carry — a collision would
    # make _names_unmodeled_subject veto that theory's own matters
    assert not (set(ld._OFF_THEORY_KEYWORDS) & set(ld._THEORIES))
    assert ld._OFF_THEORY_PROBES
    for slug in ld._CLASSIFY_ONLY_KEYWORDS:
        assert slug in ld._THEORIES
    for slug, excluded in ld._CLASSIFY_EXCLUDE_KEYWORDS.items():
        assert slug in ld._THEORIES
        assert excluded <= set(ld._THEORY_KEYWORDS[slug])  # excludes real words
    # slug field mirrors the dict key by construction
    for slug, topic in ld._THEORIES.items():
        assert topic.slug == slug
    assert ld._BROAD.slug is None


def test_resolve_theory_falls_back_to_matter_type_when_text_is_silent():
    assert ld.resolve_matter_theory({"matter_type": "eeoc_charge"})[0] == "eeo"
    assert ld.resolve_matter_theory({"matter_type": "class_action"})[0] == "wage_hour"
    # types carrying no subject signal stay broad — the escape hatch
    for mt in ("subpoena", "audit", "other"):
        slug, topic = ld.resolve_matter_theory({"matter_type": mt})
        assert slug is None
        assert topic is ld._BROAD
    assert ld.resolve_matter_theory(None) == (None, ld._BROAD)


def test_resolve_theory_declines_to_guess_on_a_tie():
    # one hit each ("discriminat" / "injur"). The matter_type's theory is among
    # the tied candidates, so it decides rather than a coin flip on ordering.
    slug, _ = ld.resolve_matter_theory({
        "matter_type": "eeoc_charge", "title": "",
        "allegation": "Discrimination claim following an injury.",
    })
    assert slug == "eeo"


def test_a_tie_never_resolves_to_a_theory_that_scored_zero():
    """eeo=1 ("harass"), safety=1 ("exposure"), wage_hour=0. Falling back to the
    class_action prior would filter a harassment matter through a wage-and-hour
    allowlist that excludes harassment entirely. Two subjects competing is a
    reason to widen, not to assert a third nobody argued for."""
    slug, topic = ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "title": "",
        "allegation": "Harassment claim; exposure was significant.",
    })
    assert slug is None
    assert topic is ld._BROAD


def test_topic_filter_passes_unknown_slugs_and_nulls():
    frag = ld._topic_filter("pd.infraction_type", 6)
    import re
    assert set(re.findall(r"\$(\d+)", frag)) == {"6", "7"}
    assert "IS NULL" in frag                        # unattributable rows stay in
    assert "NOT (pd.infraction_type = ANY($7))" in frag   # company-defined slugs stay in


def test_gather_evidence_filters_sources_to_the_theory():
    class _CapturingConn(_ArgCountConn):
        def __init__(self):
            super().__init__()
            self.topic_args: dict[str, object] = {}

        async def fetch(self, sql, *args):
            if "ir_incidents" in sql:
                self.topic_args["incidents"] = args[5]
            if "progressive_discipline" in sql:
                self.topic_args["discipline"] = args[5]
            if "compliance_requirements" in sql:
                self.topic_args["compliance"] = args[3]
            return await super().fetch(sql, *args)

    conn = _CapturingConn()
    corpus = asyncio.run(ld.gather_evidence(
        conn, "cid", None, None, _ALL_FEATURES,
        matter={"id": "m1", "company_id": "cid", "matter_type": "class_action",
                "title": "Jones", "allegation": "unpaid overtime and missed meal breaks",
                "location_id": None, "jurisdiction_state": None},
    ))
    assert conn.topic_args["incidents"] == []      # IR/OSHA drops out entirely
    assert "attendance" in conn.topic_args["discipline"]
    assert "meal_breaks" in conn.topic_args["compliance"]
    # derived, not user-set — the UI labels it "(auto)" and offers to correct it
    assert corpus["theory"] == {"slug": "wage_hour", "label": "wage-and-hour", "overridden": False}
    assert any("wage-and-hour subject" in n for n in corpus["notes"])


def test_apply_theory_false_gathers_broad_for_the_packet():
    """build_defense_packet promises the appendix + ZIP carry every incident /
    ER / discipline record in scope, cited or not, so the exhibit can't read as
    selective to opposing counsel. Subject filtering must not reach it."""
    class _CapturingConn(_ArgCountConn):
        def __init__(self):
            super().__init__()
            self.incident_topic = "unset"

        async def fetch(self, sql, *args):
            if "ir_incidents" in sql:
                self.incident_topic = args[5]
            return await super().fetch(sql, *args)

    matter = {"id": "m1", "company_id": "cid", "matter_type": "class_action",
              "title": "Jones", "allegation": "unpaid overtime, missed meal breaks",
              "location_id": None, "jurisdiction_state": None}

    # chat / sidebar: filtered
    chat = _CapturingConn()
    corpus = asyncio.run(ld.gather_evidence(chat, "cid", None, None, _ALL_FEATURES, matter=matter))
    assert chat.incident_topic == []
    assert corpus["theory"]["slug"] == "wage_hour"

    # packet: broad, no matter what the allegation says
    packet = _CapturingConn()
    corpus = asyncio.run(ld.gather_evidence(
        packet, "cid", None, None, _ALL_FEATURES, matter=matter, apply_theory=False))
    assert packet.incident_topic is None       # NULL allowlist = every incident
    assert corpus["theory"] is None
    assert not any("subject" in n for n in corpus["notes"])


def test_notes_disclose_window_and_disabled_subsystems():
    """The prompt's scope block is built from notes. An absent source must never
    read to the model as 'no such records exist' — the memo goes to counsel."""
    corpus = asyncio.run(ld.gather_evidence(
        _ArgCountConn(), "cid", "2025-01-01", "2025-06-30",
        {"incidents": True},  # discipline/training/etc. off
        matter={"id": "m1", "company_id": "cid", "matter_type": "other",
                "location_id": None, "jurisdiction_state": None},
    ))
    assert any("Evidence window: 2025-01-01 to 2025-06-30." == n for n in corpus["notes"])
    assert any("Not included (subsystem not enabled" in n for n in corpus["notes"])
    assert any("Progressive discipline" in n for n in corpus["notes"])
    # never a nonexistence claim — a feature can be disabled after records exist
    assert not any("no records exist" in n.lower() for n in corpus["notes"])


def test_notes_carry_no_ui_instructions_into_the_packet():
    """corpus['notes'] renders verbatim into the packet PDF's Scope notes.
    Counsel must not receive app-navigation copy in a legal exhibit."""
    corpus = asyncio.run(ld.gather_evidence(
        _ArgCountConn(), "cid", None, None, _ALL_FEATURES,
        matter={"id": "m1", "company_id": "cid", "matter_type": "class_action",
                "title": "", "allegation": "unpaid overtime",
                "location_id": None, "jurisdiction_state": None},
    ))
    joined = " ".join(corpus["notes"]).lower()
    assert "wage-and-hour subject" in joined
    for ui_copy in ("matter type", "set the", "click", "legal landscape"):
        assert ui_copy not in joined


def test_scope_text_never_claims_completeness():
    # a corpus with no notes can still be shaped by a feature gate or date bound
    assert "no filters applied" not in ld._scope_text({"notes": [], "theory": None}).lower()
    assert "every record" not in ld._scope_text({"notes": []}).lower()
    # notes render one-per-line, and nothing is restated
    txt = ld._scope_text({"notes": ["Evidence scoped to CA.", "Evidence window: a to b."],
                          "theory": {"slug": "eeo", "label": "discrimination / EEO"}})
    assert txt.count("- ") == 2


def test_gather_evidence_broad_theory_passes_null_allowlists():
    class _CapturingConn(_ArgCountConn):
        def __init__(self):
            super().__init__()
            self.incident_topic = "unset"

        async def fetch(self, sql, *args):
            if "ir_incidents" in sql:
                self.incident_topic = args[5]
            return await super().fetch(sql, *args)

    conn = _CapturingConn()
    corpus = asyncio.run(ld.gather_evidence(
        conn, "cid", None, None, _ALL_FEATURES,
        matter={"id": "m1", "company_id": "cid", "matter_type": "subpoena",
                "title": "Records subpoena", "allegation": None,
                "location_id": None, "jurisdiction_state": None},
    ))
    assert conn.incident_topic is None            # NULL allowlist = no filter
    assert corpus["theory"] is None
    assert not any("theory" in n for n in corpus["notes"])


def test_gather_case_law_scopes_a_run_to_the_matters_state_and_subject():
    """A research run is grounded in BOTH axes. A run made under another subject
    — or, for rows predating the column, under none, when the search had no
    subject anchor and could return an in-state case about anything — is stale
    for a themed matter, exactly as a run in another state is."""
    captured = {}

    class _Conn:
        async def fetchrow(self, sql, *args):
            captured["sql"] = sql
            captured["args"] = args
            return None

    asyncio.run(ld._gather_case_law(_Conn(), "m1", "CA", "wage_hour"))
    assert captured["args"] == ("m1", "CA", "wage_hour")
    assert "theory = $3" in captured["sql"]
    # a broad matter passes NULL and still accepts any run, as it always has
    assert "$3::varchar IS NULL" in captured["sql"]
    asyncio.run(ld._gather_case_law(_Conn(), "m1"))
    assert captured["args"] == ("m1", None, None)


# --- packet rendering guards -------------------------------------------------

def test_research_html_surfaces_partial_error():
    # A partial run (CourtListener down) persists status='complete' with an
    # error note and cases=[] — the PDF must not render that as a genuine
    # zero-result search.
    html = ld._research_html({
        "cases": [], "guidance": {"summary": "s", "key_authorities": []},
        "error": "Case search unavailable: courtlistener down",
    })
    assert "Partial run" in html
    assert "courtlistener down" in html
    # clean run renders no partial-run banner
    clean = ld._research_html({"cases": [], "guidance": {}, "error": None})
    assert "Partial run" not in clean


def test_memo_html_marks_out_of_scope_citations():
    # A cid validated at chat time but absent from the packet-time re-gather
    # must render an explicit marker, not silently-blank index cells.
    memo = {"assistant_text": "x", "open_questions": [],
            "evidence_map": [{"point": "p", "cited_ids": ["law:gone"]}]}
    corpus = {"index": {}, "sources": {}, "notes": []}
    html = ld._memo_html({}, corpus, memo, details={}, cited=["law:gone"])
    assert "no longer in evidence scope" in html


def test_dt_date_normalizes_str_and_date():
    # The RAG path pre-isoformats dates to str; the SQL path returns date
    # objects — both must render identically, date-only.
    import datetime
    assert ld._dt_date("2024-01-15") == "2024-01-15"
    assert ld._dt_date(datetime.date(2024, 1, 15)) == "2024-01-15"
    assert ld._dt_date(None) == "—"


# --- intake parser coercion ---------------------------------------------------

def test_coerce_draft_clamps_garbage():
    from app.matcha.services.legal_intake_parser import coerce_draft
    d = coerce_draft({
        "matter_type": "lawsuit-of-doom", "title": "  T  " + "x" * 300,
        "allegation": None, "jurisdiction_state": "Nevada",
        "evidence_start": "not-a-date", "evidence_end": "2025-12-31",
        "response_deadline": "2026-02-30",  # invalid calendar date
    })
    assert d["matter_type"] == "other"          # unknown type → other
    assert len(d["title"]) <= 120
    assert d["jurisdiction_state"] is None      # "Nevada" is not a 2-letter code
    assert d["evidence_start"] is None
    assert d["evidence_end"] == "2025-12-31"
    assert d["response_deadline"] is None       # Feb 30 rejected
    assert coerce_draft("not-a-dict")["matter_type"] == "other"


def test_coerce_draft_swaps_inverted_window_and_uppercases_state():
    from app.matcha.services.legal_intake_parser import coerce_draft
    d = coerce_draft({
        "matter_type": "eeoc_charge", "jurisdiction_state": "nv",
        "evidence_start": "2025-12-01", "evidence_end": "2025-01-01",
    })
    assert d["matter_type"] == "eeoc_charge"
    assert d["jurisdiction_state"] == "NV"
    assert d["evidence_start"] == "2025-01-01" and d["evidence_end"] == "2025-12-01"


# --- deadline reminder buckets -------------------------------------------------

def test_deadline_bucket_boundaries():
    from app.workers.tasks.legal_deadline_reminders import bucket_for
    assert bucket_for(0) == 1
    assert bucket_for(1) == 1
    assert bucket_for(2) == 3
    assert bucket_for(6) == 7      # worker down on day 7 still catches day 6
    assert bucket_for(14) == 14
    assert bucket_for(15) is None  # beyond lookahead
    assert bucket_for(-1) is None  # overdue — no nag, UI shows red


# --- intake gathering (ask before concluding) -------------------------------

def _corpus(sources=None, features=None, chain=True):
    return {
        "sources": sources or {},
        "index": {},
        "notes": [],
        "features": features if features is not None else {},
        "legal_context": {"chain": [{"display_name": "California"}]} if chain else None,
    }


def _full_matter():
    return {"matter_type": "other", "allegation": "a", "defense_theory": "b",
            "evidence_start": "2026-01-01", "evidence_end": "2026-02-01"}


def test_intake_gaps_flags_unset_matter_fields():
    keys = {g["key"] for g in ld.intake_gaps({"matter_type": "other"}, _corpus(chain=False))}
    assert {"allegation", "context", "window", "jurisdiction"} <= keys


def test_intake_gaps_clean_when_matter_and_sources_populated():
    m = _full_matter()
    corpus = _corpus(
        sources={"er_cases": {"label": "ER", "records": [{"cid": "er_case:1"}]},
                 "policy_ack": {"label": "Acks", "records": [{"cid": "policy_ack:1"}]}},
        features={"handbooks": True},
    )
    assert ld.intake_gaps(m, corpus) == []


def test_intake_gaps_reports_expected_but_empty_source():
    m = _full_matter()
    # er_cases is ungated and empty -> a real gap; policy_ack is populated.
    corpus = _corpus(sources={"policy_ack": {"label": "Acks", "records": [{"cid": "p:1"}]}},
                     features={"handbooks": True})
    assert {g["key"] for g in ld.intake_gaps(m, corpus)} == {"er_cases"}


def test_intake_gaps_skips_sources_the_company_does_not_run():
    """A disabled feature is not a gap — asking for training records from a
    company without the training feature is noise, and gather_evidence omits
    disabled, errored and empty sources identically."""
    m = {**_full_matter(), "matter_type": "eeoc_charge"}
    corpus = _corpus(sources={}, features={})  # training/discipline/handbooks all off
    keys = {g["key"] for g in ld.intake_gaps(m, corpus)}
    assert "training" not in keys and "discipline" not in keys
    assert "er_cases" in keys          # ungated source, genuinely empty
    assert "policy_ack" in keys        # handbooks defaults True


def _turn(monkeypatch, payload, corpus=None):
    async def fake_generate(matter, history, corpus_, latest):
        return payload
    monkeypatch.setattr(ld, "_generate", fake_generate)
    evs = []

    async def drain():
        async for e in ld.run_chat_turn({"matter_type": "other"}, [], corpus or _corpus(), "hi"):
            evs.append(e)
    asyncio.run(drain())
    return next(e["data"] for e in evs if e["type"] == "result")


def test_gathering_turn_withholds_analysis_blocks(monkeypatch):
    out = _turn(monkeypatch, {
        "assistant_text": "What was the termination date?",
        "ready_for_analysis": False,
        "intake_requests": ["The termination letter"],
        "evidence_map": [{"point": "leaked", "cited_ids": []}],
        "open_questions": ["leaked too"],
    })
    assert out["evidence_map"] == [] and out["open_questions"] == []
    assert out["intake_requests"] == ["The termination letter"]


def test_not_ready_without_requests_still_shows_analysis(monkeypatch):
    """A turn claiming not-ready but asking for nothing is a dead end; it must
    degrade to showing what it produced rather than rendering blank."""
    out = _turn(monkeypatch, {
        "assistant_text": "here", "ready_for_analysis": False, "intake_requests": [],
        "evidence_map": [{"point": "p", "cited_ids": []}], "open_questions": ["q"],
    })
    assert out["evidence_map"] and out["open_questions"] == ["q"]
    assert out["ready_for_analysis"] is True


def test_ready_turn_passes_analysis_through(monkeypatch):
    out = _turn(monkeypatch, {
        "assistant_text": "here", "ready_for_analysis": True, "intake_requests": [],
        "evidence_map": [{"point": "p", "cited_ids": []}], "open_questions": ["q"],
    })
    assert out["evidence_map"][0]["point"] == "p" and out["open_questions"] == ["q"]


def _fake_model(monkeypatch, payload, captured=None):
    class _Resp:
        text = json.dumps(payload)

    class _Models:
        async def generate_content(self, model=None, contents=None):
            if captured is not None:
                captured["prompt"] = contents
            return _Resp()

    class _Client:
        aio = type("_Aio", (), {"models": _Models()})

    monkeypatch.setattr(ld, "_genai", lambda: _Client())


def test_missing_ready_flag_defaults_to_analyzing(monkeypatch):
    """A model response that omits (or garbles) the flag must degrade to the
    pre-intake behavior — analyze and show it — not silently swallow every
    observation it just produced."""
    _fake_model(monkeypatch, {"assistant_text": "x",
                              "evidence_map": [{"point": "p", "cited_ids": []}],
                              "open_questions": []})
    out = asyncio.run(ld._generate(_full_matter(), [], _corpus(), "hi"))
    assert out["ready_for_analysis"] is True

    _fake_model(monkeypatch, {"assistant_text": "x", "ready_for_analysis": "sure",
                              "evidence_map": [], "open_questions": []})
    assert asyncio.run(ld._generate(_full_matter(), [], _corpus(), "hi"))["ready_for_analysis"] is True


def test_intake_requests_capped_and_coerced(monkeypatch):
    captured = {}
    _fake_model(monkeypatch, {
        "assistant_text": "a", "ready_for_analysis": False,
        "intake_requests": ["a", "", "  ", "b", "c", "d", "e"],
        "evidence_map": [], "open_questions": [],
    }, captured)
    out = asyncio.run(ld._generate(_full_matter(), [], _corpus(), "hi"))
    assert out["intake_requests"] == ["a", "b", "c"]     # blanks dropped, capped at 3
    assert out["ready_for_analysis"] is False
    assert "MATERIAL NOT YET IN THE RECORD" in captured["prompt"]
