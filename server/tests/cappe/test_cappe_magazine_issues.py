"""Issues in print: the reader's pages (routes/render.py) and the owner's API
(routes/issues.py), with the library refusing to delete a cover's picture."""
import asyncio
import json
from uuid import uuid4

import pytest

from app.cappe.routes import issues as issues_mod  # noqa: E402
from app.cappe.routes import render as render_mod  # noqa: E402
from app.cappe.routes import uploads as uploads_mod  # noqa: E402
from app.cappe.services.magazine import issues as mag_issues  # noqa: E402
from app.cappe.services.magazine.issue_schema import normalize_contents, normalize_cover  # noqa: E402
from tests._helpers.routes import Queue, route_client  # noqa: E402
from tests.cappe.test_cappe_magazine_routes import (  # noqa: E402
    ACCOUNT,
    ASSET,
    ASSET_ROW,
    MAG_ROW,
    NOW,
    POST,
    SENTINEL,
    SITE,
    SITE_ROW,
    Conn,
    Ctx,
    _render_conn,
    _request,
    _wire,
    story_row,
)

ISSUE, OTHER_ISSUE = uuid4(), uuid4()
PAID = uuid4()


def issue_row(**over):
    cover = normalize_cover({"photo": {"asset_id": str(ASSET)},
                             "lines": [{"text": "The harbour", "post_id": str(POST)}]})
    base = {"id": ISSUE, "site_id": SITE, "number": 3, "title": "The tide issue", "status": "released",
            "released_at": NOW, "cover": json.dumps(cover), "contents": json.dumps(normalize_contents({})),
            "cover_image": None, "hidden_at": None, "hidden_reason": None, "created_at": NOW, "updated_at": NOW}
    return {**base, **over}


def in_issue(row, section=None, line=None, position=0):
    return {**row, "position": position, "section": section, "contents_line": line}


def paid_row():
    return story_row(id=PAID, slug="night-market", title="The night market", access="paid", content=json.dumps(
        {"blocks": [{"type": "text", "md": "Free opening."}, {"type": "paywall"}, {"type": "text", "md": SENTINEL}]}))


# ── the reader's pages ───────────────────────────────────────────────────────

def _issue_render_conn(*, issue=None, stories=None, issues=None, for_story=None, magazine=MAG_ROW):
    conn = _render_conn(magazine=magazine)
    conn.set("fetchrow", "FROM cappe_magazine_issues WHERE site_id = $1 AND number = $2", issue)
    conn.set("fetchrow", "FROM cappe_magazine_issues WHERE site_id = $1 AND status = 'released'", issue)
    conn.set("fetchrow", "SELECT i.number, i.title FROM cappe_magazine_issue_stories", for_story)
    conn.set("fetch", "FROM cappe_magazine_issue_stories s JOIN cappe_posts p", stories or [])
    conn.set("fetch", "FROM cappe_magazine_issues WHERE site_id = $1 AND status = 'released' AND hidden_at IS NULL "
                      "ORDER BY number DESC LIMIT", issues or [])
    conn.set("fetch", "SELECT number, updated_at FROM cappe_magazine_issues", issues or [])
    # The specific needles above must win over the catch-alls _render_conn registered.
    for kind in ("fetchrow", "fetch"):
        table = conn._tables[kind]
        table["FROM cappe_magazine_issue"] = table.pop("FROM cappe_magazine_issue")
    return conn


@pytest.fixture
def cache(monkeypatch):
    store = {}

    async def cache_get(_redis, key):
        return store.get(key)

    async def cache_set(_redis, key, value, ttl):
        store[key] = value

    monkeypatch.setattr(render_mod, "cache_get", cache_get)
    monkeypatch.setattr(render_mod, "cache_set", cache_set)
    return store


def test_an_issue_is_one_book_and_its_paid_part_is_never_cached(monkeypatch, cache):
    stories = [in_issue(story_row(), "Features"), in_issue(paid_row(), position=1)]
    _wire(monkeypatch, _issue_render_conn(issue=issue_row(), stories=stories))
    monkeypatch.setattr(render_mod, "get_redis_cache", lambda: object())
    res = asyncio.run(render_mod.issue_page(3, _request("/issues/3")))
    html = res.body.decode()
    assert res.status_code == 200 and 'data-mz-issue' in html and 'id="mz-s-harbour-at-dawn"' in html
    assert '<a class="mzc__link" href="#mz-s-harbour-at-dawn">' in html and "Features" in html
    assert "Free opening." in html and 'data-mz-paid="night-market" hidden' in html
    cached = cache[f"cappe:render:{SITE}:__mag__:business:issue:3"]
    assert SENTINEL not in html and SENTINEL not in cached


