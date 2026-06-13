"""Cappe newsletter-send pure helpers — recipient filtering + unsubscribe.
No DB, no SMTP.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_campaigns.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.campaigns import deliverable_recipients, personalize_unsubscribe  # noqa: E402


def _sub(email, name=None, token="tok"):
    return {"email": email, "name": name, "unsubscribe_token": token}


def test_deliverable_filters_reserved_and_dedupes():
    rows = [
        _sub("real@gmail.com", "Real"),
        _sub("nope@example.com"),        # reserved → dropped
        _sub("test@foo.test"),           # reserved → dropped
        _sub("bad@thing.invalid"),       # reserved → dropped
        _sub("REAL@gmail.com", "Dup"),   # case-dupe of #1 → dropped
        _sub(""),                        # empty → dropped
    ]
    out = deliverable_recipients(rows)
    assert [r["email"] for r in out] == ["real@gmail.com"]
    assert out[0]["name"] == "Real" and out[0]["unsubscribe_token"] == "tok"


def test_deliverable_handles_missing_optional_keys():
    out = deliverable_recipients([{"email": "x@y.com"}])
    assert out == [{"email": "x@y.com", "name": None, "unsubscribe_token": None}]


def test_personalize_unsubscribe_appends_escaped_link():
    html = personalize_unsubscribe("<p>Hello</p>", 'https://h/api/cappe/public/sites/s/unsubscribe/t"x')
    assert "<p>Hello</p>" in html
    assert "Unsubscribe" in html
    # The double-quote in the url is escaped so the href can't break out.
    assert '"x"' not in html
    assert "&quot;x" in html
