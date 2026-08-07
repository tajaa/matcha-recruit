"""Pure-function tests for Tell-Us Google Places integration (autocomplete
parsing, place-details parsing, TellusPlaceCreate validation) plus fake-conn
tests for ensure_community_link. No DB, no HTTP, no network — see
TELLUS_ADMIN_MGMT_PLAN.md-style plan for the reviews-on-unclaimed-businesses
feature.
"""
from uuid import uuid4

import pytest

from app.tellus.models.tellus import TellusPlaceCreate
from app.tellus.routes.places import ensure_community_link
from app.tellus.services.google_places import _parse_autocomplete, parse_place_details


# ---------------------------------------------------------------------------
# parse_place_details
# ---------------------------------------------------------------------------

_FULL_DETAILS_PAYLOAD = {
    "id": "ChIJx8prJoS-woARJgYbTb4QeZg",
    "displayName": {"text": "Blue Bottle Coffee", "languageCode": "en"},
    "formattedAddress": "300 S Broadway, Los Angeles, CA 90013, USA",
    "location": {"latitude": 34.0505, "longitude": -118.2427},
    "addressComponents": [
        {"longText": "300", "shortText": "300", "types": ["street_number"]},
        {"longText": "South Broadway", "shortText": "S Broadway", "types": ["route"]},
        {"longText": "Los Angeles", "shortText": "Los Angeles", "types": ["locality", "political"]},
        {"longText": "California", "shortText": "CA", "types": ["administrative_area_level_1", "political"]},
        {"longText": "United States", "shortText": "US", "types": ["country", "political"]},
    ],
}


class TestParsePlaceDetails:
    def test_full_response(self):
        result = parse_place_details(_FULL_DETAILS_PAYLOAD)
        assert result == {
            "place_id": "ChIJx8prJoS-woARJgYbTb4QeZg",
            "name": "Blue Bottle Coffee",
            "address": "300 S Broadway, Los Angeles, CA 90013, USA",
            "city": "Los Angeles",
            "state": "CA",
            "lat": 34.0505,
            "lng": -118.2427,
        }

    def test_city_fallback_postal_town(self):
        payload = {
            "id": "p2", "displayName": {"text": "Village Bakery"},
            "formattedAddress": "1 High St, Little Wittering, UK",
            "location": {"latitude": 51.5, "longitude": -0.1},
            "addressComponents": [
                {"longText": "Little Wittering", "shortText": "Little Wittering", "types": ["postal_town"]},
            ],
        }
        result = parse_place_details(payload)
        assert result["city"] == "Little Wittering"
        assert result["state"] is None

    def test_missing_location_and_components(self):
        payload = {"id": "p3", "displayName": {"text": "No Geo Cafe"}}
        result = parse_place_details(payload)
        assert result["lat"] is None
        assert result["lng"] is None
        assert result["city"] is None
        assert result["state"] is None
        assert result["place_id"] == "p3"

    def test_missing_display_name_still_returns(self):
        # Caller (create_place) falls back to the submitter's own name when
        # this is None — must not raise.
        result = parse_place_details({"id": "p4"})
        assert result["name"] is None
        assert result["place_id"] == "p4"


# ---------------------------------------------------------------------------
# _parse_autocomplete
# ---------------------------------------------------------------------------

