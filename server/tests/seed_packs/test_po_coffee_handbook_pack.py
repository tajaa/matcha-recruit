"""DB-free lint for the Po Coffee Co handbook seed pack.

The HR cases triage grounds on ACTIVE/DRAFT handbook sections of the handbook's
active version (`handbook_pilot.grounding`); with none on file the check reports
clean and no incident opens a case. These checks keep the pack shaped for that
query and keep its undo exact.
"""
from __future__ import annotations

import re
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[3] / "scripts" / "seed"
PACK = PACK_DIR / "po_coffee_handbook.sql"
UNDO = PACK_DIR / "po_coffee_handbook.undo.sql"
COMPANY_ID = "c4c256c3-60ef-4cf5-8d4c-55e963c58416"
PREFIX = "c0ffeeee-0b00-"


def _sql() -> str:
    return PACK.read_text()


def test_pack_is_data_only_and_never_touches_company_config():
    sql = re.sub(r"--[^\n]*", "", _sql()).lower()
    assert not re.search(r"\b(create|alter|drop|truncate)\s+(table|index|role)", sql)
    assert "update " not in sql and "delete from" not in sql
    assert "enabled_features" not in sql


def test_handbook_is_active_for_po_coffee_with_a_published_matching_version():
    sql = _sql()
    assert COMPANY_ID in sql
    # grounding only reads sections where hv.version_number = h.active_version
    assert "'active', 'single_state', 'template', 1," in sql
    assert re.search(r"\b1, 'Initial version', TRUE\b", sql)


def test_every_pinned_id_is_under_the_undo_prefix_and_ids_are_unique():
    ids = re.findall(r"'(c0ffeeee-[0-9a-f-]+)'", _sql())
    row_ids = [i for i in ids if i != COMPANY_ID]
    assert row_ids and all(i.startswith(PREFIX) for i in row_ids)
    # handbook + version ids repeat as FKs; section ids must not collide
    sections = [i for i in row_ids if i.startswith(PREFIX + "4b00-8b00-0000000000") and i[-2:] >= "11"]
    assert len(sections) == len(set(sections)) == 5


def test_concrete_attendance_and_theft_policies_are_present():
    sql = _sql()
    assert "Three (3) no-call/no-shows within any rolling 30-day period" in sql
    assert "Theft of cash" in sql


def test_all_inserts_are_idempotent_and_undo_targets_exactly_the_prefix():
    sql = _sql()
    assert sql.count("ON CONFLICT (id) DO NOTHING") == 3
    undo = UNDO.read_text()
    for table in ("handbook_sections", "handbook_versions", "handbooks"):
        assert f"DELETE FROM {table} WHERE id::text LIKE '{PREFIX}%'" in undo
