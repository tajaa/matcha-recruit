"""Add regulation_key_definitions.severity (obligation non-compliance severity).

Severity = how bad non-compliance is (imminent physical harm / severe statutory
liability), distinct from state_variance (how much the rule differs by state).
Seeded from the curated map in ``compliance_registry.resolve_severity`` — the
same seed-from-registry pattern as base_weight — with everything unmapped
(healthcare/international keys not in REGULATIONS) left at the 'moderate' default.

Revision ID: rkdsev01
Revises: scopereg_merge02
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "rkdsev01"
down_revision: Union[str, Sequence[str], None] = "scopereg_merge02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        ALTER TABLE regulation_key_definitions
            ADD COLUMN IF NOT EXISTS severity VARCHAR(10) NOT NULL DEFAULT 'moderate'
        """
    )
    conn.exec_driver_sql(
        """
        DO $$ BEGIN
            ALTER TABLE regulation_key_definitions
                ADD CONSTRAINT ck_rkd_severity
                CHECK (severity IN ('critical', 'high', 'moderate', 'low'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
        """
    )

    # Backfill from the curated seed authority (imports app code — precedent:
    # v7w8x9y0z1a2_enrich_key_definitions). Only critical/high rows need a write;
    # moderate is the column default.
    from app.core.compliance_registry import REGULATIONS, resolve_severity

    updated = 0
    for reg in REGULATIONS:
        sev = resolve_severity(reg.category, reg.key)
        if sev == "moderate":
            continue
        result = conn.execute(
            text(
                "UPDATE regulation_key_definitions SET severity = :sev, updated_at = NOW() "
                "WHERE category_slug = :cat AND key = :key"
            ),
            {"sev": sev, "cat": reg.category, "key": reg.key},
        )
        if result.rowcount:
            updated += 1
    print(f"rkdsev01: seeded severity on {updated} key definitions")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "ALTER TABLE regulation_key_definitions DROP CONSTRAINT IF EXISTS ck_rkd_severity"
    )
    conn.exec_driver_sql(
        "ALTER TABLE regulation_key_definitions DROP COLUMN IF EXISTS severity"
    )
