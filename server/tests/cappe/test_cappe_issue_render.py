"""An issue's cover, contents and book (services/magazine/issue_render.py,
issue_pages.py), and a story linking to its issue."""
import json
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test")

from app.cappe.services.magazine import issue_pages, issue_render, pages  # noqa: E402
from app.cappe.services.magazine.issue_schema import normalize_contents, normalize_cover  # noqa: E402

NOW = datetime(2026, 10, 21, 9, tzinfo=timezone.utc)
SENTINEL = "ZXQ-subscribers-only-ZXQ"
SITE = {"name": "Salt", "slug": "salt", "theme_config": {}, "meta_config": {}}
MAG = {"name": "Salt & Light", "masthead_style": "classic", "accent": "#b45309", "paid_enabled": True, "price_cents": 500}


def asset(**over):
    base = {"id": uuid4(), "url": "https://cdn.example.test/a.jpg", "alt": "Boats", "credit_line": "Photo: Ana Ruiz",
            "license": "own", "ai_generated": False, "source_url": None, "width": 1600, "height": 1000, "variants": {}}
    return {**base, **over}


def post(slug, **over):
    base = {"id": uuid4(), "site_id": uuid4(), "slug": slug, "title": slug.replace("-", " ").title(),
            "excerpt": "A dek.", "kicker": None, "topic": "city", "layout": "standard", "byline": "Ana Ruiz",
            "access": "free", "format": "blocks", "content": {"blocks": [{"type": "text", "md": f"Words of {slug}."}]},
            "cover_asset_id": None, "reading_minutes": 2, "published_at": NOW, "updated_at": NOW,
            "section": None, "contents_line": None}
    return {**base, **over}


def issue(cover=None, contents=None, **over):
    return {"id": uuid4(), "number": 3, "title": "The tide issue", "status": "released", "released_at": NOW,
            "cover": cover or normalize_cover({}), "contents": contents or normalize_contents({}), **over}


def test_an_element_style_places_and_sets_its_words():
    line = normalize_cover({"lines": [{"text": "x", "x": 5, "y": 34.25, "w": 42, "size": 5.6, "color": "accent",
                                       "align": "right", "weight": "black", "case": "upper", "italic": True,
                                       "tracking": "wide", "font": "body"}]})["lines"][0]
    assert issue_render.element_style(line) == (
        "left:5%;top:34.3%;width:42%;font-size:5.6cqw;color:var(--mz-accent);text-align:right;font-weight:900;"
        "letter-spacing:0.12em;font-family:var(--mz-b);text-transform:uppercase;font-style:italic")


def test_the_cover_prints_its_words_escaped_and_its_credit_always():
    a = asset()
    story = str(uuid4())
    cover = normalize_cover({"photo": {"asset_id": str(a["id"]), "focal": {"x": 20, "y": 70}, "zoom": 150,
                                       "filter": "bw"},
                             "scrim": {"kind": "bottom", "strength": 60},
                             "lines": [{"text": "<script>alert(1)</script>", "sub": "Sub & more", "post_id": story,
                                        "box": "solid", "box_color": "#000000"},
                                       {"text": "Unlinked"}]})
    html = issue_render.cover_html(cover, mag=MAG, number=3, when=NOW, asset=a, hrefs={story: "#mz-s-x"})
    assert "<script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "Sub &amp; more" in html
    assert '<a class="mzc__link" href="#mz-s-x">' in html and html.count("mzc__link") == 1
    assert '<span class="mzc__box" style="background:#000000">' in html
    assert "object-position:20% 70%;transform:scale(1.5);transform-origin:20% 70%" in html
    assert 'class="mzc__photo mz-filter--bw"' in html and "to top,rgba(0,0,0,0.600)" in html
    assert "Salt &amp; Light" in html and "No. 3 · October 2026" in html
    assert 'class="mzc__credit mzc__credit--br mzc__credit--light"' in html and "Photo: Ana Ruiz" in html
    assert 'data-mzc-el="masthead"' in html and 'data-mzc-el="line:1"' in html


