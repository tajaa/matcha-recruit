#!/usr/bin/env python3
"""Seed a test gumfit_admin account."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_pool, get_connection, close_pool
from app.services.auth import hash_password
from app.config import load_settings


async def seed_gumfit_admin():
    """Create a test gumfit_admin account."""
    settings = load_settings()
    await init_pool(settings.database_url)

    email = "gumfit@test.com"
    password = "gumfit123"
    password_hash = hash_password(password)

    async with get_connection() as conn:
        # Check if user already exists
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1",
            email
        )

        if existing:
            # Update role if exists
            await conn.execute(
                "UPDATE users SET role = 'gumfit_admin', password_hash = $1 WHERE email = $2",
                password_hash, email
            )
            print(f"Updated existing user to gumfit_admin: {email}")
        else:
            # Create new user
            await conn.execute(
                """
                INSERT INTO users (email, password_hash, role, is_active)
                VALUES ($1, $2, 'gumfit_admin', true)
                """,
                email, password_hash
            )
            print(f"Created gumfit_admin user: {email}")

        print(f"Password: {password}")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(seed_gumfit_admin())
