import json

from app.matcha.services.matcha_work.agent_card.page_extract import (
    MAX_TEXT_CHARS,
    extract_page,
    page_urls,
)


def _html(ld=None, head="", body="<p>Soft and nourishing.</p>"):
    script = f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld is not None else ""
    return f"<html><head><title>Balm</title>{head}{script}</head><body>{body}<script>evil()</script></body></html>".encode()


def test_product_json_ld_with_offers_and_rating():
    ld = {
        "@context": "https://schema.org", "@type": "Product", "name": "Organic Balm",
        "brand": {"@type": "Brand", "name": "Brand"},
        "image": ["/img/a.jpg", {"url": "https://cdn.example/b.jpg"}],
        "aggregateRating": {"ratingValue": "4.6", "reviewCount": "812"},
        "offers": {"@type": "Offer", "price": "4.99", "priceCurrency": "USD",
                   "availability": "https://schema.org/InStock", "url": "/buy/balm"},
        "review": [{"reviewBody": "Love it", "author": {"name": "Sam"}, "reviewRating": {"ratingValue": 5}}],
    }
    page = extract_page(_html(ld), "https://shop.example/balm")
    product = page["products"][0]
    assert product["name"] == "Organic Balm" and product["brand"] == "Brand"
    assert product["images"] == ["https://shop.example/img/a.jpg", "https://cdn.example/b.jpg"]
    assert product["rating"] == {"value": "4.6", "count": "812", "best": 5}
    assert product["offers"][0] == {
        "price": "4.99", "currency": "USD", "availability": "InStock",
        "url": "https://shop.example/buy/balm", "seller": None,
    }
    assert product["reviews"][0]["author"] == "Sam"
    assert page_urls(page) == {"https://shop.example/balm", "https://shop.example/buy/balm"}
    assert "evil" not in page["text"]


def test_graph_form_and_aggregate_offer():
    ld = {"@graph": [
        {"@type": "WebPage", "name": "x"},
        {"@type": ["Product"], "name": "Balm", "offers": {
            "@type": "AggregateOffer", "lowPrice": 3.5, "priceCurrency": "USD",
            "offers": [{"@type": "Offer", "price": 3.5, "url": "https://shop.example/a"}],
        }},
    ]}
    page = extract_page(_html(ld), "https://shop.example/p")
    offers = page["products"][0]["offers"]
    assert offers[0]["url"] == "https://shop.example/a"
    assert any(o["price"] == 3.5 for o in offers)


def test_og_fallback_and_malformed_json_ld_ignored():
    head = '<meta property="og:image" content="/og.jpg"><meta property="og:title" content="OG Title">' \
           '<script type="application/ld+json">{not json</script>'
    page = extract_page(_html(head=head), "https://blog.example/post")
    assert page["products"] == []
    assert page["og_image"] == "https://blog.example/og.jpg"
    assert page["title"] == "OG Title"
    assert "Soft and nourishing." in page["text"]


def test_text_is_capped():
    page = extract_page(_html(body="<p>" + "word " * 5000 + "</p>"), "https://x.example/")
    assert len(page["text"]) == MAX_TEXT_CHARS and page["text_truncated"]
