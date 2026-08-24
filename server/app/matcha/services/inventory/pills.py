"""Channel system-message ("pill") builders for the inventory flow. Every
builder returns a str whose FIRST CHARACTER is the 📦 stock emoji — never
🚨 (systemContent.tsx's isUrgentSystemContent sniffs char 0 for urgent-red;
📦 must never collide with that). Own question-marker wire format, NOT
EMS's — event_intake._QUESTION_MARKER/_QUESTION_SUFFIX are that module's
own round-trip format and must not be reused across features."""

_QUESTION_MARKER = "\n\U00002753 "  # "\n❓ "
_QUESTION_SUFFIX = " Reply to this message to answer."


def movement_pill(item_name: str, qty, remaining, note: str | None, estimated: bool) -> str:
    qty_str = f"~{_fmt_qty(qty)}" if estimated else _fmt_qty(qty)
    base = f"\U0001F4E6 Deducted {qty_str} × {item_name}"
    if note:
        base += f" — {note}"
    if remaining is None:
        base += ". Count unknown — set it on the Inventory page."
    else:
        base += f". {_fmt_qty(remaining)} left."
    return base


def waste_pill(item_name: str, qty, remaining, reason: str, estimated: bool, *, reason_coerced: bool = False) -> str:
    """reason_coerced=True means the reporter's own wording was overridden
    (e.g. an alleged theft became 'unknown') — the pill says so and points
    at the page, per the provenance invariant: a personnel accusation is
    never minted from a chat aside."""
    from app.matcha.services.inventory.waste.reasons import label as _reason_label

    qty_str = f"~{_fmt_qty(qty)}" if estimated else _fmt_qty(qty)
    base = f"\U0001F4E6 Logged {qty_str} × {item_name} as waste — {_reason_label(reason)}"
    if remaining is None:
        base += ". Count unknown — set it on the Inventory page."
    else:
        base += f". {_fmt_qty(remaining)} left."
    if reason_coerced:
        base += (
            " I can't record an accusation from chat, so I logged this as "
            "unknown — set the real reason on the Inventory page if you know it."
        )
    return base


def waste_unmatched_pill(item_name=None) -> str:
    name = _safe_name(item_name)
    if not name:
        return (
            "\U0001F4E6 I don't see that item in the catalog — "
            "add it on the Inventory page first, then I can log the waste."
        )
    return (
        f"\U0001F4E6 I don't see {name} in the catalog — "
        "add it on the Inventory page first, then I can log the waste."
    )


def return_pill(item_name: str, qty, new_count, estimated: bool, unmatched: list[str] | None = None) -> str:
    """Chat-only return — no invoice/receipt/CSV needed by design, unlike
    every other addition (services/inventory/CLAUDE.md provenance
    invariant). Same estimated-quantity shape as movement_pill.
    `unmatched`: item names from the SAME return message that didn't match
    the catalog — a mixed return (one line resolves, one doesn't) must say
    so, or the reporter believes the unresolved line went back on the shelf
    too."""
    qty_str = f"~{_fmt_qty(qty)}" if estimated else _fmt_qty(qty)
    base = f"\U0001F4E6 Put back {qty_str} × {item_name}"
    if new_count is None:
        base += ". Count unknown — set it on the Inventory page."
    else:
        base += f". {_fmt_qty(new_count)} on hand."
    names = [_safe_name(n) for n in (unmatched or []) if _safe_name(n)]
    if names:
        base += f" Couldn't find {', '.join(names)} in the catalog — add it on the Inventory page first."
    return base


def _safe_name(name) -> str:
    """Item names in a pill can come straight from raw chat text (the
    return-unmatched fallback used to pass the WHOLE message). First line
    only + hard cap so a crafted message can't forge this feature's own
    \n❓ clarify wire format, or another feature's [[shift:...]] token,
    into a system message."""
    text = str(name or "").strip()
    if not text:
        return ""
    return text.splitlines()[0].strip()[:80]


def return_unmatched_pill(item_name=None) -> str:
    name = _safe_name(item_name)
    if not name:
        return (
            "\U0001F4E6 I don't see that item in the catalog — "
            "add it on the Inventory page first, then I can put the return back."
        )
    return (
        f"\U0001F4E6 I don't see {name} in the catalog — "
        "add it on the Inventory page first, then I can put the return back."
    )


def quantity_question(pill: str) -> str:
    return f"{pill}{_QUESTION_MARKER}How many?{_QUESTION_SUFFIX}"


def extract_question(pill_content: str) -> str:
    idx = pill_content.find(_QUESTION_MARKER)
    if idx == -1:
        return pill_content
    question = pill_content[idx + len(_QUESTION_MARKER):]
    if question.endswith(_QUESTION_SUFFIX):
        return question[: -len(_QUESTION_SUFFIX)]
    return question


def _fmt_qty(qty) -> str:
    """Whole numbers render bare — suggest_order works in floats, so an
    un-formatted suggestion reads as "order 20.0" in the channel."""
    try:
        f = float(qty)
    except (TypeError, ValueError):
        return str(qty)
    return str(int(f)) if f == int(f) else str(f)