def test_an_issue_that_isnt_out_is_not_found(monkeypatch):
    _wire(monkeypatch, _issue_render_conn(issue=None))
    assert asyncio.run(render_mod.issue_page(4, _request("/issues/4"))).status_code == 404
    assert asyncio.run(render_mod.issue_page(0, _request("/issues/0"))).status_code == 404


def test_the_archive_pages_through_the_issues(monkeypatch):
    issues = [issue_row(number=n, id=uuid4()) for n in range(30, 5, -1)]
    _wire(monkeypatch, _issue_render_conn(issues=issues))
    res = asyncio.run(render_mod.issues_page(_request("/issues")))
    html = res.body.decode()
    assert res.status_code == 200 and html.count('class="mz-issuecard"') == mag_issues.ARCHIVE_PAGE
    assert 'href="/issues/30"' in html and 'href="/issues/6"' not in html and 'href="/issues?page=2"' in html
    _wire(monkeypatch, _issue_render_conn(issues=[]))
    assert asyncio.run(render_mod.issues_page(_request("/issues"))).status_code == 404


def test_the_current_issue_is_the_highest_number_out_not_the_last_released():
    # No. 2 withdrawn for a typo and released again isn't the current issue.
    conn = Conn(fetchrow={"FROM cappe_magazine_issues WHERE site_id": None})
    asyncio.run(mag_issues.current_issue(conn, SITE))
    assert "ORDER BY number DESC" in conn.sql_for("fetchrow")[0]


def test_the_front_leads_with_the_current_issue_and_keeps_every_story_below(monkeypatch):
    conn = _issue_render_conn(issue=issue_row(), stories=[in_issue(story_row())])
    _wire(monkeypatch, conn)
    html = asyncio.run(render_mod.magazine_front(_request("/magazine"))).body.decode()
    assert 'class="mz-current"' in html and 'href="/issues/3"' in html and 'href="/issues/3#mz-s-harbour-at-dawn"' in html
    assert 'class="mz-card mz-card--lead"' not in html and 'href="/stories/harbour-at-dawn"' in html
    # The lead names a few stories: it reads their titles, not 40 stories' words.
    listed = [(sql, args) for kind, sql, args in conn.calls if kind == "fetch" and "cappe_magazine_issue_stories" in sql]
    assert listed and all("content" not in sql and "LIMIT" in sql and args[-1] == 8 for sql, args in listed)


def test_a_story_in_a_released_issue_links_to_it(monkeypatch):
    _wire(monkeypatch, _issue_render_conn(for_story={"number": 3, "title": "The tide issue"}))
    conn = _issue_render_conn(for_story={"number": 3, "title": "The tide issue"})
    conn.set("fetchrow", "AND slug = $2 AND status = 'published' AND hidden_at IS NULL", story_row())
    _wire(monkeypatch, conn)
    html = asyncio.run(render_mod.story_page("harbour-at-dawn", _request("/stories/harbour-at-dawn"))).body.decode()
    assert 'href="/issues/3#mz-s-harbour-at-dawn"' in html


def test_the_sitemap_lists_the_issues(monkeypatch):
    _wire(monkeypatch, _issue_render_conn(issues=[{"number": 3, "updated_at": NOW}, {"number": 2, "updated_at": NOW}]))
    res = asyncio.run(render_mod.tenant_seo(_request("/sitemap.xml"), "sitemap"))
    xml = res.body.decode()
    assert "<loc>https://bloom.gummfit.com/issues</loc>" in xml and "/issues/3</loc>" in xml and "/issues/2</loc>" in xml


# ── the owner's API ──────────────────────────────────────────────────────────

ALL_COVER = normalize_cover({"photo": {"asset_id": str(ASSET)}})


