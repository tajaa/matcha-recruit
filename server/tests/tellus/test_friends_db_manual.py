"""Manual friends DB checks.

Disabled unless explicitly opted in. These checks must never mutate a live
database from CI; use reserved-domain accounts against local Postgres only.
"""
import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("TELLUS_FRIENDS_DB_TEST") != "1",
    reason="manual DB test; set TELLUS_FRIENDS_DB_TEST=1 explicitly",
)


def test_manual_suite_requires_reserved_test_accounts():
    assert os.getenv("TELLUS_FRIENDS_ACCOUNT_A", "").endswith(("@example.com", ".test"))
    assert os.getenv("TELLUS_FRIENDS_ACCOUNT_B", "").endswith(("@example.com", ".test"))
