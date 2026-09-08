"""The guard for tests that need a real matcha database.

Five modules used to gate themselves on `os.environ.get("DATABASE_URL", "")`
being non-empty. That reads as "only run when a database is configured", but it
is not what it does: ~40 test modules call

    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

at import time so `app.config`'s settings can load. Whichever of those imports
first fabricates the variable for the whole process, so by the time a
`*_realdb.py` module is imported the guard sees a URL, declines to skip, and
its fixture dials a database that does not exist.

Alone the file skipped; in a full-suite run it errored. That stayed invisible
while CI only collected the suite, and surfaced the moment it started executing
it — as 29 errors, and in CI as `FATAL: password authentication failed for user
"test"`, because there a Postgres really is listening on 5432 and the
placebo credentials reach it.

So the guard is an explicit opt-in, not an inference. This matches the
`RUN_DB_GAP_TESTS` / `RUN_DB_WRITE_TESTS` pattern already in the suite, and the
principle the 2026-09-08 review stated when it moved the google-workspace test
behind one: *a `DATABASE_URL` present in `server/.env` is not a guard.*

    RUN_DB_TESTS=1 ./venv/bin/python -m pytest tests/matcha_work/test_progress_note_realdb.py -q

`tests/_helpers/test_db_guard.py` asserts no module goes back to reading
DATABASE_URL directly.
"""

from __future__ import annotations

import os

import pytest

#: Set to "1" to run the tests that open a real connection.
OPT_IN_ENV = "RUN_DB_TESTS"

#: What the ~40 `setdefault` call sites fabricate. Never a real database; kept
#: here so a guard can recognise it if one ever does read the URL.
PLACEHOLDER_URL = "postgresql://test:test@localhost/test"

SKIP_REASON = (
    f"needs a real matcha database — set {OPT_IN_ENV}=1 to run "
    "(DATABASE_URL alone is not a guard: other test modules fabricate it)"
)


def db_tests_enabled() -> bool:
    return os.getenv(OPT_IN_ENV) == "1"


def requires_real_db() -> pytest.MarkDecorator:
    """`pytestmark = [requires_real_db(), ...]` for a module that connects."""
    return pytest.mark.skipif(not db_tests_enabled(), reason=SKIP_REASON)


def real_database_url() -> str:
    """The configured DATABASE_URL, or "" when it is the shared placeholder.

    For a module that has opted in and now needs somewhere to connect.
    """
    url = os.environ.get("DATABASE_URL", "")
    return "" if url == PLACEHOLDER_URL else url
