"""Google Places API (New) client for Tell-Us place autocomplete.

Server-side proxy only — the API key never reaches the browser. `autocomplete()`
distinguishes unconfigured/failed (None) from genuinely-empty (list) so the
route can skip caching a transient Google outage; `place_details()` degrades
to None on any failure — callers fall back to the submitter's own free-text,
a flaky/unconfigured Places API must never block the add-a-place flow (manual
entry always works).

ToS note (decided, see server/app/tellus/CLAUDE.md): place_id is stored
indefinitely (explicitly permitted by Google's terms); displayName/address/
lat/lng are stored as part of the consumer's own submission despite Google's
30-day cache guidance for raw autocomplete results — accepted trade-off,
these are POI facts the user typed/selected, not cached search results.
"""
import logging
from typing import Any, Optional

import httpx

from ...config import get_settings

logger = logging.getLogger(__name__)

_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
_DETAILS_FIELD_MASK = "id,displayName,formattedAddress,addressComponents,location"

_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_DISCOVER_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.primaryType,places.rating,places.userRatingCount"
)


def _api_key() -> Optional[str]:
    return get_settings().google_maps_api_key


def _parse_autocomplete(payload: dict[str, Any]) -> list[dict]:
    """Pure. Google autocomplete JSON -> [{place_id, name, secondary_text}].
    Query predictions (no placePrediction, e.g. "restaurants near me") are
    dropped — we only want establishments a place row can be minted from."""
    out: list[dict] = []
    for suggestion in payload.get("suggestions", []):
        pred = suggestion.get("placePrediction")
        if not pred:
            continue
        place_id = pred.get("placeId")
        if not place_id:
            continue
        fmt = pred.get("structuredFormat", {})
        main = fmt.get("mainText", {}).get("text")
        secondary = fmt.get("secondaryText", {}).get("text")
        name = main or pred.get("text", {}).get("text") or ""
        if not name.strip():
            # Nothing to show the user or to submit as a place name later —
            # skip like a missing placeId above, don't emit a blank card.
            continue
        out.append({
            "place_id": place_id,
            "name": name,
            "secondary_text": secondary,
        })
    return out


async def autocomplete(q: str, city: Optional[str] = None, session_token: Optional[str] = None) -> Optional[list[dict]]:
    """-> [{place_id, name, secondary_text}] (up to Google's default page,
    establishments only). None when no key configured or on any Google/network
    error (caller must not cache this as "no results"); [] only for a genuine
    zero-result search. Never raises. session_token pairs this call with a
    later place_details() call so Google bills the pair as one session."""
    key = _api_key()
    if not key:
        return None
    if not q:
        return []
    body: dict[str, Any] = {
        "input": f"{q}, {city}" if city else q,
        "includedPrimaryTypes": ["establishment"],
    }
    if session_token:
        body["sessionToken"] = session_token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _AUTOCOMPLETE_URL,
                json=body,
                headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return _parse_autocomplete(resp.json())
    except Exception:
        logger.warning("Tell-Us Google Places autocomplete failed for q=%r", q, exc_info=True)
        return None


def _parse_discover(payload: dict[str, Any]) -> list[dict]:
    """Pure. searchNearby/searchText JSON ->
    [{place_id, name, address, lat, lng, primary_type, rating, user_rating_count}].
    Drops entries missing an id or a non-blank displayName.text — same rule
    _parse_autocomplete applies to placePrediction/name."""
    out: list[dict] = []
    for place in payload.get("places", []):
        place_id = place.get("id")
        name = (place.get("displayName") or {}).get("text") or ""
        if not place_id or not name.strip():
            continue
        location = place.get("location") or {}
        out.append({
            "place_id": place_id,
            "name": name,
            "address": place.get("formattedAddress"),
            "lat": location.get("latitude"),
            "lng": location.get("longitude"),
            "primary_type": place.get("primaryType"),
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount"),
        })
    return out


