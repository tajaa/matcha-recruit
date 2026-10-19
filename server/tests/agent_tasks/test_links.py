"""A store's own link out of whatever URL a finding carried."""
from app.matcha.services.matcha_work.agent_tasks.research import links as L

GOOGLE_PRODUCT = "https://www.google.com/search?ibp=oshop&q=organic lip balm&prds=catalogid:1,productid:2"


def test_google_pages_are_never_a_stores_own():
    assert L.is_google("https://shopping.google.co.uk/p") and L.is_google(GOOGLE_PRODUCT)
    # Ad clicks: following one would register a paid click.
    assert L.is_google("https://www.googleadservices.com/pagead/aclk?sa=L") and L.is_google("https://ad.doubleclick.net/x")
    assert L.store_link("https://www.googleadservices.com/pagead/aclk?sa=L") is None
    assert not L.is_google("https://www.drbronner.com/x") and not L.is_google(None)
    assert L.store_link("https://www.google.com/url?url=https://shop.test/a") == "https://shop.test/a"
    assert L.store_link("https://www.google.com/url?q=https://www.google.com/x") is None
    assert L.store_link("https://www.google.com/aclk?x=1") is None and L.store_link("ftp://x.test") is None
    assert L.store_link("https://shop.test/a") == "https://shop.test/a" and L.store_link(None) is None
