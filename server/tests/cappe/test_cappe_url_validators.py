"""Every user-supplied URL that reaches an href/url() sink must be https.

Until the 2026-09 audit `CreatorSocialUpsert.url` was the only model that
checked a scheme. A creator's portfolio link, avatar/cover image, collab
deliverable submission and proof, and an order's deliverable URL were all bare
strings rendered straight into `<a href>` or `background-image: url(...)` in the
counterparty's dashboard — a stored `javascript:` vector (audit F3).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_url_validators.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models._validators import assert_json_size, https_url  # noqa: E402

HOSTILE = [
    "javascript:alert(document.cookie)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)  ",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
    "http://insecure.example.com/x",   # scheme downgrade
    "//evil.test/x",                   # protocol-relative
    "/relative/path",
    "ftp://files.example.com/x",
]


# ── https_url (pure) ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", HOSTILE)
def test_non_https_url_is_rejected(value):
    with pytest.raises(ValueError):
        https_url(value)


def test_https_url_is_kept_and_trimmed():
    assert https_url("  https://example.com/a  ") == "https://example.com/a"


def test_none_and_empty_pass_through():
    """An optional field is cleared by sending None or ""; the field's own
    length constraint is what rejects an empty value where one is required."""
    assert https_url(None) is None
    assert https_url("") == ""
    assert https_url("   ") == ""


# ── the models that carry it ─────────────────────────────────────────────────

def _each_hostile(build):
    for value in HOSTILE:
        with pytest.raises(ValidationError):
            build(value)


def test_creator_profile_avatar_and_cover_reject_javascript():
    from app.cappe.models.creators import CreatorProfileUpdate

    _each_hostile(lambda v: CreatorProfileUpdate(avatar_url=v))
    _each_hostile(lambda v: CreatorProfileUpdate(cover_url=v))
    ok = CreatorProfileUpdate(avatar_url="https://cdn.example.com/a.png")
    assert ok.avatar_url == "https://cdn.example.com/a.png"


def test_creator_portfolio_media_and_external_links_reject_javascript():
    from app.cappe.models.creators import CreatorPortfolioItem, CreatorPortfolioUpsert

    _each_hostile(lambda v: CreatorPortfolioUpsert(title="Reel", external_url=v))
    _each_hostile(lambda v: CreatorPortfolioUpsert(title="Reel", media_url=v))

    # The READ model deliberately keeps the rule off: rows written before the
    # validator existed must still render rather than 500 the whole profile.
    legacy = CreatorPortfolioItem(
        id="11111111-1111-4111-8111-111111111111",
        created_at="2026-01-01T00:00:00Z",
        title="Reel",
        external_url="http://legacy.example.com",
    )
    assert legacy.external_url == "http://legacy.example.com"


def test_collab_deliverable_submission_and_proof_reject_javascript():
    from app.cappe.models.collab import DeliverableSubmit

    _each_hostile(lambda v: DeliverableSubmit(submission_url=v))
    _each_hostile(
        lambda v: DeliverableSubmit(submission_url="https://example.com/post", proof_media_url=v)
    )
    ok = DeliverableSubmit(submission_url="https://example.com/post")
    assert ok.submission_url == "https://example.com/post"


def test_order_item_deliverable_url_rejects_javascript():
    from app.cappe.models.shop import CappeDeliverableUpdate

    _each_hostile(lambda v: CappeDeliverableUpdate(deliverable_url=v))
    ok = CappeDeliverableUpdate(deliverable_url="https://cdn.example.com/final.zip")
    assert ok.deliverable_url == "https://cdn.example.com/final.zip"


# ── assert_json_size ─────────────────────────────────────────────────────────

def test_json_size_allows_a_normal_page():
    assert_json_size("content", {"blocks": [{"type": "hero", "heading": "Hi"}]}) is None


def test_json_size_allows_none():
    assert_json_size("content", None) is None


def test_oversized_json_is_rejected():
    with pytest.raises(ValueError, match="too large"):
        assert_json_size("content", {"blocks": ["x" * 400_000]})


def test_unserializable_json_is_rejected():
    with pytest.raises(ValueError):
        assert_json_size("content", {"k": {1, 2, 3}}, limit=10)


def test_page_update_model_rejects_an_oversized_blob():
    from app.cappe.models.sites import CappePageUpdate

    with pytest.raises(ValidationError):
        CappePageUpdate(content={"blocks": ["x" * 400_000]})
