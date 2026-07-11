"""penalties_from_metadata — the WS1 payload extractor (pure, no DB).

The requirement joins in resolve.py/labor_scope.py ship `penalties` only when
the metadata block carries at least one substantive value; a grounding-only
shell or junk metadata must never render an empty penalty chip.
"""
import json

from app.core.services.scope_registry.resolve import penalties_from_metadata


FULL = {
    "enforcing_agency": "OSHA",
    "civil_penalty_min": 0,
    "civil_penalty_max": 16131,
    "per_violation": True,
    "annual_cap": None,
    "criminal": None,
    "summary": "Serious violation up to $16,131 per violation",
}


def test_dict_metadata_with_penalties():
    assert penalties_from_metadata({"penalties": FULL}) == FULL


def test_json_string_metadata_parses():
    # asyncpg returns JSONB as str on this pool — the helper must parse it.
    assert penalties_from_metadata(json.dumps({"penalties": FULL})) == FULL


def test_missing_penalties_key():
    assert penalties_from_metadata({"grounding": "grounded"}) is None


def test_none_metadata():
    assert penalties_from_metadata(None) is None


def test_junk_string_metadata():
    assert penalties_from_metadata("not json {") is None


def test_non_dict_penalties():
    assert penalties_from_metadata({"penalties": ["oops"]}) is None
    assert penalties_from_metadata({"penalties": "text"}) is None


def test_all_null_penalties_is_insubstantive():
    empty = {k: None for k in FULL}
    assert penalties_from_metadata({"penalties": empty}) is None


def test_grounding_only_shell_is_insubstantive():
    # WS2 writes grounding/grounded_citations onto the block; those alone are
    # provenance, not a penalty worth displaying.
    shell = {"grounding": "grounded", "grounded_citations": ["29 CFR 1903.15"]}
    assert penalties_from_metadata({"penalties": shell}) is None


def test_single_substantive_value_ships():
    assert penalties_from_metadata(
        {"penalties": {"summary": "fines vary", "civil_penalty_max": None}}
    ) == {"summary": "fines vary", "civil_penalty_max": None}
