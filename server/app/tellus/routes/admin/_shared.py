"""Pure SQL filter builders for the Tell-Us internal admin list endpoints.
No DB access — unit-tested in server/tests/tellus/test_admin_management.py.
"""
from typing import Optional

from .._shared import escape_like


def account_filter_sql(
    *, q: Optional[str] = None, account_type: Optional[str] = None,
    status: Optional[str] = None, verified: Optional[bool] = None,
    start_idx: int = 1,
) -> tuple[str, list]:
    """WHERE fragment (leading ' WHERE ', or '' when unfiltered) + params,
    placeholders numbered from start_idx. q ILIKEs email + display_name."""
    clauses: list[str] = []
    params: list = []
    i = start_idx
    if q:
        clauses.append(f"(a.email ILIKE ${i} OR a.display_name ILIKE ${i})")
        params.append(f"%{escape_like(q)}%")
        i += 1
    if account_type:
        clauses.append(f"a.account_type = ${i}")
        params.append(account_type)
        i += 1
    if status:
        clauses.append(f"a.status = ${i}")
        params.append(status)
        i += 1
    if verified is not None:
        clauses.append("a.email_verified_at IS NOT NULL" if verified else "a.email_verified_at IS NULL")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


_REVIEW_STATE_FRAGMENTS = {
    "published": "r.review_state = 'held' AND r.publish_at IS NOT NULL AND r.publish_at <= NOW()",
    "held": "r.review_state = 'held' AND (r.publish_at IS NULL OR r.publish_at > NOW())",
    "withdrawn": "r.review_state = 'withdrawn'",
}


def report_filter_sql(
    *, moderation_status: Optional[str] = None, review_state: Optional[str] = None,
    brand_id: Optional[str] = None, q: Optional[str] = None, start_idx: int = 1,
) -> tuple[str, list]:
    """review_state filters the EFFECTIVE state (mirror of
    routes/_shared.py:effective_review_state) — 'published' is never stored,
    only derived from review_state='held' + publish_at in the past."""
    clauses: list[str] = []
    params: list = []
    i = start_idx
    if moderation_status:
        clauses.append(f"r.moderation_status = ${i}")
        params.append(moderation_status)
        i += 1
    if review_state:
        fragment = _REVIEW_STATE_FRAGMENTS.get(review_state)
        if fragment:
            clauses.append(fragment)
    if brand_id:
        clauses.append(f"r.brand_id = ${i}")
        params.append(brand_id)
        i += 1
    if q:
        clauses.append(f"(r.title ILIKE ${i} OR r.description ILIKE ${i})")
        params.append(f"%{escape_like(q)}%")
        i += 1
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
