"""merge heads — ghscan0001 + oshacase0001

Two parallel branches diverged earlier in history:
  * ghscan0001  (werk project scan-cursor line)
  * oshacase0001 (OSHA per-injured-employee case-details line)
Neither touches the other's tables, so this is a no-op merge that reunifies the
revision graph to a single head — `alembic upgrade head` (used by
migrate-dev.sh / migrate-prod.sh) is ambiguous while two heads exist.

Revision ID: mrgheads01
Revises: ghscan0001, oshacase0001
Create Date: 2026-06-03
"""


revision = "mrgheads01"
down_revision = ("ghscan0001", "oshacase0001")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
