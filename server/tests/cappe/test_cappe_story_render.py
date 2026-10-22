"""Story pages as rendered (services/magazine/figures, story_render, pages).

What each block pins:

  * every picture prints the credit from its library row; an AI picture
    always reads "AI illustration" whatever its row says; a cropped CC BY
    cover says it was cropped;
  * responsive `srcset`/`sizes`, width/height, lazy except the cover;
  * photo groups keep each picture's own shape (flex weights);
  * the first text block gets the drop cap, the others don't;
  * a paid story's page carries only its free part, and never the words
    after the paywall — nor does the feed;
  * Article JSON-LD survives a `</script>` in a headline; Open Graph article
    tags; the magazine's fonts and stylesheet are on the page;
  * the front: masthead, lead story, cards, topics, pager; the feed is RSS.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_story_render.py -q
"""
from datetime import datetime, timezone
from uuid import uuid4

from app.cappe.services.magazine import figures, pages, story_render

SITE = {"name": "Bloom", "slug": "bloom", "theme_config": {}, "meta_config": {}, "policies": []}
NAV = [{"slug": "home", "title": "Home"}]
MAG = {"site_id": uuid4(), "enabled": True, "name": "Salt & Light", "tagline": "Stories from the harbour",
       "masthead_style": "classic", "accent": "#A3E635", "topics": ["city", "food"], "front_at_root": False,
       "nav_label": "Magazine", "about": "About *us*.", "cover_post_id": None}
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
SENTINEL = "ZXQ-only-for-subscribers-ZXQ"


def asset(**over):
    base = {"id": uuid4(), "kind": "upload", "url": "https://cdn.example.test/a.jpg", "alt": "Boats at dawn",
            "caption": None, "credit_line": "Photo: Ana Ruiz", "license": "own", "ai_generated": False,
            "source_url": None, "width": 1600, "height": 1000,
            "variants": {"webp": [{"w": 480, "url": "https://cdn.example.test/w480.webp"},
                                  {"w": 960, "url": "https://cdn.example.test/w960.webp"}],
                         "share": {"w": 1200, "url": "https://cdn.example.test/share.jpg"}}}
    return {**base, **over}


def post(**over):
    base = {"id": uuid4(), "slug": "harbour-at-dawn", "title": "The harbour at dawn", "excerpt": "Forty boats.",
            "kicker": "Dispatch", "topic": "city", "layout": "standard", "byline": "Ana Ruiz", "access": "free",
            "format": "blocks", "content": {"blocks": []}, "cover_asset_id": None, "reading_minutes": 4,
            "published_at": NOW, "updated_at": NOW, "body": None}
    return {**base, **over}


# ── figures ──────────────────────────────────────────────────────────────────

def test_a_picture_prints_the_credit_from_its_row_and_links_its_source():
    html = figures.figure_html(asset(source_url="https://flickr.test/p/1", caption="Nets drying."))
    assert '<span class="mz-cap">Nets drying.</span>' in html
    assert '<a href="https://flickr.test/p/1" rel="nofollow noopener" target="_blank">Photo: Ana Ruiz</a>' in html


def test_an_ai_picture_is_always_credited_as_ai():
    html = figures.figure_html(asset(ai_generated=True, credit_line="Photo: totally real", source_url="https://x.test"))
    assert "AI illustration" in html and "totally real" not in html
    assert "<a " not in html  # no source link on an AI image
    assert figures.credit_text(asset(ai_generated=True)) == "AI illustration"


def test_a_cropped_cc_by_picture_says_so_but_an_own_photo_does_not():
    assert figures.credit_text(asset(license="by", credit_line="Jo / CC BY 2.0"), cropped=True) == "Jo / CC BY 2.0 (cropped)"
    assert figures.credit_text(asset(license="own"), cropped=True) == "Photo: Ana Ruiz"
    assert figures.credit_text(asset(credit_line=None)) == ""


def test_the_img_is_responsive_and_lazy_except_when_eager():
    html = figures.img_html(asset(), size="wide")
    assert 'srcset="https://cdn.example.test/w480.webp 480w, https://cdn.example.test/w960.webp 960w"' in html
    assert f'sizes="{figures.SIZES["wide"]}"' in html
    assert 'width="1600" height="1000"' in html and 'loading="lazy"' in html
    assert 'fetchpriority="high"' in figures.img_html(asset(), eager=True)
    assert 'alt="Boats at dawn"' in html


