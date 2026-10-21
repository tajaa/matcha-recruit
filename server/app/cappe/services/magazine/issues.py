"""A magazine's issues: numbered books of its stories, each with a designed
cover and contents (cappemag07).

An issue is a draft until the owner releases it. Releasing publishes the
drafts it holds, in the same transaction, and puts it on the magazine at
`/issues/<number>`; the newest released issue leads the front page. A
released issue stays editable: a draft added to it is published when the
issue is saved (the editor says so on the button), and every change shows at
once. Withdrawing takes it back to a draft and leaves its stories up.

A story is in at most one issue (`cappe_magazine_issue_stories.post_id` is
UNIQUE). The cover's picture is recorded in `cappe_magazine_issue_assets` so
the library refuses to delete it, as `cappe_post_assets` does for stories.

What a reader reaches is a released issue with no admin takedown
(`hidden_at`), and in it only the live stories (published, not hidden).
"""
from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from .issue_schema import (
    MAX_STORIES,
    IssueError,
    contents_line,
    cover_asset_ids,
    normalize_contents,
    normalize_cover,
    section_name,
    starter_cover,
)
from .stories import POST_COLS, post_row, site_assets
from .story_schema import referenced_asset_ids

ISSUE_COLS = ("id, site_id, number, title, status, released_at, cover, contents, cover_image, hidden_at, "
              "hidden_reason, created_at, updated_at")
_I_COLS = ", ".join(f"i.{c.strip()}" for c in ISSUE_COLS.split(","))
LIVE_ISSUE = "status = 'released' AND hidden_at IS NULL"
ARCHIVE_PAGE = 24


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def issue_row(r) -> dict[str, Any]:
    d = dict(r)
    for key in ("cover", "contents"):
        d[key] = _json(d.get(key)) or {}
    d["cover_image"] = _json(d.get("cover_image"))
    return d


async def get_issue(conn, site_id: UUID, issue_id: UUID, *, lock: bool = False) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        f"SELECT {ISSUE_COLS} FROM cappe_magazine_issues WHERE id = $1 AND site_id = $2"
        + (" FOR UPDATE" if lock else ""),
        issue_id, site_id,
    )
    return issue_row(row) if row else None


async def list_issues(conn, site_id: UUID) -> list[dict[str, Any]]:
    """Every issue, newest number first, with how many stories each holds."""
    rows = await conn.fetch(
        f"""SELECT {_I_COLS},
                   (SELECT COUNT(*) FROM cappe_magazine_issue_stories s WHERE s.issue_id = i.id) AS story_count
              FROM cappe_magazine_issues i WHERE i.site_id = $1 ORDER BY i.number DESC LIMIT 500""",
        site_id,
    )
    return [issue_row(r) for r in rows]


async def next_number(conn, site_id: UUID) -> int:
    return int(await conn.fetchval(
        "SELECT COALESCE(MAX(number), 0) + 1 FROM cappe_magazine_issues WHERE site_id = $1", site_id,
    ))


async def create_issue(conn, site_id: UUID, *, name: str, template: Optional[str] = None) -> dict[str, Any]:
    """A new draft with the next number, the template's cover (its masthead
    fitted to the magazine's `name`) and the default contents. Two at once
    can race for a number: the loser gets the next."""
    cover = json.dumps(starter_cover(template or "classic", name))
    contents = json.dumps(normalize_contents({}))
    for _ in range(3):
        number = await next_number(conn, site_id)
        if number > 9999:
            raise IssueError("This magazine has run out of issue numbers.")
        row = await conn.fetchrow(
            f"INSERT INTO cappe_magazine_issues (site_id, number, cover, contents) VALUES ($1, $2, $3::jsonb, $4::jsonb) "
            f"ON CONFLICT (site_id, number) DO NOTHING RETURNING {ISSUE_COLS}",
            site_id, number, cover, contents,
        )
        if row:
            return issue_row(row)
    raise IssueError("Another issue was just started. Try again.")


_STORY_COLS = ", ".join(f"p.{c.strip()}" for c in POST_COLS.split(","))


