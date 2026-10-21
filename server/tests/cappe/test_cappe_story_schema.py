"""Story blocks, layouts and rich text (services/magazine, migration cappemag02).

What each block pins:

  * a story's blocks are reshaped before they are stored: unknown keys dropped,
    enums defaulted, lengths capped, pictures by library id only;
  * the limits an owner is told about (block count, one paywall, cover first);
  * every layout starts with blocks that pass the schema;
  * the story's words in reading order, and the reading time;
  * rich text: raw HTML, scripts and `javascript:` links can't reach the page;
    h1 becomes h2; links are nofollow;
  * the client's block list (storyBlocks.ts) matches the server's.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_story_schema.py -q
"""
import pathlib
import re
from uuid import uuid4

import pytest

from app.cappe.services.magazine import richtext, story_schema
from app.cappe.services.magazine.stories import reading_stats, story_text
from app.cappe.services.magazine.topics import TOPICS, normalize_topic, topic_label

A, B = str(uuid4()), str(uuid4())
CLIENT_BLOCKS = pathlib.Path(__file__).resolve().parents[3] / "client" / "src" / "cappe" / "magazine" / "storyBlocks.ts"


def test_blocks_are_reshaped_and_unknown_keys_dropped():
    out = story_schema.normalize_story({"blocks": [
        {"type": "cover", "asset_id": A, "style": "banner", "tone": "dark", "focal": {"x": "120", "y": -4}, "junk": 1},
        {"type": "text", "md": "  Hello  ", "dropcap": "yes", "columns": 4, "variant": "shout"},
        {"type": "photo", "asset_id": None, "caption": "x" * 600, "size": "huge"},
        {"type": "photos", "layout": "pair", "items": [{"asset_id": B, "caption": "c"}, "nope"]},
        {"type": "quote", "text": "Q", "attribution": "Who", "style": "odd"},
        {"type": "sidebar", "title": "T", "md": "m"},
        {"type": "qa", "items": [{"q": "Why?", "a_md": "Because."}]},
        {"type": "divider", "extra": True},
        {"type": "paywall"},
    ]})
    blocks = out["blocks"]
    assert blocks[0] == {"type": "cover", "asset_id": A, "style": "overlay", "tone": "dark", "focal": {"x": 100, "y": 0}}
    assert blocks[1] == {"type": "text", "md": "Hello", "dropcap": True, "columns": 1, "variant": "body", "align": "left"}
    assert blocks[2]["asset_id"] is None and len(blocks[2]["caption"]) == 500 and blocks[2]["size"] == "column"
    assert blocks[3]["items"] == [{"asset_id": B, "caption": "c"}]
    assert blocks[4]["style"] == "big"
    assert blocks[7] == {"type": "divider"} and blocks[8] == {"type": "paywall"}


def test_an_empty_story_is_fine_and_other_shapes_are_not():
    assert story_schema.normalize_story(None) == {"blocks": []}
    assert story_schema.normalize_story({}) == {"blocks": []}
    with pytest.raises(story_schema.StoryError, match="list of blocks"):
        story_schema.normalize_story({"blocks": "x"})
    with pytest.raises(story_schema.StoryError, match="isn't a kind"):
        story_schema.normalize_story({"blocks": [{"type": "video"}]})
    with pytest.raises(story_schema.StoryError, match="isn't a kind"):
        story_schema.normalize_story({"blocks": ["text"]})


def test_pictures_are_library_ids_never_urls():
    with pytest.raises(story_schema.StoryError, match="library"):
        story_schema.normalize_story({"blocks": [{"type": "photo", "asset_id": "https://evil.test/x.jpg"}]})


def test_the_limits_an_owner_is_told_about():
    with pytest.raises(story_schema.StoryError, match="at most 120"):
        story_schema.normalize_story({"blocks": [{"type": "divider"}] * 121})
    with pytest.raises(story_schema.StoryError, match="one place"):
        story_schema.normalize_story({"blocks": [{"type": "paywall"}, {"type": "paywall"}]})
    with pytest.raises(story_schema.StoryError, match="first block"):
        story_schema.normalize_story({"blocks": [{"type": "divider"}, {"type": "cover"}]})
    with pytest.raises(story_schema.StoryError, match="at most 12"):
        story_schema.normalize_story({"blocks": [{"type": "photos", "items": [{}] * 13}]})
    with pytest.raises(story_schema.StoryError, match="at most 40"):
        story_schema.normalize_story({"blocks": [{"type": "qa", "items": [{}] * 41}]})
    with pytest.raises(story_schema.StoryError, match="too long"):
        story_schema.normalize_story({"blocks": [{"type": "text", "md": "x" * 20_000}] * 12})


