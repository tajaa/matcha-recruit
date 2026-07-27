"""Shared helpers for the Cappe routers."""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from ..services.common import (  # noqa: F401
    RESERVED_SUBDOMAINS,
    loads,
    loads_list,
    safe_subdomain_base,
    slugify,
)

# asyncpg returns JSONB columns as text (no global codec is registered), so
# every JSONB read goes through _loads and every write through json.dumps.


async def unique_slug(conn, base: str, table: str, column: str = "slug") -> str:
    """Return `base`, or `base-2`, `base-3`, … until it's free in table.column.

    Table/column are caller-controlled literals (never user input), so the
    f-string is safe; the value is always parameterized.
    """
    candidate = base
    n = 1
    while True:
        exists = await conn.fetchval(
            f"SELECT 1 FROM {table} WHERE {column} = $1", candidate
        )
        if not exists:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


async def unique_site_slug(conn, table: str, site_id, base: str, column: str = "slug") -> str:
    """Per-site slug uniqueness for tables with UNIQUE(site_id, slug). `table`
    and `column` are caller literals (never user input)."""
    candidate = base
    n = 1
    while await conn.fetchval(
        f"SELECT 1 FROM {table} WHERE site_id = $1 AND {column} = $2", site_id, candidate
    ):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def get_owned_site(conn, site_id: UUID, account_id: UUID):
    """Fetch a site row, 404ing if it doesn't exist or isn't this account's.

    Same id is returned for missing-vs-forbidden so we never leak which site
    ids exist across accounts.
    """
    row = await conn.fetchrow(
        "SELECT * FROM cappe_sites WHERE id = $1 AND account_id = $2",
        site_id,
        account_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return row


async def fetch_option_groups(conn, product_ids: list) -> dict:
    """{product_id: [group dicts with nested options]} for the given products.
    Read-only; shared by the owner shop routes and the public storefront."""
    if not product_ids:
        return {}
    grows = await conn.fetch(
        "SELECT id, product_id, name, select_type, required, sort_order "
        "FROM cappe_product_option_groups WHERE product_id = ANY($1::uuid[]) "
        "ORDER BY sort_order, created_at",
        product_ids,
    )
    orows = await conn.fetch(
        "SELECT o.id, o.group_id, o.name, o.price_delta_cents, o.sort_order, o.inventory "
        "FROM cappe_product_options o "
        "JOIN cappe_product_option_groups g ON g.id = o.group_id "
        "WHERE g.product_id = ANY($1::uuid[]) ORDER BY o.sort_order, o.created_at",
        product_ids,
    )
    opts_by_group: dict = {}
    for o in orows:
        opts_by_group.setdefault(o["group_id"], []).append({
            "id": o["id"], "name": o["name"],
            "price_delta_cents": o["price_delta_cents"], "sort_order": o["sort_order"],
            "inventory": o["inventory"],
        })
    by_product: dict = {}
    for g in grows:
        by_product.setdefault(g["product_id"], []).append({
            "id": g["id"], "name": g["name"], "select_type": g["select_type"],
            "required": g["required"], "sort_order": g["sort_order"],
            "options": opts_by_group.get(g["id"], []),
        })
    return by_product


async def _site_owner(conn, site_id: UUID):
    """The site owner's account (email/name + Stripe-Connect status), for creator
    notifications and storefront checkout. Returns None if the site (or its
    account) is gone."""
    return await conn.fetchrow(
        "SELECT a.email, a.name, a.stripe_account_id, a.stripe_charges_enabled "
        "FROM cappe_accounts a JOIN cappe_sites s ON s.account_id = a.id WHERE s.id = $1",
        site_id,
    )


def site_row_to_dict(row, page_count: Optional[int] = None) -> dict:
    """Map a cappe_sites row to the CappeSite response shape."""
    d = dict(row)
    d["theme_config"] = loads(row["theme_config"])
    d["meta_config"] = loads(row["meta_config"])
    if page_count is not None:
        d["page_count"] = page_count
    return d


def page_row_to_dict(row) -> dict:
    """Map a cappe_pages row to the CappePage response shape."""
    d = dict(row)
    d["content"] = loads(row["content"])
    return d
