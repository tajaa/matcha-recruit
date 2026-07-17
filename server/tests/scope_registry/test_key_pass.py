"""The key pass's two pure cores: the RKD gate and the one-key-one-section dedupe.

The disposition pass (`validate_proposal`) and the key pass
(`propose_keys_for_index`) must agree on what counts as a real key. They call
`resolve_regulation_key` so they cannot drift; these pin its contract.
`dedupe_key_claims` decides WHICH section a key lands on — i.e. the citation a
business ends up reading. Pure, no DB.
"""
from app.core.services.scope_registry.classify import (
    dedupe_key_claims,
    resolve_regulation_key,
    validate_proposal,
)

RKD = {
    "leave": {"fmla"},
    "workplace_safety": {"osha_general_duty", "injury_illness_recordkeeping"},
    # The same key living in two categories — the case the category hint exists for.
    "minimum_wage": {"exempt_salary_threshold"},
    "overtime": {"exempt_salary_threshold"},
}


# ── the gate ────────────────────────────────────────────────────────────────

def test_known_key_survives():
    key, warnings = resolve_regulation_key("fmla", "leave", RKD)
    assert key == "fmla"
    assert warnings == []


def test_known_key_without_a_category_hint_survives():
    """No hint means "search every category" — the key still exists."""
    key, warnings = resolve_regulation_key("fmla", None, RKD)
    assert key == "fmla"
    assert warnings == []


def test_invented_key_downgrades_to_null_and_warns():
    """A key the model made up must never reach a row. NULL is the honest
    outcome (applicable-but-uncodified), not a rejection of the whole item."""
    key, warnings = resolve_regulation_key("vibes_based_safety", "workplace_safety", RKD)
    assert key is None
    assert len(warnings) == 1
    assert "not in regulation_key_definitions" in warnings[0]


def test_real_key_under_the_wrong_category_is_rejected():
    """`fmla` is real, but not in workplace_safety. Accepting it would let the
    category guard in match_codifications bind it to the wrong catalog rows."""
    key, warnings = resolve_regulation_key("fmla", "workplace_safety", RKD)
    assert key is None
    assert "for category 'workplace_safety'" in warnings[0]


def test_same_key_in_two_categories_resolves_under_either():
    for category in ("minimum_wage", "overtime"):
        key, warnings = resolve_regulation_key("exempt_salary_threshold", category, RKD)
        assert key == "exempt_salary_threshold", category
        assert warnings == []


def test_absent_key_is_not_a_warning():
    """Most sections legitimately map to nothing. Silence, not noise."""
    for empty in (None, "", "   "):
        key, warnings = resolve_regulation_key(empty, "leave", RKD)
        assert key is None
        assert warnings == []


def test_whitespace_is_stripped_not_treated_as_a_new_key():
    key, _ = resolve_regulation_key("  fmla  ", "  leave  ", RKD)
    assert key == "fmla"


def test_non_string_key_does_not_explode():
    """Gemini returning a number/list must degrade, never raise."""
    for junk in (42, ["fmla"], {"key": "fmla"}):
        key, warnings = resolve_regulation_key(junk, "leave", RKD)
        assert key is None
        assert len(warnings) == 1


# ── the two callers agree ───────────────────────────────────────────────────

def test_validate_proposal_delegates_to_the_same_gate():
    """The disposition pass must downgrade an invented key identically —
    same NULL, same warning text — or the two passes disagree about reality."""
    normalized, warnings = validate_proposal(
        {
            "disposition": "universal_in_domain",
            "applies_to_categories": [],
            "excludes_categories": [],
            "regulation_key": "vibes_based_safety",
            "category_slug": "workplace_safety",
        },
        RKD,
    )
    assert normalized is not None
    assert normalized["regulation_key"] is None
    assert any("not in regulation_key_definitions" in w for w in warnings)

    _, direct = resolve_regulation_key("vibes_based_safety", "workplace_safety", RKD)
    assert warnings == direct


def test_validate_proposal_keeps_a_real_key():
    normalized, warnings = validate_proposal(
        {
            "disposition": "universal_in_domain",
            "applies_to_categories": [],
            "excludes_categories": [],
            "regulation_key": "osha_general_duty",
            "category_slug": "workplace_safety",
        },
        RKD,
    )
    assert normalized["regulation_key"] == "osha_general_duty"
    assert warnings == []


# ── dedupe: which section a key lands on ────────────────────────────────────

def _claim(citation, key, *, confidence="high", is_section=True):
    return {
        "item_id": citation, "citation": citation, "key": key,
        "category_slug": None, "confidence": confidence, "is_section": is_section,
    }


def test_section_beats_subpart_at_equal_confidence():
    """The regression this dedupe was rewritten for. Citation order alone gets
    it backwards — a space sorts before a period, so "29 CFR 1910 Subpart O"
    < "29 CFR 1910.212" — and the subpart would win. The section is the
    obligation-bearing unit and must take the key."""
    winners, _ = dedupe_key_claims(
        [
            _claim("29 CFR 1910 Subpart O", "machine_guarding", is_section=False),
            _claim("29 CFR 1910.212", "machine_guarding", is_section=True),
        ],
        already=set(),
    )
    assert [w["citation"] for w in winners] == ["29 CFR 1910.212"]


def test_confidence_outranks_section_depth():
    """The model's own judgement comes first: a high-confidence subpart beats a
    medium-confidence section."""
    winners, _ = dedupe_key_claims(
        [
            _claim("29 CFR 1910.212", "machine_guarding",
                   confidence="medium", is_section=True),
            _claim("29 CFR 1910 Subpart O", "machine_guarding",
                   confidence="high", is_section=False),
        ],
        already=set(),
    )
    assert [w["citation"] for w in winners] == ["29 CFR 1910 Subpart O"]


def test_citation_breaks_a_full_tie_deterministically():
    claims = [
        _claim("29 CFR 1904.7", "injury_illness_recordkeeping"),
        _claim("29 CFR 1904.4", "injury_illness_recordkeeping"),
    ]
    winners, warnings = dedupe_key_claims(claims, already=set())
    assert [w["citation"] for w in winners] == ["29 CFR 1904.4"]
    # Reversed input, same winner — order in must not decide.
    winners2, _ = dedupe_key_claims(list(reversed(claims)), already=set())
    assert [w["citation"] for w in winners2] == ["29 CFR 1904.4"]
    assert any("already claimed by" in w for w in warnings)


def test_a_key_already_held_by_the_index_is_skipped():
    """Idempotency: a second run must not hand the same key to a second
    section (29 CFR 1904.4 AND 1904.7 both claiming recordkeeping)."""
    winners, warnings = dedupe_key_claims(
        [_claim("29 CFR 1904.7", "injury_illness_recordkeeping")],
        already={"injury_illness_recordkeeping"},
    )
    assert winners == []
    assert any("already held by another section" in w for w in warnings)


def test_distinct_keys_all_survive():
    winners, warnings = dedupe_key_claims(
        [
            _claim("29 CFR 1910.147", "lockout_tagout"),
            _claim("29 CFR 1910.146", "confined_space"),
        ],
        already=set(),
    )
    assert {w["key"] for w in winners} == {"lockout_tagout", "confined_space"}
    assert warnings == []


def test_nothing_accepted_is_not_an_error():
    assert dedupe_key_claims([], already=set()) == ([], [])
