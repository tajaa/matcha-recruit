from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def init_pool(database_url: str):
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
    return _pool


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool first.")
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection():
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def init_db():
    async with get_connection() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_businesses (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_business_settings (
                business_id UUID PRIMARY KEY REFERENCES local_businesses(id) ON DELETE CASCADE,
                timezone VARCHAR(100) NOT NULL DEFAULT 'America/Los_Angeles',
                currency VARCHAR(10) NOT NULL DEFAULT 'USD',
                sender_name VARCHAR(255),
                sender_email VARCHAR(255),
                loyalty_message TEXT,
                vip_label VARCHAR(120) NOT NULL DEFAULT 'Local VIP',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_business_users (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL REFERENCES local_businesses(id) ON DELETE CASCADE,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) NOT NULL CHECK (role IN ('owner', 'admin', 'staff')),
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                last_login_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_business_media (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL REFERENCES local_businesses(id) ON DELETE CASCADE,
                uploaded_by UUID NOT NULL REFERENCES local_business_users(id) ON DELETE RESTRICT,
                media_type VARCHAR(20) NOT NULL CHECK (media_type IN ('image', 'video')),
                storage_path TEXT NOT NULL,
                media_url TEXT NOT NULL,
                mime_type VARCHAR(120) NOT NULL,
                original_filename VARCHAR(255),
                size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
                caption TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_cafes (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                neighborhood VARCHAR(255),
                accent_color VARCHAR(7) DEFAULT '#B15A38',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_business_cafes (
                business_id UUID NOT NULL REFERENCES local_businesses(id) ON DELETE CASCADE,
                cafe_id UUID NOT NULL REFERENCES local_cafes(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (business_id, cafe_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_reward_programs (
                id UUID PRIMARY KEY,
                cafe_id UUID NOT NULL REFERENCES local_cafes(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                visits_required INTEGER NOT NULL CHECK (visits_required > 0),
                reward_description TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (cafe_id, name)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_customers (
                id UUID PRIMARY KEY,
                cafe_id UUID NOT NULL REFERENCES local_cafes(id) ON DELETE CASCADE,
                full_name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                email VARCHAR(255),
                favorite_order TEXT,
                is_vip BOOLEAN NOT NULL DEFAULT false,
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_visits (
                id UUID PRIMARY KEY,
                cafe_id UUID NOT NULL REFERENCES local_cafes(id) ON DELETE CASCADE,
                customer_id UUID NOT NULL REFERENCES local_customers(id) ON DELETE CASCADE,
                program_id UUID REFERENCES local_reward_programs(id) ON DELETE SET NULL,
                order_total NUMERIC(10,2),
                visit_note TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_redemptions (
                id UUID PRIMARY KEY,
                cafe_id UUID NOT NULL REFERENCES local_cafes(id) ON DELETE CASCADE,
                customer_id UUID NOT NULL REFERENCES local_customers(id) ON DELETE CASCADE,
                program_id UUID NOT NULL REFERENCES local_reward_programs(id) ON DELETE CASCADE,
                redemption_note TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_email_campaigns (
                id UUID PRIMARY KEY,
                business_id UUID NOT NULL REFERENCES local_businesses(id) ON DELETE CASCADE,
                cafe_id UUID NOT NULL REFERENCES local_cafes(id) ON DELETE CASCADE,
                created_by UUID NOT NULL REFERENCES local_business_users(id) ON DELETE RESTRICT,
                title VARCHAR(255) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                body TEXT NOT NULL,
                target_segment VARCHAR(30) NOT NULL
                    CHECK (target_segment IN ('all', 'vip', 'regular', 'reward_ready')),
                status VARCHAR(20) NOT NULL
                    CHECK (status IN ('draft', 'sent', 'failed', 'simulated')),
                sent_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                sent_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS local_email_deliveries (
                id UUID PRIMARY KEY,
                campaign_id UUID NOT NULL REFERENCES local_email_campaigns(id) ON DELETE CASCADE,
                customer_id UUID NOT NULL REFERENCES local_customers(id) ON DELETE CASCADE,
                recipient_email VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL CHECK (status IN ('sent', 'failed', 'simulated')),
                error_message TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_business_users_business_id ON local_business_users(business_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_business_users_email ON local_business_users(email)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_business_media_business_id ON local_business_media(business_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_business_media_sort_order ON local_business_media(business_id, sort_order, created_at DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_business_cafes_business_id ON local_business_cafes(business_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_business_cafes_cafe_id ON local_business_cafes(cafe_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_reward_programs_cafe_id ON local_reward_programs(cafe_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_customers_cafe_id ON local_customers(cafe_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_customers_vip ON local_customers(cafe_id, is_vip)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_visits_cafe_customer ON local_visits(cafe_id, customer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_visits_program ON local_visits(program_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_redemptions_cafe_customer ON local_redemptions(cafe_id, customer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_redemptions_program ON local_redemptions(program_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_email_campaigns_business_id ON local_email_campaigns(business_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_email_campaigns_cafe_id ON local_email_campaigns(cafe_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_email_deliveries_campaign_id ON local_email_deliveries(campaign_id)")