async def issue_stories(conn, issue_id: UUID, *, live: bool = False) -> list[dict[str, Any]]:
    """The issue's stories in order, each with its section and contents line.
    `live`: only those a reader can reach."""
    where = " AND p.status = 'published' AND p.hidden_at IS NULL" if live else ""
    rows = await conn.fetch(
        f"""SELECT {_STORY_COLS}, s.position, s.section, s.contents_line
              FROM cappe_magazine_issue_stories s JOIN cappe_posts p ON p.id = s.post_id AND p.site_id = s.site_id
             WHERE s.issue_id = $1{where} ORDER BY s.position""",
        issue_id,
    )
    return [post_row(r) for r in rows]


def _clean_stories(stories: list[dict]) -> list[dict]:
    """The stories as sent: each once, in the order given, at most 40."""
    seen: set[str] = set()
    out = []
    for s in stories:
        key = str(s["post_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"post_id": key, "section": section_name(s.get("section")),
                    "contents_line": contents_line(s.get("contents_line"))})
    if len(out) > MAX_STORIES:
        raise IssueError(f"An issue holds at most {MAX_STORIES} stories.")
    return out


async def check_stories(conn, site_id: UUID, issue_id: Optional[UUID], post_ids: list[str]) -> dict[str, dict]:
    """The site's own stories for `post_ids`, keyed by id; none of them in
    another issue."""
    if not post_ids:
        return {}
    rows = await conn.fetch(
        "SELECT id, title, status FROM cappe_posts WHERE site_id = $1 AND id = ANY($2::uuid[])", site_id, post_ids,
    )
    found = {str(r["id"]): dict(r) for r in rows}
    if len(found) != len(set(post_ids)):
        raise IssueError("A story in this issue isn't in your magazine any more. Take it out.")
    if issue_id is not None:
        taken = await conn.fetchrow(
            """SELECT p.title, i.number FROM cappe_magazine_issue_stories s
                 JOIN cappe_magazine_issues i ON i.id = s.issue_id JOIN cappe_posts p ON p.id = s.post_id
                WHERE s.post_id = ANY($1::uuid[]) AND s.issue_id <> $2 ORDER BY i.number LIMIT 1""",
            post_ids, issue_id,
        )
        if taken:
            raise IssueError(f"“{taken['title']}” is already in No. {taken['number']}. A story is in one issue.")
    return found


async def check_cover_assets(conn, site_id: UUID, cover: dict) -> dict[str, dict]:
    ids = cover_asset_ids(cover)
    found = await site_assets(conn, site_id, ids)
    if len(found) != len(ids):
        raise IssueError("The cover picture isn't in your library any more. Choose another.")
    return found


async def _set_stories(conn, issue_id: UUID, site_id: UUID, stories: list[dict]) -> None:
    await conn.execute("DELETE FROM cappe_magazine_issue_stories WHERE issue_id = $1", issue_id)
    if stories:
        await conn.execute(
            """INSERT INTO cappe_magazine_issue_stories (issue_id, post_id, site_id, position, section, contents_line)
               SELECT $1, t.post_id, $2, t.ord - 1, t.section, t.line
                 FROM unnest($3::uuid[], $4::text[], $5::text[]) WITH ORDINALITY AS t(post_id, section, line, ord)""",
            issue_id, site_id, [s["post_id"] for s in stories], [s["section"] for s in stories],
            [s["contents_line"] for s in stories],
        )


async def _set_assets(conn, issue_id: UUID, site_id: UUID, ids: list[str]) -> None:
    await conn.execute("DELETE FROM cappe_magazine_issue_assets WHERE issue_id = $1", issue_id)
    if ids:
        await conn.execute(
            "INSERT INTO cappe_magazine_issue_assets (issue_id, asset_id, site_id) "
            "SELECT $1, unnest($2::uuid[]), $3 ON CONFLICT DO NOTHING",
            issue_id, sorted(set(ids)), site_id,
        )