@pytest.mark.parametrize("layout", list(story_schema.LAYOUTS))
def test_every_layout_starts_with_valid_blocks(layout):
    content = story_schema.starter_content(layout)
    assert story_schema.normalize_story(content) == content
    assert content["blocks"][0]["type"] == "cover"


def test_unknown_layout_falls_back_to_standard():
    assert story_schema.normalize_layout("zine") == "standard"
    assert story_schema.starter_content("zine") == story_schema.starter_content("standard")


def test_referenced_assets_include_the_cover_and_every_group_item():
    content = {"blocks": [{"type": "photo", "asset_id": A}, {"type": "photos", "items": [{"asset_id": B}, {"asset_id": None}]}]}
    assert story_schema.referenced_asset_ids(content, "c0ffee00-0000-4000-8000-000000000001") == {
        A, B, "c0ffee00-0000-4000-8000-000000000001"}
    assert story_schema.cover_block({"blocks": [{"type": "text"}]}) is None


def test_story_text_reads_in_order_and_counts_words():
    content = {"blocks": [
        {"type": "cover", "asset_id": None},
        {"type": "text", "md": "# Dawn\n\nThe **boats** left at [six](https://x.test)."},
        {"type": "quote", "text": "We never sleep", "attribution": "Ana"},
        {"type": "photo", "asset_id": None, "caption": "Nets drying."},
        {"type": "sidebar", "title": "Facts", "md": "- 40 boats"},
        {"type": "qa", "items": [{"q": "Why?", "a_md": "Tradition."}]},
    ]}
    text = story_text(content)
    assert text.split("\n\n") == ["Dawn", "The boats left at six.", "“We never sleep” — Ana", "Nets drying.",
                                  "Facts\n40 boats", "Why?\nTradition."]
    assert reading_stats(text) == (17, 1)
    assert reading_stats("") == (0, 0)
    assert reading_stats("word " * 500) == (500, 3)


def test_rich_text_is_safe():
    html = richtext.render_md("# Big\n\nHi <script>alert(1)</script> <img src=x onerror=alert(1)> "
                              "[go](javascript:alert(1)) [ok](https://x.test \"t\")\n\n#### Small\n\n> q\n\n- a")
    assert "<script" not in html and "<img" not in html and "javascript:" not in html
    assert "img src=x onerror=alert(1)&gt;" in html  # the tag is text on the page, not markup
    assert "<h2>Big</h2>" in html and "<h3>Small</h3>" in html
    assert '<a rel="nofollow ugc noopener" href="https://x.test" title="t">ok</a>' in html
    assert "&lt;script&gt;" in html  # the owner's text survives, as text
    assert "<blockquote>" in html and "<li>a</li>" in html
    assert richtext.render_md("   ") == "" and richtext.render_md(None) == ""


def test_rich_text_keeps_line_breaks_and_drops_tags_it_doesnt_know():
    html = richtext.render_md("one  \ntwo `code` ![pic](https://x.test/p.jpg)\n\n---\n\n    pre block")
    assert "<p>one<br>\ntwo code </p>" in html  # the break stays; the code and img tags go, the words stay
    assert "<img" not in html and "<hr" not in html and "<pre" not in html and "pre block" in html
    assert 'href="HTTPS://x.test"' in richtext.render_md("[a](HTTPS://x.test)")  # scheme check is case-blind
    assert richtext.render_md("[a](http://x.test/\x01)") == '<p><a rel="nofollow ugc noopener">a</a></p>'


def test_rich_text_survives_odd_markup():
    parser = richtext._Allowlist()
    parser.feed("<p>a<em>b</p>c</em><span/>d")  # an unclosed em, a stray end tag, a self-closing unknown
    parser.close()
    assert parser.result() == "<p>a<em>b</em></p>cd"


def test_markdown_to_text_strips_the_marks():
    assert richtext.md_to_text("## Hi **there** `x` [a](b) ![i](u)\n> q\n1. one") == "Hi there x a i\nq\none"


def test_topics_are_a_fixed_list():
    assert normalize_topic(" Fashion ") == "fashion"
    assert normalize_topic("crypto") is None and normalize_topic(None) is None
    assert topic_label("food") == "Food & drink" and topic_label(None) == ""
    assert len(TOPICS) >= 20


def test_the_client_knows_the_same_blocks_and_layouts():
    src = CLIENT_BLOCKS.read_text()
    blocks = re.search(r"export const STORY_BLOCKS = \[(.*?)\] as const", src, re.S).group(1)
    assert set(re.findall(r"'([a-z_]+)'", blocks)) == set(story_schema.STORY_BLOCKS)
    layouts = re.search(r"export const STORY_LAYOUTS = \[(.*?)\] as const", src, re.S).group(1)
    assert set(re.findall(r"'([a-z_]+)'", layouts)) == set(story_schema.LAYOUTS)
