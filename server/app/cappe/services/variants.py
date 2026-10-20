"""Cappe product variants — one row per combination of a product's variant groups.

A product's VARIANT GROUPS are its required single-pick option groups (Size,
Colour). A variant is one option from each of them ("M / Red") with its own
stock, SKU, price and picture. Every other group (optional picks, add-ons) stays
a plain option with its own price change and, optionally, its own stock.

Stock rule — the one every stock path follows (checkout, restock, re-take):
when a selection matches a variant, the variant owns the stock of the options
it is made of. Their own option stock is not touched; options outside the
variant (an add-on) still move theirs. The product's own stock, when tracked,
is the total and moves as it always has.

A selection with no variant row (a store that hasn't set any up, or a
combination it never created) behaves exactly as before variants existed.

The matching and pricing here are pure (unit-tested); `fetch_variants`,
`replace_variants` and `prune_variants` are the DB side, run inside the
caller's transaction after it has locked the product row.
"""
from __future__ import annotations

from typing import Iterable, Optional
from uuid import UUID

from fastapi import HTTPException, status

from .inventory import log_adjustment
from .options import fetch_option_groups, validate_and_price_options

MAX_VARIANTS = 100

_COLS = "id, product_id, option_ids, sku, price_cents, inventory, image_url, status, sort_order"


def variant_groups(groups) -> list[dict]:
    """The groups a variant is made of: required, single-pick."""
    return [g for g in (groups or []) if g.get("select_type") == "single" and g.get("required")]


def sorted_ids(ids: Iterable) -> list:
    """Option ids in the one order a variant stores them (uuid text order), so a
    selection finds its row by equality."""
    return sorted({i for i in ids if i is not None}, key=str)


def variant_key(groups, selected_ids) -> Optional[frozenset[str]]:
    """The selected options a variant would be made of, or None when the
    product has no variant groups or a variant group has no pick yet."""
    axes = variant_groups(groups)
    if not axes:
        return None
    selected = {str(s) for s in (selected_ids or [])}
    picks = []
    for g in axes:
        hit = [str(o["id"]) for o in g.get("options") or [] if str(o["id"]) in selected]
        if len(hit) != 1:
            return None
        picks.append(hit[0])
    return frozenset(picks)


def match_variant(variants, groups, selected_ids) -> Optional[dict]:
    """The variant row this selection is, whatever its status; None = none."""
    key = variant_key(groups, selected_ids)
    if key is None:
        return None
    for v in variants or []:
        if frozenset(str(i) for i in v["option_ids"]) == key:
            return v
    return None


def resolve_variant(variants, groups, selected_ids) -> Optional[dict]:
    """`match_variant`, refusing a combination the store doesn't sell."""
    v = match_variant(variants, groups, selected_ids)
    if v is not None and v.get("status") != "active":
        raise ValueError("That combination isn't available")
    return v


def price_selection(base_price_cents: int, groups, selected_ids, variant=None) -> tuple[int, list[dict]]:
    """(price before any discount, snapshot of the chosen options).

    Without a variant, or with one that has no price of its own, this is the
    product's price plus every chosen option's change — exactly what it was. A
    variant's own price replaces the product price AND the changes of the
    options it is made of; add-ons outside it still add theirs, and the
    snapshot then records those covered options at 0 so the line still adds up.
    Raises ValueError on an invalid selection."""
    delta, snapshot = validate_and_price_options(groups, selected_ids)
    if variant is None or variant.get("price_cents") is None:
        return max(0, base_price_cents + delta), snapshot
    covered = {str(i) for i in variant["option_ids"]}
    selected = {str(s) for s in (selected_ids or [])}
    # The snapshot lists the chosen options in group order, then option order:
    # pair each entry with its option id so "covered" is decided by id, never
    # by a name another group might share.
    chosen = [str(o["id"]) for g in groups or [] for o in g.get("options") or [] if str(o["id"]) in selected]
    out = [{**entry, "price_delta_cents": 0} if oid in covered else entry for oid, entry in zip(chosen, snapshot)]
    extra = sum(int(entry.get("price_delta_cents") or 0) for entry in out)
    return max(0, int(variant["price_cents"]) + extra), out


