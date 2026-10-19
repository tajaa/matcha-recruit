"""Job-board postings Espresso has read, kept so the next search doesn't read
or search for them again.

Every Greenhouse, Lever, Ashby or Workable posting a search or `find_jobs`
reads from its board's API is kept in `mw_job_postings` (migration
`mwjobs04`): live with what was read (the lead record: title, employer,
place, pay with its evidence, questions, description), or closed when the
ATS itself said so (`ats.read`). It is public data read from public APIs, so
the table is shared by everyone and holds nobody's search: no user, no
résumé, no criteria.

- A posting read live in the last `LIVE_HOURS` is used as read, with no new
  read; one the ATS said is closed in the last `CLOSED_DAYS` is skipped.
  Brave's index runs months behind (about 4 in 5 of its board links are
  closed), so most of a repeat search's reads were closed postings read
  again.
- `matching` finds the live postings any earlier search read with a related
  title in the person's places (`normalize.related_title`, `phases.keep_job`),
  so a search starts from what was already found, Brave or not.
- `mw_job_board_searches` remembers each board search Brave was sent (the
  query text, no one's name on it). The same search within `SEARCH_HOURS`
  asks for its next page of results instead (`plan`), so "any more?" reads
  new links rather than the same twenty; one read to its end is left out
  until the window passes. Its first page's postings come from `matching`.

None of it may cost a search its answer: every statement here fails soft
(logged, read as nothing stored). A search with no table, or no database,
works as it did before this existed.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from app.database import decode_jsonb

from . import ats, normalize, phases, places

logger = logging.getLogger(__name__)

LIVE_HOURS = 12
CLOSED_DAYS = 14
# `matching` looks back this far; a posting older than `LIVE_HOURS` is read
# again before it is shown.
MATCH_DAYS = 7
MATCH_ROWS = 400
# A board search sent within this asks for its next page; pages 0 to MAX_PAGE.
SEARCH_HOURS = 24
MAX_PAGE = 4

Key = tuple[str, str, str]  # provider, board, job id (lower case)


def key_of(ref: ats.AtsRef) -> Key:
    return (ref.provider, ref.board.lower(), ref.job_id.lower())


def key_of_url(url: str | None) -> Key | None:
    ref = ats.detect(url)
    return key_of(ref) if ref is not None else None


def key_of_record(record: dict) -> Key | None:
    """The ATS posting a read record came from (`discovery._record`'s `ats`),
    or None for a page that isn't one."""
    found = record.get("ats") if isinstance(record, dict) else None
    if not isinstance(found, dict) or found.get("provider") not in ats.NAMES:
        return None
    board, job = str(found.get("board") or ""), str(found.get("job_id") or "")
    return (found["provider"], board.lower(), job.lower()) if board and job else None


def query_key(query: str) -> str:
    return " ".join(str(query or "").lower().split())[:400]


@dataclass(frozen=True)
class Stored:
    key: Key
    url: str
    live: bool
    # Live: read live within LIVE_HOURS. Closed: said closed within CLOSED_DAYS.
    fresh: bool
    record: dict | None = None

    @property
    def read_url(self) -> str:
        """Where to read it again: its page on its board (`ats.AtsRef.board_url`)."""
        found = (self.record or {}).get("ats")
        if isinstance(found, dict) and found.get("provider") in ats.NAMES and found.get("board") and found.get("job_id"):
            return ats.AtsRef(found["provider"], str(found["board"]), str(found["job_id"]),
                              eu=bool(found.get("eu"))).board_url()
        return self.url


@dataclass(frozen=True)
class Page:
    query: str
    offset: int  # 0 is Brave's first page


def plan(queries: list[str], sent: dict[str, tuple[int, bool]]) -> list[Page]:
    """Each board search with the page to ask Brave for: the first, or the
    next after one sent within `SEARCH_HOURS` (`sent`: query key -> (next
    page, read to its end)). A search read to its end is left out."""
    out = []
    for query in queries:
        at = sent.get(query_key(query))
        if at is None:
            out.append(Page(query, 0))
        elif not at[1] and at[0] <= MAX_PAGE:
            out.append(Page(query, at[0]))
    return out


def last_page(page: Page, results: int, count: int) -> bool:
    """Whether a page Brave answered was its last for that search."""
    return results < count or page.offset >= MAX_PAGE


def _query_words(titles: list[str]) -> list[str]:
    """The words a stored posting's title must share one of (stemmed by
    Postgres; `normalize.related_title` decides after): each wanted title's
    work words, or the whole title when it is only level words."""
    words = set().union(*(normalize.work_words(title) for title in titles))
    return sorted(w for w in words if re.fullmatch(r"[a-z0-9]+", w))


def keep(rows: list[Stored], titles: list[str], criteria: dict) -> list[Stored]:
    """The stored postings a search would keep: a related title, where the
    person wants it (the read step's own rules)."""
    out = []
    for row in rows:
        record = row.record or {}
        if not record.get("title") or not normalize.related_title(record["title"], titles):
            continue
        if phases.keep_job(record.get("company") or "", record.get("remote"), criteria, record.get("location") or ""):
            out.append(row)
    return out


def _row(record: dict) -> dict | None:
    key = key_of_record(record)
    url = normalize.http_url(record.get("source_url"))
    if key is None or url is None:
        return None
    found = record["ats"]
    return {
        "provider": key[0], "board_key": key[1], "job_key": key[2],
        "ref": {k: found.get(k) for k in ("provider", "board", "job_id", "eu")},
        "url": url,
        "title": record.get("title") or "",
        "company": record.get("company") or "",
        "location": record.get("location") or "",
        "state_code": record.get("state_code"),
        "remote": record.get("remote"),
        "title_terms": " ".join(sorted(normalize.title_words(record.get("title") or ""))),
        "comp_status": record.get("comp_status"),
        "comp_annual_min": record.get("comp_annual_min"),
        "comp_annual_max": record.get("comp_annual_max"),
        "comp_currency": record.get("comp_currency"),
        "record": record,
    }


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


class Store:
    """The stored postings over one connection (None: nothing is stored)."""

    def __init__(self, conn):
        self.conn = conn

    async def _fetch(self, what: str, query: str, *args) -> list:
        if self.conn is None:
            return []
        try:
            return await self.conn.fetch(query, *args)
        except Exception:
            logger.warning("job postings: %s failed", what, exc_info=True)
            return []

    async def _execute(self, what: str, query: str, *args) -> None:
        if self.conn is None:
            return
        try:
            await self.conn.execute(query, *args)
        except Exception:
            logger.warning("job postings: %s failed", what, exc_info=True)

    async def known(self, keys: list[Key]) -> dict[Key, Stored]:
        """What is stored about each of these postings."""
        keys = list(dict.fromkeys(keys))
        if not keys:
            return {}
        rows = await self._fetch(
            "lookup",
            """SELECT provider, board_key, job_key, url, live, record,
                      CASE WHEN live THEN live_at > NOW() - make_interval(hours => $4)
                           ELSE checked_at > NOW() - make_interval(days => $5) END AS fresh
               FROM mw_job_postings
               WHERE (provider, board_key, job_key) IN
                     (SELECT * FROM unnest($1::text[], $2::text[], $3::text[]))""",
            [k[0] for k in keys], [k[1] for k in keys], [k[2] for k in keys], LIVE_HOURS, CLOSED_DAYS,
        )
        return {(row["provider"], row["board_key"], row["job_key"]): _stored(row) for row in rows}

    async def matching(self, titles: list[str], criteria: dict, *, limit: int = MATCH_ROWS) -> list[Stored]:
        """Live postings an earlier search read (within `MATCH_DAYS`) that
        this one would keep: in-state and remote ones first, newest first."""
        words = _query_words([t for t in titles if t])
        if not words:
            return []
        states = sorted({s for t in places.targets(criteria) if (s := t.state or normalize.state_of(t.label))})
        rows = await self._fetch(
            "match",
            """SELECT provider, board_key, job_key, url, live, record,
                      live_at > NOW() - make_interval(hours => $2) AS fresh
               FROM mw_job_postings
               WHERE live AND live_at > NOW() - make_interval(days => $3)
                 AND to_tsvector('english', title_terms) @@ to_tsquery('english', $1)
               ORDER BY (COALESCE(state_code = ANY($4::text[]), false) OR (remote IS TRUE AND $5::boolean)) DESC,
                        live_at DESC
               LIMIT $6""",
            " | ".join(words), LIVE_HOURS, MATCH_DAYS, states, places.takes_remote(criteria), limit,
        )
        return keep([_stored(row) for row in rows], titles, criteria)

    async def save(self, records: list[dict], closed: list[Key] = ()) -> None:
        """Postings just read: live with what was read, or closed (the ATS
        said so). A key read both ways in one batch is live."""
        live: dict[Key, dict] = {}
        for record in records:
            row = _row(record)
            if row is not None:
                live[(row["provider"], row["board_key"], row["job_key"])] = row
        if live:
            await self._execute(
                "save",
                """INSERT INTO mw_job_postings AS p
                       (provider, board_key, job_key, ref, url, live, title, company, location, state_code,
                        remote, title_terms, comp_status, comp_annual_min, comp_annual_max, comp_currency,
                        record, first_seen_at, checked_at, live_at, closed_at)
                   SELECT r.provider, r.board_key, r.job_key, r.ref, r.url, true, r.title, r.company,
                          r.location, r.state_code, r.remote, r.title_terms, r.comp_status,
                          r.comp_annual_min, r.comp_annual_max, r.comp_currency, r.record,
                          NOW(), NOW(), NOW(), NULL
                   FROM jsonb_to_recordset($1::jsonb) AS r(
                       provider text, board_key text, job_key text, ref jsonb, url text, title text,
                       company text, location text, state_code text, remote boolean, title_terms text,
                       comp_status text, comp_annual_min numeric, comp_annual_max numeric,
                       comp_currency text, record jsonb)
                   ON CONFLICT (provider, board_key, job_key) DO UPDATE SET
                       ref = EXCLUDED.ref, url = EXCLUDED.url, live = true, title = EXCLUDED.title,
                       company = EXCLUDED.company, location = EXCLUDED.location,
                       state_code = EXCLUDED.state_code, remote = EXCLUDED.remote,
                       title_terms = EXCLUDED.title_terms, comp_status = EXCLUDED.comp_status,
                       comp_annual_min = EXCLUDED.comp_annual_min, comp_annual_max = EXCLUDED.comp_annual_max,
                       comp_currency = EXCLUDED.comp_currency, record = EXCLUDED.record,
                       checked_at = NOW(), live_at = NOW(), closed_at = NULL""",
                _dumps(list(live.values())),
            )
        gone = [k for k in dict.fromkeys(closed) if k not in live]
        if gone:
            await self._execute(
                "save closed",
                """INSERT INTO mw_job_postings AS p (provider, board_key, job_key, live, checked_at, closed_at)
                   SELECT k.provider, k.board_key, k.job_key, false, NOW(), NOW()
                   FROM unnest($1::text[], $2::text[], $3::text[]) AS k(provider, board_key, job_key)
                   ON CONFLICT (provider, board_key, job_key) DO UPDATE SET
                       live = false, checked_at = NOW(), closed_at = COALESCE(p.closed_at, NOW())""",
                [k[0] for k in gone], [k[1] for k in gone], [k[2] for k in gone],
            )

    async def sent(self, queries: list[str]) -> dict[str, tuple[int, bool]]:
        """The board searches among these sent within `SEARCH_HOURS`: query
        key -> (the next page to ask for, read to its end)."""
        keys = list(dict.fromkeys(query_key(q) for q in queries))
        if not keys:
            return {}
        rows = await self._fetch(
            "searches",
            """SELECT query, next_offset, exhausted FROM mw_job_board_searches
               WHERE query = ANY($1::text[]) AND started_at > NOW() - make_interval(hours => $2)""",
            keys, SEARCH_HOURS,
        )
        return {row["query"]: (int(row["next_offset"]), bool(row["exhausted"])) for row in rows}

    async def searched(self, pages: list[tuple[Page, bool]]) -> None:
        """Pages Brave answered whose postings are now stored, each with
        whether it was the search's last. A first page starts the window
        again."""
        rows: dict[str, tuple[int, bool]] = {}
        for page, last in pages:
            rows[query_key(page.query)] = (page.offset + 1, last)
        if not rows:
            return
        await self._execute(
            "save searches",
            """INSERT INTO mw_job_board_searches AS s (query, started_at, searched_at, next_offset, exhausted)
               SELECT q.query, NOW(), NOW(), q.next_offset, q.exhausted
               FROM unnest($1::text[], $2::int[], $3::boolean[]) AS q(query, next_offset, exhausted)
               ON CONFLICT (query) DO UPDATE SET
                   started_at = CASE WHEN EXCLUDED.next_offset = 1 THEN NOW() ELSE s.started_at END,
                   searched_at = NOW(),
                   next_offset = CASE WHEN EXCLUDED.next_offset = 1 THEN 1
                                      ELSE GREATEST(s.next_offset, EXCLUDED.next_offset) END,
                   exhausted = CASE WHEN EXCLUDED.next_offset = 1 THEN EXCLUDED.exhausted
                                    ELSE s.exhausted OR EXCLUDED.exhausted END""",
            list(rows), [r[0] for r in rows.values()], [r[1] for r in rows.values()],
        )


def _stored(row) -> Stored:
    record = decode_jsonb(row["record"], None)
    return Stored(
        key=(row["provider"], row["board_key"], row["job_key"]),
        url=row["url"] or (record or {}).get("source_url") or "",
        live=bool(row["live"]),
        fresh=bool(row["fresh"]),
        record=record if isinstance(record, dict) else None,
    )


@asynccontextmanager
async def store(connect: Callable[[], Any]) -> AsyncIterator[Store]:
    """A `Store` on a connection of its own (`connect`, the caller's
    `connection_or_direct`); one that can't be opened stores nothing."""
    async with AsyncExitStack() as stack:
        try:
            conn = await stack.enter_async_context(connect())
        except Exception:
            logger.warning("job postings: no database connection", exc_info=True)
            conn = None
        yield Store(conn)


class Reads:
    """An ATS reader (`Deps.ats_fetch`) that notes each posting its ATS said
    is closed (`ats.read`), so the store can skip it next time. A stand-in
    reader (tests) is called as is and notes nothing."""

    def __init__(self, fetch: Callable[..., Any] = ats.fetch):
        self._fetch = fetch
        self.closed: set[Key] = set()

    async def fetch(self, ref: ats.AtsRef, *, more: Callable[[], bool] | None = None):
        if self._fetch is not ats.fetch:
            return await self._fetch(ref, more=more)
        got = await ats.read(ref, more=more)
        if got.closed:
            self.closed.add(key_of(ref))
        return got.posting
