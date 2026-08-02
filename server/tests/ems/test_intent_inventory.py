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
]

LOG_NEGATIVES = [
    "@huume we gave John a written warning",
    "@huume someone used the slicer and got hurt",
    "@huume we needed more staff last night and someone got hurt",
    "@huume customer threw a chair",
    "@huume the walk-in ran all night",
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