def _owner(**over):
    """A connection for the owner's routes. Specific needles first: the first
    registered substring that matches answers."""
    fetchrow = {
        "FROM cappe_sites WHERE id": SITE_ROW,
        "FROM cappe_magazines": MAG_ROW,
        "INSERT INTO cappe_magazine_issues": issue_row(status="draft", released_at=None, number=4),
        "UPDATE cappe_magazine_issues SET status = 'released'": issue_row(),
        "UPDATE cappe_magazine_issues SET status = 'draft'": issue_row(status="draft", released_at=None),
        "UPDATE cappe_magazine_issues SET": issue_row(),
        "FROM cappe_magazine_issues WHERE id = $1": issue_row(),
        "JOIN cappe_magazine_issues i ON i.id = s.issue_id JOIN cappe_posts p": None,
    }
    fetch = {
        "SELECT id, title, status FROM cappe_posts": [{"id": POST, "title": "The harbour at dawn", "status": "draft"}],
        "UPDATE cappe_posts p SET status = 'published'": [],
        "FROM cappe_magazine_issue_stories s JOIN cappe_posts p": [in_issue(story_row())],
        "FROM cappe_magazine_issues i WHERE i.site_id": [{**issue_row(), "story_count": 1}],
        "SELECT s.post_id, s.issue_id, i.number": [{"post_id": POST, "issue_id": ISSUE, "number": 3}],
        "SELECT post_id FROM cappe_magazine_issue_stories": [{"post_id": POST}],
        "FROM cappe_assets WHERE site_id = $1 AND id = ANY": [ASSET_ROW],
        "FROM cappe_posts WHERE site_id = $1 AND id = ANY": [story_row()],
        "FROM cappe_pages": [],
    }
    fetchval = {"COALESCE(MAX(number), 0) + 1": 4, "SELECT COUNT(*) FROM cappe_magazine_issue_stories": 1,
                "SELECT plan FROM cappe_accounts": "business"}
    for kind, table in (("fetchrow", fetchrow), ("fetch", fetch), ("fetchval", fetchval)):
        table.update(over.get(kind, {}))
    return Conn(fetchrow=fetchrow, fetch=fetch, fetchval=fetchval, execute=over.get("execute"))


@pytest.fixture
def invalidated(monkeypatch):
    calls = []

    async def fake(site_id):
        calls.append(site_id)

    monkeypatch.setattr(issues_mod, "invalidate_render_cache", fake)
    return calls


@pytest.fixture
def limits(monkeypatch):
    calls = []

    async def fake(key, bucket, limit, window):
        calls.append((bucket, limit))

    monkeypatch.setattr(issues_mod, "check_rate_limit", fake)
    return calls


def _client(monkeypatch, conn):
    from app.cappe.services.magazine import magazines as mags
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(issues_mod, "get_connection", lambda: Ctx(conn))
    monkeypatch.setattr(mags, "resolve_entitlements", AsyncMock(side_effect=lambda plan, conn=None: SimpleNamespace(
        has=lambda f: f == "magazine" and plan in ("business", "writer"))))
    return route_client(issues_mod.router, overrides={issues_mod.require_cappe_account: ACCOUNT})


BASE = f"/sites/{SITE}/magazine/issues"


def test_options_offer_the_templates_and_say_which_stories_are_taken(monkeypatch):
    with _client(monkeypatch, _owner()) as client:
        res = client.get(f"{BASE}/options")
    body = res.json()
    assert res.status_code == 200 and [t["key"] for t in body["templates"]] == ["classic", "headline", "minimal",
                                                                                "boxed", "poster"]
    assert body["max_lines"] == 8 and body["max_stories"] == 40 and body["next_number"] == 4
    assert body["taken"] == [{"post_id": str(POST), "issue_id": str(ISSUE), "number": 3}]


def test_the_list_shows_each_issue_with_its_cover_picture(monkeypatch):
    with _client(monkeypatch, _owner()) as client:
        body = client.get(BASE).json()
    assert body[0]["number"] == 3 and body[0]["story_count"] == 1 and body[0]["status"] == "released"
    assert body[0]["cover_picture"]["url"] == "https://cdn.example.test/a.jpg" and body[0]["hidden"] is False


def test_a_new_issue_takes_the_next_number_and_fits_the_masthead(monkeypatch):
    conn = _owner(fetchrow={"INSERT INTO cappe_magazine_issues": Queue([None, issue_row(status="draft", number=5)])})
    with _client(monkeypatch, conn) as client:
        res = client.post(BASE, json={"template": "headline"})
    assert res.status_code == 201 and res.json()["number"] == 5
    inserts = [args for kind, sql, args in conn.calls if "INSERT INTO cappe_magazine_issues" in sql]
    assert len(inserts) == 2  # a lost race takes the next number
    cover = json.loads(inserts[0][2])
    assert cover["template"] == "headline" and cover["masthead"]["size"] < 16  # "Salt & Light" is long
    assert cover["lines"][0]["text"] == "Your cover line"


