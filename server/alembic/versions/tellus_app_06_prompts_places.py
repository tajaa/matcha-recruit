"""tellus_app_06 — brand prompts, report answers, unclaimed places.

Revision ID: tellus_app_06
Revises: tellus_app_05
"""
from alembic import op
from sqlalchemy import text as sa_text

revision = "tellus_app_06"
down_revision = "tellus_app_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unclaimed places: brands may exist without an owning account.
    op.execute("ALTER TABLE tellus_brands ALTER COLUMN owner_account_id DROP NOT NULL")
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE tellus_brands ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'signup'")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_brands ADD CONSTRAINT ck_tellus_brands_source
                CHECK (source IN ('signup', 'consumer_added'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_brand_prompts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            prompt TEXT NOT NULL,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_brand_prompts_brand ON tellus_brand_prompts (brand_id, position)")

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_report_answers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id UUID NOT NULL REFERENCES tellus_reports(id) ON DELETE CASCADE,
            prompt_id UUID REFERENCES tellus_brand_prompts(id) ON DELETE SET NULL,
            prompt_text TEXT NOT NULL,
            answer TEXT NOT NULL,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_report_answers_report ON tellus_report_answers (report_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_report_answers")
    op.execute("DROP TABLE IF EXISTS tellus_brand_prompts")
    op.execute("ALTER TABLE tellus_brands DROP CONSTRAINT IF EXISTS ck_tellus_brands_source")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE tellus_brands DROP COLUMN IF EXISTS claimed_at")
    # Irreversible once ownerless brands exist — fail loudly instead of deleting data.
    ownerless = op.get_bind().execute(
        sa_text("SELECT COUNT(*) FROM tellus_brands WHERE owner_account_id IS NULL")
    ).scalar()
    if ownerless:
        raise RuntimeError(f"{ownerless} ownerless brands exist; cannot restore NOT NULL. Restore from RDS snapshot.")
    op.execute("ALTER TABLE tellus_brands ALTER COLUMN owner_account_id SET NOT NULL")
