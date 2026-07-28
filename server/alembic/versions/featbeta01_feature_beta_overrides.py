"""Add feature_beta_overrides — lets an admin move a feature from beta to
ready (or back) without a code change + deploy.

feature_flags.BETA_FEATURES stays the code-level default classification (a
new flag can ship declared beta with zero migration). This table OVERRIDES
that per key: a row with is_beta=false promotes a code-beta flag to ready;
is_beta=true declares a flag beta that code doesn't. Deliberately still
DB-free at the one place that matters most: merge_company_features (pure +
sync, runs in pool-free Celery workers) never consults this table — beta
status is only ever read at WRITE-time gates (assert_feature_allowed,
validate_features, the broker toggle normalizer) and two display surfaces
(GET /admin/feature-flags, /auth/me), all of which already hold a connection.

Revision ID: featbeta01
Revises: featgrant01
Create Date: 2026-07-28
"""
from alembic import op

revision = "featbeta01"
down_revision = "featgrant01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS feature_beta_overrides (
            feature_key TEXT PRIMARY KEY,
            is_beta BOOLEAN NOT NULL,
            updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS feature_beta_overrides")
