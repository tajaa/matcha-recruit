"""add_pay_equity_reviews_dispersion_pct

Revision ID: payequity02
Revises: emphris0003
Create Date: 2026-07-17 10:10:00.000000

`gap_pct` is documented as "adjusted pay gap %, if measured" and the manual
study-entry path writes exactly that. The auto-analysis path has been writing
something else entirely into the same column — the percentage of ROLES whose pay
spread exceeds the dispersion threshold — and derive_pay_equity renders it to
brokers as "{gap}% gap, remediation pending". A company with 40% of its roles
showing spread has been reporting a "40.0% gap" to underwriters.

This gives dispersion its own column so gap_pct can mean what it says. Existing
rows are left alone: we cannot tell, per row, which of the two quantities a
historical value was, and guessing would be inventing data. Rows written from
here on are unambiguous — auto rows put dispersion in dispersion_pct and leave
gap_pct NULL unless demographics let us measure a real gap.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'payequity02'
down_revision: Union[str, Sequence[str], None] = 'emphris0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pay_equity_reviews ADD COLUMN IF NOT EXISTS dispersion_pct NUMERIC(5,2)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE pay_equity_reviews DROP COLUMN IF EXISTS dispersion_pct")
