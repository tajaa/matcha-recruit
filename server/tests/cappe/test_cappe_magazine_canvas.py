"""The owner's editor on the page (render/assets/editor.js): the edit renders
of a story and an issue carry the editor and its markers, and only they do;
every field the page marks is one the dashboard's editor accepts (client
canvas/fields.ts); the edit previews take unsaved stories through the same
checks as a save; and the Markdown the editor writes renders as the fixture
both sides share says."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.cappe.routes import issues as issues_mod  # noqa: E402
from app.cappe.services.magazine import issue_pages, pages  # noqa: E402
from app.cappe.services.magazine.issue_schema import normalize_contents, normalize_cover  # noqa: E402
from app.cappe.services.magazine.richtext import render_md  # noqa: E402
from app.cappe.services.magazine.story_render import render_block, render_blocks  # noqa: E402
from tests.cappe.test_cappe_magazine_issues import BASE, _client, _owner, limits, paid_row  # noqa: E402,F401
from tests.cappe.test_cappe_magazine_routes import (  # noqa: E402
    ASSET,
    OTHER_ASSET,
    POST,
    SENTINEL,
    SITE,
    _blog_client,
    _owner_conn,
)

ROOT = Path(__file__).resolve().parents[3]
FIELDS_TS = ROOT / "client/src/cappe/magazine/canvas/fields.ts"
MD_CASES = json.loads((ROOT / "server/tests/cappe/fixtures/magazine_md_cases.json").read_text(encoding="utf-8"))
WHEN = datetime(2026, 10, 21, tzinfo=timezone.utc)

A = {"a1": {"id": "a1", "url": "https://cdn.example.test/a.jpg", "width": 1200, "height": 800, "alt": "Boats",
            "credit_line": "Photo: Ana", "variants": {}}}
SITE_D = {"name": "Bloom", "slug": "bloom", "theme_config": {}, "meta_config": {}}
MAG = {"name": "Salt & Light", "masthead_style": "classic", "paid_enabled": True, "price_cents": 500}

EVERY_BLOCK = {
    "text": {"type": "text", "md": "Words."},
    "photo": {"type": "photo", "asset_id": "a1", "caption": "Dawn", "size": "column",
              "overlays": [{"x": 50, "y": 50, "text": "One"}, {"x": 20, "y": 80, "text": ""}]},
    "photos": {"type": "photos", "layout": "pair", "items": [{"asset_id": "a1", "caption": "One"},
                                                              {"asset_id": None, "caption": ""}]},
    "quote": {"type": "quote", "text": "", "attribution": ""},
    "sidebar": {"type": "sidebar", "title": "", "md": ""},
    "qa": {"type": "qa", "items": [{"q": "Why?", "a_md": "Because."}, {"q": "", "a_md": ""}]},
    "divider": {"type": "divider"},
    "paywall": {"type": "paywall"},
}


def _ts_list(src: str, name: str) -> str:
    return src[src.index(f"export const {name}"):]


def allowlist() -> dict[str, set[str]]:
    """BLOCK_FIELDS from the client's fields.ts."""
    body = _ts_list(FIELDS_TS.read_text(encoding="utf-8"), "BLOCK_FIELDS")
    body = body[:body.index("\n}\n")]
    return {m.group(1): set(re.findall(r"'([^']+)'", m.group(2)))
            for m in re.finditer(r"^\s+(\w+): \[([^\]]*)\],$", body, re.M)}


def marked(html: str) -> set[str]:
    """Every field the page marks, with item indexes as `#`."""
    return {re.sub(r"\.\d+\.", ".#.", f) for f in re.findall(r'data-mz-f="([^"]+)"', html)}


def story(**over):
    blocks = [{"type": "cover", "asset_id": "a1", "style": "stacked"}, {"type": "text", "md": "Free opening."},
              {"type": "paywall"}, {"type": "text", "md": SENTINEL}]
    return {"id": "p1", "slug": "low-tide", "title": "Low tide", "kicker": "", "excerpt": "Boats.", "format": "blocks",
            "access": "paid", "layout": "standard", "byline": "Ana", "published_at": WHEN,
            "content": {"blocks": blocks}, "reading_minutes": 3, **over}