def test_a_new_issue_gives_up_after_three_races(monkeypatch):
    conn = _owner(fetchrow={"INSERT INTO cappe_magazine_issues": None})
    with _client(monkeypatch, conn) as client:
        assert client.post(BASE).status_code == 409
    conn = _owner(fetchval={"COALESCE(MAX(number), 0) + 1": 10000})
    with _client(monkeypatch, conn) as client:
        assert "run out" in client.post(BASE).json()["detail"]


def test_an_issue_of_another_site_or_none_is_not_found(monkeypatch):
    with _client(monkeypatch, _owner(fetchrow={"FROM cappe_magazine_issues WHERE id = $1": None})) as client:
        assert client.get(f"{BASE}/{ISSUE}").status_code == 404
        assert client.put(f"{BASE}/{ISSUE}", json={"title": "x"}).status_code == 404
        assert client.delete(f"{BASE}/{ISSUE}").status_code == 404
        assert client.post(f"{BASE}/{ISSUE}/release").status_code == 404
    with _client(monkeypatch, _owner(fetchrow={"UPDATE cappe_magazine_issues SET status = 'draft'": None})) as client:
        assert client.post(f"{BASE}/{OTHER_ISSUE}/withdraw").status_code == 404
    with _client(monkeypatch, _owner(fetchrow={"FROM cappe_sites WHERE id": None})) as client:
        assert client.get(BASE).status_code == 404


def test_get_returns_the_stories_with_their_pictures(monkeypatch):
    with _client(monkeypatch, _owner()) as client:
        body = client.get(f"{BASE}/{ISSUE}").json()
    story = body["stories"][0]
    assert story["post_id"] == str(POST) and story["status"] == "published" and story["picture"]["url"]
    assert body["cover_picture"]["id"] == str(ASSET) and body["cover"]["lines"][0]["post_id"] == str(POST)


def test_saving_sets_the_stories_in_order_and_prunes_links(monkeypatch, invalidated):
    second = uuid4()
    conn = _owner(fetch={"SELECT id, title, status FROM cappe_posts": [
        {"id": POST, "title": "A", "status": "published"}, {"id": second, "title": "B", "status": "published"}]})
    gone = str(uuid4())
    cover = {"lines": [{"text": "Kept", "post_id": str(second)}, {"text": "Pruned", "post_id": gone}]}
    with _client(monkeypatch, conn) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={
            "title": "  Autumn ", "cover": cover, "contents": {"layout": "grid"},
            "stories": [{"post_id": str(second), "section": " Features "}, {"post_id": str(POST)},
                        {"post_id": str(second)}]})
    assert res.status_code == 200, res.text
    args = conn.args_for("INSERT INTO cappe_magazine_issue_stories")
    assert args[2] == [str(second), str(POST)] and args[3] == ["Features", None]
    update = conn.args_for("UPDATE cappe_magazine_issues SET")
    saved_cover = json.loads(update[1])
    assert update[0] == "Autumn" and [ln["post_id"] for ln in saved_cover["lines"]] == [str(second), None]
    assert json.loads(update[2])["layout"] == "grid" and invalidated == [SITE]
    assert conn.sql_for("execute")[0].startswith("DELETE FROM cappe_magazine_issue_assets")


def test_a_story_in_another_issue_or_another_magazine_is_refused(monkeypatch, invalidated):
    taken = _owner(fetchrow={"JOIN cappe_magazine_issues i ON i.id = s.issue_id JOIN cappe_posts p":
                             {"title": "The harbour at dawn", "number": 2}})
    with _client(monkeypatch, taken) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={"stories": [{"post_id": str(POST)}]})
    assert res.status_code == 422 and "already in No. 2" in res.json()["detail"]
    foreign = _owner(fetch={"SELECT id, title, status FROM cappe_posts": []})
    with _client(monkeypatch, foreign) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={"stories": [{"post_id": str(uuid4())}]})
    assert res.status_code == 422 and "isn't in your magazine" in res.json()["detail"]
    with _client(monkeypatch, _owner(fetch={"FROM cappe_assets WHERE site_id = $1 AND id = ANY": []})) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={"cover": ALL_COVER})
    assert res.status_code == 422 and "library" in res.json()["detail"]
    with _client(monkeypatch, _owner()) as client:
        assert client.put(f"{BASE}/{ISSUE}", json={"stories": [{"post_id": str(uuid4())}] * 41}).status_code == 422
    assert invalidated == []