def test_an_unsafe_url_or_an_empty_slot_renders_nothing():
    assert figures.figure_html(None) == ""
    assert figures.figure_html(asset(url="javascript:alert(1)")) == ""
    assert figures.img_html(asset(variants={"webp": [{"w": "x", "url": "https://a.test"}]})).count("srcset") == 0


def test_the_share_image_is_the_jpeg_copy():
    assert figures.share_image(asset()) == "https://cdn.example.test/share.jpg"
    assert figures.share_image(asset(variants={})) == "https://cdn.example.test/a.jpg"
    assert figures.share_image(None) is None


# ── story blocks ─────────────────────────────────────────────────────────────

def test_photo_groups_keep_each_pictures_shape():
    a, b = asset(width=1000, height=1000), asset(id=uuid4(), url="https://cdn.example.test/b.jpg", width=2000, height=1000)
    assets = {str(a["id"]): a, str(b["id"]): b}
    html = story_render.render_block({"type": "photos", "layout": "pair",
                                      "items": [{"asset_id": str(a["id"])}, {"asset_id": str(b["id"])}]}, assets)
    assert 'class="mz-photos mz-row mz-row--pair"' in html
    assert 'style="flex:1.0000 1 0%"' in html and 'style="flex:2.0000 1 0%"' in html
    mosaic = story_render.render_block({"type": "photos", "layout": "mosaic", "items": [{"asset_id": str(a["id"])}]}, assets)
    assert "mz-cols--mosaic" in mosaic
    assert story_render.render_block({"type": "photos", "items": [{"asset_id": "missing"}]}, assets) == ""


def test_only_the_first_text_block_gets_the_drop_cap():
    html = story_render.render_blocks([
        {"type": "cover", "asset_id": None},
        {"type": "text", "md": "First.", "dropcap": True},
        {"type": "text", "md": "Second.", "dropcap": True, "columns": 2},
    ], {})
    assert html.count("mz-dropcap") == 1 and html.index("mz-dropcap") < html.index("Second.")
    assert "mz-text--cols" in html


def test_quotes_sidebars_interviews_and_dividers():
    html = story_render.render_blocks([
        {"type": "quote", "text": "We never sleep", "attribution": "<Ana>", "style": "side"},
        {"type": "sidebar", "title": "Facts", "md": "- 40 boats"},
        {"type": "qa", "items": [{"q": "Why?", "a_md": "**Tradition.**"}, {"q": "", "a_md": ""}]},
        {"type": "divider"},
        {"type": "quote", "text": ""},
        {"type": "paywall"},
    ], {})
    assert '<blockquote class="mz-pull mz-pull--side"><p>We never sleep</p><cite>&lt;Ana&gt;</cite></blockquote>' in html
    assert "<aside class=\"mz-sidebar\"><h3>Facts</h3>" in html and "<li>40 boats</li>" in html
    assert html.count("mz-qa__item") == 1 and "<strong>Tradition.</strong>" in html
    assert '<hr class="mz-divider" />' in html


def test_the_paywall_splits_the_story():
    blocks = [{"type": "text", "md": "a"}, {"type": "paywall"}, {"type": "text", "md": "b"}]
    assert story_render.split_at_paywall(blocks) == ([blocks[0]], [blocks[2]])
    four = [{"type": "text", "md": str(i)} for i in range(4)]
    assert story_render.split_at_paywall(four, preview_blocks=3) == (four[:3], four[3:])


def test_the_cover_spread_styles():
    p = post()
    a = asset(license="by", credit_line="Jo / CC BY 2.0")
    overlay = story_render.cover_html(p, {"style": "overlay", "tone": "dark", "focal": {"x": 30, "y": 70}}, a, byline_html="")
    assert "mz-cover--overlay mz-tone--dark" in overlay and "object-position:30% 70%" in overlay
    assert "Jo / CC BY 2.0 (cropped)" in overlay and 'fetchpriority="high"' in overlay
    stacked = story_render.cover_html(p, {"style": "stacked"}, a, byline_html="")
    # In the book every cover is cut to fit its page, so a stacked one is cropped too.
    assert "Jo / CC BY 2.0 (cropped)" in stacked and "object-position:50% 50%" in stacked
    assert '<p class="mz-kicker">Dispatch</p>' in stacked and "<h1 class=\"mz-headline\">The harbour at dawn</h1>" in stacked
    assert "mz-cover--plain" in story_render.cover_html(p, None, None, byline_html="")


# ── pages ────────────────────────────────────────────────────────────────────

