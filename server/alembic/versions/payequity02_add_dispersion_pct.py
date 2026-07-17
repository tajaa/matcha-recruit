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

This gives dispersion its own column so gap_pct can mean what it says, and moves
the existing auto rows over.

Those rows are identifiable, which is easy to miss: the auto path hardcoded one
exact methodology literal (below), and nothing else writes it — the study form
collects review_date/scope/gap_pct/remediation and never sets methodology. So a
row carrying that string is an auto row, and its gap_pct is a dispersion share,
with no guesswork involved. Leaving them would keep the mislabel live until each
tenant happened to re-run the analysis: derive_pay_equity reads the newest study,
so a stale auto row goes on telling an underwriter "40.0% gap" indefinitely.

Rows whose methodology is NULL or anything else are hand-entered studies whose
gap_pct always meant a real gap — untouched. The WHERE is written so re-running
is a no-op.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'payequity02'
down_revision: Union[str, Sequence[str], None] = 'emphris0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The exact string the auto path wrote (pay_equity_analysis.review_row, pre-fix).
# Matching it verbatim is the point — a LIKE could catch a hand-typed methodology
# that happens to mention dispersion, and relabel a real gap as a screen result.
_AUTO_METHODOLOGY = (
    "pay_rate dispersion by job title "
    "(screen only; protected-class gap needs HRIS demographics)"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pay_equity_reviews ADD COLUMN IF NOT EXISTS dispersion_pct NUMERIC(5,2)"
    )
    # Set-based, keyed on the literal — no row-by-row pass (server/CLAUDE.md).
    op.execute(f"""
        UPDATE pay_equity_reviews
        SET dispersion_pct = gap_pct,
            gap_pct = NULL
        WHERE methodology = '{_AUTO_METHODOLOGY}'
          AND gap_pct IS NOT NULL
          AND dispersion_pct IS NULL
    """)


def downgrade() -> None:
    # Put the auto rows' number back in gap_pct before the column goes, so a
    # downgrade doesn't silently discard it.
    op.execute(f"""
        UPDATE pay_equity_reviews
        SET gap_pct = dispersion_pct
        WHERE methodology = '{_AUTO_METHODOLOGY}'
          AND gap_pct IS NULL
          AND dispersion_pct IS NOT NULL
    """)
    op.execute("ALTER TABLE pay_equity_reviews DROP COLUMN IF EXISTS dispersion_pct")
