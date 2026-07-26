"""bootstrap.seeds_platform — chat-room + bootstrap-admin seeds, platform_settings, risk snapshots (verbatim split of app/database.py lines 5082-5184).
"""
import json


async def create_seeds_platform(conn):
        # Create default chat rooms if none exist
        room_exists = await conn.fetchval("SELECT COUNT(*) FROM chat_rooms")
        if room_exists == 0:
            await conn.execute("""
                INSERT INTO chat_rooms (name, slug, description, icon, is_default) VALUES
                    ('General', 'general', 'General discussion and introductions', '💬', TRUE),
                    ('Job Hunting', 'job-hunting', 'Share tips and experiences about the job search', '🔍', TRUE),
                    ('Interview Prep', 'interview-prep', 'Practice and prepare for interviews together', '🎯', TRUE),
                    ('Career Advice', 'career-advice', 'Get and give career guidance', '📈', TRUE),
                    ('Off Topic', 'off-topic', 'Anything goes (within reason)', '🎲', TRUE)
            """)
            print("[DB] Created default chat rooms")

        # Create default admin if no admins exist
        admin_exists = await conn.fetchval("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if admin_exists == 0:
            import os
            from app.core.services.auth import hash_password
            default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme123")
            user_row = await conn.fetchrow(
                """
                    INSERT INTO users (email, password_hash, role)
                    VALUES ('admin@matcha.local', $1, 'admin')
                    RETURNING id
                """,
                hash_password(default_password)
            )
            await conn.execute(
                "INSERT INTO admins (user_id, name) VALUES ($1, 'System Admin')",
                user_row["id"]
            )
            print("[DB] Created default admin user (admin@matcha.local)")

        # Platform settings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                key VARCHAR(100) PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value)
            VALUES ('visible_features', $1::jsonb)
            ON CONFLICT (key) DO NOTHING
            """,
            json.dumps(["offer_letters","client_management","blog","policies","handbooks","er_copilot","onboarding","employees"])
        )
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value)
            VALUES ('risk_assessment_weights', $1::jsonb)
            ON CONFLICT (key) DO NOTHING
            """,
            json.dumps({"compliance": 0.30, "incidents": 0.25, "er_cases": 0.25, "workforce": 0.15, "legislative": 0.05})
        )
        await conn.execute(
            """
            INSERT INTO platform_settings (key, value)
            VALUES ('landing_media', $1::jsonb)
            ON CONFLICT (key) DO NOTHING
            """,
            json.dumps({
                "hero_video_url": None,
                "hero_poster_url": None,
                "sizzle_videos": [],
                "customer_logos": [],
                "testimonials": [],
            })
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_assessment_snapshots (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                overall_score INT NOT NULL,
                overall_band TEXT NOT NULL,
                dimensions JSONB NOT NULL,
                report TEXT,
                recommendations JSONB,
                weights JSONB NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                computed_by UUID REFERENCES users(id),
                UNIQUE (company_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_assessment_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                overall_score INT NOT NULL,
                overall_band TEXT NOT NULL,
                dimensions JSONB NOT NULL,
                weights JSONB NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                source VARCHAR(20) NOT NULL DEFAULT 'scheduled'
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_risk_history_company_date
            ON risk_assessment_history(company_id, computed_at DESC)
        """)

