"""Add blog post submission-for-review fields.

Lets non-admin Matcha Work users submit a blog project to the master admin
for approval/publishing. Adds:
- submitted_for_review: BOOLEAN flag for the admin "Pending Review" filter
- submitter_id: who submitted (for attribution distinct from author_id which
  the admin overwrites on approval)
- source_project_id: link back to the originating mw_projects row so the
  reviewer can open the underlying blog project
- review_notes: admin's rejection / acceptance notes

Revision ID: zzzc9d0e1f2g3
Revises: zzzb8c9d0e1f2
Create Date: 2026-04-24
"""
from alembic import op

revision = "zzzc9d0e1f2g3"
down_revision = "zzzb8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE blog_posts
            ADD COLUMN IF NOT EXISTS submitted_for_review BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS submitter_id UUID REFERENCES users(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS source_project_id UUID REFERENCES mw_projects(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS review_notes TEXT,
            ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_blog_posts_submitted_for_review "
        "ON blog_posts(submitted_for_review) WHERE submitted_for_review = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_blog_posts_submitted_for_review")
    op.execute("""
        ALTER TABLE blog_posts
            DROP COLUMN IF EXISTS submitted_for_review,
            DROP COLUMN IF EXISTS submitter_id,
            DROP COLUMN IF EXISTS source_project_id,
            DROP COLUMN IF EXISTS review_notes,
            DROP COLUMN IF EXISTS submitted_at
    """)