def render_story(edit: bool, **over) -> str:
    return pages.render_story(SITE_D, [], MAG, story(**over), A, more=[], more_covers={}, origin="https://x.test", edit=edit)


def render_issue(edit: bool) -> str:
    stories = [{**story(id=str(POST)), "section": "Features", "contents_line": None},
               {**story(id="p2", slug="salt", access="free", content={"blocks": [{"type": "text", "md": "Salt."}]}),
                "section": "Features", "contents_line": "A line"}]
    cover = normalize_cover({"lines": [{"text": "Low tide", "post_id": str(POST)}]}, story_ids={str(POST)})
    issue = {"id": "i1", "number": 3, "title": "Tide", "cover": cover, "contents": normalize_contents({}), "released_at": WHEN}
    return issue_pages.render_issue(SITE_D, [], MAG, issue, stories, A, origin="https://x.test", edit=edit)


# ── what the page marks ──────────────────────────────────────────────────────

def test_every_block_marks_exactly_the_fields_the_editor_takes():
    allowed = allowlist()
    assert set(allowed) == {"cover", *EVERY_BLOCK}
    for kind, block in EVERY_BLOCK.items():
        html = render_block(block, A, edit=True)
        assert marked(html) == allowed[kind], kind
        rich = set(re.findall(r'data-mz-f="([^"]+)" data-mz-k="rich"', html))
        assert {re.sub(r"\.\d+\.", ".#.", f) for f in rich} <= {"md", "items.#.a_md"}, kind
    assert allowed["cover"] == set()  # the cover's words are the story's own
    src = FIELDS_TS.read_text(encoding="utf-8")
    story_fields = set(re.findall(r"'(@\w+)'", _ts_list(src, "STORY_FIELDS").split("\n")[0]))
    assert marked(render_story(True)) >= story_fields == {"@title", "@kicker", "@excerpt", "@byline"}


def test_blocks_are_numbered_by_their_place_in_the_story_and_empty_ones_shown():
    blocks = [{"type": "text", "md": "One."}, {"type": "text", "md": ""}, {"type": "photo", "asset_id": None}]
    edit = render_blocks(blocks, A, edit=True)
    assert re.findall(r'data-mz-b="(\d+)"', edit) == ["0", "1", "2"]
    assert 'data-mz-ph="Write here"' in edit and "Choose a picture" in edit and "data-mz-pick" in edit
    plain = render_blocks(blocks, A)
    assert "data-mz-" not in plain and "Choose a picture" not in plain and "One." in plain


def test_only_edit_renders_carry_the_editor():
    for edit_html, plain_html in ((render_story(True), render_story(False)), (render_issue(True), render_issue(False))):
        for mark in ("data-mz-edit", "data-mz-f=", "data-mz-b=", "mz-goto", ".mze-bar"):
            assert mark in edit_html and mark not in plain_html, mark
    # The owner's page has no paywall: it shows the paid part to edit.
    assert "cz-shopper-refresh" in render_story(False) and "cz-shopper-refresh" not in render_story(True)
    # Only the owner's previews ask for the editor; the reader's routes never do.
    for mod in ("render.py", "reader_magazines.py", "public/blog.py", "public/magazine.py"):
        path = ROOT / "server/app/cappe/routes" / mod
        if path.exists():
            assert "edit=" not in path.read_text(encoding="utf-8"), mod
    owners = {p.name for p in (ROOT / "server/app/cappe/routes").rglob("*.py") if "edit=body.edit" in p.read_text(encoding="utf-8")}
    assert owners == {"blog.py", "issues.py"}


def test_a_paid_story_is_whole_only_in_its_owners_edit_render():
    edit, plain = render_story(True), render_story(False)
    assert SENTINEL in edit and "Subscribers only from here" in edit
    assert SENTINEL not in plain and "Subscribers only from here" not in plain
    assert "mz-paywall-mark" not in plain
    issue_edit, issue_plain = render_issue(True), render_issue(False)
    assert SENTINEL in issue_edit and SENTINEL not in issue_plain


