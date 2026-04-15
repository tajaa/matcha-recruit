"""Profile resumes + channel-wide job postings + channel-owned posting fee.

- user_resumes: one parsed resume per user (profile-scoped).
- channel_job_postings.open_to_all: channel-wide apply without an invite row.
- channel_job_applications.resume_snapshot: audit snapshot of the applicant's
  profile resume at submit time.
- channels.job_posting_fee_cents: channel-owned fee for job postings (NULL
  falls back to the platform default).

Revision ID: zzt0u1v2w3x4
Revises: zzs9t0u1v2w3
Create Date: 2026-04-15
"""
from alembic import op

revision = "zzt0u1v2w3x4"
down_revision = "zzs9t0u1v2w3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_resumes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            filename text NOT NULL,
            resume_url text NOT NULL,
            raw_text text,
            parsed_data jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            updated_at timestamptz NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        ALTER TABLE channel_job_postings
          ADD COLUMN IF NOT EXISTS open_to_all boolean NOT NULL DEFAULT false
        """
    )

    op.execute(
        """
        ALTER TABLE channel_job_applications
          ADD COLUMN IF NOT EXISTS resume_snapshot jsonb
        """
    )

    op.execute(
        """
        ALTER TABLE channels
          ADD COLUMN IF NOT EXISTS job_posting_fee_cents integer
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS job_posting_fee_cents")
    op.execute("ALTER TABLE channel_job_applications DROP COLUMN IF EXISTS resume_snapshot")
    op.execute("ALTER TABLE channel_job_postings DROP COLUMN IF EXISTS open_to_all")
    op.execute("DROP TABLE IF EXISTS user_resumes")
