"""DB-free checks for the isolated App Review seed generator."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import bcrypt

PACK = (
    Path(__file__).resolve().parents[3] / "scripts/seed/matcha_schedule_app_review.py"
)


def render(
    *args: str, password: str | None = "review-test-password"
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("MATCHA_APP_REVIEW_PASSWORD", None)
    if password is not None:
        env["MATCHA_APP_REVIEW_PASSWORD"] = password
    return subprocess.run(
        [sys.executable, str(PACK), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_requires_password_for_seed_but_not_undo():
    missing = render(password=None)
    assert missing.returncode == 2
    assert "MATCHA_APP_REVIEW_PASSWORD must be set" in missing.stderr
    assert not missing.stdout
    assert render("--undo", password=None).returncode == 0


def test_rejects_password_over_bcrypt_byte_limit():
    result = render(password="é" * 37)
    assert result.returncode == 2
    assert "72 UTF-8 bytes" in result.stderr
    assert not result.stdout


def test_seed_is_scoped_and_has_working_credentials_and_future_shifts():
    result = render()
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "review-test-password" not in sql
    password_hash = re.search(r"'(\$2[aby]\$10\$[^']+)'", sql)
    assert password_hash
    assert bcrypt.checkpw(b"review-test-password", password_hash.group(1).encode())
    assert sql.count("INSERT INTO companies") == 1
    assert sql.count("INSERT INTO users") == 2
    assert sql.count("INSERT INTO employees") == 2
    assert sql.count("INSERT INTO schedule_shifts") == 63
    assert sql.count("INSERT INTO schedule_shift_assignments") == 48
    assert sql.count("ON CONFLICT") == 117
    assert "'published'" in sql
    assert "'America/Los_Angeles'" in sql
    assert '"employee_schedule":true' in sql
    assert '"time_off":true' in sql
    emails = re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", sql)
    assert emails and all(email.endswith("@example.com") for email in emails)
    assert not re.search(
        r"\b(CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\b", sql, re.IGNORECASE
    )


def test_undo_is_limited_to_fixed_demo_ids_and_email_addresses():
    sql = render("--undo", password=None).stdout
    assert sql.count("DELETE FROM") == 7
    assert "a7700000-0000-4000-8000-000000000001" in sql
    assert "DEMO-MATCHA-SCHEDULE Review Cafe" in sql
    assert "is_test = TRUE" in sql
    assert "demo-matcha-schedule@example.com" in sql
    assert "coworker-matcha-schedule@example.com" in sql
    assert "DELETE FROM inbox_messages" in sql
    # Undo never removes a conversation that includes a non-demo participant.
    assert "DELETE FROM inbox_conversations WHERE created_by IN" in sql
    assert "p.user_id NOT IN" in sql
    assert sql.index("DELETE FROM companies") < sql.index("DELETE FROM users")