def test_an_issue_marks_its_cover_and_contents():
    html = render_issue(True)
    fields = set(re.findall(r'data-mz-f="([^"]+)"', html))
    assert {"issue:lines.0.text", "issue:lines.0.sub", "issue:issue_line.text", "issue:contents.heading",
            f"issue:line:{POST}", "issue:line:p2", f"issue:section:{POST}"} <= fields
    assert 'data-mzc-el="line:0"' in html and 'data-mzc-el="masthead"' in html and "data-mz-art" in html
    assert "data-mz-contents" in html and f'data-mz-s="{POST}"' in html and 'data-mz-s="p2"' in html
    assert "data-mz-focal" in html
    assert 'data-mz-f="issue:' not in render_issue(False)


# ── the Markdown the editor writes ───────────────────────────────────────────

@pytest.mark.parametrize("case", MD_CASES, ids=[c["name"] for c in MD_CASES])
def test_the_editors_markdown_renders_as_the_fixture_says(case):
    assert render_md(case["md"]) == case["rendered"]


# ── the previews ─────────────────────────────────────────────────────────────

def test_the_story_preview_marks_the_page_only_when_asked(monkeypatch):
    blocks = {"blocks": [{"type": "cover", "asset_id": str(ASSET)}, {"type": "text", "md": "Hello."}]}
    with _blog_client(monkeypatch, _owner_conn()) as client:
        edit = client.post(f"/sites/{SITE}/stories/preview", json={"title": "Dawn", "content": blocks, "edit": True})
        plain = client.post(f"/sites/{SITE}/stories/preview", json={"title": "Dawn", "content": blocks})
    assert edit.status_code == plain.status_code == 200 and edit.headers["cache-control"] == "no-store"
    assert 'data-mz-f="@title"' in edit.text and "mz-goto" in edit.text and 'data-mz-s="preview"' in edit.text
    assert 'data-mz-f="' not in plain.text and "mz-goto" not in plain.text


def _issue_conn():
    return _owner(fetch={"SELECT id, title, status FROM cappe_posts": [{"id": PAID_ID, "title": "Paid", "status": "draft"}],
                         "FROM cappe_posts WHERE site_id = $1 AND id = ANY": [paid_row()],
                         "FROM cappe_assets WHERE site_id = $1 AND id = ANY": []})


PAID_ID = paid_row()["id"]


def test_the_issue_edit_preview_shows_unsaved_stories_checked_as_a_save(monkeypatch, limits):  # noqa: F811
    body = {"issue_id": None, "number": 7, "cover": {}, "edit": True, "stories": [{"post_id": str(PAID_ID)}]}
    unsaved = {"title": "The night market, later", "content": {"blocks": [{"type": "text", "md": "Unsaved **words**."},
                                                                          {"type": "paywall"},
                                                                          {"type": "text", "md": SENTINEL}]}}
    with _client(monkeypatch, _issue_conn()) as client:
        res = client.post(f"{BASE}/preview", json={**body, "stories_content": {str(PAID_ID): unsaved,
                                                                               str(uuid4()): unsaved}})
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store"
    assert "The night market, later" in res.text and "Unsaved <strong>words</strong>." in res.text
    assert SENTINEL in res.text and "mz-goto" in res.text  # the owner's page: the paid part, to edit
    assert ("cappe_issue_edit_preview", issues_mod.EDIT_PREVIEWS_PER_HOUR) in limits
    assert ("cappe_issue_preview", issues_mod.PREVIEWS_PER_HOUR) not in limits
    # A picture that isn't in the site's library, or a block that isn't one: refused.
    foreign = {"content": {"blocks": [{"type": "photo", "asset_id": str(OTHER_ASSET)}]}}
    with _client(monkeypatch, _issue_conn()) as client:
        res = client.post(f"{BASE}/preview", json={**body, "stories_content": {str(PAID_ID): foreign}})
    assert res.status_code == 422 and "library" in res.json()["detail"]
    with _client(monkeypatch, _issue_conn()) as client:
        res = client.post(f"{BASE}/preview", json={**body, "stories_content": {str(PAID_ID): {"content": {"blocks": [{"type": "nope"}]}}}})
    assert res.status_code == 422
    # Without `edit`: the reader's view, the paid part kept out even with unsaved words.
    with _client(monkeypatch, _issue_conn()) as client:
        res = client.post(f"{BASE}/preview", json={**body, "edit": False, "stories_content": {str(PAID_ID): unsaved}})
    assert res.status_code == 200 and SENTINEL not in res.text and 'data-mz-f="' not in res.text
