"""Reading, checking and showing a finding's facts."""
import pytest

from app.matcha.services.matcha_work.agent_tasks.research import fields as F

from ._fixtures import TODAY

L = F.LIBRARY


def test_values_coerce_by_type():
    assert F.coerce(L["price"], "$3,200/mo", today=TODAY) == 3200.0
    assert F.coerce(L["price"], "12k", today=TODAY) == 12000.0
    assert F.coerce(L["price"], True, today=TODAY) is None
    assert F.coerce(L["rating"], "4.6", today=TODAY) == 4.6
    assert F.coerce(L["rating"], 9, today=TODAY) is None
    assert F.coerce(L["in_stock"], "In stock", today=TODAY) is True
    assert F.coerce(L["in_stock"], "sold out", today=TODAY) is False
    assert F.coerce(L["in_stock"], "maybe", today=TODAY) is None
    assert F.coerce(L["in_stock"], False, today=TODAY) is False
    assert F.coerce(L["pets"], ["Dogs welcome", "cats ok"], today=TODAY) == ["dogs", "cats"]
    assert F.coerce(L["pets"], "dogs ok but no pets over 30lb", today=TODAY) == ["none"]
    assert F.coerce(L["pets"], "", today=TODAY) is None
    assert F.coerce(L["amenities"], "In-unit washer/dryer, garage parking", today=TODAY) == ["laundry", "parking"]
    assert F.coerce(L["available_date"], "now", today=TODAY) == "2026-10-14"
    assert F.coerce(L["available_date"], "Jan 5", today=TODAY) == "2027-01-05"
    assert F.coerce(L["available_date"], "11/20/26", today=TODAY) == "2026-11-20"
    assert F.coerce(L["available_date"], "2026-12-01T00:00:00", today=TODAY) == "2026-12-01"
    assert F.coerce(L["available_date"], "Febtember 40", today=TODAY) is None
    assert F.coerce(L["available_date"], "13/45", today=TODAY) is None
    assert F.coerce(L["neighborhood"], "  Mission\n District ", today=TODAY) == "Mission District"
    assert F.coerce(L["price"], None, today=TODAY) is None


def test_units_and_display():
    assert [F.unit_of(u) for u in ("MONTH", "$3,200/mo", "per night", "P1W", "ANN", "", "3200")] == [
        "month", "month", "night", "week", "year", None, None]
    assert F.display(L["price"], 3200.0, currency="USD", unit="month") == "$3,200/mo"
    assert F.display(L["price"], 12.5, currency="EUR") == "€12.50"
    assert F.display(L["price"], 9.0, currency="JPY") == "JPY 9"
    assert F.display(L["beds"], 1.0) == "1" and F.display(L["baths"], 1.5) == "1.5"
    assert F.display(L["rating"], 4.0) == "4.0" and F.display(L["in_stock"], False) == "No"
    assert F.display(L["pets"], ["dogs", "cats"]) == "Dogs OK, Cats OK"
    assert F.display(L["available_date"], "2026-11-01") == "Nov 1, 2026"


def test_entry_and_merge_prefer_better_evidence():
    model = F.entry(L["price"], "3100", status="claimed", origin="model", today=TODAY, url="https://r.test", quote="q")
    page = F.entry(L["price"], 3200, status="verified", origin="page_text", today=TODAY, unit="month")
    ld = F.entry(L["price"], 3250, status="verified", origin="jsonld", today=TODAY)
    assert model["currency"] == "USD" and model["unit"] is None and model["evidence"]["url"] == "https://r.test"
    assert F.entry(L["price"], "n/a", status="verified", origin="x", today=TODAY) is None
    assert F.entry(L["price"], 1, status="unknown", origin="x", today=TODAY) is None
    merged = F.merge({"price": model}, {"price": page})
    assert merged["price"]["value"] == 3200.0
    assert F.merge(merged, {"price": ld})["price"]["value"] == 3250.0
    assert F.merge(merged, {"price": model})["price"]["value"] == 3200.0
    assert F.merge({}, {"made_up": page, "price": "junk"}) == {}


def test_a_claim_must_state_its_value():
    assert F.verify_quote("Rent is $3,200 a month", "Sunny unit. Rent is  $3,200 a month. Dogs ok")
    assert not F.verify_quote("short", "short text")
    assert F.supports(L["price"], 3200, "Rent: $3,200 a month") and not F.supports(L["price"], 3000, "Rent $3,200")
    assert F.supports(L["pets"], ["dogs"], "Dogs welcome") and not F.supports(L["pets"], ["dogs"], "Cats welcome")
    assert F.supports(L["available_date"], "2026-11-01", "available Nov 1")
    assert F.supports(L["available_date"], "2026-10-14", "available now")
    assert not F.supports(L["available_date"], "2026-11-01", "available in December")
    assert F.supports(L["in_stock"], True, "anything")
    assert F.supports(L["neighborhood"], "Mission District", "in the heart of the Mission District")
    assert not F.supports(L["neighborhood"], "Mission District", "in Noe Valley")


