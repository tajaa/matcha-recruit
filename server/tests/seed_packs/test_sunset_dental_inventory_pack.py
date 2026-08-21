"""DB-free lint for the Sunset Smile Dental Wilshire inventory seed pack.

The pack is intended for guarded execution through scripts/seed-prod.sh, so
these checks catch unsafe SQL and broken pinned-ID relationships before a
database is involved.
"""
from __future__ import annotations

import re
from pathlib import Path


PACK_DIR = Path(__file__).resolve().parents[3] / "scripts" / "seed"
PACK = PACK_DIR / "sunset_dental_inventory.sql"
UNDO = PACK_DIR / "sunset_dental_inventory.undo.sql"
OWNED_TABLES = {"inventory_items", "inventory_movements", "inventory_orders"}
WILSHIRE_LOCATION_ID = "59bf0bdc-558f-4530-8917-a792eb7f5d98"
UUID_RE = re.compile(r"'(?P<id>5eedaaaa-[0-9a-f-]+)'")


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _statements(sql: str) -> list[str]:
    return [stmt.strip() for stmt in _strip_comments(sql).split(";") if stmt.strip()]


def _insert_block(sql: str, table: str) -> str:
    blocks = _insert_blocks(sql, table)
    assert blocks, f"no INSERT INTO {table} block found"
    return blocks[0]


def _insert_blocks(sql: str, table: str) -> list[str]:
    stripped = _strip_comments(sql)
    return re.findall(
        rf"INSERT INTO {re.escape(table)}\b.*?ON CONFLICT.*?;",
        stripped,
        re.IGNORECASE | re.DOTALL,
    )


def _pack_text() -> str:
    return PACK.read_text()


def _undo_text() -> str:
    return UNDO.read_text()


def test_pack_has_no_transaction_control_or_ddl():
    stripped = _strip_comments(_pack_text())
    assert not re.search(
        r"(^|;)[ \t]*(begin|commit|rollback|savepoint|release|start\s+transaction)\b",
        stripped,
        re.IGNORECASE | re.MULTILINE,
    )
    assert not re.search(r"\b(create|drop|alter|truncate|grant|revoke)\b", stripped, re.IGNORECASE)


def test_every_insert_is_idempotent_and_targets_owned_tables():
    stripped = _strip_comments(_pack_text())
    targets = set(re.findall(r"INSERT INTO (\w+)", stripped, re.IGNORECASE))
    assert targets == OWNED_TABLES
    insert_statements = re.findall(r"\bINSERT INTO\b.*?(?=;)", stripped, re.IGNORECASE | re.DOTALL)
    assert len(insert_statements) == len(targets) + 2
    for statement in insert_statements:
        assert "on conflict" in statement.lower(), statement[:100]


def test_pack_has_expected_catalog_size_and_keeps_missing_item_demo():
    item_block = "\n".join(_insert_blocks(_pack_text(), "inventory_items"))
    item_ids = set(UUID_RE.findall(item_block))
    assert len(item_ids) == 22
    assert item_block.count(f"'{WILSHIRE_LOCATION_ID}'") == 22
    assert "Suction Tips" not in item_block


def test_all_referenced_item_and_receipt_ids_are_pinned_rows():
    text = _pack_text()
    item_block = "\n".join(_insert_blocks(text, "inventory_items"))
    item_ids = set(UUID_RE.findall(item_block))
    movement_block = "\n".join(_insert_blocks(text, "inventory_movements"))
    order_block = _insert_block(text, "inventory_orders")

    movement_item_ids = set(re.findall(r"'(5eedaaaa-0001-[^']+)'", movement_block))
    assert movement_item_ids
    assert movement_item_ids <= item_ids

    order_item_ids = set(re.findall(r"'(5eedaaaa-0001-[^']+)'", order_block))
    assert order_item_ids
    assert order_item_ids <= item_ids
    assert "5eedaaaa-0002-4001-8001-000000000046" in movement_block
    assert "5eedaaaa-0002-4001-8001-000000000046" in order_block


def test_undo_deletes_orders_before_movements_before_items():
    order = re.findall(r"DELETE FROM (\w+)", _undo_text())
    assert order == ["inventory_orders", "inventory_movements", "inventory_items"]
    assert "5eedaaaa-0003-%" in _undo_text()
    assert "5eedaaaa-0002-%" in _undo_text()
    assert "5eedaaaa-0001-%" in _undo_text()
