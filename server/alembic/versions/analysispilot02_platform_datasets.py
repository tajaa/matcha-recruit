"""Analysis Pilot — admit `source_kind='platform'` for datasets built from platform records

Revision ID: analysispilot02
Revises: signdoc01
Create Date: 2026-07-20

`analysispilot01` created `analysis_pilot_datasets.source_kind VARCHAR(12) NOT NULL
CHECK (source_kind IN ('csv','xlsx','pdf'))` — the three UPLOAD paths, which were
the only ingestion routes at the time. Datasets can now also be built
deterministically from the company's own records (`services/analysis_platform_sources.py`),
which is a fourth source kind. VARCHAR(12) already fits 'platform'; only the
CHECK has to widen, so this drops and re-creates that one constraint.

Nothing is rewritten and no row changes: every existing dataset keeps its
current `source_kind`, and the new value is only ever written by the new
`POST /analysis-pilot/pilot/sessions/{id}/datasets/platform` route.

`downgrade()` is honest about the one thing it cannot do: re-adding the narrow
CHECK fails while any 'platform' row exists, so it deletes those rows first.
They are point-in-time snapshots rebuilt from live tables on demand, so the data
is not lost — but a session that cited one loses that dataset, which is why the
delete is explicit here rather than a surprise inside a failed constraint add.

NOTE: the alembic history on this branch has multiple leaves. `down_revision` is
set to `signdoc01` — the tip of the chain that carries `analysispilot01`
(analysispilot01 → hnswvec01 → leadqual01 → limadq02 → hbshare01 → signdoc01) at
authoring time. Confirm the correct head for your environment before upgrading
(the repo applies migrations via `scripts/migrate-dev.sh` / `migrate-prod.sh`,
not a bare `upgrade head`).
"""

from alembic import op


revision = "analysispilot02"
down_revision = "signdoc01"
branch_labels = None
depends_on = None

_CHECK = "analysis_pilot_datasets_source_kind_check"


def upgrade():
    op.execute(f"ALTER TABLE analysis_pilot_datasets DROP CONSTRAINT IF EXISTS {_CHECK}")
    op.execute(
        f"""
        ALTER TABLE analysis_pilot_datasets
            ADD CONSTRAINT {_CHECK}
            CHECK (source_kind IN ('csv', 'xlsx', 'pdf', 'platform'))
        """
    )


def downgrade():
    # A row the narrowed CHECK would reject must go before the constraint is
    # re-added, or the ALTER fails and the whole downgrade rolls back.
    op.execute("DELETE FROM analysis_pilot_datasets WHERE source_kind = 'platform'")
    op.execute(f"ALTER TABLE analysis_pilot_datasets DROP CONSTRAINT IF EXISTS {_CHECK}")
    op.execute(
        f"""
        ALTER TABLE analysis_pilot_datasets
            ADD CONSTRAINT {_CHECK}
            CHECK (source_kind IN ('csv', 'xlsx', 'pdf'))
        """
    )