def _page(**over):
    return {"url": "https://shop.test/p", "title": "x", "text": "", "products": [], **over}


def test_from_page_reads_one_node_about_the_item():
    product = {"name": "Organic Lip Balm", "brand": "Acme", "rating": {"value": 9, "count": 120, "best": 10},
               "offers": [{"price": "14.99", "currency": "USD", "availability": "InStock", "seller": "Acme"},
                          {"price": "12.50", "currency": "USD", "availability": "OutOfStock"}]}
    out = F.from_page(_page(products=[product]), url="https://shop.test/p", title="Organic Lip Balm", today=TODAY)
    assert out["price"]["value"] == 12.5 and out["in_stock"]["value"] is False
    assert out["rating"]["value"] == 4.5 and out["review_count"]["value"] == 120 and out["brand"]["value"] == "Acme"
    assert all(e["status"] == "verified" and e["evidence"]["origin"] == "jsonld" for e in out.values())
    # A results page with several products is no single item's evidence.
    two = [product, {**product, "name": "Other thing"}]
    assert F.from_page(_page(products=two), url="u", title="Something else", today=TODAY) == {}
    assert "price" in F.from_page(_page(products=two), url="u", title="organic lip balm", today=TODAY)

    listing = {"name": "Sunny 1BR", "bedrooms": 1, "bathrooms": 1, "floor_size": {"value": 60, "unit": "MTK"},
               "pets_allowed": "yes", "amenities": ["Laundry"], "address": "SF, CA",
               "offers": [{"price": 3200, "currency": "USD", "unit": "MONTH", "available_from": "2026-11-01"}]}
    out = F.from_page(_page(listings=[listing]), url="u", title="Sunny", today=TODAY)
    assert out["price"]["unit"] == "month" and out["sqft"]["value"] == 646
    assert out["pets"]["value"] == ["pets_ok"] and out["amenities"]["value"] == ["laundry"]
    assert out["available_date"]["value"] == "2026-11-01" and out["beds"]["value"] == 1
    no_pets = F.from_page(_page(listings=[{**listing, "pets_allowed": "no", "offers": []}]), url="u", title="", today=TODAY)
    assert no_pets["pets"]["value"] == ["none"]

    place = {"name": "Ramen", "rating": {"value": 4.6, "count": 812}, "address": "SF", "cuisine": "Ramen",
             "price_range": "$$", "telephone": "555", "hours": ["Fri 17:00-02:00"]}
    out = F.from_page(_page(places=[place]), url="u", title="Ramen", today=TODAY)
    assert out["hours"]["value"] == "Fri 17:00-02:00" and out["price_level"]["value"] == "$$"
    event = {"name": "Show", "start": "2026-11-02T20:00", "venue": "The Hall",
             "offers": [{"price": 40, "currency": "USD"}]}
    out = F.from_page(_page(events=[event]), url="u", title="Show", today=TODAY)
    assert out["when"]["value"] == "2026-11-02T20:00" and out["price"]["value"] == 40
    loose = F.from_page(_page(offers=[{"price": 99, "currency": "USD", "unit": "NIGHT"}]), url="u", title="", today=TODAY)
    assert loose["price"]["unit"] == "night"


def test_listing_text_scan_is_conservative():
    text = "Sunny 1 bed / 1 ba in the Mission. $3,200/mo. 650 sq ft. Dogs welcome! Cats OK. Available Nov 1."
    out = F.scan_listing_text(text, url="https://apts.test/1", today=TODAY)
    assert out["price"]["value"] == 3200 and out["price"]["unit"] == "month"
    assert out["beds"]["value"] == 1 and out["baths"]["value"] == 1 and out["sqft"]["value"] == 650
    assert out["pets"]["value"] == ["dogs", "cats"] and out["available_date"]["value"] == "2026-11-01"
    assert all(F.verify_quote(e["evidence"]["quote"], text) for e in out.values())
    # A building page listing several units states no one rent.
    many = F.scan_listing_text("Units from $2,900/mo to $3,600/mo. Studio and 2 bed.", url="u", today=TODAY)
    assert "price" not in many and "beds" not in many
    assert F.scan_listing_text("Sorry, no pets. 1 bed", url="u", today=TODAY)["pets"]["value"] == ["none"]
    assert F.scan_listing_text("Studio for rent", url="u", today=TODAY)["beds"]["value"] == 0
    far = "Dogs allowed. " + "x " * 200 + "Cats allowed."
    assert F.scan_listing_text(far, url="u", today=TODAY)["pets"]["value"] == ["dogs"]


def test_check_text_lists_every_value():
    assert "$3,200/mo" in F.check_text({"price": {"display": "$3,200/mo", "value": 3200}, "x": "junk"})


@pytest.mark.parametrize("raw,want", [("yes", ["pets_ok"]), ("no", ["none"]), ("pet-friendly", ["pets_ok"])])
def test_pet_words(raw, want):
    assert F.tags_in("pets", raw) == want
