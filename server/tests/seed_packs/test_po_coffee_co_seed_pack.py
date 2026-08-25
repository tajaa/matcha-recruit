"""Po Coffee Co must not alter tenant-owned feature configuration."""

from pathlib import Path


PACK_DIR = Path(__file__).resolve().parents[3] / "scripts" / "seed"


def test_po_coffee_co_pack_and_undo_leave_company_features_untouched():
    for filename in ("po_coffee_co.sql", "po_coffee_co.undo.sql"):
        sql = (PACK_DIR / filename).read_text().lower()
        assert "update companies" not in sql
        assert "enabled_features" not in sql


def test_po_coffee_co_locations_are_ready_for_scheduling():
    sql = (PACK_DIR / "po_coffee_co.sql").read_text()
    assert "jurisdiction_id, timezone" in sql
    assert "America/Los_Angeles" in sql
    assert "WHERE business_locations.jurisdiction_id IS NULL OR business_locations.timezone IS NULL" in sql
