"""add_xp_features

Revision ID: 9d4e8f7a6b5c
Revises: f66269e69a70
Create Date: 2026-01-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9d4e8f7a6b5c'
down_revision: Union[str, Sequence[str], None] = 'f66269e69a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add XP features: Vibe Checks, eNPS Surveys, and Performance Reviews."""

    # ================================
    # Vibe Check Config
    # ================================
    op.create_table(
        'vibe_check_configs',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('frequency', sa.String(20), nullable=False, server_default='weekly'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_anonymous', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('questions', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['org_id'], ['companies.id'], ondelete='CASCADE'),
        sa.CheckConstraint("frequency IN ('daily', 'weekly', 'biweekly', 'monthly')", name='check_vibe_frequency'),
        sa.UniqueConstraint('org_id', name='unique_org_vibe_config')
    )
    op.create_index('idx_vibe_configs_org', 'vibe_check_configs', ['org_id'])

    # ================================
    # Vibe Check Responses
    # ================================
    op.create_table(
        'vibe_check_responses',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=True),
        sa.Column('mood_rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text()),
        sa.Column('custom_responses', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('sentiment_analysis', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['org_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.CheckConstraint('mood_rating >= 1 AND mood_rating <= 5', name='check_mood_rating')
    )
    op.create_index('idx_vibe_responses_org_created', 'vibe_check_responses', ['org_id', 'created_at'])
    op.create_index('idx_vibe_responses_employee', 'vibe_check_responses', ['employee_id'])

    # ================================
    # eNPS Surveys
    # ================================
    op.create_table(
        'enps_surveys',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('is_anonymous', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('custom_question', sa.Text()),
        sa.Column('created_by', sa.UUID()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['org_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('draft', 'active', 'closed', 'archived')", name='check_enps_status'),
        sa.CheckConstraint('end_date >= start_date', name='check_enps_dates')
    )
    op.create_index('idx_enps_surveys_org_status', 'enps_surveys', ['org_id', 'status'])

    # ================================
    # eNPS Responses
    # ================================
    op.create_table(
        'enps_responses',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('survey_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID()),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text()),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('sentiment_analysis', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['survey_id'], ['enps_surveys.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.CheckConstraint('score >= 0 AND score <= 10', name='check_enps_score'),
        sa.CheckConstraint("category IN ('detractor', 'passive', 'promoter')", name='check_enps_category'),
        sa.UniqueConstraint('survey_id', 'employee_id', name='unique_survey_employee')
    )
    op.create_index('idx_enps_responses_survey', 'enps_responses', ['survey_id'])

    # ================================
    # Review Templates
    # ================================
    op.create_table(
        'review_templates',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('categories', postgresql.JSONB(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['org_id'], ['companies.id'], ondelete='CASCADE')
    )
    op.create_index('idx_review_templates_org', 'review_templates', ['org_id'])

    # ================================
    # Review Cycles
    # ================================
    op.create_table(
        'review_cycles',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('template_id', sa.UUID()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['org_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['review_templates.id'], ondelete='SET NULL'),
        sa.CheckConstraint("status IN ('draft', 'active', 'completed', 'archived')", name='check_review_cycle_status'),
        sa.CheckConstraint('end_date >= start_date', name='check_review_cycle_dates')
    )
    op.create_index('idx_review_cycles_org_status', 'review_cycles', ['org_id', 'status'])

    # ================================
    # Performance Reviews
    # ================================
    op.create_table(
        'performance_reviews',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('cycle_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('manager_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('self_ratings', postgresql.JSONB()),
        sa.Column('self_comments', sa.Text()),
        sa.Column('self_submitted_at', sa.TIMESTAMP()),
        sa.Column('manager_ratings', postgresql.JSONB()),
        sa.Column('manager_comments', sa.Text()),
        sa.Column('manager_overall_rating', sa.Numeric(3, 2)),
        sa.Column('manager_submitted_at', sa.TIMESTAMP()),
        sa.Column('ai_analysis', postgresql.JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.TIMESTAMP()),
        sa.ForeignKeyConstraint(['cycle_id'], ['review_cycles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manager_id'], ['employees.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "status IN ('pending', 'self_submitted', 'manager_submitted', 'completed', 'skipped')",
            name='check_performance_review_status'
        ),
        sa.UniqueConstraint('cycle_id', 'employee_id', name='unique_cycle_employee')
    )
    op.create_index('idx_reviews_cycle', 'performance_reviews', ['cycle_id'])
    op.create_index('idx_reviews_employee', 'performance_reviews', ['employee_id'])
    op.create_index('idx_reviews_manager', 'performance_reviews', ['manager_id'])


def downgrade() -> None:
    """Remove XP features."""
    op.drop_table('performance_reviews')
    op.drop_table('review_cycles')
    op.drop_table('review_templates')
    op.drop_table('enps_responses')
    op.drop_table('enps_surveys')
    op.drop_table('vibe_check_responses')
    op.drop_table('vibe_check_configs')
