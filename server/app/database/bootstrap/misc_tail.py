"""bootstrap.misc_tail — error_logs, channels (+backfill), stray mw_risk_flags/mw_notifications, newsletter (verbatim split of app/database.py lines 6195-6549).
"""


async def create_misc_tail(conn):
        # ── Error Logs ───────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                method VARCHAR(10) NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                error_type VARCHAR(255) NOT NULL,
                error_message TEXT NOT NULL,
                traceback TEXT,
                user_id UUID,
                user_role VARCHAR(20),
                company_id UUID,
                request_body TEXT,
                query_params TEXT
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_error_logs_timestamp
            ON error_logs(timestamp DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_error_logs_path
            ON error_logs(path)
        """)

        # ── Channels (group chat) ────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id),
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(120) NOT NULL,
                description TEXT,
                created_by UUID NOT NULL REFERENCES users(id),
                is_archived BOOLEAN DEFAULT false,
                visibility VARCHAR(20) DEFAULT 'public',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(company_id, slug)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channels_company
            ON channels(company_id, is_archived, updated_at DESC)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) DEFAULT 'member',
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                last_read_at TIMESTAMPTZ,
                is_muted BOOLEAN DEFAULT false,
                UNIQUE(channel_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_members_user
            ON channel_members(user_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                sender_id UUID REFERENCES users(id),
                content TEXT NOT NULL,
                attachments JSONB DEFAULT '[]'::jsonb,
                reply_to_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                edited_at TIMESTAMPTZ,
                message_type VARCHAR(20) NOT NULL DEFAULT 'user'
            )
        """)
        # sender_id is nullable (EMS system/Huume messages have no human
        # sender) — see alembic/versions/ems01_event_management.py. init_db()
        # early-returns before this module runs whenever the `users` table
        # already exists (bootstrap/__init__.py), so this CREATE TABLE only
        # ever runs on a genuinely fresh DB — an existing DB's shape is
        # migrated by ems01, not by an ALTER here.
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_messages_channel
            ON channel_messages(channel_id, created_at DESC)
        """)
        # Add attachments column if missing (for existing tables)
        await conn.execute("""
            ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'::jsonb
        """)
        # Reply threading
        await conn.execute("""
            ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS reply_to_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL
        """)
        # Server-side idempotency on (sender_id, client_message_id). Partial
        # unique index lets legacy rows stay NULL without colliding. See
        # alembic/versions/zzzz_b03_channel_messages_cmid.py for the prod
        # migration; this mirrors the schema for fresh init_db bootstraps.
        await conn.execute("""
            ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS client_message_id UUID
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uniq_channel_messages_sender_cmid
            ON channel_messages (sender_id, client_message_id)
            WHERE client_message_id IS NOT NULL
        """)
        # Reactions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_reactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                message_id UUID NOT NULL REFERENCES channel_messages(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                emoji TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (message_id, user_id, emoji)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channel_reactions_message
            ON channel_reactions(message_id)
        """)
        # Channel permissions columns (for existing tables)
        await conn.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'public'")
        await conn.execute("ALTER TABLE channel_members ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'member'")
        # Category for channel browse/filter UX (matches Alembic migration zzzz8g9h0i1j2).
        await conn.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS category VARCHAR(50)")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channels_category
                ON channels(company_id, category)
                WHERE category IS NOT NULL
        """)
        # Store-location scope for Ops channel dispatch (matches Alembic migration oploc01).
        await conn.execute("ALTER TABLE channels ADD COLUMN IF NOT EXISTS location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_channels_location
                ON channels(location_id) WHERE location_id IS NOT NULL
        """)
        # Backfill: set channel creators as owners
        await conn.execute("""
            UPDATE channel_members cm SET role = 'owner'
            FROM channels ch
            WHERE cm.channel_id = ch.id AND cm.user_id = ch.created_by AND cm.role = 'member'
        """)

        # Risk flags (pre-computed by background analysis)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_risk_flags (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                priority INT NOT NULL DEFAULT 0,
                category TEXT NOT NULL,
                location_subject TEXT NOT NULL,
                description TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'medium',
                source_type TEXT NOT NULL DEFAULT 'pattern',
                source_id TEXT,
                link TEXT,
                group_label TEXT DEFAULT 'Locations',
                is_ai_generated BOOLEAN DEFAULT FALSE,
                analyzed_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_risk_flags_company
            ON mw_risk_flags(company_id, priority)
        """)

        # Matcha Work notifications
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_notifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                link TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_notifications_user
            ON mw_notifications(user_id, is_read, created_at DESC)
        """)

        # Newsletter system
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255),
                source VARCHAR(50) DEFAULT 'website',
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
                status VARCHAR(20) DEFAULT 'active',
                subscribed_at TIMESTAMPTZ DEFAULT NOW(),
                unsubscribed_at TIMESTAMPTZ,
                metadata JSONB DEFAULT '{}'::jsonb
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_newsletter_subscribers_status
            ON newsletter_subscribers(status, subscribed_at DESC)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_suppressions (
                email VARCHAR(255) PRIMARY KEY,
                reason VARCHAR(50) DEFAULT 'admin_delete',
                suppressed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                suppressed_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletters (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(500) NOT NULL,
                subject VARCHAR(500) NOT NULL,
                content_html TEXT,
                curated_article_ids UUID[] DEFAULT '{}',
                status VARCHAR(20) DEFAULT 'draft',
                scheduled_at TIMESTAMPTZ,
                sent_at TIMESTAMPTZ,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_sends (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                newsletter_id UUID NOT NULL REFERENCES newsletters(id) ON DELETE CASCADE,
                subscriber_id UUID NOT NULL REFERENCES newsletter_subscribers(id) ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'pending',
                sent_at TIMESTAMPTZ,
                opened_at TIMESTAMPTZ,
                clicked_at TIMESTAMPTZ,
                UNIQUE(newsletter_id, subscriber_id)
            )
        """)

        # P0 — newsletter compliance + ops columns added incrementally so
        # fresh setups + already-deployed DBs converge on the same shape.
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'newsletter_subscribers' AND column_name = 'soft_bounce_count'
                ) THEN
                    ALTER TABLE newsletter_subscribers
                        ADD COLUMN soft_bounce_count INT NOT NULL DEFAULT 0;
                END IF;
            END $$;
        """)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'newsletters' AND column_name = 'preheader'
                ) THEN
                    ALTER TABLE newsletters ADD COLUMN preheader VARCHAR(255);
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'newsletters' AND column_name = 'scheduled_send_started_at'
                ) THEN
                    ALTER TABLE newsletters ADD COLUMN scheduled_send_started_at TIMESTAMPTZ;
                END IF;
                -- Block-builder design (migration nldesign01)
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'newsletters' AND column_name = 'design_json'
                ) THEN
                    ALTER TABLE newsletters ADD COLUMN design_json JSONB;
                END IF;
            END $$;
        """)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'newsletter_sends' AND column_name = 'bounced_at'
                ) THEN
                    ALTER TABLE newsletter_sends ADD COLUMN bounced_at TIMESTAMPTZ;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'newsletter_sends' AND column_name = 'bounce_kind'
                ) THEN
                    ALTER TABLE newsletter_sends ADD COLUMN bounce_kind VARCHAR(20);
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_newsletters_scheduled
                ON newsletters(status, scheduled_at)
                WHERE status = 'scheduled' AND scheduled_at IS NOT NULL
        """)

        # P1 — tags + per-subscriber tag attachments.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_tags (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug VARCHAR(64) NOT NULL UNIQUE,
                label VARCHAR(120) NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_subscriber_tags (
                subscriber_id UUID NOT NULL REFERENCES newsletter_subscribers(id) ON DELETE CASCADE,
                tag_id UUID NOT NULL REFERENCES newsletter_tags(id) ON DELETE CASCADE,
                attached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (subscriber_id, tag_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_newsletter_subscriber_tags_tag
                ON newsletter_subscriber_tags(tag_id)
        """)
        await conn.execute("""
            INSERT INTO newsletter_tags (slug, label, description) VALUES
                ('tier-free', 'Free tier', 'Subscribers who signed up while logged in as a resources_free customer'),
                ('tier-lite', 'Matcha Lite', 'Subscribers from Matcha Lite tenants'),
                ('tier-platform', 'Platform', 'Subscribers from bespoke / platform tenants'),
                ('tier-personal', 'Matcha Work Personal', 'Personal-workspace individuals')
            ON CONFLICT (slug) DO NOTHING
        """)

        # P2 — saved newsletter templates.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                content_html TEXT,
                preheader VARCHAR(255),
                design_json JSONB,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "ALTER TABLE newsletter_templates ADD COLUMN IF NOT EXISTS design_json JSONB"
        )

        # Newsletter idea scratchpad (migration nlideas01)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_ideas (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(255) NOT NULL,
                notes TEXT,
                media_url TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'idea',
                newsletter_id UUID REFERENCES newsletters(id) ON DELETE SET NULL,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
