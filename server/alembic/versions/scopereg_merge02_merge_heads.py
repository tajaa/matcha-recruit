"""Merge the two live Alembic heads before the scope-registry dimension work.

The tree diverged into two tips:
  * ``citeverify01`` — scope-registry / citation-verification branch
  * ``legaldef05``   — brokerpilot ← legal-pilot branch

``rkdsev01`` (RKD severity) and ``scopetag01`` (classification jurisdiction
scope) chain off this merge so there is a single head again. Empty upgrade —
no schema change (precedent: ``2c12cf3aaab4_merge_heads.py``).

Revision ID: scopereg_merge02
Revises: citeverify01, legaldef05
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401


revision: str = "scopereg_merge02"
down_revision: Union[str, Sequence[str], None] = ("citeverify01", "legaldef05")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