async def _publish_drafts(conn, issue_id: UUID, site_id: UUID) -> list[str]:
    """Publish the issue's draft stories; their titles."""
    rows = await conn.fetch(
        """UPDATE cappe_posts p SET status = 'published', published_at = COALESCE(p.published_at, NOW()),
                  updated_at = NOW()
             FROM cappe_magazine_issue_stories s
            WHERE s.issue_id = $1 AND s.post_id = p.id AND p.site_id = $2 AND p.status = 'draft'
        RETURNING p.title""",
        issue_id, site_id,
    )
    return [r["title"] for r in rows]


def _unique_problem(exc: Exception, number: Optional[int]) -> Optional[str]:
    text = str(exc)
    if "uq_cappe_magazine_issues_number" in text:
        return f"No. {number} is already taken. Choose another number."
    if "uq_cappe_magazine_issue_stories_post" in text:
        return "One of these stories was just put in another issue. A story is in one issue."
    return None


async def save_issue(conn, site_id: UUID, issue_id: UUID, fields: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Store what was sent (`title`, `number`, `cover`, `contents`,
    `stories`). Call inside a transaction. Returns the issue and the titles of
    any drafts it published (a released issue publishes what is added to it)."""
    current = await get_issue(conn, site_id, issue_id, lock=True)
    if current is None:
        raise LookupError("issue")
    stories = None
    if "stories" in fields:
        stories = _clean_stories(fields["stories"] or [])
        await check_stories(conn, site_id, issue_id, [s["post_id"] for s in stories])
    if stories is not None:
        story_ids = {s["post_id"] for s in stories}
    else:
        story_ids = {str(r["post_id"]) for r in await conn.fetch(
            "SELECT post_id FROM cappe_magazine_issue_stories WHERE issue_id = $1", issue_id)}

    sets, args = [], []

    def put(col: str, value: Any, cast: str = "") -> None:
        args.append(value)
        sets.append(f"{col} = ${len(args)}{cast}")

    if "title" in fields:
        put("title", (fields["title"] or "").strip()[:120] or None)
    if "number" in fields and fields["number"] is not None:
        put("number", int(fields["number"]))
    # The cover is re-checked when the stories change too: a cover line may
    # link only to a story in the issue.
    if "cover" in fields or stories is not None:
        cover = normalize_cover(fields.get("cover", current["cover"]), story_ids=story_ids)
        await check_cover_assets(conn, site_id, cover)
        put("cover", json.dumps(cover), "::jsonb")
        await _set_assets(conn, issue_id, site_id, cover_asset_ids(cover))
    if "contents" in fields:
        put("contents", json.dumps(normalize_contents(fields["contents"])), "::jsonb")
    if stories is not None:
        await _set_stories(conn, issue_id, site_id, stories)
    sets.append("updated_at = NOW()")
    args += [issue_id, site_id]
    try:
        row = await conn.fetchrow(
            f"UPDATE cappe_magazine_issues SET {', '.join(sets)} WHERE id = ${len(args) - 1} AND site_id = ${len(args)} "
            f"RETURNING {ISSUE_COLS}",
            *args,
        )
    except Exception as exc:
        problem = _unique_problem(exc, fields.get("number"))
        if problem:
            raise IssueError(problem) from exc
        raise
    published = await _publish_drafts(conn, issue_id, site_id) if current["status"] == "released" else []
    return issue_row(row), published


async def release_issue(conn, site_id: UUID, issue_id: UUID) -> tuple[dict[str, Any], list[str]]:
    """Put the issue out: its drafts published, then the issue. Call inside a
    transaction."""
    current = await get_issue(conn, site_id, issue_id, lock=True)
    if current is None:
        raise LookupError("issue")
    if current["status"] == "released":
        return current, []
    count = await conn.fetchval("SELECT COUNT(*) FROM cappe_magazine_issue_stories WHERE issue_id = $1", issue_id)
    if not count:
        raise IssueError("Add at least one story before releasing the issue.")
    published = await _publish_drafts(conn, issue_id, site_id)
    row = await conn.fetchrow(
        f"UPDATE cappe_magazine_issues SET status = 'released', released_at = NOW(), updated_at = NOW() "
        f"WHERE id = $1 AND site_id = $2 RETURNING {ISSUE_COLS}",
        issue_id, site_id,
    )
    return issue_row(row), published


async def withdraw_issue(conn, site_id: UUID, issue_id: UUID) -> Optional[dict[str, Any]]:
    """Back to a draft; its stories stay published. Released again later, it
    takes the new date."""
    row = await conn.fetchrow(
        f"UPDATE cappe_magazine_issues SET status = 'draft', released_at = NULL, updated_at = NOW() "
        f"WHERE id = $1 AND site_id = $2 RETURNING {ISSUE_COLS}",
        issue_id, site_id,
    )
    return issue_row(row) if row else None


async def delete_issue(conn, site_id: UUID, issue_id: UUID) -> Optional[str]:
    """Delete a draft issue (its stories stay). The status it had, or None."""
    current = await get_issue(conn, site_id, issue_id, lock=True)
    if current is None:
        return None
    if current["status"] == "draft":
        await conn.execute("DELETE FROM cappe_magazine_issues WHERE id = $1 AND site_id = $2", issue_id, site_id)
    return current["status"]


async def taken_stories(conn, site_id: UUID) -> list[dict[str, Any]]:
    """Which issue each story is in, for the story picker."""
    rows = await conn.fetch(
        """SELECT s.post_id, s.issue_id, i.number FROM cappe_magazine_issue_stories s
             JOIN cappe_magazine_issues i ON i.id = s.issue_id WHERE s.site_id = $1""",
        site_id,
    )
    return [dict(r) for r in rows]


async def issues_using(conn, site_id: UUID, asset_id: UUID) -> list[int]:
    """Numbers of the issues whose cover shows a picture (to refuse deleting it)."""
    rows = await conn.fetch(
        """SELECT i.number FROM cappe_magazine_issue_assets a JOIN cappe_magazine_issues i ON i.id = a.issue_id
            WHERE a.site_id = $1 AND a.asset_id = $2 ORDER BY i.number DESC LIMIT 5""",
        site_id, asset_id,
    )
    return [r["number"] for r in rows]


# ── what readers reach ──────────────────────────────────────────────────────

async def live_issue(conn, site_id: UUID, number: int) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        f"SELECT {ISSUE_COLS} FROM cappe_magazine_issues WHERE site_id = $1 AND number = $2 AND {LIVE_ISSUE}",
        site_id, number,
    )
    return issue_row(row) if row else None


async def current_issue(conn, site_id: UUID) -> Optional[dict[str, Any]]:
    """The newest released issue, which leads the front page."""
    row = await conn.fetchrow(
        f"SELECT {ISSUE_COLS} FROM cappe_magazine_issues WHERE site_id = $1 AND {LIVE_ISSUE} "
        "ORDER BY released_at DESC, number DESC LIMIT 1",
        site_id,
    )
    return issue_row(row) if row else None


async def live_issues(conn, site_id: UUID, *, limit: int = ARCHIVE_PAGE, offset: int = 0) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"SELECT {ISSUE_COLS} FROM cappe_magazine_issues WHERE site_id = $1 AND {LIVE_ISSUE} "
        "ORDER BY number DESC LIMIT $2 OFFSET $3",
        site_id, limit, offset,
    )
    return [issue_row(r) for r in rows]


async def book_assets(conn, site_id: UUID, cover: dict, stories: list[dict]) -> dict[str, dict]:
    """Every picture an issue's book shows: the cover's and its stories'."""
    ids = set(cover_asset_ids(cover))
    for post in stories:
        ids |= set(referenced_asset_ids(post.get("content") or {}, post.get("cover_asset_id")))
    return await site_assets(conn, site_id, ids)


async def issue_for_story(conn, site_id: UUID, post_id: UUID) -> Optional[dict[str, Any]]:
    """The released issue a story is in, for its "read it in the issue" link."""
    row = await conn.fetchrow(
        """SELECT i.number, i.title FROM cappe_magazine_issue_stories s
              JOIN cappe_magazine_issues i ON i.id = s.issue_id
             WHERE s.site_id = $1 AND s.post_id = $2 AND i.status = 'released' AND i.hidden_at IS NULL""",
        site_id, post_id,
    )
    return dict(row) if row else None

