import re
from pathlib import Path

from app.matcha.services.inventory.waste.reasons import (
    WASTE_REASONS,
    coerce_chat_reason,
    is_unexplained,
)

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "invwaste01_inventory_waste.py"
)


def _db_check_reasons() -> tuple[str, ...]:
    """Parse the waste_reason IN (...) list straight out of the migration
    source so this test fails the moment Python and SQL drift apart."""
    text = _MIGRATION.read_text()
    match = re.search(r"waste_reason IN \(([^)]+)\)", text, re.DOTALL)
    assert match, "could not find the waste_reason CHECK in the migration"
    return tuple(re.findall(r"'([a-z_]+)'", match.group(1)))


def test_reasons_match_db_check():
    assert WASTE_REASONS == _db_check_reasons()


def test_chat_reason_coerces_theft():
    assert coerce_chat_reason("theft") == "unknown"


def test_chat_reason_coerces_unknown_garbage():
    assert coerce_chat_reason("shrinkage!!") == "unknown"


def test_chat_reason_coerces_none():
    assert coerce_chat_reason(None) == "unknown"


def test_chat_reason_passthrough():
    assert coerce_chat_reason("spoilage") == "spoilage"
    assert coerce_chat_reason("expired") == "expired"


def test_is_unexplained():
    assert is_unexplained("theft") is True
    assert is_unexplained("unknown") is True
    assert is_unexplained("spoilage") is False
    assert is_unexplained(None) is False
