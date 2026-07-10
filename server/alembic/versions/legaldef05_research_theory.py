"""legal_matter_research.theory — the subject a research run was scoped to

Case-law search is constrained on two axes, and the run row already recorded
only one of them (jurisdiction_state). Recording the subject too lets
legal_defense._gather_case_law refuse a run whose subject no longer matches the
matter's — including every row written before the subject anchor existed, whose
query could return an in-state case about anything (the reported San Diego
gunshot opinion in a Los Angeles wage-and-hour matter).

NULL = the run was unscoped (a broad matter: subpoena / audit / other, or an
ambiguous allegation). Values mirror legal_matters.subject_theory minus 'all',
which is an input meaning "derive nothing", never a resolved output.

Revision ID: legaldef05
Revises: legaldef04
"""
from alembic import op
import sqlalchemy as sa

revision = "legaldef05"
down_revision = "legaldef04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_matter_research",
        sa.Column("theory", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_legal_matter_research_theory",
        "legal_matter_research",
        sa.text("theory IS NULL OR theory IN ('wage_hour', 'eeo', 'safety')"),
    )


def downgrade() -> None:
    op.drop_constraint("ck_legal_matter_research_theory", "legal_matter_research", type_="check")
    op.drop_column("legal_matter_research", "theory")
