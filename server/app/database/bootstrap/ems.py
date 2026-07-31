"""bootstrap.ems — ems_events + ems_event_audit_log + company_event_protocols
(mirrors alembic/versions/ems01_event_management.py + ems02_urgency_and_protocols.py).

clarify_message_id / clarification_rounds / uniq_ems_events_clarify back
conversational clarification — see that migration's docstring for the full
explanation of the atomic-claim index.
"""


async def create_ems(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS ems_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            reporter_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            title VARCHAR(300),
            category VARCHAR(50) NOT NULL DEFAULT 'uncategorized',
            severity_hint VARCHAR(20),
            doc JSONB NOT NULL DEFAULT '{}'::jsonb,
            narrative TEXT NOT NULL,
            incident_recommendation BOOLEAN NOT NULL DEFAULT false,
            incident_reasoning TEXT,
            suggested_incident_type VARCHAR(50),
            suggested_severity VARCHAR(20),
            urgency VARCHAR(10) CHECK (urgency IN ('osha', 'severe')),
            protocol_qualifies BOOLEAN,
            protocol_reasoning TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'logged'
                CHECK (status IN ('logged', 'promoted', 'dismissed')),
            incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
            promoted_by UUID REFERENCES users(id),
            promoted_at TIMESTAMPTZ,
            dismissed_by UUID REFERENCES users(id),
            dismissed_at TIMESTAMPTZ,
            token_usage JSONB,
            clarify_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            clarification_rounds SMALLINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ems_events_company
        ON ems_events(company_id, created_at DESC)
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_events_message
        ON ems_events(message_id) WHERE message_id IS NOT NULL
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_events_clarify
        ON ems_events(clarify_message_id) WHERE clarify_message_id IS NOT NULL
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS ems_event_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL REFERENCES ems_events(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id),
            action VARCHAR(50) NOT NULL,
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ems_event_audit_log_event
        ON ems_event_audit_log(event_id, created_at DESC)
    """)

    await conn.execute("""
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