def test_a_story_page_has_the_magazines_fonts_article_tags_and_structured_data():
    a = asset()
    p = post(title='Dawn </script><script>alert(1)</script>', content={"blocks": [
        {"type": "cover", "asset_id": str(a["id"]), "style": "stacked"},
        {"type": "text", "md": "The **boats**.", "dropcap": True},
    ]})
    html = pages.render_story(SITE, NAV, MAG, p, {str(a["id"]): a}, more=[post(slug="two", title="Two")],
                              more_covers={}, origin="https://bloom.gummfit.com")
    assert "family=Bodoni%20Moda" in html and "family=Spectral" in html and ".mz-dropcap" in html
    assert "--mz-accent:#A3E635" in html
    assert '<meta property="og:type" content="article" />' in html
    assert '<meta property="article:section" content="City life" />' in html
    assert '<meta property="og:image" content="https://cdn.example.test/share.jpg" />' in html
    assert '<link rel="canonical" href="https://bloom.gummfit.com/stories/harbour-at-dawn" />' in html
    assert '<link rel="alternate" type="application/rss+xml"' in html
    # The headline's </script> can't close the JSON-LD block.
    ld = html[html.index('<script type="application/ld+json">'):]
    ld = ld[:ld.index("</script>")]
    assert "</script>" not in ld and "\\u003c/script\\u003e" in ld and '"@type": "Article"' in ld
    assert "Photo: Ana Ruiz" in html and "<strong>boats</strong>" in html
    assert 'href="/stories/two"' in html and "More from Salt &amp; Light" in html
    assert "4 min read" in html and "By Ana Ruiz" in html


def test_a_story_reads_as_pages_turned_left_and_right():
    p = post(content={"blocks": [{"type": "text", "md": "Words."}]})
    html = pages.render_story(SITE, NAV, MAG, p, {}, more=[post(slug="two", title="Two")], more_covers={}, origin="https://b.test")
    reader = html[html.index('<div class="mz-reader" data-mz-book>'):]
    book = reader[:reader.index("</script>")]
    # The article sits in the pages; the arrows, the page count and the script
    # that turns them come with it. "More from" stays below the book.
    assert book.index('data-mz-prev') < book.index('<div class="mz-book" tabindex="0" role="region"') \
        < book.index('<div class="mz-pages"><article class="mz-story') < book.index("data-mz-next") < book.index("data-mz-folio")
    assert "Words." in book and "ArrowRight" in book and "More from" not in book
    assert 'aria-label="Previous page" hidden' in book and 'aria-label="Next page" hidden' in book
    # The book's look ships in the page's stylesheet.
    assert ".mz-pages{" in html and "column-fill:auto" in html
    # A matte cover and glossy pages: the light lies over the spread, outside
    # the pages that move; the pages end on a marker the script places on a
    # whole spread, and the script marks the spread showing.
    assert '<div class="mz-spread"><div class="mz-book"' in book
    assert '<i class="mz-end" aria-hidden="true"></i></div></div><div class="mz-gloss" aria-hidden="true"></div></div>' in book
    assert '.mz-reader[data-mz-at="0"] .mz-gloss{opacity:0}' in html and ".mz-pages::before{" in html
    assert "data-mz-at" in book and "getClientRects" in book and "end.style.left" in book


def test_a_long_pull_quote_is_set_to_fit_a_page():
    short = story_render.render_block({"type": "quote", "text": "The work had its own clock."}, {})
    long = story_render.render_block({"type": "quote", "text": "x" * (story_render.LONG_QUOTE + 1)}, {})
    assert 'class="mz-pull mz-pull--big"' in short and "mz-pull--long" in long


def test_a_picture_tells_the_page_its_shape():
    a = asset(width=2000, height=1000)
    html = story_render.photo_html({"type": "photo", "asset_id": str(a["id"]), "size": "column"}, a)
    assert 'style="--mz-ar:2.0000"' in html
    cropped = story_render.photo_html({"type": "photo", "asset_id": str(a["id"]), "size": "column",
                                      "crop": {"x": 0, "y": 0, "w": 50, "h": 100}}, a)
    assert 'style="--mz-ar:1.0000"' in cropped
    circle = story_render.photo_html({"type": "photo", "asset_id": str(a["id"]), "size": "column", "shape": "circle"}, a)
    assert 'style="--mz-ar:1.0000"' in circle
    # Without its size the picture has no ratio to give; the page falls back.
    unsized = story_render.photo_html({"type": "photo", "asset_id": str(a["id"]), "size": "column"}, asset(width=None, height=None))
    assert "--mz-ar" not in unsized and "<img" in unsized


