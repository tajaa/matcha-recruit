"""Pure-function tests for the public-review hold + brand slug helpers (no DB).

`effective_review_state` derives 'published' at read time rather than storing
it (see tellus_app_05's docstring) — these tests pin that derivation so a
future refactor can't silently reintroduce a stored 'published' state.
"""
from datetime import datetime, timedelta, timezone

from app.tellus.routes._shared import effective_review_state, slugify


def _row(**overrides):
    base = {"review_state": None, "publish_at": None}
    base.update(overrides)
    return base


class TestEffectiveReviewState:
    def test_private_feedback_is_none(self):
        assert effective_review_state(_row()) is None

    def test_held_with_future_publish_at_stays_held(self):
        future = datetime.now(timezone.utc) + timedelta(hours=10)
        row = _row(review_state="held", publish_at=future)
        assert effective_review_state(row) == "held"

    def test_held_with_past_publish_at_is_published(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        row = _row(review_state="held", publish_at=past)
        assert effective_review_state(row) == "published"

    def test_withdrawn_stays_withdrawn_regardless_of_publish_at(self):
        past = datetime.now(timezone.utc) - timedelta(hours=100)
        row = _row(review_state="withdrawn", publish_at=past)
        assert effective_review_state(row) == "withdrawn"

    def test_missing_column_is_none(self):
        # A pre-tellus_app_05 row shape (no review_state key at all).
        assert effective_review_state({}) is None


class TestSlugify:
    def test_lowercases_and_dashes_specials(self):
        assert slugify("Joe's Café #2") == "joe-s-caf-2"

    def test_strips_leading_trailing_dashes(self):
        assert slugify("--Acme--") == "acme"

    def test_empty_or_all_special_falls_back(self):
        assert slugify("") == "brand"
        assert slugify("###") == "brand"

    def test_collapses_runs_of_specials(self):
        assert slugify("Acme   &   Sons!!") == "acme-sons"

    def test_truncates_long_names_to_60_chars(self):
        long_name = "A" * 100
        result = slugify(long_name)
        assert len(result) == 60
        assert result == "a" * 60

    def test_truncation_does_not_leave_trailing_dash(self):
        # 59 letters + a dash lands exactly on the 60-char cut — must trim
        # the dangling dash rather than emit "...letters-".
        name = ("b" * 59) + "-" + ("c" * 10)
        result = slugify(name)
        assert not result.endswith("-")
        assert len(result) <= 60
