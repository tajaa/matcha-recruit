import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.config import load_settings
from app.database import init_pool, close_pool, get_connection

async def run():
    settings = load_settings()
    await init_pool(settings.database_url)
    async with get_connection() as conn:
        company = await conn.fetchrow("SELECT id, name FROM companies WHERE name ILIKE '%Matcha-Tech%'")
        if company:
            print(f"Company ID: {company['id']}")
            
            # Check Slack provisioning status
            slack = await conn.fetchrow("SELECT config, status FROM integration_connections WHERE company_id = $1 AND provider = 'slack'", company['id'])
            if slack:
                print(f"Slack status: {slack['status']}, Config: {slack['config']}")
            else:
                print("No Slack integration found for Matcha-Tech.")
        else:
            print("Matcha-Tech not found.")
    await close_pool()

if __name__ == '__main__':
    asyncio.run(run())
