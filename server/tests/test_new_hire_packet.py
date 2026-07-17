"""Pure-logic tests for the new-hire jurisdiction packet.

The DB-backed build_packet / new_state_summary are exercised manually on dev DB
(see the plan); here we cover the pure level-bucketing helper and the notice
category set.
"""

from app.matcha.services import new_hire_packet as nhp


def test_bucket_for_level():
    assert nhp.bucket_for_level("federal") == "federal"
    assert nhp.bucket_for_level("state") == "state"
    assert nhp.bucket_for_level("county") == "local"
    assert nhp.bucket_for_level("city") == "local"
    assert nhp.bucket_for_level(None) == "state"        # unknown → state bucket, never dropped
    assert nhp.bucket_for_level("  City ") == "local"    # trim + case


def test_notice_categories_are_real_slugs():
    # Guard against slug drift (the ER slug-mismatch lesson): every notice
    # category must be a category the catalog actually emits. These 6 were
    # verified present in CATEGORY_KEYS at authoring.
    expected = {"i9_everify", "pay_frequency", "final_pay",
                "sick_leave", "background_checks", "workers_comp"}
    assert set(nhp.NOTICE_CATEGORIES) == expected
