"""
Seed a test handbook for Matcha-Tech (smoothie shop, Los Angeles, CA).

Run with:
    python -m scripts.seed_matcha_tech_handbook
    python -m scripts.seed_matcha_tech_handbook --company-id <uuid>
    python -m scripts.seed_matcha_tech_handbook --client-email <email>
"""

import argparse
import asyncio
import os
import sys

# Add parent directory to path so "app" imports resolve when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.core.models.handbook import (
    CompanyHandbookProfileInput,
    HandbookCreateRequest,
    HandbookScopeInput,
    HandbookSectionInput,
)
from app.core.services.handbook_service import HandbookService
from app.database import close_pool, get_connection, init_pool

COMPANY_NAME = "Matcha-Tech"
HANDBOOK_TITLE = "2026 Handbook Test 6 - Matcha-Tech Smoothie (LA, NYC, Miami, Chicago)"


async def _resolve_company_id(
    company_id_override: str | None = None,
    client_email: str | None = None,
) -> str:
    async with get_connection() as conn:
        if company_id_override:
            row = await conn.fetchrow(
                "SELECT id, name FROM companies WHERE id = $1",
                company_id_override,
            )
            if not row:
                raise ValueError(f"Company not found for id: {company_id_override}")
            print(f"Using company by id: {row['name']} ({row['id']})")
            return str(row["id"])

        if client_email:
            row = await conn.fetchrow(
                """
                SELECT c.id, c.name
                FROM users u
                JOIN clients cl ON cl.user_id = u.id
                JOIN companies c ON c.id = cl.company_id
                WHERE LOWER(u.email) = LOWER($1)
                LIMIT 1
                """,
                client_email,
            )
            if not row:
                raise ValueError(f"No client/company mapping found for email: {client_email}")
            print(f"Using client-mapped company: {row['name']} ({row['id']})")
            return str(row["id"])

        matches = await conn.fetch(
            """
            SELECT id, name, created_at
            FROM companies
            WHERE LOWER(name) = LOWER($1)
            ORDER BY created_at ASC
            """,
            COMPANY_NAME,
        )
        if len(matches) > 1:
            print(f"Found {len(matches)} companies named '{COMPANY_NAME}'.")
            for row in matches:
                print(f" - {row['id']} (created_at={row['created_at']})")

        if matches:
            company = matches[0]
            print(f"Using existing company: {company['name']} ({company['id']})")
            return str(company["id"])

        company = await conn.fetchrow(
            """
            INSERT INTO companies (name, industry, size)
            VALUES ($1, $2, $3)
            RETURNING id, name
            """,
            COMPANY_NAME,
            "Food & Beverage",
            "small",
        )
        print(f"Created company: {company['name']} ({company['id']})")
        return str(company["id"])


async def _find_existing_handbook(company_id: str) -> str | None:
    async with get_connection() as conn:
        handbook_id = await conn.fetchval(
            """
            SELECT id
            FROM handbooks
            WHERE company_id = $1
              AND title = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            company_id,
            HANDBOOK_TITLE,
        )
        return str(handbook_id) if handbook_id else None


def _build_request() -> HandbookCreateRequest:
    return HandbookCreateRequest(
        title=HANDBOOK_TITLE,
        mode="multi_state",
        source_type="template",
        scopes=[
            HandbookScopeInput(
                state="CA",
                city="Los Angeles",
                zipcode="90012",
            ),
            HandbookScopeInput(
                state="NY",
                city="New York",
                zipcode="10001",
            ),
            HandbookScopeInput(
                state="FL",
                city="Miami",
                zipcode="33101",
            ),
            HandbookScopeInput(
                state="IL",
                city="Chicago",
                zipcode="60601",
            ),
        ],
        profile=CompanyHandbookProfileInput(
            legal_name="Matcha-Tech LLC",
            dba="Matcha-Tech Smoothie Bar",
            ceo_or_president="Avery Tan",
            headcount=18,
            remote_workers=False,
            minors=False,
            tipped_employees=True,
            union_employees=False,
            federal_contracts=False,
            group_health_insurance=True,
            background_checks=True,
            hourly_employees=True,
            salaried_employees=True,
            commissioned_employees=False,
            tip_pooling=True,
        ),
        custom_sections=[
            HandbookSectionInput(
                section_key="smoothie_food_safety",
                title="Smoothie Prep & Food Safety",
                section_order=260,
                section_type="custom",
                content=(
                    "All smoothie prep staff must follow posted sanitization and food-handling procedures, "
                    "including handwashing, glove use, allergen labeling, and cold-storage checks at opening "
                    "and close."
                ),
            ),
            HandbookSectionInput(
                section_key="overtime_shift_addendum",
                title="Overtime",
                section_order=270,
                section_type="custom",
                content=(
                    "Non-exempt employees must receive manager approval before working overtime, except during "
                    "customer safety or store-closure emergencies. All overtime worked must be recorded in the "
                    "timekeeping system and will be paid per applicable law."
                ),
            ),
            HandbookSectionInput(
                section_key="severance_guidelines",
                title="Severance",
                section_order=280,
                section_type="custom",
                content=(
                    "Severance is not guaranteed and is evaluated case-by-case based on business conditions, "
                    "role impact, tenure, and compliance with post-employment obligations. Any severance offer "
                    "must be documented in a signed separation agreement."
                ),
            ),
        ],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed Matcha-Tech multi-city handbook")
    parser.add_argument(
        "--company-id",
        dest="company_id",
        help="Target company UUID to seed into",
    )
    parser.add_argument(
        "--client-email",
        dest="client_email",
        help="Resolve target company from clients.user_id mapping by email",
    )
    return parser


async def seed_matcha_tech_handbook(company_id_override: str | None = None, client_email: str | None = None) -> None:
    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        company_id = await _resolve_company_id(company_id_override=company_id_override, client_email=client_email)
        existing_handbook_id = await _find_existing_handbook(company_id)
        if existing_handbook_id:
            print(f"Handbook already exists: {existing_handbook_id}")
            return

        request = _build_request()
        handbook = await HandbookService.create_handbook(company_id=company_id, data=request)
        print("Created handbook successfully.")
        print(f"Handbook ID: {handbook.id}")
        print(f"Title: {handbook.title}")
        print(f"Status: {handbook.status}")
        print(f"Sections: {len(handbook.sections)}")
    finally:
        await close_pool()


if __name__ == "__main__":
    args = _build_parser().parse_args()
    asyncio.run(
        seed_matcha_tech_handbook(
            company_id_override=args.company_id,
            client_email=args.client_email,
        )
    )
