"""Clear the saved Deal Flow templates for the removed broker tabs.

Revision ID: brokerdrop02
Revises: brokerdrop01
Create Date: 2026-10-09

The admin Deal Flow tool lost its "Broker" and "Book Pricing" tabs and the
broker-discount fields. Their saved editor payloads in `deal_flow_templates`
(keys `broker` and `book`) are unreachable now, so they are deleted, and the
default "Broker Pricing (10% off)" note block (`sav_n2`) is stripped from a saved
`full` template so a previously saved copy stops printing it.

Irreversible, but only the admin's own editor drafts: pricing history lives in
the generated proposals, not here.

One `op.execute` per statement and no `:name` binds (see
tests/alembic/test_single_statement_migrations.py).
"""
from alembic import op

revision = "brokerdrop02"
down_revision = "brokerdrop01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM deal_flow_templates WHERE template_key IN ('broker', 'book')")
    op.execute(
        """
        UPDATE deal_flow_templates
        SET payload = jsonb_set(
            payload,
            '{blocks}',
            COALESCE(
                (SELECT jsonb_agg(b) FROM jsonb_array_elements(payload -> 'blocks') AS b WHERE b ->> 'id' <> 'sav_n2'),
                '[]'::jsonb
            )
        )
        WHERE template_key = 'full'
          AND jsonb_typeof(payload -> 'blocks') = 'array'
        """
    )


def downgrade():
    raise RuntimeError(
        "brokerdrop02 is irreversible: the saved broker/book Deal Flow templates were deleted."
    )
