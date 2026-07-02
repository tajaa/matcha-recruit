"""Pure-function tests for the Tell-Us rewards engine (no DB).

Covers the level curve, level progress derivation, usefulness scoring, and
code generation. The DB-touching paths (award/redeem atomicity, ledger
idempotency) are integration-level — run manually against dev per the repo's
DB-test policy.
"""
from app.tellus.services.points_service import (
    _gen_code,
    level_for_points,
    level_progress,
    level_threshold,
)
from app.tellus.services.feedback_service import USEFULNESS_THRESHOLD, score_usefulness


class TestLevelCurve:
    def test_thresholds(self):
        # threshold(L) = 50·L·(L-1)
        assert level_threshold(1) == 0
        assert level_threshold(2) == 100
        assert level_threshold(3) == 300
        assert level_threshold(4) == 600
        assert level_threshold(5) == 1000

    def test_level_for_points_boundaries(self):
        assert level_for_points(0) == 1
        assert level_for_points(99) == 1
        assert level_for_points(100) == 2   # exactly at threshold → new level
        assert level_for_points(299) == 2
        assert level_for_points(300) == 3
        assert level_for_points(1000) == 5

    def test_negative_and_zero_safe(self):
        assert level_for_points(-50) == 1

    def test_curve_consistency(self):
        # For every level 1..30, threshold(L) maps back to exactly L.
        for lvl in range(1, 31):
            t = level_threshold(lvl)
            assert level_for_points(t) == lvl
            if t > 0:
                assert level_for_points(t - 1) == lvl - 1

    def test_level_progress_shape(self):
        p = level_progress(150)
        assert p["level"] == 2
        assert p["level_floor"] == 100
        assert p["level_ceiling"] == 300
        assert p["points_to_next_level"] == 150


class TestUsefulness:
    def test_empty_is_below_threshold(self):
        score = score_usefulness("", False, False, False, False)
        assert score < USEFULNESS_THRESHOLD

    def test_detail_and_media_raise_score(self):
        bare = score_usefulness("short", False, False, False, False)
        rich = score_usefulness("x" * 600, True, True, True, True)
        assert rich > bare
        assert rich <= 100

    def test_identified_beats_anonymous(self):
        anon = score_usefulness("decent length description here", False, False, False, False)
        known = score_usefulness("decent length description here", False, False, False, True)
        assert known == anon + 15

    def test_clamped_to_100(self):
        assert score_usefulness("x" * 100000, True, True, True, True) <= 100


class TestRedemptionCode:
    def test_shape_and_uniqueness(self):
        codes = {_gen_code() for _ in range(200)}
        assert len(codes) == 200
        for c in codes:
            assert c.startswith("TU-")
            assert len(c) == 11  # 'TU-' + 8 hex chars