def _order_suggestion_clause(suggestion: dict | None, order_qty) -> str:
    """Shared tail of stockout_pill/reorder_pill. The lead-in is a
    semicolon when the history clause precedes it and a fresh sentence
    otherwise — without this the pill read ". suggest ordering 20."."""
    days_clause = ""
    if suggestion and suggestion.get("avg_stockout_interval_days"):
        days = round(suggestion["avg_stockout_interval_days"])
        days_clause = f" You've run out ~every {days} days;"
    if order_qty is None:
        return days_clause + (
            " not enough history yet to suggest an amount — set one on the Inventory page."
            if days_clause else
            " Not enough history yet to suggest an amount — set one on the Inventory page."
        )
    verb = "suggest" if days_clause else "Suggest"
    return f"{days_clause} {verb} ordering {_fmt_qty(order_qty)}."


def stockout_pill(item_name: str, suggestion: dict | None, order_qty) -> str:
    base = f"\U0001F4E6 {item_name} marked out of stock."
    base += _order_suggestion_clause(suggestion, order_qty)
    base += " Reply **confirm** to queue it, a number to change the amount, or **cancel**."
    return base


def reorder_pill(item_name: str, suggestion: dict | None, order_qty) -> str:
    """Same staged-order shape as `stockout_pill` (identical trailing
    "Reply **confirm**..." sentence, so `_bg_inventory_reply`'s
    confirm/cancel/quantity-edit parsing is unaffected) but for a request
    someone explicitly asked for — never claims the item was marked out of
    stock, since no `stockout` movement was recorded and the current count
    may be fine."""
    base = f"\U0001F4E6 Staging an order for {item_name}."
    base += _order_suggestion_clause(suggestion, order_qty)
    base += " Reply **confirm** to queue it, a number to change the amount, or **cancel**."
    return base


def order_updated_pill(item_name: str, new_qty) -> str:
    """Quantity-change reply on an already-staged order. inventory_orders
    has no column recording whether the order originated from a `stockout`
    or an explicit `order_request` — a shared, neutral pill for both,
    replacing the old call that always rendered stockout_pill (claiming
    "marked out of stock" even for a plain reorder request)."""
    base = f"\U0001F4E6 Updated the order for {item_name}: {_fmt_qty(new_qty)}."
    base += " Reply **confirm** to queue it, or **cancel**."
    return base


def channel_receipt_pill(received: list[dict], unmatched: list[str]) -> str:
    """Channel `@huume` receipt-shaped intake — never a bare 'received' claim
    (see receipts.receive_channel_lines' provenance invariant): each line
    either checks in against its own open order, or gets steered toward a
    real audit trail. `received`: [{item_name, quantity, new_count}]."""
    steer = (
        "Use Receive Delivery on the Inventory page (it wants the invoice), "
        "or queue an order first and I'll check it in when it lands."
    )

    if not received:
        return (
            "\U0001F4E6 Sounds like a delivery — I can't book received stock from chat alone. "
            f"{steer}"
        )

    def _line(r: dict) -> str:
        return f"{r['quantity']:g} × {r['item_name']}" if isinstance(r["quantity"], (int, float)) else f"{r['quantity']} × {r['item_name']}"

    if len(received) == 1 and not unmatched:
        r = received[0]
        base = f"\U0001F4E6 Received {_line(r)} — checked in against the open order."
        if r.get("new_count") is not None:
            base += f" {r['new_count']} in stock now."
        return base

    base = f"\U0001F4E6 Checked in against open orders: {', '.join(_line(r) for r in received)}."
    if unmatched:
        base += f" Couldn't check in {', '.join(unmatched)} — no open order; {steer}"
    return base


def order_confirmed_pill(item_name: str, qty) -> str:
    return f"\U0001F4E6 Order queued: {_fmt_qty(qty)} × {item_name}. Approved and marked ordered."


def order_cancelled_pill(item_name: str) -> str:
    return f"\U0001F4E6 Order for {item_name} cancelled."


def rearm_pill() -> str:
    return "\U0001F4E6 Didn't catch that — reply **confirm**, a number, or **cancel**."


def receipt_draft_pill(*, vendor, invoice_number, preview: list[dict]) -> str:
    """Review pill for an attached invoice/packing-slip, before the admin's
    confirm reply commits it (`receipts.receive_channel_lines`, strict —
    same provenance invariant as `channel_receipt_pill`: only lines that
    match an open order will actually check in, nothing is auto-created).
    `preview`: `receipts.resolve_lines`' output — used here for display
    only, RE-resolved fresh at confirm time against current state."""
    header = f"\U0001F4E6 Got the {vendor} invoice" if vendor else "\U0001F4E6 Got that delivery invoice"
    if invoice_number:
        header += f" (#{invoice_number})"
    header += " — here's what I can check in:"
    lines = [header]
    for p in preview:
        label = p.get("matched_name") or p.get("item_name")
        qty = p.get("quantity")
        qty_str = f"{qty:g}" if isinstance(qty, (int, float)) else (qty or "?")
        if p.get("open_order_id"):
            lines.append(f"✓ {qty_str} × {label} — has an open order")
        else:
            lines.append(f"✗ {qty_str} × {label} — no open order, will be skipped")
    lines.append("Reply **confirm** to check in the matched lines, or **cancel**.")
    return "\n".join(lines)


def receipt_draft_cancelled_pill() -> str:
    return "\U0001F4E6 Scrapped that invoice — nothing was checked in."
