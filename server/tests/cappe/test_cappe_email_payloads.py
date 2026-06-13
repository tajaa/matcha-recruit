"""Cappe transactional-email pure helpers — money/items/when formatting and the
HTML shell escaping. No DB, no SMTP (builders that actually send are not called).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_email_payloads.py -q
"""
import os
from datetime import datetime, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.email import (  # noqa: E402
    _email_shell,
    build_order_items_summary,
    fmt_money,
    format_when,
)


def test_fmt_money_usd_and_zero():
    assert fmt_money(4000) == "$40.00"
    assert fmt_money(0) == "$0.00"
    assert fmt_money(None) == "$0.00"
    assert fmt_money(123456) == "$1,234.56"


def test_fmt_money_symbols_and_unknown_currency():
    assert fmt_money(500, "EUR") == "€5.00"
    assert fmt_money(500, "gbp") == "£5.00"
    # Unknown currency → ISO code suffix, no symbol.
    assert fmt_money(123400, "JPY") == "1,234.00 JPY"


def test_build_order_items_summary():
    out = build_order_items_summary([
        {"title": "Print", "quantity": 2},
        {"title": "Session", "quantity": 1},
    ])
    assert out == "2× Print, 1× Session"


def test_build_order_items_summary_defaults_and_skips_junk():
    out = build_order_items_summary([{"title": "Thing"}, "not-a-dict", {"quantity": 3}])
    # default qty 1 when missing; default title "Item"; non-dict skipped.
    assert out == "1× Thing, 3× Item"
    assert build_order_items_summary(None) == ""


def test_format_when_uses_site_timezone():
    dt = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)  # 20:00 UTC
    s = format_when(dt, "America/New_York")                 # → 16:00 EDT
    assert "Jun 15" in s and "4:00 PM" in s


def test_format_when_bad_timezone_falls_back():
    dt = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)
    s = format_when(dt, "Not/AZone")  # bad tz → leave in UTC (8:00 PM)
    assert "8:00 PM" in s


def test_email_shell_escapes_cta_url():
    html = _email_shell("Heading", "<p>ok</p>", cta_label="Go", cta_url='https://e.test/a"onmouseover=1')
    # The double-quote in the url must be entity-escaped so it can't break the href.
    assert '"onmouseover=1"' not in html
    assert "&quot;onmouseover=1" in html
    assert "Heading" in html and "<p>ok</p>" in html


def test_email_shell_no_cta_when_url_missing():
    html = _email_shell("H", "<p>b</p>", cta_label="Go")  # no url → no button
    assert "<a href" not in html
