"""Rich text (services/magazine/rt.py): what the editor types is checked
before it is kept, renders safely, and keeps a Markdown copy. The fixture is
shared with the client (canvas/rt.ts), whose editor reads the same HTML back
into the same documents."""
from __future__ import annotations

import json
import pathlib

import pytest

from app.cappe.services.magazine import pages, rt, story_schema
from app.cappe.services.magazine.rt import RtError, md_to_rt, normalize_rt, render_rt, rt_has_words, rt_to_md
from app.cappe.services.magazine.stories import with_documents
from app.cappe.services.magazine.story_render import render_block

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "magazine_rt_cases.json").read_text(encoding="utf-8"))
# Documents as an editor or a paste might send them, and what is kept of each;
# the client's cleanRt is pinned to the same answers.
CLEAN_CASES = json.loads((FIXTURES / "magazine_rt_clean_cases.json").read_text(encoding="utf-8"))


def _t(text, *marks):
    n = {"type": "text", "text": text}
    if marks:
        n["marks"] = [m if isinstance(m, dict) else {"type": m} for m in marks]
    return n


def _p(*inline):
    return {"type": "paragraph", "content": list(inline)} if inline else {"type": "paragraph"}


def _doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_the_shared_cases(case):
    assert normalize_rt(case["rt"]) == case["rt"]
    assert render_rt(case["rt"]) == case["html"]
    assert rt_to_md(case["rt"]) == case["md"]
    assert (md_to_rt(case["md"]) == case["rt"]) is case["md_reads_back"]


@pytest.mark.parametrize("case", CLEAN_CASES, ids=[c["name"] for c in CLEAN_CASES])
def test_what_is_kept_of_what_is_sent(case):
    assert normalize_rt(case["raw"]) == case["rt"]


def _words(doc):
    return " ".join(n["text"] for n in rt._texts(doc["content"]))


def test_nothing_nested_too_deep_is_lost():
    # Lists and quotes past six levels keep every word, as paragraphs at the sixth.
    keep = next(c for c in CLEAN_CASES if c["name"].startswith("a list nested seven"))
    assert "Keep these interview notes" in _words(keep["rt"]) and "Keep these interview notes" in rt_to_md(keep["rt"])
    # Blocks we don't keep, nested past any sense, are walked without recursion.
    deep = _p(_t("bottom"))
    for _ in range(3_000):
        deep = {"type": "tableCell", "content": [deep]}
    assert normalize_rt(_doc(deep)) == _doc(_p(_t("bottom")))
    wrapped = _t("bottom", "bold")
    for _ in range(3_000):
        wrapped = {"type": "span", "content": [wrapped]}
    assert normalize_rt(_doc(_p(wrapped))) == _doc(_p(_t("bottom", "bold")))


def test_links_keep_web_and_mail_addresses_only():
    for bad in ("javascript:alert(1)", "JAVASCRIPT:alert(1)", "data:text/html,x", "vbscript:x", "/relative",
                "https://ex\nample.com", "https://example.com/\x00", "", "h" * 2_001, None, 7):
        doc = normalize_rt(_doc(_p(_t("click", {"type": "link", "attrs": {"href": bad}}))))
        assert doc == _doc(_p(_t("click"))), bad
    kept = normalize_rt(_doc(_p(_t("x", {"type": "link", "attrs": {"href": "  HTTPS://Example.com/a  ", "target": "_blank",
                                                                       "onclick": "x()", "class": "evil"}}))))
    assert kept["content"][0]["content"][0]["marks"] == [{"type": "link", "attrs": {"href": "HTTPS://Example.com/a"}}]
    html = render_rt(_doc(_p(_t("q", {"type": "link", "attrs": {"href": 'https://example.com/"><script>'}}))))
    assert html == '<p><a rel="nofollow ugc noopener" href="https://example.com/&quot;&gt;&lt;script&gt;">q</a></p>'


def test_only_known_marks_once_each_in_one_order():
    doc = normalize_rt(_doc(_p(
        _t("a", "italic", "bold", "bold", "code", {"type": "textStyle", "attrs": {"color": "red"}}, "nope", 3),
        _t("b", "bold", "italic"),
    )))
    assert doc == _doc(_p(_t("ab", "bold", "italic")))


def test_blocks_we_dont_keep_keep_their_words():
    doc = normalize_rt(_doc(
        {"type": "codeBlock", "content": [_t("print(1)")]},
        {"type": "image", "attrs": {"src": "https://evil.test/x.png"}},
        {"type": "horizontalRule"},
        {"type": "table", "content": [{"type": "tableRow", "content": [{"type": "tableCell", "content": [_p(_t("cell"))]}]}]},
        {"type": "heading", "attrs": {"level": 1}, "content": [_t("Big")]},
        {"type": "heading", "attrs": {"level": 6}},
        "junk", 4, None,
    ))
    assert doc == _doc(_p(_t("print(1)")), _p(_t("cell")),
                       {"type": "heading", "attrs": {"level": 2}, "content": [_t("Big")]},
                       {"type": "heading", "attrs": {"level": 3}})


def test_quotes_and_lists_are_kept_in_shape():
    doc = normalize_rt(_doc(
        {"type": "blockquote", "content": [{"type": "heading", "attrs": {"level": 2}, "content": [_t("Said")]}]},
        {"type": "blockquote", "content": []},
        {"type": "orderedList", "attrs": {"start": -4}, "content": [
            {"type": "listItem", "content": [{"type": "bulletList", "content": [{"type": "listItem", "content": [_p(_t("in"))]}]}]},
            {"type": "listItem", "content": []}, "x"]},
        {"type": "bulletList", "content": []},
    ))
    assert doc == _doc(
        {"type": "blockquote", "content": [_p(_t("Said"))]},
        {"type": "orderedList", "attrs": {"start": 1}, "content": [{"type": "listItem", "content": [
            {"type": "paragraph"}, {"type": "bulletList", "content": [{"type": "listItem", "content": [_p(_t("in"))]}]}]}]},
    )


