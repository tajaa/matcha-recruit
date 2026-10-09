"""Remove the broker product: drop its tables and the `broker` user role.

Revision ID: brokerdrop01
Revises: benefitoe01
Create Date: 2026-10-09

The broker portal, its API, workers and admin tooling are gone from the code.
This drops what they owned:

- `brokers` and the 27 `broker_*` tables (members, company links, contracts,
  branding, chat, incident shares, external clients, pilot, risk alerts,
  milestones, lite referral tokens, ...).
- the `broker` value from `users_role_check`.
- the two `scheduler_settings` rows (`broker_risk_alerts`, `broker_milestones`) that
  gated the removed Celery tasks, so they stop showing in the admin scheduler list.

Deliberately NOT touched: tenant-owned tables that brokers merely wrote into
(`insurance_quotes`, `company_epl_attestations`, `company_wc_mods`,
`company_wc_class_exposures`, `wc_loss_runs`). `DROP TABLE ... CASCADE` removes
their foreign keys to `brokers` / `broker_external_clients`, but the rows and
the (now dangling, nullable) `broker_id` columns stay. Tenant code still reads
them.

Safety: the upgrade refuses to run while any user still has role='broker', so a
forgotten account fails the migration loudly instead of being locked out by the
new role constraint. Resolve those users first (reassign or delete), then
re-run.

Irreversible: dropped data cannot be restored by `downgrade()`. Take a backup
first (`deploy/backup-prod.sh`).

One `op.execute` per statement (asyncpg prepares each statement) and no `:name`
binds (see tests/alembic/test_single_statement_migrations.py).
"""
from alembic import op

revision = "brokerdrop01"
down_revision = "benefitoe01"
branch_labels = None
depends_on = None

# Children before parents for readability; CASCADE makes the order non-load-bearing.
BROKER_TABLES = (
    "broker_pilot_messages",
    "broker_pilot_documents",
    "broker_pilot_packets",
    "broker_pilot_audit_log",
    "broker_pilot_sessions",
    "broker_company_messages",
    "broker_company_conversation_reads",
    "broker_company_conversations",
    "broker_external_intake_tokens",
    "broker_external_epl_attestations",
    "broker_external_property",
    "broker_external_wc",
    "broker_external_clients",
    "broker_risk_alerts",
    "broker_milestones",
    "broker_outreach_cache",
    "broker_submission_notes",
    "broker_loss_premiums",
    "broker_incident_shares",
    "broker_lite_referral_tokens",
    "broker_client_setups",
    "broker_company_transitions",
    "broker_company_links",
    "broker_contracts",
    "broker_branding_configs",
    "broker_terms_acceptances",
    "broker_members",
    "brokers",
)

ROLES_AFTER = (
    "admin", "client", "candidate", "employee", "creator", "agency", "gumfit_admin", "individual",
)


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE role = 'broker') THEN
                RAISE EXCEPTION 'users with role=broker still exist - reassign or delete them before removing the broker product';
            END IF;
        END
        $$
        """
    )
    op.execute("DELETE FROM scheduler_settings WHERE task_key IN ('broker_risk_alerts', 'broker_milestones')")
    for table in BROKER_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    roles = ", ".join(f"'{r}'" for r in ROLES_AFTER)
    op.execute(f"ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ({roles}))")


def downgrade():
    raise RuntimeError(
        "brokerdrop01 is irreversible: the broker tables and their data were dropped. "
        "Restore from a backup taken before this migration."
    )
