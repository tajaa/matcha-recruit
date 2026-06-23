"""Pure-logic tests for the SOV parser's coercion (no Gemini / no network).

Only app.matcha.services.property_sov_parser pure helpers.
"""

from app.matcha.services import property_sov_parser as p


# --- construction normalization --------------------------------------------

def test_normalize_construction_exact_key():
    assert p.normalize_construction("frame") == "frame"
    assert p.normalize_construction("fire_resistive") == "fire_resistive"


def test_normalize_construction_aliases_and_iso_class():
    assert p.normalize_construction("Fire Resistive") == "fire_resistive"
    assert p.normalize_construction("ISO 6") == "fire_resistive"
    assert p.normalize_construction("wood frame") == "frame"
    assert p.normalize_construction("Masonry Non-Combustible") == "masonry_non_combustible"


def test_normalize_construction_unknown_is_none():
    assert p.normalize_construction("igloo") is None
    assert p.normalize_construction("") is None
    assert p.normalize_construction(None) is None


# --- numeric / bool coercion -----------------------------------------------

def test_num_handles_currency_and_suffixes():
    assert p._num("$5,000,000") == 5_000_000.0
    assert p._num("1.5M") == 1_500_000.0
    assert p._num("750K") == 750_000.0
    assert p._num(-5) is None        # negative dropped
    assert p._num("") is None


def test_bool_coercion():
    assert p._bool("yes") is True
    assert p._bool("Sprinklered") is True
    assert p._bool("no") is False
    assert p._bool("maybe") is None


# --- coerce_building --------------------------------------------------------

def test_coerce_building_full_row():
    b = p.coerce_building({
        "name": "HQ", "state": "tx", "construction_type": "ISO 6",
        "building_value": "$5,000,000", "sprinklered": "yes", "year_built": "2008",
        "protection_class": "2",
    })
    assert b["state"] == "TX"
    assert b["construction_type"] == "fire_resistive"
    assert b["building_value"] == 5_000_000.0
    assert b["sprinklered"] is True
    assert b["year_built"] == 2008


def test_coerce_building_unknown_construction_is_nulled_not_dropped():
    b = p.coerce_building({"name": "Shed", "construction_type": "igloo"})
    assert b is not None and b["construction_type"] is None


def test_coerce_building_empty_row_is_none():
    assert p.coerce_building({"name": "", "note": "  "}) is None
    assert p.coerce_building({}) is None


def test_coerce_building_year_out_of_range_dropped():
    b = p.coerce_building({"name": "X", "year_built": "1200"})
    assert b["year_built"] is None


def test_coerce_buildings_caps_and_filters():
    payload = {"buildings": [{"name": "A"}, {}, {"address": "1 St"}]}
    out = p._coerce_buildings(payload)
    assert len(out) == 2   # empty middle row dropped
