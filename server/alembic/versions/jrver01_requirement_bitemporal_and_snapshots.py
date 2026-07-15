"""Bitemporal version history + source snapshots for jurisdiction_requirements.

WHY THIS EXISTS
----------------
A compliance product's defensibility rests on answering, months later, "what did
we tell this business on date X, and was it correct then?". The catalog could not
answer it: `jurisdiction_requirements` updates OVERWRITE in place
(`SET ... updated_at = NOW()`), and the only history — `policy_change_log` — is
app-side, field-diff-only, and bypassed by the admin PATCH, the research-review
approve, the routed research upserts, and codify. So there was no queryable
transaction-time axis and no frozen evidence of the source page as it read.

Two tables, both write-once:

1. `jurisdiction_requirement_versions` — a TRIGGER-fed, append-only row-image log.
   Trigger-fed on purpose: the `policy_change_log` lesson is that any capture the
   application must remember to call gets silently skipped by some write path.
   A row trigger cannot be bypassed by any INSERT/UPDATE/DELETE. Each version
   carries a transaction-time interval (`recorded_at` .. `superseded_at`, NULL =
   current), so a point-in-time read is:
       SELECT row_data FROM jurisdiction_requirement_versions
       WHERE requirement_id = $1 AND recorded_at <= $ts
         AND (superseded_at IS NULL OR superseded_at > $ts)
   The world-time axis (`effective_date`/`expiration_date`) already lives on the
   row and rides inside `row_data`, giving true bitemporal queries. `row_data` is
   `to_jsonb(row)` so it is immune to future column changes.

2. `requirement_source_snapshots` — the frozen government-page text (not just a
   URL — pages change and die) captured at value-bearing events (research,
   approve, codify, verify), deduped by content hash.

IMMUTABILITY NOTE: the app connects as a superuser, so a REVOKE cannot hard-block
writes to these tables. Immutability is enforced by convention — nothing in the
codebase UPDATEs or DELETEs them, and the versions table is written ONLY by the
trigger. Do not add an update/delete path.

Revision ID: jrver01
Revises: vertcov02
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "jrver01"
down_revision = "vertcov02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. version history (trigger-fed, append-only) ────────────────────────
    op.create_table(
        "jurisdiction_requirement_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # No FK: versions must survive the requirement's (and jurisdiction's) delete.
        sa.Column("requirement_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("op", sa.String(length=1), nullable=False),  # I / U / D
        sa.Column("row_data", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_source", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("op IN ('I','U','D')", name="ck_jrv_op"),
    )
    op.create_index(
        "ix_jrv_requirement_recorded", "jurisdiction_requirement_versions",
        ["requirement_id", "recorded_at"],
    )
    # Fast "current version of X" lookup.
    op.execute(
        "CREATE INDEX ix_jrv_current ON jurisdiction_requirement_versions "
        "(requirement_id) WHERE superseded_at IS NULL"
    )

    # The capture trigger. Reads attribution from session GUCs the write paths
    # set with `SET LOCAL app.change_source = '…'` (NULL-safe via the missing_ok
    # 'true' arg — an unattributed write still captures, just unlabeled).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION capture_requirement_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_source TEXT := NULLIF(current_setting('app.change_source', true), '');
            v_actor  UUID := NULLIF(current_setting('app.actor_id', true), '')::uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                UPDATE jurisdiction_requirement_versions
                   SET superseded_at = now()
                 WHERE requirement_id = OLD.id AND superseded_at IS NULL;
                INSERT INTO jurisdiction_requirement_versions
                    (requirement_id, jurisdiction_id, op, row_data, change_source, actor_id)
                VALUES (OLD.id, OLD.jurisdiction_id, 'D', to_jsonb(OLD), v_source, v_actor);
                RETURN OLD;
            ELSIF TG_OP = 'UPDATE' THEN
                UPDATE jurisdiction_requirement_versions
                   SET superseded_at = now()
                 WHERE requirement_id = NEW.id AND superseded_at IS NULL;
                INSERT INTO jurisdiction_requirement_versions
                    (requirement_id, jurisdiction_id, op, row_data, change_source, actor_id)
                VALUES (NEW.id, NEW.jurisdiction_id, 'U', to_jsonb(NEW), v_source, v_actor);
                RETURN NEW;
            ELSE  -- INSERT
                INSERT INTO jurisdiction_requirement_versions
                    (requirement_id, jurisdiction_id, op, row_data, change_source, actor_id)
                VALUES (NEW.id, NEW.jurisdiction_id, 'I', to_jsonb(NEW), v_source, v_actor);
                RETURN NEW;
            END IF;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_capture_requirement_version "
        "AFTER INSERT OR UPDATE OR DELETE ON jurisdiction_requirements "
        "FOR EACH ROW EXECUTE FUNCTION capture_requirement_version()"
    )

    # Seed one 'I' version per existing row so as-of queries never fall off the
    # front edge. Set-based (one INSERT..SELECT) per the migration rules; the
    # trigger is not involved here. recorded_at approximated from created_at.
    op.execute(
        """
        INSERT INTO jurisdiction_requirement_versions
            (requirement_id, jurisdiction_id, op, row_data, recorded_at, change_source)
        SELECT r.id, r.jurisdiction_id, 'I', to_jsonb(r),
               COALESCE(r.created_at, now()), 'backfill'
        FROM jurisdiction_requirements r
        """
    )

    # ── 2. source snapshots (frozen evidence) ────────────────────────────────
    op.create_table(
        "requirement_source_snapshots",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # No FK cascade: evidence must survive a requirement delete too.
        sa.Column("requirement_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_rss_requirement", "requirement_source_snapshots",
        ["requirement_id", "fetched_at"],
    )
    # Same page content stored once per requirement (dedupe on hash).
    op.execute(
        "CREATE UNIQUE INDEX uq_rss_req_hash ON requirement_source_snapshots "
        "(requirement_id, content_hash) WHERE content_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_capture_requirement_version ON jurisdiction_requirements")
    op.execute("DROP FUNCTION IF EXISTS capture_requirement_version()")
    op.drop_table("requirement_source_snapshots")
    op.drop_table("jurisdiction_requirement_versions")
