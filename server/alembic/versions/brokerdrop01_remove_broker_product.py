"""Remove the broker product: drop its tables and the `broker` user role.

Revision ID: brokerdrop01
Revises: benefitoe01
Create Date: 2026-10-09

The broker portal, its API, workers and admin tooling are gone from the code.
This drops what they owned:

- `brokers` and the 27 `broker_*` tables (members, company links, contracts,
  branding, chat, incident shares, external clients, pilot, risk alerts,
  milestones, lite referral tokens, ...).
- the `broker` value from `users_role_check`, and the users still on that role.
- the two `scheduler_settings` rows (`broker_risk_alerts`, `broker_milestones`) that
  gated the removed Celery tasks, so they stop showing in the admin scheduler list.

Deliberately NOT touched: tenant-owned tables that brokers merely wrote into
(`insurance_quotes`, `company_epl_attestations`, `company_wc_mods`,
`company_wc_class_exposures`, `wc_loss_runs`). `DROP TABLE ... CASCADE` removes
their foreign keys to `brokers` / `broker_external_clients`, but the rows and
the (now dangling, nullable) `broker_id` columns stay. Tenant code still reads
them.

Broker logins: every remaining `role='broker'` user is deleted, after the
drops. They were all test and demo accounts (10 on dev, which is a clone of
prod), and the new role check would reject the rows anyway. An earlier draft
refused to run while any existed, which stopped the first dev upgrade; deleting
them by hand first doesn't work either, because `broker_client_setups` and
`broker_company_links` reference users with no delete rule until they are
dropped. Every other reference to a user is ON DELETE SET NULL or CASCADE: rows
a broker wrote into tenant tables keep their data with `created_by` /
`updated_by` cleared, error reports lose the user link, and the account's own
notifications go. A reference added later without a rule fails the delete, and
with it the whole migration, in `migrate-prod.sh`'s rehearsal.

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
    op.execute("DELETE FROM scheduler_settings WHERE task_key IN ('broker_risk_alerts', 'broker_milestones')")
    for table in BROKER_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    # After the drops: two broker tables referenced users with no delete rule.
    op.execute("DELETE FROM users WHERE role = 'broker'")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    roles = ", ".join(f"'{r}'" for r in ROLES_AFTER)
    op.execute(f"ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ({roles}))")


def downgrade():
    raise RuntimeError(
        "brokerdrop01 is irreversible: the broker tables and their data were dropped. "
        "Restore from a backup taken before this migration."
    )