def uncovered_option_ids(selected_ids, variant) -> list:
    """The chosen options whose own stock still moves: those outside the variant."""
    if variant is None:
        return list(selected_ids or [])
    covered = {str(i) for i in variant["option_ids"]}
    return [o for o in (selected_ids or []) if str(o) not in covered]


def variant_label(groups, option_ids) -> str:
    """"M / Red" — the variant's options in the product's group order."""
    wanted = {str(i) for i in option_ids or []}
    parts = []
    for g in groups or []:
        for o in g.get("options") or []:
            if str(o["id"]) in wanted:
                parts.append(str(o.get("name")))
    return " / ".join(parts)


def _row(r) -> dict:
    return {**dict(r), "option_ids": list(r["option_ids"] or [])}


async def fetch_variants(conn, product_ids: list) -> dict:
    """{product_id: [variant dicts]} for the given products. Read-only."""
    if not product_ids:
        return {}
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM cappe_product_variants WHERE product_id = ANY($1::uuid[]) "
        "ORDER BY sort_order, created_at, id",
        list(product_ids),
    )
    out: dict = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(_row(r))
    return out


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def resolve_refs(groups, refs) -> list:
    """A variant's {group, option} names → its sorted option ids. Pure.

    Every variant group must be named exactly once, by a name that means one
    group and one option — the editor sends names because options created in
    the same save have no ids yet."""
    axes = variant_groups(groups)
    if not axes:
        raise _invalid("Variants need at least one required, pick-one option group (like Size).")
    picked: dict[str, str] = {}
    for ref in refs:
        named = [g for g in axes if g["name"] == ref.group]
        if len(named) != 1:
            raise _invalid(
                f'"{ref.group}" isn\'t a required, pick-one option group of this product.' if not named
                else f'Two option groups are called "{ref.group}". Rename one to set up variants.'
            )
        g = named[0]
        opts = [o for o in g.get("options") or [] if o["name"] == ref.option]
        if len(opts) != 1:
            raise _invalid(
                f'"{ref.group}" has no option called "{ref.option}".' if not opts
                else f'Two options in "{ref.group}" are called "{ref.option}". Rename one to set up variants.'
            )
        if str(g["id"]) in picked:
            raise _invalid(f'A variant picks one "{g["name"]}", not two.')
        picked[str(g["id"])] = opts[0]["id"]
    missing = [g["name"] for g in axes if str(g["id"]) not in picked]
    if missing:
        raise _invalid(f'Each variant needs a {", ".join(missing)}.')
    return sorted_ids(picked.values())


def _stock_conflict(now) -> HTTPException:
    state = "is no longer tracked" if now is None else f"is now {now}"
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A variant's stock changed while you were editing — it {state}. "
               "Reload the product and set the stock again.",
    )