def test_too_many_distinct_stories_are_refused():
    with pytest.raises(mag_issues.IssueError, match="at most 40"):
        mag_issues._clean_stories([{"post_id": uuid4()} for _ in range(41)])


def test_a_taken_number_is_explained(monkeypatch):
    def clash(sql, args):
        raise Exception('duplicate key value violates unique constraint "uq_cappe_magazine_issues_number"')

    with _client(monkeypatch, _owner(fetchrow={"UPDATE cappe_magazine_issues SET": clash})) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={"number": 2})
    assert res.status_code == 422 and "No. 2 is already taken" in res.json()["detail"]

    def race(sql, args):
        raise Exception('duplicate key value violates unique constraint "uq_cappe_magazine_issue_stories_post"')

    with _client(monkeypatch, _owner(fetchrow={"UPDATE cappe_magazine_issues SET": race})) as client:
        assert "another issue" in client.put(f"{BASE}/{ISSUE}", json={"title": "x"}).json()["detail"]

    # The real race: the story went into another issue after check_stories,
    # so the stories' own insert trips the index — a message, not a 500.
    def taken(sql, args):
        raise Exception('duplicate key value violates unique constraint "uq_cappe_magazine_issue_stories_post"')

    with _client(monkeypatch, _owner(execute={"INSERT INTO cappe_magazine_issue_stories": taken})) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={"stories": [{"post_id": str(POST)}]})
    assert res.status_code == 422 and "another issue" in res.json()["detail"]

    def other(sql, args):
        raise RuntimeError("boom")

    with _client(monkeypatch, _owner(fetchrow={"UPDATE cappe_magazine_issues SET": other})) as client:
        with pytest.raises(RuntimeError):
            client.put(f"{BASE}/{ISSUE}", json={"title": "x"})


def test_a_draft_added_to_a_released_issue_is_published_by_the_save(monkeypatch, invalidated):
    conn = _owner(fetch={"UPDATE cappe_posts p SET status = 'published'": [{"title": "The harbour at dawn"}]})
    with _client(monkeypatch, conn) as client:
        res = client.put(f"{BASE}/{ISSUE}", json={"stories": [{"post_id": str(POST)}]})
    assert res.json()["published"] == ["The harbour at dawn"]
    draft = _owner(fetchrow={"FROM cappe_magazine_issues WHERE id = $1": issue_row(status="draft", released_at=None)})
    with _client(monkeypatch, draft) as client:
        assert client.put(f"{BASE}/{ISSUE}", json={"title": "x"}).json()["published"] == []
    assert not draft.sql_for("fetch") or not any("UPDATE cappe_posts" in s for s in draft.sql_for("fetch"))


def test_release_publishes_the_drafts_with_the_issue(monkeypatch, invalidated):
    draft = issue_row(status="draft", released_at=None)
    conn = _owner(fetchrow={"FROM cappe_magazine_issues WHERE id = $1": draft},
                  fetch={"UPDATE cappe_posts p SET status = 'published'": [{"title": "The harbour at dawn"}]})
    with _client(monkeypatch, conn) as client:
        res = client.post(f"{BASE}/{ISSUE}/release")
    assert res.status_code == 200 and res.json()["status"] == "released" and res.json()["published"] == ["The harbour at dawn"]
    assert invalidated == [SITE]
    order = [sql for _k, sql, _a in conn.calls if sql.lstrip().startswith("UPDATE")]
    assert "UPDATE cappe_posts" in order[0] and "SET status = 'released'" in order[1]


def test_release_needs_stories_and_a_live_magazine(monkeypatch, invalidated):
    draft = issue_row(status="draft", released_at=None)
    empty = _owner(fetchrow={"FROM cappe_magazine_issues WHERE id = $1": draft},
                   fetchval={"SELECT COUNT(*) FROM cappe_magazine_issue_stories": 0})
    with _client(monkeypatch, empty) as client:
        res = client.post(f"{BASE}/{ISSUE}/release")
    assert res.status_code == 409 and "at least one story" in res.json()["detail"]
    with _client(monkeypatch, _owner(fetchval={"SELECT plan FROM cappe_accounts": "free"})) as client:
        res = client.post(f"{BASE}/{ISSUE}/release")
    assert res.status_code == 409 and "Turn on your magazine" in res.json()["detail"]
    # Already out: nothing changes.
    already = _owner()
    with _client(monkeypatch, already) as client:
        assert client.post(f"{BASE}/{ISSUE}/release").json()["published"] == []
    assert not any("SET status = 'released'" in s for s in already.sql_for("fetchrow"))