def test_an_ai_cover_says_so_and_a_cropped_cc_by_one_says_cropped():
    ai = asset(ai_generated=True, credit_line="Whatever the owner typed", license="ai")
    cover = normalize_cover({"photo": {"asset_id": str(ai["id"])}})
    html = issue_render.cover_html(cover, mag=MAG, number=1, asset=ai, link_credit=False)
    assert "AI illustration" in html and "Whatever the owner typed" not in html
    by = asset(license="by", credit_line="Photo: Kim / CC BY 2.0", source_url="https://example.com/p")
    html = issue_render.cover_html(normalize_cover({"photo": {"asset_id": str(by["id"])}}), mag=MAG, number=1, asset=by)
    assert "Photo: Kim / CC BY 2.0 (cropped)" in html and 'href="https://example.com/p"' in html
    # Where the cover is itself a link, the credit is plain words.
    plain = issue_render.cover_html(normalize_cover({}), mag=MAG, number=1, asset=by, link_credit=False)
    assert "<a " not in plain and "(cropped)" in plain


def test_a_hidden_issue_line_and_no_photo_and_each_scrim():
    cover = normalize_cover({"issue_line": {"hidden": True}, "background": "accent", "scrim": {"kind": "none"}})
    html = issue_render.cover_html(cover, mag=MAG, number=2)
    assert "mzc__issue" not in html and "mzc__photo" not in html and "mzc__scrim" not in html
    assert "--mzc-bg:var(--mz-accent)" in html and "mzc__credit" not in html
    assert issue_render._scrim({"kind": "full", "strength": 40}) == '<div class="mzc__scrim" style="background:rgba(0,0,0,0.300)"></div>'
    assert "to bottom" in issue_render._scrim({"kind": "top", "strength": 40})
    assert issue_render._scrim({"kind": "top", "strength": 0}) == ""
    # A picture without a safe address draws nothing.
    assert issue_render._photo(cover, asset(url="javascript:alert(1)"), size="card", eager=False) == ""


def test_the_contents_group_sections_and_keep_each_heading_with_its_first_row():
    stories = [post("one", section="Features", kicker="Food"), post("two", section="Features"),
               post("three", section=None, contents_line="Our own line", byline="Kim")]
    entries = [{"post": s, "asset": asset() if i == 0 else None, "section": s["section"], "line": s["contents_line"]}
               for i, s in enumerate(stories)]
    html = issue_render.contents_html(normalize_contents({"show_bylines": True}), entries, label="No. 3")
    assert html.count('class="mz-contents__group"') == 2 and html.count("mz-contents__keep") == 1
    keep = re.search(r'<div class="mz-contents__keep">(.*?)</div>', html).group(1)
    assert "Features" in keep and 'href="#mz-s-one"' in keep and 'href="#mz-s-two"' not in keep
    assert 'data-mz-pageno="one"' in html and "Our own line" in html and "By Kim" in html and "Food" in html
    assert html.count("mz-toc__pic") == 1  # the others have no picture
    grid = issue_render.contents_html(normalize_contents({"layout": "grid", "show_numbers": False,
                                                          "show_pictures": False, "show_deks": False}),
                                      entries, label="No. 3")
    keep = re.search(r'<div class="mz-contents__keep">(.*?)</div>', grid).group(1)
    assert 'href="#mz-s-two"' in keep  # a grid's first row is two
    assert "mz-contents--nonum" in grid and "data-mz-pageno" not in grid and "mz-toc__pic" not in grid
    assert "A dek." not in grid and "Our own line" in grid  # the writer's own line still shows
    feature = issue_render.contents_html(normalize_contents({"layout": "feature", "heading": ""}), entries, label="x")
    assert feature.count("mz-toc--feature") == 1 and "mz-contents__heading" not in feature


def _paid_story():
    return post("night-market", access="paid", content={"blocks": [
        {"type": "text", "md": "Free opening."}, {"type": "paywall"}, {"type": "text", "md": SENTINEL}]})


