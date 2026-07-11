"""jurisdiction_requirements: source_url liveness flag (retain, don't erase)

The compliance research pass HEAD-checks every ``source_url``; the old behavior
overwrote a 404/timeout URL with ``''`` (and blanked ``source_name``),
destroying the pointer back to the authority — the very thing we re-check when a
policy may have changed. This adds two columns so a dead link is *flagged*
instead of erased:

  * source_url_status  — 'unchecked' (default) | 'ok' | 'dead'
  * source_checked_at  — when the last liveness check ran

Written by ``compliance_service._validate_source_urls`` + the two
jurisdiction_requirements upserts. Read-side surfacing (admin/ScopeStudio) can
follow; the column existing means the URL is no longer lost in the meantime.

Not auto-applied — the user runs ./scripts/migrate-dev.sh / migrate-prod.sh.

Revision ID: srcstatus01
Revises: statbody01
Create Date: 2026-07-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "srcstatus01"
down_revision: Union[str, Sequence[str], None] = "statbody01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS source_url_status VARCHAR(20) DEFAULT 'unchecked',
            ADD COLUMN IF NOT EXISTS source_checked_at TIMESTAMP
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE jurisdiction_requirements
            DROP COLUMN IF EXISTS source_checked_at,
            DROP COLUMN IF EXISTS source_url_status
        """
    )
