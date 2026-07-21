"""Analysis Pilot — admit `source_kind='platform'` for datasets built from platform records

Revision ID: analysispilot02
Revises: signdoc01
Create Date: 2026-07-20

`analysispilot01` created `analysis_pilot_datasets.source_kind VARCHAR(12) NOT NULL
CHECK (source_kind IN ('csv','xlsx','pdf'))` — the three UPLOAD paths, which were
the only ingestion routes at the time. Datasets can now also be built
deterministically from the company's own records (`services/analysis_platform_sources.py`),
which is a fourth source kind. VARCHAR(12) already fits 'platform'; only the
CHECK has to widen, so this drops and re-creates that one constraint — looked up
from `pg_constraint` rather than by assumed name (see `_DROP_SOURCE_KIND_CHECKS`).

It also drops the NOT NULL on `storage_path`: a platform dataset is built from
live rows and stores no file, so it has no path at all.

Nothing is rewritten and no row changes: every existing dataset keeps its
current `source_kind` and its `storage_path`, and the new value is only ever
written by the new
`POST /analysis-pilot/pilot/sessions/{id}/datasets/platform` route.

`downgrade()` is honest about the one thing it cannot do: re-adding the narrow
CHECK (and the NOT NULL) fails while any 'platform' / path-less row exists, so it
deletes those rows first. They are point-in-time snapshots rebuilt from live
tables on demand, so the data is not lost — but a session that cited one loses
that dataset, which is why the delete is explicit here rather than a surprise
inside a failed constraint add.

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

# Drop whatever CHECK actually constrains `source_kind`, by lookup rather than by
# assumed name. `DROP CONSTRAINT IF EXISTS <guessed-name>` silently no-ops when
# the live constraint is named anything else (a restored dump, a hand-fixed
# environment), and the migration then "succeeds" while the old narrow CHECK
# survives — every platform insert fails afterwards against a constraint this
# file believes it replaced.
_DROP_SOURCE_KIND_CHECKS = """
DO $$
DECLARE c record;
BEGIN
    FOR c IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY (con.conkey)
        WHERE rel.relname = 'analysis_pilot_datasets'
          AND con.contype = 'c'
          AND att.attname = 'source_kind'
    LOOP
        EXECUTE format('ALTER TABLE analysis_pilot_datasets DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;
"""


def upgrade():
    op.execute(_DROP_SOURCE_KIND_CHECKS)
    op.execute(
        f"""
        ALTER TABLE analysis_pilot_datasets
            ADD CONSTRAINT {_CHECK}
            CHECK (source_kind IN ('csv', 'xlsx', 'pdf', 'platform'))
        """
    )
    # A platform dataset is built from live rows and stores no file, so its
    # `storage_path` is NULL. The alternative — a sentinel string in a NOT NULL
    # column — makes every storage call site responsible for recognizing a path
    # that isn't one, and the first one that forgets hands it to S3.
    op.execute("ALTER TABLE analysis_pilot_datasets ALTER COLUMN storage_path DROP NOT NULL")


def downgrade():
    # Rows the narrowed CHECK (or the restored NOT NULL) would reject must go
    # first, or the ALTER fails and the whole downgrade rolls back. These are
    # point-in-time snapshots rebuilt on demand, so no source data is lost.
    op.execute("DELETE FROM analysis_pilot_datasets WHERE source_kind = 'platform'")
    op.execute("DELETE FROM analysis_pilot_datasets WHERE storage_path IS NULL")
    op.execute("ALTER TABLE analysis_pilot_datasets ALTER COLUMN storage_path SET NOT NULL")
    op.execute(_DROP_SOURCE_KIND_CHECKS)
    op.execute(
        f"""
        ALTER TABLE analysis_pilot_datasets
            ADD CONSTRAINT {_CHECK}
            CHECK (source_kind IN ('csv', 'xlsx', 'pdf'))
        """
    )
