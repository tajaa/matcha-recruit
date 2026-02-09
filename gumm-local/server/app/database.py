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
            CREATE TABLE IF NOT EXISTS local_cafes (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                neighborhood VARCHAR(255),
                accent_color VARCHAR(7) DEFAULT '#B15A38',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
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

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_reward_programs_cafe_id ON local_reward_programs(cafe_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_customers_cafe_id ON local_customers(cafe_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_customers_vip ON local_customers(cafe_id, is_vip)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_visits_cafe_customer ON local_visits(cafe_id, customer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_visits_program ON local_visits(program_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_redemptions_cafe_customer ON local_redemptions(cafe_id, customer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_local_redemptions_program ON local_redemptions(program_id)")
