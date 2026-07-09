"""legal_matters.subject_theory — user override for evidence subject scoping

The evidence corpus is scoped to the matter's subject (wage-and-hour / EEO /
workplace-safety), derived from the allegation text with matter_type as the
fallback. A derivation can be wrong, and the matter's OTHER scoping axis
(jurisdiction) already carries stored, editable overrides — location_id and
jurisdiction_state. This gives subject scoping the same treatment.

NULL = derive (the default). 'all' = explicitly pull every subject. The
derivation never writes this column; only a user does.

Revision ID: legaldef04
Revises: leadqual01
"""
from alembic import op
import sqlalchemy as sa

revision = "legaldef04"
down_revision = "leadqual01"
branch_labels = None
depends_on = None

_ALLOWED = ("wage_hour", "eeo", "safety", "all")


def upgrade() -> None:
    op.add_column(
        "legal_matters",
        sa.Column("subject_theory", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_legal_matters_subject_theory",
        "legal_matters",
        sa.text(
            "subject_theory IS NULL OR subject_theory IN "
            "('wage_hour', 'eeo', 'safety', 'all')"
        ),
    )


def downgrade() -> None:
    op.drop_constraint("ck_legal_matters_subject_theory", "legal_matters", type_="check")
    op.drop_column("legal_matters", "subject_theory")
