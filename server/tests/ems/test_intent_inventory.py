import pytest

from app.matcha.services.ems.intent import ASK, INVENTORY, LOG, classify_intent

INVENTORY_POSITIVES = [
    "@huume we gifted some Cherry Farms cookies to Elizabeth our manager",
    "@huume we ran out of salads again",
    "@huume we're low on cups",
    "@huume we used up the last coffee filters",
    "@huume we received the produce delivery",
    "@huume we need to reorder napkins",
    "hey @huume we ran out of salads",
    # F5 — quantity-led "used" (bare "used" stays excluded, see negatives).
    "@huume we used 2 boxes of nitrile gloves",
    "@huume we used a case of paper towels",
    "@huume we used some napkins",
    "@huume i used a few gloves",
    # F6 — chat-only addition claims, routed to the same strict receipt
    # branch as every other addition (never auto-created, never a lie).
    "@huume we got 3 more reams of printer paper in stock, please add them",
    "@huume we bought 10 more masks",
    "@huume please add these gloves back to the inventory",
    # NOTE: a bot-directed "can you add ..." (no object clause reaching
    # "stock"/"inventory" first) classifies SCHEDULE instead — that's the
    # pre-existing bot-directed staffing pattern (_SCHEDULE_PATTERNS,
    # "can you add/staff/book/schedule/put"), checked before INVENTORY,
    # and deliberately not narrowed here.
    # F7 — chat-only returns (no document required, unlike other additions).
    "@huume a patient returned an unopened box of nitrile gloves, put it back in stock",
    "@huume the customer returned two masks",
    "@huume we got a return from a client",
    "@huume someone returned their gloves",
    "@huume please put them back in stock",
    "@huume put that back into inventory",
]

LOG_NEGATIVES = [
    "@huume we gave John a written warning",
    "@huume someone used the slicer and got hurt",
    "@huume we needed more staff last night and someone got hurt",
    "@huume customer threw a chair",
    "@huume the walk-in ran all night",
    # F5 — bare "used" (no quantity-led object) must stay LOG.
    "@huume someone used the fryer without gloves on",
    # F7 — "returned" not led by a person-subject stays LOG (e.g. an
    # employee's own attendance, not a stock event).
    "@huume Dana returned from lunch late",
    "@huume she returned to work Monday",
    # code-review fix (2026-08-05): the "returned"-subject pattern's
    # subject list (patient/customer/client/guest/someone/they) DOES cover
    # "someone"/"they" — a bare returned\b used to match their own
    # movement, not a stock event. A negative lookahead after "returned"
    # now excludes to/from/back so these stay LOG.
    "@huume someone returned to the line drunk and shoved a coworker",
    "@huume they returned from break 40 minutes late",
    "@huume a customer returned back to the counter and yelled at staff",
    # code-review fix (2026-08-05): the ADD-to-stock and PUT-back-in-stock
    # patterns used to be unanchored (\b, matched anywhere via .search()),
    # so injury/conduct narration containing either phrase mid-sentence
    # misrouted to INVENTORY. Now message-initial only.
    "@huume Dana slipped carrying a case, I told her to put it back in stock and she's got a sprained wrist",
    "@huume the shelf collapsed while John tried to add boxes back to the inventory rack and it hit his foot",
]

ASK_NEGATIVES = [
    "@huume did we run out of cups?",
    "@huume how many cookies do we have?",
]

# Not a RECALL/interrogative match (no "?", no recall verb) — falls to LOG,
# same bias-to-LOG default as any other unmatched report-shaped message.
LOG_NEGATIVES.append("@huume what did we order last week")


@pytest.mark.parametrize("text", INVENTORY_POSITIVES)
def test_inventory_positive(text):
    assert classify_intent(text) == INVENTORY


@pytest.mark.parametrize("text", LOG_NEGATIVES)
def test_log_negative_bias_to_log(text):
    assert classify_intent(text) == LOG


@pytest.mark.parametrize("text", ASK_NEGATIVES)
def test_ask_negative(text):
    assert classify_intent(text) == ASK
