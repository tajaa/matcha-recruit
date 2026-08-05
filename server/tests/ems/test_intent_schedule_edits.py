"""SCHEDULE intent for EDITS to an existing shift — swap / reassign /
retime / cancel.

Added 2026-08-04 after a live-prod report: "@huume can you swap those two?
give Cara's shift Casey and Caseys to Cara's" classified LOG and minted a
phantom `ems_events` row. Two independent causes, both pinned below —
no SCHEDULE pattern carried a swap verb at all, and the ASK
weak-interrogative fallback only fires when the message *ends* with "?"
(this one ends with a name), so there was nothing left to catch it.

The edit patterns lean wider than the create patterns on purpose: a
SCHEDULE match is a routing decision, not a commitment.
`_bg_schedule_request` falls back to `_bg_ems_intake` whenever the parse
comes back non-actionable, so a false positive costs one flash-lite call
and is still documented — while a false NEGATIVE writes a permanent event
row for what was actually a work request. The bias-to-LOG counter-cases in
TestStillLogs are what keep that widening honest.

    cd server && ./venv/bin/python -m pytest tests/ems/test_intent_schedule_edits.py -q
"""

import pytest

from app.matcha.services.ems.intent import INVENTORY, LOG, SCHEDULE, classify_intent


class TestTheReportedBug:
    def test_prod_message_verbatim_reaches_schedule(self):
        # The exact string from the prod screenshot. Note it does NOT end
        # with "?" — that is why the ASK fallback never caught it.
        assert classify_intent(
            "@huume can you swap those two? give Cara's shift Casey and Caseys to Cara's"
        ) == SCHEDULE

    def test_trimmed_question_form_is_ask_not_log(self):
        # Ends with "?" so the weak-interrogative fallback catches it and it
        # reaches the ASK tool loop. Either route is fine — LOG is not.
        assert classify_intent("@huume can you swap those two?") != LOG


class TestEditPhrasings:
    @pytest.mark.parametrize("message", [
        # A — bot-directed, unambiguous verb, no shift noun needed
        "@huume can you swap Carmen and Casey's shifts on Wednesday",
        "@huume could you switch those",
        "@huume can you reassign Carmen's Wednesday shift to Casey",
        # B — bot-directed, ambiguous verb, must reach a shift noun
        "@huume can you make Wednesday's opener 7am to 3pm instead",
        "@huume can you move the closer to 1pm",
        "@huume can you cancel Saturday's opening shift",
        # C — bare imperative
        "@huume give Cara's shift to Casey",
        "@huume push the Wednesday opener back an hour",
        "@huume take Dana off the schedule",
        "@huume put Casey on the Wednesday closer instead of Dana",
        # D — cancel family
        "@huume cancel Wednesday's opener",
        "@huume scrap the closer on Wednesday, we're closing early",
        # E — third-person report of a wanted change
        "@huume Carmen and Casey want to trade shifts next week",
        "@huume Dana wants to swap her Friday shift",
    ])
    def test_edit_phrasing_reaches_schedule(self, message):
        assert classify_intent(message) == SCHEDULE


class TestStillLogs:
    """The widening must not eat incident reports. Every case here mentions
    an edit verb or a shift noun and is still a REPORT, not a request."""

    @pytest.mark.parametrize("message", [
        # Tense-exactness: \bmove\b never matches "moved".
        "@huume we moved the freezer and someone got hurt",
        "@huume we needed more staff last night and someone got hurt",
        # 'cancel' with no shift noun within the token budget.
        "@huume we had to cancel a patient's appointment because the drill broke",
        # Bare 'gave' stays out of the edit verb list.
        "@huume Dana gave a patient the wrong form",
        # 'took' is past tense; 'switch' here is a noun-ish object, no shift noun.
        "@huume someone took the wrong instrument tray",
        # An explicit report request always wins over an edit verb.
        "@huume I need to report an incident",
    ])
    def test_report_still_logs(self, message):
        assert classify_intent(message) == LOG


class TestInventoryCountRemaining:
    """'down to N' reads as a stock level, not an incident — it used to LOG."""

    @pytest.mark.parametrize("message", [
        "@huume we're down to 3 boxes of gloves",
        "@huume we are down to our last case of suction tips",
    ])
    def test_down_to_is_inventory(self, message):
        assert classify_intent(message) == INVENTORY

    def test_ran_out_still_inventory(self):
        assert classify_intent("@huume we ran out of nitrile gloves") == INVENTORY
