"""Enrich regulation_key_definitions with full metadata from compliance_registry.

Backfills name, description, enforcing_agency, state_variance, base_weight,
and update_frequency for all 459 key definitions using RegulationDef data.

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1
Create Date: 2026-03-25
"""

from alembic import op
from sqlalchemy import text

revision = "v7w8x9y0z1a2"
down_revision = "u6v7w8x9y0z1"
branch_labels = None
depends_on = None


def upgrade():
    # Widen update_frequency to TEXT — some values exceed 100 chars
    op.execute("ALTER TABLE regulation_key_definitions ALTER COLUMN update_frequency TYPE TEXT")

    from app.core.compliance_registry import REGULATIONS

    conn = op.get_bind()

    updated = 0
    for reg in REGULATIONS:
        name = reg.name.replace("'", "''")
        desc = (reg.description or "").replace("'", "''")
        agency = (reg.enforcing_agency or "").replace("'", "''")
        variance = reg.state_variance
        freq = (reg.update_frequency or "").replace("'", "''")
        weight = 1.5 if variance == "High" else 1.0

        result = conn.execute(text(f"""
            UPDATE regulation_key_definitions SET
                name = '{name}',
                description = '{desc}',
                enforcing_agency = '{agency}',
                state_variance = '{variance}',
                base_weight = {weight},
                update_frequency = '{freq}',
                updated_at = NOW()
            WHERE category_slug = '{reg.category}' AND key = '{reg.key}'
        """))
        if result.rowcount > 0:
            updated += 1

    print(f"Enriched {updated} key definitions")


def downgrade():
    pass  # Metadata enrichment is non-destructive
