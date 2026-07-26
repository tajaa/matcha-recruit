"""bootstrap.portal_chat — employee portal, blog, chat, AI chat, scheduler_settings, RSS, pattern recognition (verbatim split of app/database.py lines 3497-3836).
"""


async def create_portal_chat(conn):
        # ===========================================
        # Employee Self-Service Portal Tables
        # ===========================================
        # NOTE: Employee portal tables are now managed via Alembic migrations
        # See: alembic/versions/7c1de748641e_add_employee_portal_tables.py
        # See: alembic/versions/6e4ad940b98b_update_users_role_constraint_for_.py

        # Blog posts table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                author_id UUID REFERENCES users(id) ON DELETE SET NULL,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) NOT NULL UNIQUE,
                content TEXT NOT NULL,
                excerpt TEXT,
                cover_image TEXT,
                status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
                tags JSONB DEFAULT '[]',
                meta_title VARCHAR(255),
                meta_description TEXT,
                published_at TIMESTAMP,
                likes_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_posts_published_at ON blog_posts(published_at)
        """)

        # Add likes_count column if not exists
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'blog_posts' AND column_name = 'likes_count'
                ) THEN
                    ALTER TABLE blog_posts ADD COLUMN likes_count INTEGER DEFAULT 0;
                END IF;
            END $$;
        """)

        # Blog Likes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_likes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                post_id UUID NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                session_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE NULLS NOT DISTINCT (post_id, user_id, session_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_likes_post_id ON blog_likes(post_id)
        """)

        # Blog Comments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_comments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                post_id UUID NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                author_name VARCHAR(255),
                content TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'spam')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_comments_post_id ON blog_comments(post_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_comments_status ON blog_comments(status)
        """)

        # ===========================================
        # Chat System Tables (Standalone Community Chat)
        # ===========================================

        # Chat Users table (completely separate from main users)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                avatar_url VARCHAR(500),
                bio TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_users_email ON chat_users(email)
        """)

        # Chat Rooms table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_rooms (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                icon VARCHAR(10),
                is_default BOOLEAN DEFAULT FALSE,
                created_by UUID REFERENCES chat_users(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_rooms_slug ON chat_rooms(slug)
        """)

        # Chat Room Memberships
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_room_members (
                room_id UUID REFERENCES chat_rooms(id) ON DELETE CASCADE,
                user_id UUID REFERENCES chat_users(id) ON DELETE CASCADE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (room_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_room_members_user ON chat_room_members(user_id)
        """)

        # Chat Messages table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                room_id UUID REFERENCES chat_rooms(id) ON DELETE CASCADE,
                user_id UUID REFERENCES chat_users(id) ON DELETE SET NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                edited_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_user ON chat_messages(user_id)
        """)

        # (Gummfit creator/agency/deal/campaign tables removed — still in DB, just not bootstrapped here)

        # AI Chat tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id),
                user_id UUID NOT NULL REFERENCES users(id),
                title TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_conversations_company_user
            ON ai_conversations(company_id, user_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
            ON ai_messages(conversation_id, created_at)
        """)

        # Add attachments column to ai_messages
        await conn.execute("""
            ALTER TABLE ai_messages
            ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'
        """)
        # Add conversation_type for regulatory Q&A vs general chat
        await conn.execute("""
            ALTER TABLE ai_conversations
            ADD COLUMN IF NOT EXISTS conversation_type VARCHAR(30) DEFAULT 'general'
        """)

        # ===========================================
        # Scheduler Settings Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_settings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_key VARCHAR(100) UNIQUE NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                description TEXT,
                enabled BOOLEAN DEFAULT true,
                max_per_cycle INTEGER DEFAULT 2,
                -- Self-cadence marker for tasks the hourly worker restart would
                -- otherwise re-fire every hour (see scoperg02).
                last_run_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Seed scheduler settings (disabled by default for safety)
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('compliance_checks', 'Compliance Auto-Checks', 'Automated compliance checks for business locations on a recurring schedule.', false, 2),
                ('deadline_escalation', 'Deadline Escalation', 'Re-evaluate deadline severities for upcoming legislation based on proximity to effective dates.', false, 0),
                ('legislation_watch', 'Legislation Watch (RSS)', 'Monitor RSS feeds from state DOL/legislature sites for upcoming legislation.', false, 0),
                ('pattern_recognition', 'Pattern Recognition', 'Detect coordinated legislative changes across jurisdictions.', false, 0),
                ('discipline_expiry', 'Discipline Expiry Sweep', 'Flips active discipline records past expires_at to expired and writes audit rows.', false, 10000),
                ('ir_deadline_alerts', 'IR Deadline & SLA Alerts', 'Nudges owners on overdue corrective actions, stale critical incidents, unclassified OSHA recordables, and the OSHA 8/24hr emergency window.', false, 200)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # ===========================================
        # RSS Feed Sources Table (Phase 4.1)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_feed_sources (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                state VARCHAR(2) NOT NULL,
                feed_url TEXT NOT NULL UNIQUE,
                feed_name VARCHAR(255) NOT NULL,
                feed_type VARCHAR(50) DEFAULT 'dol',
                categories TEXT[],
                is_active BOOLEAN DEFAULT true,
                last_fetched_at TIMESTAMP,
                last_item_hash VARCHAR(64),
                error_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_sources_state ON rss_feed_sources(state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_sources_active ON rss_feed_sources(is_active)
        """)

        # RSS Feed Items table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_feed_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                feed_id UUID NOT NULL REFERENCES rss_feed_sources(id) ON DELETE CASCADE,
                item_hash VARCHAR(64) NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                pub_date TIMESTAMP,
                description TEXT,
                processed BOOLEAN DEFAULT false,
                gemini_triggered BOOLEAN DEFAULT false,
                relevance_score DECIMAL(3,2),
                detected_category VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(feed_id, item_hash)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_items_feed_id ON rss_feed_items(feed_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_items_processed ON rss_feed_items(processed)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_items_relevance ON rss_feed_items(relevance_score)
        """)

        # Seed initial RSS feeds for major states
        await conn.execute("""
            INSERT INTO rss_feed_sources (state, feed_url, feed_name, feed_type, categories)
            VALUES
                ('CA', 'https://www.dir.ca.gov/rss/news.xml', 'CA DIR News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'overtime', 'meal_breaks']),
                ('NY', 'https://dol.ny.gov/rss.xml', 'NY DOL News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'pay_frequency']),
                ('WA', 'https://lni.wa.gov/news/rss.xml', 'WA L&I News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'overtime'])
            ON CONFLICT (feed_url) DO NOTHING
        """)

        # ===========================================
        # Pattern Recognition Tables (Phase 3.3)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS legislative_patterns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pattern_key VARCHAR(100) NOT NULL UNIQUE,
                display_name VARCHAR(255) NOT NULL,
                category VARCHAR(50),
                trigger_month INTEGER,
                trigger_day INTEGER,
                lookback_days INTEGER DEFAULT 30,
                min_jurisdictions INTEGER DEFAULT 3,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Pattern Detections table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pattern_detections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pattern_id UUID REFERENCES legislative_patterns(id) ON DELETE CASCADE,
                detection_year INTEGER NOT NULL,
                jurisdictions_matched JSONB NOT NULL,
                jurisdictions_flagged JSONB,
                detection_date TIMESTAMP DEFAULT NOW(),
                alerts_created INTEGER DEFAULT 0,
                UNIQUE(pattern_id, detection_year)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pattern_detections_year ON pattern_detections(detection_year)
        """)

        # Seed known legislative patterns
        await conn.execute("""
            INSERT INTO legislative_patterns (pattern_key, display_name, category, trigger_month, trigger_day, lookback_days, min_jurisdictions)
            VALUES
                ('jan_1_wage_update', 'January 1st Minimum Wage Update', 'minimum_wage', 1, 1, 60, 3),
                ('july_1_fiscal_year', 'July 1st Fiscal Year Updates', NULL, 7, 1, 30, 2),
                ('jan_1_sick_leave', 'January 1st Sick Leave Update', 'sick_leave', 1, 1, 45, 2)
            ON CONFLICT (pattern_key) DO NOTHING
        """)

