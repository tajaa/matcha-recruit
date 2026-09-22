"""Add Schedule Autopilot profile and generation modes.

Revision ID: autopilot02
Revises: autopilot01
"""

from alembic import op


revision = "autopilot02"
down_revision = "autopilot01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
          ADD COLUMN IF NOT EXISTS weather_sensitivity VARCHAR(16) NOT NULL DEFAULT 'none',
          ADD COLUMN IF NOT EXISTS min_floor_staff SMALLINT NOT NULL DEFAULT 1,
          ADD COLUMN IF NOT EXISTS target_labor_pct NUMERIC(5,2),
          ADD COLUMN IF NOT EXISTS autopilot_shift_min_minutes SMALLINT,
          ADD COLUMN IF NOT EXISTS autopilot_shift_max_minutes SMALLINT
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE schedule_location_profiles ADD CONSTRAINT schedule_location_profiles_weather_check
            CHECK (weather_sensitivity IN ('none','rain_hurts','rain_helps'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
          ALTER TABLE schedule_location_profiles ADD CONSTRAINT schedule_location_profiles_floor_check
            CHECK (min_floor_staff BETWEEN 0 AND 20);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
          ALTER TABLE schedule_location_profiles ADD CONSTRAINT schedule_location_profiles_labor_pct_check
            CHECK (target_labor_pct IS NULL OR target_labor_pct BETWEEN 1 AND 90);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
          ALTER TABLE schedule_location_profiles ADD CONSTRAINT schedule_location_profiles_autopilot_shift_check
            CHECK (
              (autopilot_shift_min_minutes IS NULL OR autopilot_shift_min_minutes BETWEEN 120 AND 720)
              AND (autopilot_shift_max_minutes IS NULL OR autopilot_shift_max_minutes BETWEEN 120 AND 720)
              AND (autopilot_shift_min_minutes IS NULL OR autopilot_shift_max_minutes IS NULL
                   OR autopilot_shift_min_minutes <= autopilot_shift_max_minutes)
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
        """
    )
    op.execute("ALTER TABLE schedule_generation_runs DROP CONSTRAINT IF EXISTS schedule_generation_runs_source_check")
    op.execute("ALTER TABLE schedule_generation_runs DROP CONSTRAINT IF EXISTS schedule_generation_runs_source_mode_check")
    op.execute(
        "ALTER TABLE schedule_generation_runs ADD CONSTRAINT schedule_generation_runs_source_check "
        "CHECK (source_mode IN ('existing','template','autopilot'))"
    )
    op.execute(
        "ALTER TABLE schedule_automation_rules "
        "ADD COLUMN IF NOT EXISTS mode VARCHAR(16) NOT NULL DEFAULT 'template'"
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE schedule_automation_rules ADD CONSTRAINT schedule_automation_rules_mode_check
            CHECK (mode IN ('template','autopilot'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN
          ALTER TABLE schedule_automation_rules ADD CONSTRAINT schedule_automation_rules_template_check
            -- Deleted templates leave a disabled rule with a NULL template id.
            CHECK (mode <> 'template' OR week_template_id IS NOT NULL OR enabled=false);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schedule_automation_rules DROP CONSTRAINT IF EXISTS schedule_automation_rules_template_check")
    op.execute("ALTER TABLE schedule_automation_rules DROP CONSTRAINT IF EXISTS schedule_automation_rules_mode_check")
    op.execute("UPDATE schedule_automation_rules SET enabled=false, next_run_at=NULL WHERE mode='autopilot'")
    op.execute("ALTER TABLE schedule_automation_rules DROP COLUMN IF EXISTS mode")
    op.execute("ALTER TABLE schedule_generation_runs DROP CONSTRAINT IF EXISTS schedule_generation_runs_source_check")
    op.execute(
        "ALTER TABLE schedule_generation_runs ADD CONSTRAINT schedule_generation_runs_source_check "
        "CHECK (source_mode IN ('existing','template')) NOT VALID"
    )
    for constraint in (
        "schedule_location_profiles_autopilot_shift_check",
        "schedule_location_profiles_labor_pct_check",
        "schedule_location_profiles_floor_check",
        "schedule_location_profiles_weather_check",
    ):
        op.execute(f"ALTER TABLE schedule_location_profiles DROP CONSTRAINT IF EXISTS {constraint}")
    op.execute(
        """
        ALTER TABLE schedule_location_profiles
          DROP COLUMN IF EXISTS autopilot_shift_max_minutes,
          DROP COLUMN IF EXISTS autopilot_shift_min_minutes,
          DROP COLUMN IF EXISTS target_labor_pct,
          DROP COLUMN IF EXISTS min_floor_staff,
          DROP COLUMN IF EXISTS weather_sensitivity
        """
    )
