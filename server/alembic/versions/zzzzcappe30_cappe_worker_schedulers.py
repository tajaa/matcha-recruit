"""Seed Cappe reconciliation scheduler rows."""

from alembic import op

revision = "zzzzcappe30"
down_revision = "zzzzcappe29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES
        ('cappe_collab_auto_approve', 'Cappe Collab Auto-Approve', 'Reconcile overdue collab deliverables.', false, 50),
        ('cappe_domain_finalize', 'Cappe Domain Finalize', 'Reconcile domains stuck registering.', false, 20)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM scheduler_settings WHERE task_key IN ('cappe_collab_auto_approve', 'cappe_domain_finalize')"
    )