def test_a_dispatch_is_a_news_article_and_a_paid_story_hides_its_paid_part():
    p = post(layout="dispatch", access="paid", content={"blocks": [
        {"type": "text", "md": "Free words."},
        {"type": "paywall"},
        {"type": "text", "md": SENTINEL},
    ]})
    html = pages.render_story(SITE, NAV, MAG, p, {}, more=[], more_covers={}, origin="https://b.test")
    assert '"@type": "NewsArticle"' in html
    assert "Free words." in html and SENTINEL not in html
    assert 'class="mz-paywall mz-measure" data-mz-paid' in html


def test_a_legacy_markdown_post_renders_as_one_text_block():
    p = post(format="markdown", body="Plain *words*.", content={})
    html = pages.render_story(SITE, NAV, MAG, p, {}, more=[], more_covers={}, origin="https://b.test")
    assert "Plain <em>words</em>." in html


def test_the_front_page():
    a = asset()
    lead = post(id=uuid4(), slug="lead", title="Lead story", content={"blocks": [{"type": "cover", "asset_id": str(a["id"])}]})
    cards = [post(id=uuid4(), slug=f"s{i}", title=f"Story {i}", topic="food") for i in range(2)]
    html = pages.render_front(SITE, NAV, MAG, lead=lead, posts=cards, covers={str(lead["id"]): a},
                              topics=["city", "food"], page=1, has_more=True, origin="https://b.test")
    assert '<h1 class="mz-masthead__name"><a href="/magazine">Salt &amp; Light</a></h1>' in html
    assert "Stories from the harbour" in html
    assert "mz-card mz-card--lead" in html and 'href="/stories/lead"' in html
    assert html.count('class="mz-card"') == 2 and 'href="/topics/food"' in html
    assert '<a rel="next" href="/magazine?page=2">Older stories</a>' in html and 'rel="prev"' not in html
    assert "About <em>us</em>." in html
    assert '<meta property="og:image" content="https://cdn.example.test/share.jpg" />' in html

    page2 = pages.render_front(SITE, NAV, {**MAG, "front_at_root": True}, lead=None, posts=[], covers={},
                               topics=[], page=2, has_more=False, origin="https://b.test")
    assert '<a rel="prev" href="/">Newer stories</a>' in html.replace("x", "x") or 'rel="prev"' in page2
    assert "on their way" in page2 and "About <em>us</em>." not in page2
    assert '<a href="/">Salt &amp; Light</a>' in page2


def test_a_topic_page_marks_the_current_topic():
    html = pages.render_topic(SITE, NAV, MAG, "food", posts=[post(topic="food")], covers={}, topics=["city", "food"],
                              page=1, has_more=False, origin="https://b.test")
    assert '<a href="/topics/food" aria-current="page">Food &amp; drink</a>' in html
    assert '<h1 class="mz-topic-title">Food &amp; drink</h1>' in html
    assert "<title>Food &amp; drink — Salt &amp; Light</title>" in html


def test_the_feed_is_rss_with_full_free_stories_and_only_the_dek_of_paid_ones():
    a = asset()
    free = post(slug="free", cover_asset_id=a["id"], content={"blocks": [{"type": "text", "md": "Whole story."}]})
    paid = post(slug="paid", access="paid", excerpt="Just the dek", content={"blocks": [{"type": "text", "md": SENTINEL}]})
    xml = pages.render_feed(MAG, [free, paid], {str(a["id"]): a}, origin="https://b.test")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"')
    assert "<title>Salt &amp; Light</title>" in xml and "<link>https://b.test/magazine</link>" in xml
    assert "Whole story." in xml and "Photo: Ana Ruiz" in xml
    assert SENTINEL not in xml and "Just the dek" in xml
    assert "<pubDate>Tue, 20 Oct 2026 09:00:00 +0000</pubDate>" in xml
    assert '<guid isPermaLink="true">https://b.test/stories/free</guid>' in xml


def test_plain_words_from_bracket_heavy_text_take_linear_time():
    # Each `[` used to start a scan to the end of the text: quadratic, seconds
    # for one long story (CodeQL py/polynomial-redos).
    import time

    from app.cappe.services.magazine.richtext import md_to_text

    started = time.monotonic()
    md_to_text("[\\" * 50_000 + "[](" * 30_000)
    assert time.monotonic() - started < 0.5
    assert md_to_text("See [the harbour](https://example.com/a(b)) and ![x](y.png)") == "See the harbour and x"
    assert md_to_text("A [link](https://example.com) here") == "A link here"