class TestAutocompleteParsing:
    def test_suggestions_mapped(self):
        payload = {
            "suggestions": [
                {
                    "placePrediction": {
                        "placeId": "ChIJabc",
                        "text": {"text": "Blue Bottle Coffee, 300 S Broadway, Los Angeles, CA"},
                        "structuredFormat": {
                            "mainText": {"text": "Blue Bottle Coffee"},
                            "secondaryText": {"text": "300 S Broadway, Los Angeles, CA"},
                        },
                    }
                }
            ]
        }
        result = _parse_autocomplete(payload)
        assert result == [{
            "place_id": "ChIJabc", "name": "Blue Bottle Coffee",
            "secondary_text": "300 S Broadway, Los Angeles, CA",
        }]

    def test_query_predictions_skipped(self):
        payload = {"suggestions": [{"queryPrediction": {"text": {"text": "coffee near me"}}}]}
        assert _parse_autocomplete(payload) == []

    def test_missing_place_id_skipped(self):
        payload = {"suggestions": [{"placePrediction": {"structuredFormat": {}}}]}
        assert _parse_autocomplete(payload) == []

    def test_empty_payload(self):
        assert _parse_autocomplete({}) == []

    def test_falls_back_to_flat_text_when_no_structured_format(self):
        payload = {"suggestions": [{"placePrediction": {
            "placeId": "p1", "text": {"text": "Some Place"},
        }}]}
        result = _parse_autocomplete(payload)
        assert result == [{"place_id": "p1", "name": "Some Place", "secondary_text": None}]


# ---------------------------------------------------------------------------
# TellusPlaceCreate.google_place_id
# ---------------------------------------------------------------------------

class TestPlaceCreateModel:
    def test_google_place_id_optional(self):
        m = TellusPlaceCreate(name="Joe's Diner", city="Austin")
        assert m.google_place_id is None

    def test_google_place_id_round_trips(self):
        m = TellusPlaceCreate(name="Joe's Diner", city="Austin", google_place_id="ChIJabc123")
        assert m.google_place_id == "ChIJabc123"

    def test_google_place_id_length_cap(self):
        with pytest.raises(Exception):
            TellusPlaceCreate(name="Joe's Diner", city="Austin", google_place_id="x" * 301)


# ---------------------------------------------------------------------------
# ensure_community_link — fake conn, no DB
# ---------------------------------------------------------------------------

class _FakeConn:
    """Records every call; dispatches fetchval/execute on SQL substring.
    `active_token` simulates an already-active link (None = mint needed)."""

    def __init__(self, *, active_token=None, store_id=None):
        self.calls: list[tuple] = []
        self._active_token = active_token
        self._store_id = store_id
        self._minted_link_id = "link-1"

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "SELECT token FROM tellus_links" in query:
            return self._active_token
        if "SELECT id FROM tellus_stores" in query:
            return self._store_id
        if "INSERT INTO tellus_links" in query:
            return self._minted_link_id
        raise AssertionError(f"unexpected fetchval: {query}")

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "INSERT 0 1"

    def _calls_matching(self, needle: str):
        return [c for c in self.calls if needle in c[1]]


class TestEnsureCommunityLink:
    @pytest.mark.asyncio
    async def test_returns_existing_active_token_without_minting(self):
        conn = _FakeConn(active_token="tok-existing")
        token = await ensure_community_link(conn, uuid4())
        assert token == "tok-existing"
        assert conn._calls_matching("INSERT INTO tellus_links") == []
        assert conn._calls_matching("INSERT INTO tellus_link_history") == []

    @pytest.mark.asyncio
    async def test_mints_link_and_history_when_none_active(self):
        conn = _FakeConn(active_token=None, store_id="store-1")
        token = await ensure_community_link(conn, uuid4(), detail="test mint")
        assert token  # a fresh urlsafe token, non-empty
        assert len(conn._calls_matching("INSERT INTO tellus_links")) == 1
        history_calls = conn._calls_matching("INSERT INTO tellus_link_history")
        assert len(history_calls) == 1
        assert history_calls[0][2][2] == "test mint"  # detail arg

    @pytest.mark.asyncio
    async def test_resolves_store_id_when_not_supplied(self):
        conn = _FakeConn(active_token=None, store_id="store-resolved")
        await ensure_community_link(conn, uuid4())
        assert len(conn._calls_matching("SELECT id FROM tellus_stores")) == 1

    @pytest.mark.asyncio
    async def test_skips_store_lookup_when_store_id_supplied(self):
        conn = _FakeConn(active_token=None)
        await ensure_community_link(conn, uuid4(), store_id="store-given")
        assert conn._calls_matching("SELECT id FROM tellus_stores") == []
