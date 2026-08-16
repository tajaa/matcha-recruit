"""Pure-function + model tests for Tell-Us Discover (no DB).

DB-touching paths (distance ordering, follow round-trip, materialize-once)
are integration-level — run manually against dev per the repo's DB-test
policy. See TELLUS_DISCOVER_PLAN.md at the repo root for the full design.
"""
import inspect

import pytest
from pydantic import ValidationError

import app.tellus.routes.discover as discover_route
from app.tellus.models.tellus import TellusDiscoverEntry
from app.tellus.services.discover_service import (
    bbox_predicate,
    dedupe_google,
    discover_cache_key,
    normalize_google_type,
)


class TestDiscoverCacheKey:
    def test_nearby_coords_share_a_key(self):
        a = discover_cache_key(34.0522, -118.2437, 15.0, None)
        b = discover_cache_key(34.05223, -118.24371, 15.0, None)
        assert a == b

    def test_distant_coords_differ(self):
        a = discover_cache_key(34.0522, -118.2437, 15.0, None)
        b = discover_cache_key(34.06, -118.2437, 15.0, None)
        assert a != b

    def test_query_is_part_of_the_key(self):
        a = discover_cache_key(34.0522, -118.2437, 15.0, "tacos")
        b = discover_cache_key(34.0522, -118.2437, 15.0, None)
        assert a != b

    def test_query_is_case_and_whitespace_insensitive(self):
        a = discover_cache_key(34.0522, -118.2437, 15.0, " Tacos ")
        b = discover_cache_key(34.0522, -118.2437, 15.0, "tacos")
        assert a == b

    def test_radius_is_part_of_the_key(self):
        a = discover_cache_key(34.0522, -118.2437, 15.0, None)
        b = discover_cache_key(34.0522, -118.2437, 25.0, None)
        assert a != b


class TestNormalizeGoogleType:
    def test_known_type_maps_to_label(self):
        assert normalize_google_type("cafe") == "Cafe"
        assert normalize_google_type("restaurant") == "Restaurant"

    def test_unknown_type_is_dropped(self):
        assert normalize_google_type("spaceship_dealer") is None

    def test_non_string_is_dropped(self):
        assert normalize_google_type(None) is None
        assert normalize_google_type(123) is None
        assert normalize_google_type([]) is None


class TestDedupeGoogle:
    def test_drops_places_already_on_tellus(self):
        rows = [{"place_id": "A"}, {"place_id": "B"}]
        assert dedupe_google(rows, {"A"}) == [{"place_id": "B"}]

    def test_keeps_places_not_on_tellus(self):
        rows = [{"place_id": "B"}]
        assert dedupe_google(rows, {"A"}) == rows

    def test_empty_known_set_keeps_everything(self):
        rows = [{"place_id": "A"}, {"place_id": "B"}]
        assert dedupe_google(rows, set()) == rows

    def test_row_without_place_id_is_dropped(self):
        rows = [{"place_id": None}, {"name": "no id field"}, {"place_id": "B"}]
        assert dedupe_google(rows, set()) == [{"place_id": "B"}]


class TestBboxPredicate:
    def test_uses_supplied_placeholders(self):
        sql = bbox_predicate("$4", "$5", "$6")
        assert "$4" in sql and "$5" in sql and "$6" in sql
        assert "st.lat" in sql and "st.lng" in sql

    def test_guards_the_pole_singularity(self):
        sql = bbox_predicate("$1", "$2", "$3")
        assert "greatest(cos(radians($1)), 0.01)" in sql


class TestDiscoverModels:
    def test_google_entry_needs_no_slug(self):
        entry = TellusDiscoverEntry(source="google", name="Blue Bottle")
        assert entry.slug is None
        assert entry.claimed is False

    def test_unknown_source_rejected(self):
        with pytest.raises(ValidationError):
            TellusDiscoverEntry(source="yelp", name="X")


class TestDiscoverNeverPersistsGoogle:
    """Pins the ToS decision in code — same idiom as the likes.py/hearted_*
    disjointness guard: a Google-sourced row must never be written to
    tellus_brands/tellus_stores directly by this route. Materialization only
    ever happens through the existing POST /places, which re-resolves via
    Google Place Details server-side."""

    def test_route_module_never_inserts_places(self):
        src = inspect.getsource(discover_route)
        assert "INSERT INTO tellus_brands" not in src
        assert "INSERT INTO tellus_stores" not in src
