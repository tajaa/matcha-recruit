"""Homes, places, events and loose offers on a page; task photos on our CDN."""
import io
import json
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.core.services.safe_fetch import FetchedResponse
from app.matcha.services.matcha_work.agent_card import images
from app.matcha.services.matcha_work.agent_card.page_extract import extract_page, page_urls


def _html(*nodes):
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(n)}</script>' for n in nodes)
    return f"<html><head><title>x</title>{scripts}</head><body><p>hello</p></body></html>".encode()


def test_product_pages_keep_their_exact_shape():
    page = extract_page(_html({"@type": "Product", "name": "Balm", "offers": {"price": 9}}), "https://shop.test/p")
    assert set(page) == {"url", "title", "description", "og_image", "products", "text", "text_truncated"}
    # A loose offer next to a product is the product's, not a separate one.
    page = extract_page(_html({"@type": "Product", "name": "Balm"}, {"@type": "Offer", "price": 9}), "https://s.test")
    assert "offers" not in page


def test_homes_places_events_and_offers():
    listing = {"@type": "RealEstateListing", "url": "/l/1", "name": "Sunny 1BR",
               "offers": {"@type": "Offer", "price": 3200, "priceCurrency": "USD",
                          "priceSpecification": [{"@type": "UnitPriceSpecification", "unitText": "MONTH"}],
                          "availabilityStarts": "2026-11-01", "url": "https://apts.test/apply"},
               "mainEntity": {"@type": "Apartment", "numberOfBedrooms": 1, "numberOfBathroomsTotal": 1,
                              "floorSize": {"value": 650, "unitCode": "FTK"}, "petsAllowed": True,
                              "amenityFeature": [{"name": "Laundry"}, {"name": "Gym", "value": False}, "Parking"],
                              "address": {"addressLocality": "San Francisco", "addressRegion": "CA",
                                          "addressCountry": {"name": "US"}},
                              "image": [{"url": "/a.jpg"}]}}
    place = {"@type": ["Restaurant", "LocalBusiness"], "name": "Ramen", "servesCuisine": ["Ramen", "Japanese"],
             "priceRange": "$$", "telephone": "555", "aggregateRating": {"ratingValue": 4.6, "reviewCount": 812},
             "openingHours": ["Mo-Fr 17:00-23:00"], "acceptsReservations": True,
             "hasMenu": {"url": "/menu"}, "url": "https://ramen.test/",
             "openingHoursSpecification": [{"dayOfWeek": ["https://schema.org/Saturday"], "opens": "17:00",
                                            "closes": "02:00"}, "junk", {"dayOfWeek": "Sunday"}]}
    event = {"@type": "Event", "name": "Show", "startDate": "2026-11-02T20:00", "url": "/e",
             "location": {"name": "The Hall", "address": {"addressLocality": "Oakland"}},
             "offers": [{"price": 40, "priceCurrency": "USD"}]}
    loose = {"@type": "Offer", "price": None, "priceSpecification": {"price": 99, "unitText": "NIGHT"},
             "itemOffered": {"name": "Cabin"}, "priceCurrency": "USD"}
    page = extract_page(_html(listing, place, event, loose), "https://apts.test/x")
    [home] = page["listings"]
    assert home["type"] == "RealEstateListing" and home["bedrooms"] == 1 and home["pets_allowed"] == "yes"
    assert home["amenities"] == ["Laundry", "Parking"] and home["floor_size"] == {"value": 650, "unit": "FTK"}
    assert home["offers"][0]["unit"] == "MONTH" and home["offers"][0]["available_from"] == "2026-11-01"
    assert home["address"] == "San Francisco, CA, US" and home["images"] == ["https://apts.test/a.jpg"]
    [ramen] = page["places"]
    assert ramen["cuisine"] == "Ramen, Japanese" and ramen["rating"]["count"] == 812
    assert ramen["hours"] == ["Mo-Fr 17:00-23:00", "Saturday 17:00-02:00"] and ramen["menu_url"] == "https://apts.test/menu"
    assert ramen["accepts_reservations"] == "yes"
    [show] = page["events"]
    assert show["venue"] == "The Hall" and show["address"] == "Oakland" and show["offers"][0]["price"] == 40
    [cabin] = page["offers"]
    assert cabin["price"] == 99 and cabin["unit"] == "NIGHT" and cabin["item"] == "Cabin"
    assert {"https://apts.test/l/1", "https://apts.test/apply", "https://ramen.test/", "https://apts.test/e"} <= page_urls(page)


def _png():
    out = io.BytesIO()
    Image.new("RGB", (40, 40), (1, 2, 3)).save(out, format="PNG")
    return out.getvalue()


class _Storage:
    def __init__(self, url="https://cdn.test/x.webp"):
        self.url = url

    async def upload_file(self, data, filename, prefix, content_type):
        return self.url


