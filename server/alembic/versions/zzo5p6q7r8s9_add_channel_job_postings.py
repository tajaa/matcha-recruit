"""Add channel job postings: postings, invitations, and applications.

Revision ID: zzo5p6q7r8s9
Revises: zzn4o5p6q7r8
Create Date: 2026-04-11
"""
from alembic import op

revision = "zzo5p6q7r8s9"
down_revision = "zzn4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── channel_job_postings table ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_job_postings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            posted_by uuid NOT NULL REFERENCES users(id),
            title text NOT NULL,
            description text,
            requirements text,
            compensation_summary text,
            location text,
            status text NOT NULL DEFAULT 'draft',
            stripe_product_id text,
            stripe_price_id text,
            stripe_subscription_id text,
            subscription_status text,
            paid_through timestamptz,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            updated_at timestamptz NOT NULL DEFAULT NOW(),
            closed_at timestamptz
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_job_postings_channel_status
        ON channel_job_postings(channel_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_job_postings_posted_by_status
        ON channel_job_postings(posted_by, status)
    """)

    # ── channel_job_invitations table ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_job_invitations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            posting_id uuid NOT NULL REFERENCES channel_job_postings(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_at timestamptz NOT NULL DEFAULT NOW(),
            viewed_at timestamptz,
            UNIQUE(posting_id, user_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_job_invitations_user_viewed
        ON channel_job_invitations(user_id, viewed_at)
    """)

    # ── channel_job_applications table ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_job_applications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            posting_id uuid NOT NULL REFERENCES channel_job_postings(id) ON DELETE CASCADE,
            applicant_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cover_letter text,
            status text NOT NULL DEFAULT 'submitted',
            reviewer_notes text,
            reviewed_by uuid REFERENCES users(id),
            submitted_at timestamptz NOT NULL DEFAULT NOW(),
            reviewed_at timestamptz,
            UNIQUE(posting_id, applicant_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_job_applications_posting_status
        ON channel_job_applications(posting_id, status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_job_applications")
    op.execute("DROP TABLE IF EXISTS channel_job_invitations")
    op.execute("DROP TABLE IF EXISTS channel_job_postings")
