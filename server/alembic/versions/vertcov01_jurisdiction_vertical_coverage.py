"""Coverage ledger for tenant-triggered vertical (industry) research.

WHY THIS EXISTS
----------------
The catalog is jurisdiction x industry x category. Reachability was fixed
(jparent01/jsonfix01): a tenant's Compliance tab now sees the full jurisdiction
chain, industry-filtered. But nothing populates the industry dimension for a
vertical nobody has hand-authored yet — a dental office in LA gets zero dental
rows because dental was never researched, and nothing records that fact so it
could be filled.

`research_specialization_for_jurisdiction` (compliance_service.py) already does
the research + grounding + upsert correctly. What it lacks is memory: its
`skip_existing` check infers coverage from "are there rows already", which
cannot distinguish never-researched from researched-and-genuinely-empty, so an
empty cell gets re-researched forever and the loop never converges.

This ledger is that memory, one row per (jurisdiction, industry, category):
  pending      -> never attempted
  in_progress  -> a fill is running right now (crash-safe marker)
  covered      -> researched, requirements written
  empty        -> researched, genuinely nothing found — DO NOT retry
  failed       -> researched, errored — retry allowed

Keyed on jurisdiction_id (not company/location), so federal dental research
runs once nationally and state research once per state. Every later tenant in
that jurisdiction reads `covered`/`empty` and triggers zero Gemini calls — the
whole point of a shared, tenant-independent catalog.

Revision ID: vertcov01
Revises: jsonfix01
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "vertcov01"
down_revision = "jsonfix01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jurisdiction_vertical_coverage",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("jurisdiction_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("industry_tag", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("requirements_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by_company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','covered','empty','failed')",
            name="ck_jvc_status",
        ),
        sa.UniqueConstraint("jurisdiction_id", "industry_tag", "category", name="uq_jvc_cell"),
    )
    op.create_index(
        "ix_jvc_lookup", "jurisdiction_vertical_coverage",
        ["jurisdiction_id", "industry_tag", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_jvc_lookup", table_name="jurisdiction_vertical_coverage")
    op.drop_table("jurisdiction_vertical_coverage")
