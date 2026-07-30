"""cappe: site-scoped Merlin setup concierge conversations + staged actions

Merlin conversations were strictly page-scoped: `page_id` was NOT NULL and
every list query filtered on it. The setup concierge (dashboard, not the page
editor) needs a SITE-scoped conversation instead — there is no open page to
attach it to.

- `page_id` becomes nullable. Existing page-scoped queries
  (`store.py:list_conversations` WHERE page_id = $1, and the page-mismatch 404
  in `routes/merlin.py`) already exclude NULL-page rows with zero code changes
  — a setup conversation can never leak into the page editor.
- `kind` distinguishes the two conversation shapes ('page' | 'setup'). The
  CHECK constraint pins page_id NOT NULL to kind='page' specifically, rather
  than relying on callers to keep the two in sync.
- `staged_actions` (setup-kind only) holds the confirm-first proposal queue —
  server-row writes (create product, promo banner, ...) the concierge proposes
  and the user approves before anything is executed. See
  services/merlin/setup_actions.py.

Purely additive; downgrade discards any setup conversations that accumulated
(their staged actions were never a source of truth for anything else).

Revision ID: zzzzcappe27
Revises: zzzzcappe26
Create Date: 2026-07-30
"""
from alembic import op

revision = "zzzzcappe27"
down_revision = "zzzzcappe26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_merlin_conversations ALTER COLUMN page_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE cappe_merlin_conversations "
        "ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'page'"
    )
    op.execute(
        "ALTER TABLE cappe_merlin_conversations ADD COLUMN IF NOT EXISTS staged_actions JSONB"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cappe_merlin_convos_site_kind
        ON cappe_merlin_conversations(site_id, kind, updated_at DESC)
        """
    )
    # No IF NOT EXISTS for ADD CONSTRAINT in Postgres — drop-then-add so a
    # rerun after a partial failure (this statement ran, a later one didn't)
    # doesn't abort the whole upgrade on a duplicate-constraint error.
    op.execute(
        "ALTER TABLE cappe_merlin_conversations DROP CONSTRAINT IF EXISTS ck_cappe_merlin_convo_scope"
    )
    op.execute(
        """
        ALTER TABLE cappe_merlin_conversations
        ADD CONSTRAINT ck_cappe_merlin_convo_scope
        CHECK (kind <> 'page' OR page_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_merlin_conversations DROP CONSTRAINT IF EXISTS ck_cappe_merlin_convo_scope")
    op.execute("DROP INDEX IF EXISTS idx_cappe_merlin_convos_site_kind")
    op.execute("DELETE FROM cappe_merlin_conversations WHERE page_id IS NULL")
    op.execute("ALTER TABLE cappe_merlin_conversations DROP COLUMN IF EXISTS staged_actions")
    op.execute("ALTER TABLE cappe_merlin_conversations DROP COLUMN IF EXISTS kind")
    op.execute("ALTER TABLE cappe_merlin_conversations ALTER COLUMN page_id SET NOT NULL")
