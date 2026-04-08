"""Drop unused/legacy tables that have no schema definitions or active code references.

Revision ID: zzh8i9j0k1l2
Revises: zzg7h8i9j0k1
Create Date: 2026-04-07

Tables dropped:
- RLS test artifacts: _rls_self_test_*, _rls_test_*
- Unused HR features: enps_*, performance_reviews, review_cycles, review_templates,
  vibe_check_*, industry_compliance_profiles
- Legacy creator/campaign: affiliate_*, agencies, agency_members, brand_deals,
  campaigns, campaign_*, contract_*, creator_*, deal_*, gumfit_*, revenue_*
"""
from alembic import op

revision = "zzh8i9j0k1l2"
down_revision = "zzg7h8i9j0k1"
branch_labels = None
depends_on = None

TABLES_TO_DROP = [
    # RLS test artifacts
    "_rls_self_test_a2e67d89",
    "_rls_test_3caa0d19",
    # Unused HR features
    "enps_responses",
    "enps_surveys",
    "performance_reviews",
    "review_templates",
    "review_cycles",
    "vibe_check_responses",
    "vibe_check_configs",
    "industry_compliance_profiles",
    # Legacy creator/campaign system
    "deal_contracts",
    "deal_applications",
    "creator_deal_matches",
    "campaign_payments",
    "campaign_offers",
    "brand_deals",
    "campaigns",
    "contract_payments",
    "contract_templates",
    "creator_expenses",
    "creator_platform_connections",
    "creator_valuations",
    "creators",
    "gumfit_assets",
    "gumfit_invites",
    "affiliate_events",
    "affiliate_links",
    "agency_members",
    "agencies",
    "revenue_entries",
    "revenue_streams",
]


def upgrade() -> None:
    for table in TABLES_TO_DROP:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    # These tables had no schema definitions — cannot recreate.
    pass
