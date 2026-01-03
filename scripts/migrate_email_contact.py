import asyncio
import os
import sys

# Add server directory to path
sys.path.append(os.path.join(os.getcwd(), 'server'))

from app.database import get_connection, init_pool
from app.config import load_settings

async def migrate():
    print("Migrating lead_emails table...")
    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        async with get_connection() as conn:
            await conn.execute("ALTER TABLE lead_emails ALTER COLUMN contact_id DROP NOT NULL;")
            print("Successfully made contact_id nullable.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
