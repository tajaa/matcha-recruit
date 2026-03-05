"""expand RLS coverage with admin bypass and self-lookup

Revision ID: f1d6d19f0f3e
Revises: z7a8b9c0d1e
Create Date: 2026-03-05

Recreates the original 8-table policies from e72bfad5eca9 with admin
bypass, adds RLS to ~50 more tenant-keyed tables, and creates a
self-lookup policy on ``employees`` so auth resolution works before
the tenant context is known.
"""

from alembic import op


revision = "f1d6d19f0f3e"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


# ── Tables from the original RLS migration (e72bfad5eca9) ────────────
ORIGINAL_COMPANY_ID_TABLES = [
    "ir_incidents",
    "offer_letters",
    "positions",
    "policies",
    "er_cases",
]
ORIGINAL_ORG_ID_TABLES = [
    "employees",
    "onboarding_tasks",
    "enps_surveys",
]

# ── New tables to add ────────────────────────────────────────────────
# Only tables that have a direct company_id / org_id column.
# Child tables (e.g. er_case_documents → er_cases, handbook_sections →
# handbook_versions → handbooks) inherit protection via parent-table RLS
# and application-level JOINs.
NEW_COMPANY_ID_TABLES = [
    "business_locations",
    "compliance_check_log",
    "compliance_alerts",
    "upcoming_legislation",
    "handbooks",
    "handbook_wizard_drafts",
    "handbook_freshness_checks",
    "employee_onboarding_drafts",
    "integration_connections",
    "onboarding_runs",
    "external_identities",
    "provisioning_audit_logs",
    "company_handbook_profiles",
    "mw_threads",
    "mw_elements",
    "mw_token_usage_events",
    "mw_review_requests",
    "mw_credit_balances",
    "mw_credit_transactions",
    "mw_stripe_sessions",
    "mw_subscriptions",
    "poster_orders",
    "broker_client_setups",
    "broker_company_links",
    "broker_company_transitions",
]

NEW_ORG_ID_TABLES = [
    "employee_documents",
    "employee_invitations",
    "leave_requests",
    "leave_deadlines",
    "offboarding_cases",
    "employee_career_profiles",
    "internal_opportunities",
    "onboarding_notification_settings",
    "vibe_check_configs",
    "vibe_check_responses",
    "review_templates",
    "review_cycles",
    "accommodation_cases",
]


def _using_clause(tenant_col: str) -> str:
    return (
        f"{tenant_col}::text = current_setting('app.current_tenant_id', true) "
        "OR current_setting('app.is_admin', true) = 'true'"
    )


def _enable_rls(table: str, tenant_col: str) -> None:
    """Enable RLS + create policy. Skips if table doesn't exist."""
    using = _using_clause(tenant_col)
    op.execute(f"ALTER TABLE IF EXISTS {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE IF EXISTS {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ BEGIN
            CREATE POLICY tenant_isolation ON {table}
                USING ({using});
        EXCEPTION WHEN duplicate_object THEN NULL;
                  WHEN undefined_table THEN NULL;
        END $$
    """)


def _recreate_policy(table: str, tenant_col: str) -> None:
    """Drop the old policy (no admin bypass) and create an updated one."""
    using = _using_clause(tenant_col)
    op.execute(f"""
        DO $$ BEGIN
            DROP POLICY tenant_isolation ON {table};
        EXCEPTION WHEN undefined_object THEN NULL;
        END $$
    """)
    op.execute(f"""
        DO $$ BEGIN
            CREATE POLICY tenant_isolation ON {table}
                USING ({using});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"DROP POLICY IF EXISTS auth_self_lookup ON {table}")
    op.execute(f"ALTER TABLE IF EXISTS {table} DISABLE ROW LEVEL SECURITY")


def upgrade():
    # 1. Recreate existing policies with admin bypass
    for table in ORIGINAL_COMPANY_ID_TABLES:
        _recreate_policy(table, "company_id")
    for table in ORIGINAL_ORG_ID_TABLES:
        _recreate_policy(table, "org_id")

    # 2. Enable RLS on new tables
    for table in NEW_COMPANY_ID_TABLES:
        _enable_rls(table, "company_id")
    for table in NEW_ORG_ID_TABLES:
        _enable_rls(table, "org_id")

    # 3. Self-lookup policy on employees so auth resolution can query
    #    the employee record by user_id before the tenant context is set.
    op.execute("""
        DO $$ BEGIN
            CREATE POLICY auth_self_lookup ON employees
                USING (user_id::text = current_setting('app.current_user_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)


def downgrade():
    op.execute("DROP POLICY IF EXISTS auth_self_lookup ON employees")

    for table in NEW_COMPANY_ID_TABLES + NEW_ORG_ID_TABLES:
        _disable_rls(table)

    # Restore original policies without admin bypass
    for table in ORIGINAL_COMPANY_ID_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation ON {table}
                    USING (company_id::text = current_setting('app.current_tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)
    for table in ORIGINAL_ORG_ID_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation ON {table}
                    USING (org_id::text = current_setting('app.current_tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)
