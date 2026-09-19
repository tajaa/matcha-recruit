"""Signup answers a duplicate address exactly like a fresh one.

Login goes to real trouble not to leak account existence — an unknown email is
run against a precomputed dummy bcrypt hash so it costs the same time — and
resend always 202s. Signup handed the same fact back in one request by
answering 409 "an account with this email already exists" (audit B7/M7).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_auth_signup_oracle.py -q
"""
import inspect
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.routes import auth as mod  # noqa: E402
from app.cappe.services import email as email_mod  # noqa: E402


def test_duplicate_signup_does_not_answer_409():
    src = inspect.getsource(mod.signup)
    collision = src.split("UniqueViolationError", 1)[1]
    # The whole point: the duplicate branch returns the ordinary
    # "check your email" response rather than a conflict.
    assert "409" not in collision
    assert "HTTP_409_CONFLICT" not in collision
    assert "already exists" not in collision


def test_duplicate_signup_returns_the_same_shape_as_a_fresh_one():
    src = inspect.getsource(mod.signup)
    collision = src.split("UniqueViolationError", 1)[1]
    assert "verification_required=True" in collision


def test_the_real_owner_is_told_out_of_band():
    """Suppressing the 409 only works if the person who actually owns the
    address finds out someone tried to sign up with it."""
    src = inspect.getsource(mod.signup)
    assert "send_cappe_account_exists_email" in src
    assert hasattr(email_mod, "send_cappe_account_exists_email")


def test_collision_creates_nothing():
    src = inspect.getsource(mod.signup)
    collision = src.split("UniqueViolationError", 1)[1].split("account = CappeAccount", 1)[0]
    for write in ("INSERT", "UPDATE", "DELETE"):
        assert write not in collision.upper()


def test_login_still_uses_a_constant_time_dummy_hash():
    """The other half of the same property — regressing this would restore the
    timing oracle signup just stopped being a direct one."""
    src = inspect.getsource(mod)
    assert "_DUMMY_PASSWORD_HASH" in src
