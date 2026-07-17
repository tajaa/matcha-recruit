"""add_employee_is_manager_column

Revision ID: emphris0002
Revises: empsched02
Create Date: 2026-07-17 10:00:00.000000

Every HRIS normalizer has emitted `is_manager` since the sync was written, and
nothing has ever stored it — the orchestrator's INSERT/UPDATE lists are hand-
maintained, so a key nobody added there is silently inert. This is that column.

Nullable on purpose: NULL means "never synced", which is a different fact from
a synced FALSE ("HRIS says this person manages no one"). The orchestrator
COALESCEs on it, so NULL also means "no new fact — keep what's there".

Distinct from the existing `is_supervisor`, which is Matcha-set and carries
training/certification semantics. Same English word, different sources of truth;
collapsing them would let an HRIS resync silently rewrite training scope.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'emphris0002'
down_revision: Union[str, Sequence[str], None] = 'empsched02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS is_manager BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS is_manager")
