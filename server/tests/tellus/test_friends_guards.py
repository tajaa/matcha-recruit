"""Source guards for friends' privacy, moderation, and transaction invariants."""
import inspect


def _code_only(obj) -> str:
    source = inspect.getsource(obj)
    doc = inspect.getdoc(obj)
    if doc:
        source = source.replace(doc, "")
    return "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))


def test_feed_copies_public_review_predicate():
    from app.tellus.routes import friends

    source = _code_only(friends.friend_activity_feed)
    assert "review_state = 'held'" in source
    assert "publish_at <= NOW()" in source
    assert "moderation_status = 'visible'" in source


def test_friends_routes_never_select_email():
    from app.tellus.routes import friends

    assert "email" not in _code_only(friends)


def test_feed_uses_keyset_cursor_and_bounded_branch_limits():
    from app.tellus.routes import friends

    source = _code_only(friends.friend_activity_feed)
    assert "decode_cursor" in source
    assert "ORDER BY r.publish_at DESC, r.id DESC LIMIT $4" in source
    assert "ORDER BY bf.created_at DESC, bf.brand_id DESC LIMIT $4" in source
