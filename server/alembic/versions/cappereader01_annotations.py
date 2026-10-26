"""Private magazine reader annotations. Additive; no existing rows change.

Apply before deploying the annotation API. Old application versions ignore
this table. Downgrade refuses while annotations exist to prevent data loss.
"""
from alembic import op

revision = "cappereader01"
down_revision = "cappefont01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE cappe_reader_annotations (
            account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            post_id UUID NOT NULL REFERENCES cappe_posts(id) ON DELETE CASCADE,
            id UUID NOT NULL,
            body JSONB NOT NULL CHECK (jsonb_typeof(body) = 'object' AND octet_length(body::text) <= 65536),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (account_id, post_id, id)
        )
    """)
    op.execute("CREATE INDEX idx_cappe_reader_annotations_post ON cappe_reader_annotations (post_id)")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cappe_reader_annotations) THEN
                RAISE EXCEPTION 'Reader annotations exist; export or remove them before downgrading';
            END IF;
        END $$
    """)
    op.execute("DROP TABLE cappe_reader_annotations")
