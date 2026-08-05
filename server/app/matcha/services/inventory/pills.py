"""Channel system-message ("pill") builders for the inventory flow. Every
builder returns a str whose FIRST CHARACTER is the 📦 stock emoji — never
🚨 (systemContent.tsx's isUrgentSystemContent sniffs char 0 for urgent-red;
📦 must never collide with that). Own question-marker wire format, NOT
EMS's — event_intake._QUESTION_MARKER/_QUESTION_SUFFIX are that module's
own round-trip format and must not be reused across features."""

_QUESTION_MARKER = "\n\U00002753 "  # "\n❓ "
_QUESTION_SUFFIX = " Reply to this message to answer."


def movement_pill(item_name: str, qty, remaining, note: str | None, estimated: bool) -> str:
    qty_str = f"~{qty}" if estimated else str(qty)
    base = f"\U0001F4E6 Deducted {qty_str} × {item_name}"
    if note:
        base += f" — {note}"
    if remaining is None:
        base += ". Count unknown — set it on the Inventory page."
    else:
        base += f". {remaining} left."
    return base


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


def stockout_pill(item_name: str, suggestion: dict | None, order_qty) -> str:
    base = f"\U0001F4E6 {item_name} marked out of stock."
    if suggestion and suggestion.get("avg_stockout_interval_days"):
        days = round(suggestion["avg_stockout_interval_days"])
        base += f" You've run out ~every {days} days;"
    if order_qty is not None:
        base += f" suggest ordering {order_qty}."
    else:
        base += " not enough history yet to suggest an amount — set one on the Inventory page."
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
    if suggestion and suggestion.get("avg_stockout_interval_days"):
        days = round(suggestion["avg_stockout_interval_days"])
        base += f" You've historically run out ~every {days} days;"
    if order_qty is not None:
        base += f" suggest ordering {order_qty}."
    else:
        base += " not enough history yet to suggest an amount — set one on the Inventory page."
    base += " Reply **confirm** to queue it, a number to change the amount, or **cancel**."
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
    return f"\U0001F4E6 Order queued: {qty} × {item_name}. Approved and marked ordered."


def order_cancelled_pill(item_name: str) -> str:
    return f"\U0001F4E6 Order for {item_name} cancelled."


def rearm_pill() -> str:
    return "\U0001F4E6 Didn't catch that — reply **confirm**, a number, or **cancel**."
