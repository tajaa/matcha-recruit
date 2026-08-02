"""SCHEDULE intent classification — "@huume I need an opener and a closer
for our La Jolla store next week" and its cousins.

The asymmetry under test is the same one `test_ems_intent.py` pins for LOG:
an unmatched message defaults to LOG (a lost event is unrecoverable), so
every SCHEDULE pattern is deliberately narrow — start-anchored, requiring
BOTH a request verb and a shift-noun. The load-bearing cases below are the
counter-cases: phrasings that mention scheduling words but are reports, not
requests, and must still LOG.

    cd server && ./venv/bin/python -m pytest tests/ems/test_intent_schedule.py -q
"""

import pytest

from app.matcha.services.ems.intent import ASK, HELP, LOG, SCHEDULE, classify_intent


class TestScheduleRequests:
    def test_flagship_sentence_schedules(self):
        assert classify_intent(
            "@huume I need an opener and a closer for our La Jolla store next week"
        ) == SCHEDULE

    @pytest.mark.parametrize("message", [
        "@huume can you schedule two front desk people for Saturday",
        "@huume schedule an opener friday",
        "@huume add a closing shift on the 3rd",
        "@huume we'll need coverage next weekend",
        "@huume could you staff the closing shift tomorrow",
        "@huume book Maria for the opener monday",
        "@huume can you put someone on the schedule for Sunday",
        "@huume set up a closer for next tuesday",
    ])
    def test_staffing_requests_schedule(self, message):
        assert classify_intent(message) == SCHEDULE

    @pytest.mark.parametrize("message", [
        # verbatim prod misroutes, 2026-08-02 — preamble sentence + push/assign verbs
        "@huume okay lets try this day by day then. We need to create a schedule "
        "for tomorrow. I need two openers starting at 8am. Closers leave at 6pm.",
        "@huume can you push to the schedule though? Lets add two openers to start",
        "@huume can you assing employees to the open shifts for 8/3?",
        "@huume how about now, can you assing employees to the 8/3 shifts?",
    ])
    def test_prod_misroutes_now_schedule(self, message):
        assert classify_intent(message) == SCHEDULE


class TestReportsStillLog:
    """Reports that mention schedule-adjacent words but are documentation,
    not a staffing request — the load-bearing counter-cases."""

    @pytest.mark.parametrize("message", [
        "@huume the opener called out sick",
        "@huume we needed more staff last night and someone got hurt",
        "@huume I need to report an incident",
        "@huume we need to talk about what happened at closing",
        "@huume the schedule printout by the fridge got soaked",
        "@huume closing went long because the register crashed",
        "@huume I need the manager to know the freezer died",
        "@huume staff meeting got heated today",
        "@huume can you push the meeting notes to the team",
        "@huume we used the slicer and someone got hurt",
    ])
    def test_reports_log(self, message):
        assert classify_intent(message) == LOG

    def test_past_tense_need_does_not_trigger_schedule(self):
        # \bneed\b must not match inside "needed" — the word-boundary +
        # exact-tense requirement is what keeps this LOG.
        assert classify_intent("@huume we needed an opener today and nobody showed") == LOG


class TestRecallAndHelpUnaffected:
    def test_recall_question_still_asks(self):
        assert classify_intent("@huume what happened last week?") == ASK

    def test_schedule_word_in_recall_still_asks(self):
        # SCHEDULE is checked before RECALL, but "can you show" isn't in the
        # SCHEDULE verb set (schedule/staff/book/add/set up/put), so this
        # still falls through to the recall pattern.
        assert classify_intent("@huume can you show me the schedule complaints") == ASK

    def test_help_still_wins(self):
        assert classify_intent("@huume what can you do") == HELP
