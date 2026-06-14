"""Cappe product options — pure validation + pricing (no DB, unit-tested).

A product's option groups (Size, Milk, Add-ons) carry options with a signed
price_delta_cents. At checkout the customer sends only the selected option ids;
this module validates them against the product's live groups and returns the
total delta plus a snapshot to persist on the order line. Money is recomputed
here server-side — never trusted from the client.
"""


def validate_and_price_options(groups, selected_ids):
    """Validate a selection and price it.

    `groups`: the product's option groups as dicts —
        [{id, name, select_type:'single'|'multi', required:bool,
          options:[{id, name, price_delta_cents}]}].
    `selected_ids`: iterable of option ids the customer chose.

    Returns (delta_total_cents, snapshot) where snapshot is
        [{group, name, price_delta_cents}] for the chosen options.
    Raises ValueError on an invalid selection (the route maps it to HTTP 400):
      - an id that doesn't belong to this product
      - more than one option in a single-select group
      - no option in a required group
    """
    selected = {str(s) for s in (selected_ids or [])}

    # Index every option that belongs to this product.
    valid: dict[str, tuple[dict, dict]] = {}
    for g in groups or []:
        for o in g.get("options") or []:
            valid[str(o["id"])] = (g, o)

    # Reject any selected id not belonging to this product's groups.
    unknown = selected - set(valid)
    if unknown:
        raise ValueError("Unknown product option")

    delta_total = 0
    snapshot: list[dict] = []
    for g in groups or []:
        group_ids = [str(o["id"]) for o in (g.get("options") or [])]
        chosen = [oid for oid in group_ids if oid in selected]
        label = g.get("name") or "option"
        if g.get("select_type") == "single" and len(chosen) > 1:
            raise ValueError(f"Pick only one {label}")
        if g.get("required") and len(chosen) < 1:
            raise ValueError(f"Please choose a {label}")
        for oid in chosen:
            _, o = valid[oid]
            d = int(o.get("price_delta_cents") or 0)
            delta_total += d
            snapshot.append({"group": g.get("name"), "name": o.get("name"), "price_delta_cents": d})

    return delta_total, snapshot
