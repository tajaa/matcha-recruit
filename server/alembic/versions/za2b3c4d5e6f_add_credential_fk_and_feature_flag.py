"""add credential_requirement_id FK to onboarding tasks + credential_templates feature flag

Revision ID: za2b3c4d5e6f
Revises: z1a2b3c4d5e6
Create Date: 2026-03-26
"""

from alembic import op


revision = "za2b3c4d5e6f"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Link onboarding tasks to credential requirements
    op.execute("""
        ALTER TABLE employee_onboarding_tasks
            ADD COLUMN IF NOT EXISTS credential_requirement_id UUID
            REFERENCES employee_credential_requirements(id) ON DELETE SET NULL
    """)

    # Enable credential_templates feature flag (off by default)
    op.execute("""
        UPDATE platform_settings
        SET value = jsonb_set(
            COALESCE(value, '{}'::jsonb),
            '{credential_templates}',
            'false'::jsonb
        )
        WHERE key = 'default_features'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE employee_onboarding_tasks
            DROP COLUMN IF EXISTS credential_requirement_id
    """)
