"""No-DB guard against reintroducing the 2026-08-15 access-link 500.

`$n + ($m * INTERVAL '1 second')` lets Postgres infer $n as interval, which
cannot assign to a timestamptz column (DatatypeMismatchError on every call).
"""
import inspect
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import booking_suggestion_access  # noqa: E402


def test_expiry_params_are_not_interval_arithmetic():
    src = inspect.getsource(booking_suggestion_access)
    assert "INTERVAL '1 second'" not in src
