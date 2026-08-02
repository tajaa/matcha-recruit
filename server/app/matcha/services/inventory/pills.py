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


def receipt_pill(item_name: str, qty, new_count) -> str:
    base = f"\U0001F4E6 Received {qty} × {item_name}."
    if new_count is not None:
        base += f" {new_count} in stock now."
    return base


def order_confirmed_pill(item_name: str, qty) -> str:
    return f"\U0001F4E6 Order queued: {qty} × {item_name}. Approved and marked ordered."


def order_cancelled_pill(item_name: str) -> str:
    return f"\U0001F4E6 Order for {item_name} cancelled."


def rearm_pill() -> str:
    return "\U0001F4E6 Didn't catch that — reply **confirm**, a number, or **cancel**."
