"""
Seed script to populate test employee data.
Run with: python scripts/seed_employees.py
"""
import asyncio
import sys
import os
from datetime import date

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.database import init_pool, close_pool, get_connection


async def seed_employees():
    settings = load_settings()
    await init_pool(settings.database_url)

    async with get_connection() as conn:
        # Get first company (or create one)
        company = await conn.fetchrow("SELECT id, name FROM companies LIMIT 1")

        if not company:
            print("No company found. Creating test company...")
            company = await conn.fetchrow("""
                INSERT INTO companies (name, industry, size, website)
                VALUES ('Acme Corp', 'Technology', '50-200', 'https://acme.com')
                RETURNING id, name
            """)
            print(f"Created company: {company['name']}")

        company_id = company['id']
        print(f"Using company: {company['name']} ({company_id})")

        # Check if employees already exist
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1", company_id
        )

        if existing > 0:
            print(f"Found {existing} existing employees. Skipping seed.")
            await close_pool()
            return

        # Seed test employees
        test_employees = [
            {
                'email': 'john.smith@acme.com',
                'first_name': 'John',
                'last_name': 'Smith',
                'work_state': 'CA',
                'employment_type': 'full_time',
                'start_date': date(2023, 1, 15),
            },
            {
                'email': 'sarah.johnson@acme.com',
                'first_name': 'Sarah',
                'last_name': 'Johnson',
                'work_state': 'NY',
                'employment_type': 'full_time',
                'start_date': date(2023, 3, 1),
            },
            {
                'email': 'mike.williams@acme.com',
                'first_name': 'Mike',
                'last_name': 'Williams',
                'work_state': 'TX',
                'employment_type': 'part_time',
                'start_date': date(2023, 6, 15),
            },
            {
                'email': 'emily.brown@acme.com',
                'first_name': 'Emily',
                'last_name': 'Brown',
                'work_state': 'WA',
                'employment_type': 'contractor',
                'start_date': date(2024, 1, 10),
            },
            {
                'email': 'david.chen@acme.com',
                'first_name': 'David',
                'last_name': 'Chen',
                'work_state': 'CA',
                'employment_type': 'full_time',
                'start_date': date(2024, 2, 20),
            },
        ]

        print(f"\nSeeding {len(test_employees)} test employees...")

        for emp in test_employees:
            await conn.execute("""
                INSERT INTO employees (org_id, email, first_name, last_name, work_state, employment_type, start_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, company_id, emp['email'], emp['first_name'], emp['last_name'],
                emp['work_state'], emp['employment_type'], emp['start_date'])
            print(f"  + {emp['first_name']} {emp['last_name']} ({emp['email']})")

        # Add one employee with a pending invitation
        invited_emp = await conn.fetchrow("""
            INSERT INTO employees (org_id, email, first_name, last_name, work_state, employment_type, start_date)
            VALUES ($1, 'alex.martinez@acme.com', 'Alex', 'Martinez', 'FL', 'full_time', $2)
            RETURNING id
        """, company_id, date(2024, 3, 1))
        print(f"  + Alex Martinez (alex.martinez@acme.com)")

        # Get admin user to be inviter
        admin = await conn.fetchrow("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if admin:
            # Create a pending invitation for Alex
            await conn.execute("""
                INSERT INTO employee_invitations (org_id, employee_id, invited_by, token, status, expires_at)
                VALUES ($1, $2, $3, 'test-invite-token-12345', 'pending', NOW() + INTERVAL '7 days')
            """, company_id, invited_emp['id'], admin['id'])
            print(f"    -> Created pending invitation for Alex")

        # Add one terminated employee
        await conn.execute("""
            INSERT INTO employees (org_id, email, first_name, last_name, work_state, employment_type, start_date, termination_date)
            VALUES ($1, 'former.employee@acme.com', 'Former', 'Employee', 'OR', 'full_time', $2, $3)
        """, company_id, date(2022, 1, 1), date(2023, 12, 31))
        print(f"  + Former Employee (former.employee@acme.com) [TERMINATED]")

        print(f"\nDone! Seeded 7 employees.")

    await close_pool()


if __name__ == '__main__':
    asyncio.run(seed_employees())