def test_the_issue_is_one_book_and_its_paid_parts_stay_out():
    cover_asset = asset()
    free, paid = post("low-tide", section="Features"), _paid_story()
    stories = [free, paid]
    cover = normalize_cover({"photo": {"asset_id": str(cover_asset["id"])},
                             "lines": [{"text": "Low tide", "post_id": str(free["id"])}]})
    html = issue_pages.render_issue(SITE, [], MAG, issue(cover), stories, {str(cover_asset["id"]): cover_asset},
                                    origin="https://salt.gummfit.test")
    assert SENTINEL not in html and "Free opening." in html and "Words of low-tide." in html
    assert 'data-mz-book data-mz-issue' in html and 'data-mz-flow' in html and "data-mz-skip" in html
    assert html.index('class="mz-issue__face"') < html.index('class="mz-issue" data-mz-flow')
    assert 'id="mz-s-low-tide"' in html and 'id="mz-s-night-market"' in html
    assert '<a class="mzc__link" href="#mz-s-low-tide">' in html and 'href="#mz-s-night-market"' in html
    # One paywall per paid story, none carrying the single page's id, and one script.
    assert html.count("data-mz-paywall ") == 1 and 'id="mz-paywall"' not in html
    assert 'data-mz-paid="night-market" hidden' in html
    assert html.count("// A paid story's paywall") == 1 and html.count("// A story's pages") == 1
    assert 'class="mz-story__issue"' not in html and 'class="mz-story__topic"' not in html  # a story page's own
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1))
    assert ld["@type"] == "PublicationIssue" and ld["issueNumber"] == "3" and ld["isAccessibleForFree"] is False
    assert ld["hasPart"][0] == {"@type": "Article", "headline": "Low Tide",
                                "url": "https://salt.gummfit.test/stories/low-tide"}
    assert ld["hasPart"][-1]["cssSelector"] == ".mz-paid" and ld["image"] == ["https://cdn.example.test/a.jpg"]
    assert "Salt &amp; Light, No. 3 — The tide issue" in html and "In this issue: Low Tide, Night Market" in html
    assert ".mzc{" in html  # the issue's CSS is on the page


def test_a_free_issue_has_no_paywall_script():
    html = issue_pages.render_issue(SITE, [], MAG, issue(title=None), [post("low-tide")], {}, origin="")
    assert "data-mz-paywall" not in html and "// A paid story's paywall" not in html
    assert "isAccessibleForFree" not in html and "Salt &amp; Light, No. 3</h1>" in html


def test_the_archive_and_the_front_pages_lead():
    a = asset()
    cover = normalize_cover({"photo": {"asset_id": str(a["id"])}})
    issues = [issue(cover, number=4), issue(cover, number=3, title=None)]
    html = issue_pages.render_archive(SITE, [], MAG, issues, {str(a["id"]): a}, page=2, has_more=True, origin="https://s.test")
    assert html.count('class="mz-issuecard"') == 2 and 'href="/issues/4"' in html and 'href="/issues/3"' in html
    assert 'rel="prev" href="/issues"' in html and 'rel="next" href="/issues?page=3"' in html
    assert "The tide issue" in html and "No. 3 · October 2026" in html
    # A cover inside a link prints its credit as words.
    assert re.search(r'<a class="mz-issuecard"[^>]*>(?:(?!</a>).)*<a ', html, re.S) is None
    assert 'rel="prev" href="/issues?page=2"' in issue_pages.render_archive(
        SITE, [], MAG, issues, {}, page=3, has_more=False, origin="")

    stories = [post(f"s{i}") for i in range(10)]
    lead = issue_pages.current_issue_html(MAG, issues[0], stories, {str(a["id"]): a})
    assert 'href="/issues/4"' in lead and lead.count("<li>") == 8 and 'href="/issues/4#mz-s-s0"' in lead
    assert issue_pages.current_issue_image(issues[0], {str(a["id"]): a}) == "https://cdn.example.test/a.jpg"
    front = pages.render_front(SITE, [], MAG, lead=post("lead"), posts=[], covers={}, topics=[], page=1,
                               has_more=False, origin="", current_html=lead)
    assert 'class="mz-current"' in front and 'class="mz-card mz-card--lead"' not in front and ".mzc{" in front
    plain = pages.render_front(SITE, [], MAG, lead=post("lead"), posts=[], covers={}, topics=[], page=1,
                               has_more=False, origin="")
    assert 'class="mz-card mz-card--lead"' in plain and ".mzc{" not in plain


def test_a_story_in_an_issue_links_to_its_place_in_it():
    html = pages.render_story(SITE, [], MAG, post("low-tide"), {}, more=[], more_covers={}, origin="",
                              issue={"number": 3, "title": "The tide issue"})
    assert '<p class="mz-story__issue">From No. 3 — <a href="/issues/3#mz-s-low-tide">read it in the issue</a></p>' in html
    assert 'class="mz-story__issue"' not in pages.render_story(SITE, [], MAG, post("low-tide"), {}, more=[], more_covers={},
                                                       origin="")
    # A paid story's own page: one wall, with the id its script and tests know.
    paid = pages.render_story(SITE, [], MAG, _paid_story(), {}, more=[], more_covers={}, origin="")
    assert paid.count('id="mz-paywall"') == 1 and paid.count("// A paid story's paywall") == 1 and SENTINEL not in paid