def test_withdraw_and_delete(monkeypatch, invalidated):
    with _client(monkeypatch, _owner()) as client:
        res = client.post(f"{BASE}/{ISSUE}/withdraw")
        assert res.status_code == 200 and res.json()["status"] == "draft"
        res = client.delete(f"{BASE}/{ISSUE}")
        assert res.status_code == 409 and "Withdraw" in res.json()["detail"]
    draft = _owner(fetchrow={"FROM cappe_magazine_issues WHERE id = $1": issue_row(status="draft", released_at=None)})
    with _client(monkeypatch, draft) as client:
        assert client.delete(f"{BASE}/{ISSUE}").status_code == 204
    assert any(s.startswith("DELETE FROM cappe_magazine_issues") for s in draft.sql_for("execute"))
    assert invalidated == [SITE, SITE]


def test_the_preview_renders_unsaved_and_never_caches(monkeypatch, limits):
    conn = _owner(fetch={"SELECT id, title, status FROM cappe_posts": [{"id": PAID, "title": "Paid", "status": "draft"}],
                         "FROM cappe_posts WHERE site_id = $1 AND id = ANY": [paid_row()]})
    with _client(monkeypatch, conn) as client:
        res = client.post(f"{BASE}/preview", json={
            "issue_id": str(ISSUE), "number": 7, "title": "Preview", "cover": {"lines": [{"text": "Cover words"}]},
            "contents": {"layout": "feature"}, "stories": [{"post_id": str(PAID), "section": "Food"},
                                                           {"post_id": str(uuid4())}]})
    assert res.status_code == 422  # a story that isn't the site's
    with _client(monkeypatch, conn) as client:
        res = client.post(f"{BASE}/preview", json={
            "issue_id": str(ISSUE), "number": 7, "cover": {"lines": [{"text": "Cover words"}]},
            "stories": [{"post_id": str(PAID), "section": "Food"}]})
    html = res.text
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store"
    assert "Cover words" in html and "Free opening." in html and SENTINEL not in html and "Food" in html
    assert "No. 7 · October 2026" in html  # the saved issue's release date
    assert ("cappe_issue_preview", issues_mod.PREVIEWS_PER_HOUR) in limits
    with _client(monkeypatch, _owner(fetchrow={"FROM cappe_magazines": None})) as client:
        res = client.post(f"{BASE}/preview", json={"cover": {}, "stories": []})
    assert res.status_code == 200 and "Bloom" in res.text  # no magazine yet: the site's name


def test_the_preview_leaves_out_an_archived_story(monkeypatch, limits):
    def posts(sql, args):
        # The database's answer: the archived story comes back only if the query lets it.
        return [] if "status IN ('draft', 'published')" in sql else [story_row(status="archived")]

    conn = _owner(fetch={"SELECT id, title, status FROM cappe_posts": [{"id": POST, "title": "x", "status": "archived"}],
                         "FROM cappe_posts WHERE site_id = $1 AND id = ANY": posts})
    with _client(monkeypatch, conn) as client:
        res = client.post(f"{BASE}/preview", json={"cover": {}, "stories": [{"post_id": str(POST)}]})
    assert res.status_code == 200 and "mz-s-harbour-at-dawn" not in res.text


def test_the_library_keeps_a_cover_picture(monkeypatch):
    conn = Conn(fetchrow={"FROM cappe_sites WHERE id": SITE_ROW},
                fetch={"FROM cappe_post_assets": [], "FROM cappe_magazine_issue_assets": [{"number": 3}]})
    monkeypatch.setattr(uploads_mod, "get_connection", lambda: Ctx(conn))
    with route_client(uploads_mod.router, overrides={uploads_mod.require_cappe_account: ACCOUNT}) as client:
        res = client.delete(f"/sites/{SITE}/assets/{ASSET}")
    assert res.status_code == 409 and "cover of No. 3" in res.json()["detail"]
