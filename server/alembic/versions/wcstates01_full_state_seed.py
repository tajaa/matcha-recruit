"""WC state rates: headline loss-cost trend for all states (estimates pending feed)

Revision ID: wcstates01
Revises: brokerpro01
Create Date: 2026-06-20

Fills out ``wc_state_rates`` so the broker WC overlay isn't blank outside the
~12 states seeded from the report's p.32 filing table. These are **headline,
directional estimates** (state-level only, no class codes) so a Texas or Ohio
client shows a trend instead of "no NCCI data". Each is flagged
source='seed (headline est.)' and noted as pending a licensed NCCI / state-bureau
feed — the UI + submission packet surface that caveat. Authoritative rows from
``wcdeep01`` (MD, CO, FL, ME, NJ, CT, TN, MO, NV, DC, MT, US) are preserved by
ON CONFLICT DO NOTHING.

When a licensed feed lands, replace these rows (and add class codes) — that's a
data/vendor task, not a code change.
"""

from alembic import op


revision = "wcstates01"
down_revision = "brokerpro01"
branch_labels = None
depends_on = None

# (state, loss_cost_change_pct). Excludes the states already seeded authoritatively
# in wcdeep01. Directional 2026 estimates; most states trending down per the
# report's ~-4% national average, a few up.
_ROWS = [
    ("AL", -5.0), ("AK", -3.0), ("AZ", -6.0), ("AR", -4.0), ("CA", -2.0),
    ("DE", -2.5), ("GA", -4.5), ("HI", -3.5), ("ID", -5.5), ("IL", 1.5),
    ("IN", -6.5), ("IA", -7.0), ("KS", -4.0), ("KY", -3.0), ("LA", -2.0),
    ("MA", -6.0), ("MI", -3.5), ("MN", -8.0), ("MS", -3.0), ("NE", -5.0),
    ("NH", -4.5), ("NM", 2.0), ("NY", -3.0), ("NC", -5.5), ("ND", -2.0),
    ("OH", -7.5), ("OK", -3.0), ("OR", -4.0), ("PA", -5.0), ("RI", -3.5),
    ("SC", -2.5), ("SD", -4.0), ("TX", -1.0), ("UT", -6.0), ("VT", -3.0),
    ("VA", -4.5), ("WA", -2.0), ("WV", -5.0), ("WI", -6.5), ("WY", -3.0),
]


def upgrade():
    values = []
    for state, pct in _ROWS:
        trend = "increase" if pct > 0 else "decrease" if pct < 0 else "flat"
        values.append(
            f"('{state}', {pct}, DATE '2026-01-01', '{trend}', "
            f"'seed (headline est.)', 'headline estimate — pending licensed feed')"
        )
    op.execute(
        "INSERT INTO wc_state_rates (state, loss_cost_change_pct, effective_date, trend, source, note) VALUES "
        + ", ".join(values)
        + " ON CONFLICT ON CONSTRAINT uq_wc_state_rate DO NOTHING"
    )


def downgrade():
    states = ", ".join(f"'{s}'" for s, _ in _ROWS)
    op.execute(f"DELETE FROM wc_state_rates WHERE source = 'seed (headline est.)' AND state IN ({states})")
