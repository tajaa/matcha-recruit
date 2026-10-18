"""Ten findings at a time.

A research round doesn't show everything it found. It releases a batch: the
best findings not shown yet that meet their kind's bar (`missing`), at most
`BATCH`, in rank order. The rest wait. "10 more" (a `more` round) releases the
next batch from them before it searches again, so the person is fed a few
good findings at a time rather than every one the search turned up.

Released ids are each round's `summary["batch"]`: no column of their own. A
task whose plan has `batches` shows only those, plus what the person saved or
chose (`SHOWN_SQL`, `shown`); a task planned before batches shows everything,
as it did.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.database import decode_jsonb

BATCH = 10
# Photos copied for a finding when its batch is released.
PHOTOS_PER_ITEM = 2

# What a finding of each kind must show before it is released. A finding that
# can't be priced, pictured or called waits; the summary says how many do. A
# kind that needs a price also waits on one only another site states (claimed)
# that is outside the person's price limit: `over_limit`.
REQUIRED: dict[str, tuple[str, ...]] = {
    "listing": ("price", "photo", "contact"),
    "place": ("photo", "contact"),
    "product": ("price", "photo"),
}
OVER_LIMIT = "over_limit"
MARKED = ("saved", "chosen")

# The findings a person sees, for SQL with the task as `t` and its items as `i`.
SHOWN_SQL = """(NOT COALESCE((t.plan->>'batches')::boolean, false)
    OR i.user_state IN ('saved', 'chosen')
    OR i.id::text IN (SELECT jsonb_array_elements_text(r.summary->'batch') FROM mw_agent_task_rounds r
                      WHERE r.task_id = i.task_id AND jsonb_typeof(r.summary->'batch') = 'array'))"""


def _get(row: Any, key: str, default: Any) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _decoded(row: Any, key: str, default: Any) -> Any:
    return decode_jsonb(_get(row, key, None), default) or default


def has_price(row: Any) -> bool:
    fields = _decoded(row, "fields", {})
    if isinstance(fields.get("price"), dict):
        return True
    return any(isinstance(u, dict) and u.get("rent") for u in _decoded(row, "units", []))


def has_photo(row: Any) -> bool:
    return bool(_decoded(row, "images", []))


def has_contact(row: Any) -> bool:
    fields = _decoded(row, "fields", {})
    return isinstance(fields.get("phone"), dict)


_CHECKS = {"price": has_price, "photo": has_photo, "contact": has_contact}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def claimed_price(row: Any) -> dict | None:
    price = _decoded(row, "fields", {}).get("price")
    return price if isinstance(price, dict) and price.get("status") == "claimed" else None


def over_limit(row: Any, plan: dict | None) -> bool:
    """Whether the finding's price is one only another site states (`claimed`,
    a look-up's snippet) and is outside the person's price limit. A claimed
    fact never breaks a limit in the ranking (it isn't the finding's own word),
    but a building a listing site says starts at $3,600 isn't one to show
    someone who said $3,200: it waits, and the suggestion can offer the limit
    it would take."""
    price = claimed_price(row)
    low = _number(price.get("value")) if price else None
    if low is None:
        return False
    high = _number(price.get("high")) or low
    for limit in (plan or {}).get("constraints") or []:
        if not isinstance(limit, dict) or limit.get("field") != "price":
            continue
        if limit.get("unit") and price.get("unit") and limit["unit"] != price["unit"]:
            continue
        value, op = limit.get("value"), limit.get("op")
        if op == "between" and isinstance(value, list) and len(value) == 2:
            bounds = sorted(v for v in (_number(x) for x in value) if v is not None)
            ceiling, floor = (bounds[1], bounds[0]) if len(bounds) == 2 else (None, None)
        else:
            cap = _number(value)
            ceiling, floor = (cap if op == "lte" else None), (cap if op == "gte" else None)
        if (ceiling is not None and low > ceiling) or (floor is not None and high < floor):
            return True
    return False


def missing(row: Any, item_kind: str | None, plan: dict | None = None) -> list[str]:
    """What this finding still lacks to be released (empty: it can be)."""
    needs = REQUIRED.get(item_kind or "", ())
    out = [need for need in needs if not _CHECKS[need](row)]
    if "price" in needs and "price" not in out and over_limit(row, plan):
        out.append(OVER_LIMIT)
    return out


def released(summaries: Iterable[Any]) -> list[str]:
    """Every finding a round released, oldest round first, each once."""
    out: dict[str, None] = {}
    for summary in summaries:
        batch = (decode_jsonb(summary, {}) or {}).get("batch") if summary is not None else None
        for item_id in batch if isinstance(batch, list) else []:
            out.setdefault(str(item_id), None)
    return list(out)


def uses_batches(plan: dict | None) -> bool:
    return bool((plan or {}).get("batches"))


def shown(rows: list[Any], *, plan: dict | None, released_ids: Iterable[str]) -> list[Any]:
    """`rows` as the person sees them: all of them for a task from before
    batches, else the released ones and what the person marked."""
    if not uses_batches(plan):
        return rows
    keep = set(released_ids)
    return [r for r in rows if str(_get(r, "id", "")) in keep or _get(r, "user_state", "") in MARKED]


def pick(rows: list[Any], *, item_kind: str | None, plan: dict | None = None, exclude: Iterable[str] = (),
         n: int = BATCH) -> list[Any]:
    """The next batch: `rows` (rank order) not in `exclude` that meet their
    kind's bar under `plan`, at most `n`."""
    skip = {str(i) for i in exclude}
    return [r for r in rows if str(_get(r, "id", "")) not in skip and not missing(r, item_kind, plan)][:n]


def shortfall(rows: list[Any], *, item_kind: str | None, plan: dict | None = None,
              exclude: Iterable[str] = ()) -> dict[str, int]:
    """For the findings still waiting: how many lack each requirement."""
    skip = {str(i) for i in exclude}
    out: dict[str, int] = {}
    for row in rows:
        if str(_get(row, "id", "")) in skip:
            continue
        for need in missing(row, item_kind, plan):
            out[need] = out.get(need, 0) + 1
    return out
