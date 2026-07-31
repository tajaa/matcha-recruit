"""EMS urgency (OSHA/severe) + company event protocols.

ems_events.urgency: 'osha' (deterministic 29 CFR 1904.39 keyword hit —
services/ir/ir_incident_parsing._detect_osha_reportable_keywords) or
'severe' (model-judged), NULL otherwise. protocol_qualifies/-_reasoning:
the classify call's judgment of the event against the company's own
protocol file (NULL = never assessed, distinct from False).

company_event_protocols: one row per company — structured notify contacts
(notify_emails / notify_all_admins, read deterministically by
services/ems/urgent_notify.py) + free-text sections Gemini grounds on
(services/ems/protocols.protocol_prompt_excerpt).

Follow-up (NOT this migration): add company_event_protocols to the RLS
coverage pattern in f1d6d19f0f3e_expand_rls_coverage.py.

Revision ID: ems02
Revises: schedchat01
"""

from alembic import op

revision = "ems02"
down_revision = "schedchat01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS urgency VARCHAR(10) "
        "CHECK (urgency IN ('osha', 'severe'))"
    )
    op.execute("ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS protocol_qualifies BOOLEAN")
    op.execute("ALTER TABLE ems_events ADD COLUMN IF NOT EXISTS protocol_reasoning TEXT")
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_event_protocols (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            notify_emails TEXT[] NOT NULL DEFAULT '{}',
            notify_all_admins BOOLEAN NOT NULL DEFAULT true,
            incident_definition TEXT NOT NULL DEFAULT '',
            culture_notes TEXT NOT NULL DEFAULT '',
            corrective_actions TEXT NOT NULL DEFAULT '',
            updated_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS company_event_protocols")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS protocol_reasoning")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS protocol_qualifies")
    op.execute("ALTER TABLE ems_events DROP COLUMN IF EXISTS urgency")
