"""Seed the vertical-coverage sweep scheduler row (DISABLED).

The sweep (`workers/tasks/vertical_coverage_sweep.py`) reclaims wedged
`in_progress` ledger cells, drains calls the per-build cap deferred, and fills
verticals for tenants who onboarded before their industry was scoped.

Seeded **disabled**, like every other research-making scheduler row: the task
makes LIVE GEMINI CALLS, and the hourly worker restart re-fires @worker_ready.
Enable it deliberately from /admin (Schedulers) once you want the spend.

`last_run_at` is added by scoperg02 and is what the task's atomic interval claim
keys on — it is required for this task to rate-limit itself, so the ADD COLUMN is
repeated defensively here (IF NOT EXISTS) rather than assumed.

Revision ID: vertcov02
Revises: vertcov01
Create Date: 2026-07-14
"""
from alembic import op

revision = "vertcov02"
down_revision = "vertcov01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP"
    )
    conn.exec_driver_sql(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'vertical_coverage_sweep',
            'Vertical Coverage Sweep',
            'Reclaims stale in-progress vertical-research cells, drains deferred '
            'research calls, and fills industry-specific compliance for tenants '
            'whose vertical was never scoped. Makes live Gemini calls; rate-limited '
            'to one sweep per day. Default off.',
            false,
            12
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "DELETE FROM scheduler_settings WHERE task_key = 'vertical_coverage_sweep'"
    )
