"""Pure-logic tests for the Book of Business renewal-date resolver.

No DB — only app.matcha.routes.broker.brokers._shared._resolve_renewal.
"""

from datetime import date

from app.matcha.routes.broker.brokers._shared import _resolve_renewal


def test_both_none():
    assert _resolve_renewal(None, None) == (None, None)


def test_explicit_only():
    assert _resolve_renewal(date(2027, 3, 1), None) == ("2027-03-01", "broker")


def test_derived_only():
    assert _resolve_renewal(None, date(2027, 5, 15)) == ("2027-05-15", "coverage")


def test_both_set_broker_wins():
    assert _resolve_renewal(date(2027, 3, 1), date(2027, 6, 1)) == ("2027-03-01", "broker")


def test_explicit_wins_even_when_derived_is_earlier():
    # A broker's own answer must not be silently overridden by an earlier
    # coverage-line expiry — the broker is the authority once they've set one.
    assert _resolve_renewal(date(2027, 6, 1), date(2027, 3, 1)) == ("2027-06-01", "broker")