async def search_nearby(lat: float, lng: float, radius_m: float, max_results: int = 20) -> Optional[list[dict]]:
    """-> [{place_id, name, address, lat, lng, primary_type, rating,
    user_rating_count}]. None when no key configured or on any Google/network
    error (caller must not cache this); [] only for a genuine zero-result
    search. Never raises. No sessionToken — this is a per-request Nearby
    Search SKU, unlike autocomplete's session-billed pair with place_details().
    No includedTypes filter: searchNearby only accepts Table A types and
    "establishment" (autocomplete's includedPrimaryTypes value) is not one of
    them — omitting the filter returns all nearby types, which is what a
    discovery surface wants."""
    key = _api_key()
    if not key:
        return None
    body: dict[str, Any] = {
        "maxResultCount": max_results,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _NEARBY_URL,
                json=body,
                headers={
                    "X-Goog-Api-Key": key,
                    "X-Goog-FieldMask": _DISCOVER_FIELD_MASK,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return _parse_discover(resp.json())
    except Exception:
        logger.warning("Tell-Us Google Places nearby search failed for lat=%r lng=%r", lat, lng, exc_info=True)
        return None


async def search_text(
    q: str, lat: Optional[float] = None, lng: Optional[float] = None,
    radius_m: Optional[float] = None, max_results: int = 20,
) -> Optional[list[dict]]:
    """-> [{place_id, name, address, lat, lng, primary_type, rating,
    user_rating_count}]. Same None/[] contract as search_nearby. locationBias
    (not locationRestriction) — a text query can legitimately match outside
    the radius (e.g. a well-known chain name), bias just ranks nearby higher."""
    key = _api_key()
    if not key:
        return None
    if not q:
        return []
    body: dict[str, Any] = {"textQuery": q, "maxResultCount": max_results}
    if lat is not None and lng is not None and radius_m is not None:
        body["locationBias"] = {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}
        }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _TEXT_URL,
                json=body,
                headers={
                    "X-Goog-Api-Key": key,
                    "X-Goog-FieldMask": _DISCOVER_FIELD_MASK,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return _parse_discover(resp.json())
    except Exception:
        logger.warning("Tell-Us Google Places text search failed for q=%r", q, exc_info=True)
        return None


def parse_place_details(payload: dict[str, Any]) -> dict:
    """Pure. Google Place Details (New) JSON ->
    {place_id, name, address, city, state, lat, lng}. Any missing piece is
    None rather than raising — callers fall back to the submitter's own
    free-text for whatever Google didn't give us."""
    components = payload.get("addressComponents", [])

    def _component(*types: str) -> Optional[str]:
        for c in components:
            if any(t in c.get("types", []) for t in types):
                return c.get("shortText") or c.get("longText")
        return None

    location = payload.get("location") or {}
    return {
        "place_id": payload.get("id"),
        "name": (payload.get("displayName") or {}).get("text"),
        "address": payload.get("formattedAddress"),
        # postal_town / sublocality fallbacks cover countries (and some US
        # unincorporated areas) where Google has no "locality" component.
        "city": _component("locality", "postal_town", "sublocality"),
        "state": _component("administrative_area_level_1"),
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
    }


async def place_details(place_id: str, session_token: Optional[str] = None) -> Optional[dict]:
    """GET Place Details by id. None on any failure — caller falls back to
    the submitter's free-text name/city/state (the place still gets created,
    just without a verified Google address). session_token, when it matches
    the token used on the preceding autocomplete() call, closes out that
    billing session instead of billing this as a separate request."""
    key = _api_key()
    if not key or not place_id:
        return None
    url = _DETAILS_URL.format(place_id=place_id)
    if session_token:
        url += f"?sessionToken={session_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": _DETAILS_FIELD_MASK},
            )
            resp.raise_for_status()
            return parse_place_details(resp.json())
    except Exception:
        logger.warning("Tell-Us Google Places details failed for place_id=%r", place_id, exc_info=True)
        return None