async def replace_variants(conn, site_id: UUID, product_id: UUID, variants) -> None:
    """Bring a product's variants in line with `variants` (None = leave them,
    [] = remove them all), keeping the id of every combination that survives.

    Rows pair by id when the id still names the same combination, else by the
    combination itself. A row's combination never changes: order lines and
    the stock ledger point at it, and a variant that started meaning a
    different thing would restock the wrong shelf. Stock is tri-state like
    option stock, checked against `expected_inventory`, and every change is a
    ledger row. MUST run inside the caller's transaction, after the product row
    is locked and the option groups written."""
    if variants is None:
        return
    if len(variants) > MAX_VARIANTS:
        raise _invalid(f"A product can have at most {MAX_VARIANTS} variants.")
    groups = (await fetch_option_groups(conn, [product_id])).get(product_id, []) if variants else []
    wanted = [(v, resolve_refs(groups, v.options)) for v in variants]
    seen: set[tuple] = set()
    for _v, ids in wanted:
        key = tuple(str(i) for i in ids)
        if key in seen:
            raise _invalid(f'"{variant_label(groups, ids)}" is listed twice.')
        seen.add(key)

    prior = [_row(r) for r in await conn.fetch(
        f"SELECT {_COLS} FROM cappe_product_variants WHERE product_id = $1 AND site_id = $2 "
        "ORDER BY id FOR UPDATE",
        product_id, site_id,
    )]
    left = list(prior)

    def claim(pred):
        hit = next((row for row in left if pred(row)), None)
        if hit is not None:
            left.remove(hit)
        return hit

    pairs = []
    for v, ids in wanted:
        same = lambda row, ids=ids: [str(i) for i in row["option_ids"]] == [str(i) for i in ids]  # noqa: E731
        hit = claim(lambda row, v=v, same=same: v.id is not None and row["id"] == v.id and same(row))
        pairs.append(hit)
    for i, ((v, ids), hit) in enumerate(zip(wanted, pairs)):
        if hit is None:
            pairs[i] = claim(lambda row, ids=ids: [str(x) for x in row["option_ids"]] == [str(x) for x in ids])

    for pos, ((v, ids), was) in enumerate(zip(wanted, pairs)):
        label = variant_label(groups, ids)
        if was is None:
            vid = await conn.fetchval(
                """INSERT INTO cappe_product_variants
                       (site_id, product_id, option_ids, sku, price_cents, inventory, image_url, status, sort_order)
                   VALUES ($1, $2, $3::uuid[], $4, $5, $6, $7, $8, $9) RETURNING id""",
                site_id, product_id, ids, v.sku, v.price_cents, v.inventory, v.image_url, v.status, pos,
            )
            if v.inventory is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=product_id, variant_id=vid,
                    delta=v.inventory, balance_after=v.inventory, reason="adjustment",
                    note=f"Opening stock — {label}",
                )
            continue
        sets = ["sku = $1", "price_cents = $2", "image_url = $3", "status = $4", "sort_order = $5",
                "updated_at = NOW()"]
        args: list = [v.sku, v.price_cents, v.image_url, v.status, pos]
        if "inventory" in v.model_fields_set and v.inventory != was["inventory"]:
            if "expected_inventory" in v.model_fields_set and v.expected_inventory != was["inventory"]:
                raise _stock_conflict(was["inventory"])
            args.append(v.inventory)
            sets.append(f"inventory = ${len(args)}")
            if v.inventory is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=product_id, variant_id=was["id"],
                    delta=v.inventory - (was["inventory"] or 0), balance_after=v.inventory,
                    reason="adjustment", note=f"Set in the product editor — {label}",
                )
        args.append(was["id"])
        await conn.execute(
            f"UPDATE cappe_product_variants SET {', '.join(sets)} WHERE id = ${len(args)}", *args,
        )
    if left:
        await conn.execute(
            "DELETE FROM cappe_product_variants WHERE id = ANY($1::uuid[]) AND site_id = $2",
            [row["id"] for row in left], site_id,
        )


def fits(groups, option_ids) -> bool:
    """Whether a stored combination is still one option from each of the
    product's variant groups — and nothing else."""
    return variant_key(groups, option_ids) == frozenset(str(i) for i in (option_ids or []))


async def prune_variants(conn, site_id: UUID, product_id: UUID, groups) -> None:
    """Drop the variants that no longer fit the product's option groups as just
    written (`groups`, in `fetch_option_groups` shape): one made of a deleted
    option, one whose group stopped being a variant group (made optional or
    pick-many), or one missing a pick from a variant group added since. Nobody
    can pick such a combination at checkout again; left behind, it would still
    mark options sold out on the storefront and count on the dashboard."""
    rows = await conn.fetch(
        "SELECT id, option_ids FROM cappe_product_variants WHERE product_id = $1 AND site_id = $2 "
        "ORDER BY id FOR UPDATE",
        product_id, site_id,
    )
    misfits = [r["id"] for r in rows if not fits(groups, r["option_ids"])]
    if misfits:
        await conn.execute(
            "DELETE FROM cappe_product_variants WHERE id = ANY($1::uuid[]) AND site_id = $2",
            misfits, site_id,
        )