def test_what_isnt_a_document_and_the_limits():
    assert normalize_rt(None) is None and normalize_rt("<p>x</p>") is None and normalize_rt({"type": "p"}) is None
    assert normalize_rt({"type": "doc", "content": "x"}) == rt.empty_rt()
    assert normalize_rt(_doc(_p(_t("a" * 30), _t("b" * 30))), max_chars=40) == _doc(_p(_t("a" * 30 + "b" * 10)))
    assert normalize_rt(_doc(_p(_t("x\r\ny")))) == _doc(_p(_t("x\ny")))
    with pytest.raises(RtError, match="too long"):
        normalize_rt(_doc(*[_p(_t("w")) for _ in range(rt.MAX_NODES)]), max_chars=10**7)


def test_half_a_character_is_never_kept():
    # An emoji cut in two (a lone surrogate) can't be printed on a page.
    assert normalize_rt(_doc(_p(_t("Dawn \ud83d"), _t("x\udc00y 😀", "bold")))) == _doc(_p(_t("Dawn "), _t("xy 😀", "bold")))
    # Characters are counted whole: an emoji at the limit is kept or cut, never halved.
    assert normalize_rt(_doc(_p(_t("ab😀c"))), max_chars=3) == _doc(_p(_t("ab😀")))


def test_words_and_the_empty_story():
    assert render_rt(None) == "" and render_rt(_doc(_p(), _p(_t("  ")))) == ""
    assert not rt_has_words(None) and not rt_has_words(rt.empty_rt()) and rt_has_words(_doc(_p(_t("x"))))
    assert rt_to_md(None) == "" and md_to_rt(None) == md_to_rt("") == rt.empty_rt()


def test_every_old_story_still_opens():
    # Markdown the base accepted: quotes nested past six, and more list items
    # than the first node budget allowed.
    for md in ("> " * 8 + "hello", "- a\n" * 2_000):
        doc = md_to_rt(md)
        assert "hello" in _words(doc) or _words(doc).count("a") == 2_000
        story = story_schema.normalize_story({"blocks": [{"type": "text", "md": md}]})
        assert story["blocks"][0]["rt"] == doc
        assert with_documents({"blocks": [{"type": "text", "md": md}]})["blocks"][0]["rt"] == doc


def test_markdown_past_the_budget_comes_back_as_plain_paragraphs(monkeypatch):
    monkeypatch.setattr(rt, "MAX_NODES", 8)
    assert md_to_rt("**one** *two*\n\n- three\n- four\n\nfive") == _doc(_p(_t("one two three four")), _p(_t("five")))
    monkeypatch.setattr(rt, "MAX_NODES", 3)
    assert md_to_rt("one\n\ntwo\n\nthree") == _doc(_p(_t("one two three")))


def test_a_document_saved_under_other_limits_still_shows(monkeypatch):
    block = {"type": "text", "md": "From *Markdown*.", "rt": _doc(_p(_t("a")), _p(_t("b")), _p(_t("c")))}
    monkeypatch.setattr(rt, "MAX_NODES", 4)
    assert "From <em>Markdown</em>." in render_block(block, {})
    assert pages._doc(block, "md", "rt") == _doc(_p(_t("From "), _t("Markdown", "italic"), _t(".")))


def test_markdown_stories_become_documents():
    md = "Hello *there*,\nfriend.\n\n## Nets\n\n- one\n- two\n\n> Quoted  \nline\n\n<script>x()</script>"
    assert md_to_rt(md) == _doc(
        _p(_t("Hello "), _t("there", "italic"), _t(", friend.")),
        {"type": "heading", "attrs": {"level": 2}, "content": [_t("Nets")]},
        {"type": "bulletList", "content": [{"type": "listItem", "content": [_p(_t("one"))]},
                                           {"type": "listItem", "content": [_p(_t("two"))]}]},
        {"type": "blockquote", "content": [_p(_t("Quoted"), {"type": "hardBreak"}, _t("line"))]},
        _p(_t("<script>x()</script>")),  # markup in Markdown is words, escaped wherever they are shown
    )
    assert md_to_rt("[a link](javascript:alert(1))") == _doc(_p(_t("a link")))


def test_the_owners_editor_gets_a_document_for_every_rich_field():
    stored = {"blocks": [
        {"type": "text", "md": "**Old**"},
        {"type": "text", "md": "stale", "rt": _doc(_p(_t("Kept")))},
        {"type": "sidebar", "title": "T", "md": "Side"},
        {"type": "qa", "items": [{"q": "Q", "a_md": "A"}, {"q": "Q2", "a_md": "x", "a_rt": _doc(_p(_t("Mine")))}, "junk"]},
        {"type": "divider"}, "junk",
    ]}
    blocks = with_documents(stored)["blocks"]
    assert blocks[0]["rt"] == _doc(_p(_t("Old", "bold")))
    assert blocks[1]["rt"] == _doc(_p(_t("Kept")))
    assert blocks[2]["rt"] == _doc(_p(_t("Side")))
    assert [i["a_rt"] for i in blocks[3]["items"]] == [_doc(_p(_t("A"))), _doc(_p(_t("Mine")))]
    assert blocks[4] == {"type": "divider"} and len(blocks) == 5
    assert "rt" not in stored["blocks"][0]  # what was stored is left alone
