"""Source guards for existing activity hooks into brand loyalty."""
import inspect

from app.tellus.routes import places
from app.tellus.services import board_service, feedback_service


def test_review_hook_is_public_and_identified_only():
    source = inspect.getsource(feedback_service.create_report)
    assert "if identified and public_review" in source
    assert "event_key=\"review\"" in source
    assert "tellus_brands.reward_mode" not in source


def test_board_approval_has_brand_scoped_reference():
    source = inspect.getsource(board_service.approve_reply_and_award)
    assert "brand_id" in source
    assert "event_key=\"board_reply\"" in source
    assert "board_reply:{reply_id}" in source


def test_follow_awards_only_after_insert_returning():
    source = inspect.getsource(places.follow_place)
    assert "RETURNING brand_id" in source
    assert "if inserted is not None" in source
    assert "event_key=\"follow\"" in source


def test_unfollow_does_not_reference_loyalty_award():
    source = inspect.getsource(places.unfollow_place)
    assert "award_event" not in source