@pytest.mark.asyncio
async def test_rehost_urls_keeps_order_limit_and_drops_failures(monkeypatch):
    monkeypatch.setattr(images, "get_storage", lambda: _Storage())
    good = FetchedResponse(url="u", final_url="u", status=200, content_type="image/png", body=_png(), truncated=False)
    bad = FetchedResponse(url="u", final_url="u", status=404, content_type="text/html", body=b"", truncated=False)
    monkeypatch.setattr(images, "fetch_public", AsyncMock(side_effect=[bad, good, good]))
    wanted = [{"source_url": "https://img.test/1", "page_url": "p", "alt": "a"}, {"source_url": "ftp://x"},
              "junk", {"source_url": "https://img.test/2", "page_url": "p"}, {"source_url": "https://img.test/3"}]
    kept, warnings = await images.rehost_urls(wanted, prefix="t", limit=1)
    assert kept == [{"url": "https://cdn.test/x.webp", "page_url": "p", "alt": ""}] and len(warnings) == 1

    monkeypatch.setattr(images, "get_storage", lambda: _Storage("s3://private/x"))
    monkeypatch.setattr(images, "fetch_public", AsyncMock(return_value=good))
    kept, warnings = await images.rehost_urls(wanted, prefix="t", limit=3)
    assert kept == [] and "no public URL" in warnings[0]

    monkeypatch.setattr(images, "_rehost_one", AsyncMock(side_effect=TimeoutError))
    kept, warnings = await images.rehost_urls(wanted, prefix="t", limit=3)
    assert kept == [] and len(warnings) == 3
    assert await images.rehost_urls(wanted, prefix="t", limit=3, total_seconds=0) == ([], [])


def test_page_links_are_same_site_detail_links():
    from app.matcha.services.matcha_work.agent_card.page_extract import page_links

    html = b"""<html><body>
      <nav><a href="/apartments/sf/rentals">All San Francisco rentals</a></nav>
      <ol>
        <li><a href="/apa/d/san-francisco-sunny-1br/123.html">Sunny 1BR, dogs OK - $3,200</a></li>
        <li><a href="https://www.list.test/apa/d/sf-loft/456.html#photos">Mission loft with yard</a></li>
        <li><a href="/apa/d/san-francisco-sunny-1br/123.html">Sunny 1BR again</a></li>
        <li><a href="https://other.test/apa/d/x/789.html">Off-site listing elsewhere</a></li>
        <li><a href="/a">Short path link</a></li><li><a href="/apa/d/long/path/1">Go</a></li>
        <li><a href="mailto:x@list.test">Email the landlord</a></li>
      </ol>
      <footer><a href="/about/the-company">About the company</a></footer></body></html>"""
    links = page_links(html, "https://list.test/search/apa")
    assert links == [
        {"text": "Sunny 1BR, dogs OK - $3,200", "url": "https://list.test/apa/d/san-francisco-sunny-1br/123.html"},
        {"text": "Mission loft with yard", "url": "https://www.list.test/apa/d/sf-loft/456.html"},
    ]
    assert len(page_links(html, "https://list.test/search/apa", limit=1)) == 1


@pytest.mark.asyncio
async def test_the_research_loader_vouches_for_links():
    from app.core.services.safe_fetch import UnsafeURL
    from app.matcha.services.matcha_work.agent_tasks.research import fetch

    body = b'<html><body><p>' + b"word " * 4000 + b'</p><a href="/apa/d/one/1.html">Sunny 1BR</a></body></html>'
    ok = FetchedResponse(url="https://list.test/s", final_url="https://list.test/s", status=200,
                         content_type="text/html", body=body, truncated=False)
    page, urls = await fetch.fetch_page("https://list.test/s", fetch=AsyncMock(return_value=ok))
    assert page["links"] == [{"text": "Sunny 1BR", "url": "https://list.test/apa/d/one/1.html"}]
    assert "https://list.test/apa/d/one/1.html" in urls and len(json.dumps(page)) <= fetch.MAX_OUTPUT_CHARS + 50
    assert page["text_truncated"] is True
    for fetcher, error in (
        (AsyncMock(side_effect=UnsafeURL("private")), "Refused"),
        (AsyncMock(side_effect=RuntimeError("x")), "Could not load"),
        (AsyncMock(return_value=FetchedResponse(url="u", final_url="u", status=403, content_type="text/html",
                                                 body=b"", truncated=False)), "HTTP 403"),
        (AsyncMock(return_value=FetchedResponse(url="u", final_url="u", status=200, content_type="image/png",
                                                 body=b"", truncated=False)), "Not an HTML page"),
    ):
        page, urls = await fetch.fetch_page("https://list.test/s", fetch=fetcher)
        assert error in page["error"] and urls == set()


@pytest.mark.asyncio
async def test_a_page_that_breaks_the_reader_is_an_error(monkeypatch):
    from app.matcha.services.matcha_work.agent_tasks.research import fetch

    ok = FetchedResponse(url="u", final_url="u", status=200, content_type="text/html", body=b"<p>x</p>", truncated=False)
    monkeypatch.setattr(fetch, "_read", lambda *_: (_ for _ in ()).throw(RecursionError()))
    page, urls = await fetch.fetch_page("u", fetch=AsyncMock(return_value=ok))
    assert "structure" in page["error"] and urls == set()
