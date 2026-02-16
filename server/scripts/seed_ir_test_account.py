#!/usr/bin/env python3
"""Seed one IR-focused test account (1 client admin + 3 employees + incident data).

This script is idempotent and safe to rerun.

What it does:
1. Selects a target company (first existing by default, or via --company-id/--company-name).
2. Creates/updates one client user and maps them to the company context.
3. Creates/updates three employee users and employee records mapped to the same org.
4. Ensures one business location exists for the company.
5. Restricts company features to only: incidents, er_copilot, offer_letters, policies.
6. Seeds realistic IR incidents, documents, and cached analysis entries.

Usage:
    cd server
    python scripts/seed_ir_test_account.py
    python scripts/seed_ir_test_account.py --company-name "Acme Corp"
    python scripts/seed_ir_test_account.py --company-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.core.services.auth import hash_password
from app.database import close_pool, get_connection, init_pool


DEFAULT_CLIENT_EMAIL = "ir.admin@matcha-seed.com"
DEFAULT_PASSWORD = os.getenv("IR_TEST_SEED_PASSWORD", "ir_seed_123")
DEFAULT_LOCATION_NAME = "IR Seed HQ"
DEFAULT_COMPANY_NAME = "IR Seed Company"


@dataclass(frozen=True)
class EmployeeSeed:
    email: str
    first_name: str
    last_name: str
    work_state: str
    employment_type: str
    start_date: date
    phone: str


EMPLOYEES: list[EmployeeSeed] = [
    EmployeeSeed(
        email="riley.chen+ir@matcha-seed.com",
        first_name="Riley",
        last_name="Chen",
        work_state="CA",
        employment_type="full_time",
        start_date=date(2023, 2, 6),
        phone="555-1101",
    ),
    EmployeeSeed(
        email="jordan.lee+ir@matcha-seed.com",
        first_name="Jordan",
        last_name="Lee",
        work_state="TX",
        employment_type="full_time",
        start_date=date(2023, 7, 10),
        phone="555-1102",
    ),
    EmployeeSeed(
        email="morgan.davis+ir@matcha-seed.com",
        first_name="Morgan",
        last_name="Davis",
        work_state="NY",
        employment_type="part_time",
        start_date=date(2024, 1, 15),
        phone="555-1103",
    ),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _naive_utc_days_ago(days_ago: int, hour: int = 15) -> datetime:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    return dt.replace(tzinfo=None)


def _incident_number() -> str:
    now = datetime.now(timezone.utc)
    suffix = secrets.token_hex(2).upper()
    return f"IR-{now.year}-{now.month:02d}-{suffix}"


def _incident_templates(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    emp1, emp2, emp3 = employees
    emp1_name = f"{emp1['first_name']} {emp1['last_name']}"
    emp2_name = f"{emp2['first_name']} {emp2['last_name']}"
    emp3_name = f"{emp3['first_name']} {emp3['last_name']}"

    return [
        {
            "title": "Seed - Loading Dock Near Miss (Wet Floor)",
            "description": (
                "A pallet jack slipped near Dock Door 2 due to a wet surface. "
                "No injury occurred, but a serious foot/leg injury was possible."
            ),
            "incident_type": "near_miss",
            "severity": "high",
            "status": "action_required",
            "occurred_at": _naive_utc_days_ago(1, 9),
            "location": "Dock Door 2",
            "reported_by_name": emp1_name,
            "reported_by_email": emp1["email"],
            "witnesses": [
                {
                    "name": emp2_name,
                    "contact": emp2["email"],
                    "statement": "Observed wheel slippage near pooled water from an open bay door.",
                }
            ],
            "category_data": {
                "hazard_identified": "Wet concrete",
                "potential_outcome": "Lower-extremity injury",
                "immediate_action": "Area cordoned and cleanup dispatched",
            },
            "root_cause": None,
            "corrective_actions": "Install anti-slip mats and add hourly dock floor checks during rain.",
            "documents": [
                {"filename": "dock-floor-photo-1.jpg", "document_type": "photo", "mime_type": "image/jpeg", "file_size": 248312},
                {"filename": "witness-statement-riley.txt", "document_type": "statement", "mime_type": "text/plain", "file_size": 1934},
            ],
            "analysis": {
                "categorization": {
                    "suggested_type": "near_miss",
                    "confidence": 0.95,
                    "reasoning": "No injury occurred, but unsafe conditions created a credible injury risk.",
                },
                "severity": {
                    "suggested_severity": "high",
                    "factors": ["High traffic area", "Slip risk", "Potential severe injury"],
                    "reasoning": "No harm this time, but recurrence could result in recordable injury.",
                },
                "recommendations": {
                    "recommendations": [
                        {"action": "Install anti-slip mats at Dock Door 2", "priority": "immediate", "responsible_party": "Facilities"},
                        {"action": "Require wet-floor checks every 60 minutes", "priority": "short_term", "responsible_party": "Operations"},
                    ],
                    "summary": "Control dock moisture and enforce recurring checks to prevent recurrence.",
                },
                "similar": {
                    "similar_incidents": [],
                    "pattern_summary": "Insufficient data for pattern detection.",
                },
            },
        },
        {
            "title": "Seed - Forklift Contact with Storage Racking",
            "description": (
                "Forklift clipped lower racking beam while reversing in aisle 4. "
                "Product fell from first level, no injuries reported."
            ),
            "incident_type": "safety",
            "severity": "medium",
            "status": "investigating",
            "occurred_at": _naive_utc_days_ago(3, 14),
            "location": "Warehouse Aisle 4",
            "reported_by_name": emp2_name,
            "reported_by_email": emp2["email"],
            "witnesses": [
                {"name": emp1_name, "contact": emp1["email"], "statement": "Heard impact and observed displaced pallets."},
                {"name": emp3_name, "contact": emp3["email"], "statement": "Visibility was limited due to stacked returns."},
            ],
            "category_data": {
                "equipment_involved": "Forklift FL-17",
                "safety_gear_worn": True,
                "environmental_factors": ["Crowded staging zone"],
            },
            "root_cause": None,
            "corrective_actions": None,
            "documents": [
                {"filename": "incident-form-fl17.pdf", "document_type": "form", "mime_type": "application/pdf", "file_size": 118233},
                {"filename": "rack-damage-photo.jpg", "document_type": "photo", "mime_type": "image/jpeg", "file_size": 332144},
            ],
            "analysis": {
                "categorization": {
                    "suggested_type": "safety",
                    "confidence": 0.97,
                    "reasoning": "Vehicle operation incident with property damage in an active warehouse.",
                },
                "severity": {
                    "suggested_severity": "medium",
                    "factors": ["No injury", "Property damage", "Repeat risk"],
                    "reasoning": "Immediate harm was limited, but potential for injury remains.",
                },
                "root_cause": {
                    "primary_cause": "Restricted aisle visibility",
                    "contributing_factors": ["Overstaged inventory", "Reverse maneuver in tight space"],
                    "prevention_suggestions": ["Reconfigure staging lane", "Spotter requirement during peak load hours"],
                    "reasoning": "Layout and visibility constraints increased collision probability.",
                },
                "similar": {
                    "similar_incidents": [],
                    "pattern_summary": "No reliable similarity set yet.",
                },
            },
        },
        {
            "title": "Seed - Hostile Verbal Exchange in Team Area",
            "description": (
                "Employee reported repeated raised-voice comments from a coworker during standup prep. "
                "No threats reported, but team disruption occurred."
            ),
            "incident_type": "behavioral",
            "severity": "medium",
            "status": "reported",
            "occurred_at": _naive_utc_days_ago(5, 10),
            "location": "Operations Pod B",
            "reported_by_name": emp3_name,
            "reported_by_email": emp3["email"],
            "witnesses": [
                {"name": emp1_name, "contact": emp1["email"], "statement": "Observed escalation over task ownership language."}
            ],
            "category_data": {
                "parties_involved": [{"name": emp3_name, "role": "Coordinator"}, {"name": emp2_name, "role": "Lead"}],
                "manager_notified": True,
            },
            "root_cause": "Escalation during ambiguous task ownership discussion.",
            "corrective_actions": "Manager mediation and written expectations for standup conduct.",
            "documents": [
                {"filename": "behavioral-notes.txt", "document_type": "statement", "mime_type": "text/plain", "file_size": 2451},
            ],
            "analysis": {
                "categorization": {
                    "suggested_type": "behavioral",
                    "confidence": 0.94,
                    "reasoning": "Incident concerns workplace conduct and interpersonal behavior.",
                },
                "recommendations": {
                    "recommendations": [
                        {"action": "Run mediated conversation within 48 hours", "priority": "immediate", "responsible_party": "Manager"},
                        {"action": "Document team communication norms", "priority": "short_term", "responsible_party": "HRBP"},
                    ],
                    "summary": "Address conduct quickly and establish explicit communication expectations.",
                },
                "similar": {
                    "similar_incidents": [],
                    "pattern_summary": "No repeated behavior trend detected yet.",
                },
            },
        },
        {
            "title": "Seed - Missing Scanner Device from Cage Inventory",
            "description": (
                "One handheld scanner was unaccounted for during shift turnover count. "
                "Device recovered later in unlabeled cart."
            ),
            "incident_type": "property",
            "severity": "low",
            "status": "resolved",
            "occurred_at": _naive_utc_days_ago(12, 16),
            "location": "Equipment Cage",
            "reported_by_name": emp1_name,
            "reported_by_email": emp1["email"],
            "witnesses": [],
            "category_data": {
                "asset_damaged": "Handheld scanner SC-22",
                "estimated_cost": 0,
                "insurance_claim": False,
            },
            "root_cause": "Inconsistent sign-out/check-in logging at shift handoff.",
            "corrective_actions": "Implemented mandatory checkout sheet and end-of-shift verification.",
            "documents": [
                {"filename": "shift-turnover-log.csv", "document_type": "form", "mime_type": "text/csv", "file_size": 4893},
            ],
            "analysis": {
                "categorization": {
                    "suggested_type": "property",
                    "confidence": 0.92,
                    "reasoning": "Incident centered on temporary loss of company asset.",
                },
                "root_cause": {
                    "primary_cause": "Process gap in handoff control",
                    "contributing_factors": ["No enforced sign-out", "Shared cart storage"],
                    "prevention_suggestions": ["Barcode checkout workflow", "Shift-end checklist enforcement"],
                    "reasoning": "Asset tracking controls were insufficient during transition periods.",
                },
                "similar": {
                    "similar_incidents": [],
                    "pattern_summary": "Single isolated event at this time.",
                },
            },
        },
        {
            "title": "Seed - Unauthorized Rear Door Tailgating",
            "description": (
                "A non-badged visitor entered through a secured rear door while following staff during closeout."
            ),
            "incident_type": "other",
            "severity": "high",
            "status": "closed",
            "occurred_at": _naive_utc_days_ago(24, 19),
            "location": "Rear Entrance",
            "reported_by_name": "Security Desk",
            "reported_by_email": "security@matcha.local",
            "witnesses": [{"name": emp2_name, "contact": emp2["email"], "statement": "Observed door held open > 30 seconds."}],
            "category_data": {
                "entry_point": "Rear Entrance",
                "time_of_day": "After hours",
            },
            "root_cause": "Door discipline lapse during end-of-day operations.",
            "corrective_actions": "Tailgating reminder + installed door ajar alert.",
            "documents": [
                {"filename": "rear-door-cctv-summary.txt", "document_type": "other", "mime_type": "text/plain", "file_size": 3012},
            ],
            "analysis": {
                "categorization": {
                    "suggested_type": "other",
                    "confidence": 0.89,
                    "reasoning": "Security access violation outside core injury/property categories.",
                },
                "severity": {
                    "suggested_severity": "high",
                    "factors": ["Unauthorized access", "After-hours timing", "Security exposure"],
                    "reasoning": "Potential for material security impact despite no direct harm.",
                },
                "recommendations": {
                    "recommendations": [
                        {"action": "Retrain staff on anti-tailgating protocol", "priority": "immediate", "responsible_party": "Security"},
                        {"action": "Quarterly rear-entry access audit", "priority": "long_term", "responsible_party": "Facilities"},
                    ],
                    "summary": "Strengthen access control behavior and monitor for repeat failures.",
                },
                "similar": {
                    "similar_incidents": [],
                    "pattern_summary": "Potential emerging trend if repeated within 90 days.",
                },
            },
        },
    ]


async def ensure_user(conn, email: str, role: str, password: str) -> tuple[str, str]:
    """Create or update a user and return (user_id, action)."""
    password_hash = hash_password(password)
    existing = await conn.fetchrow("SELECT id, role FROM users WHERE email = $1", email)

    if existing:
        await conn.execute(
            """
            UPDATE users
            SET role = $1, password_hash = $2, is_active = true, updated_at = NOW()
            WHERE id = $3
            """,
            role,
            password_hash,
            existing["id"],
        )
        action = "updated" if existing["role"] == role else f"updated_role({existing['role']}->{role})"
        return str(existing["id"]), action

    created = await conn.fetchrow(
        """
        INSERT INTO users (email, password_hash, role, is_active)
        VALUES ($1, $2, $3, true)
        RETURNING id
        """,
        email,
        password_hash,
        role,
    )
    return str(created["id"]), "created"


async def ensure_company(conn, company_id: str | None, company_name: str | None) -> tuple[str, str]:
    """Select or create a target company for seeding."""
    if company_id:
        row = await conn.fetchrow("SELECT id, name FROM companies WHERE id = $1", company_id)
        if not row:
            raise ValueError(f"Company not found for --company-id: {company_id}")
        return str(row["id"]), row["name"]

    if company_name:
        row = await conn.fetchrow(
            """
            SELECT id, name
            FROM companies
            WHERE LOWER(name) = LOWER($1)
            ORDER BY created_at
            LIMIT 1
            """,
            company_name,
        )
        if row:
            return str(row["id"]), row["name"]

        created = await conn.fetchrow(
            """
            INSERT INTO companies (name, industry, size, status)
            VALUES ($1, 'Technology', '11-50', 'approved')
            RETURNING id, name
            """,
            company_name,
        )
        return str(created["id"]), created["name"]

    first = await conn.fetchrow(
        "SELECT id, name FROM companies ORDER BY created_at LIMIT 1"
    )
    if first:
        return str(first["id"]), first["name"]

    created = await conn.fetchrow(
        """
        INSERT INTO companies (name, industry, size, status)
        VALUES ($1, 'Technology', '11-50', 'approved')
        RETURNING id, name
        """,
        DEFAULT_COMPANY_NAME,
    )
    return str(created["id"]), created["name"]


async def set_limited_feature_set(conn, company_id: str) -> bool:
    """Set company features to only IR, ER Copilot, Offer Letters, and Policies."""
    has_column = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'companies' AND column_name = 'enabled_features'
        )
        """
    )
    if not has_column:
        return False

    feature_payload = {
        "offer_letters": True,
        "policies": True,
        "compliance": False,
        "compliance_plus": False,
        "employees": False,
        "vibe_checks": False,
        "enps": False,
        "performance_reviews": False,
        "er_copilot": True,
        "incidents": True,
        "time_off": False,
        "accommodations": False,
    }

    await conn.execute(
        "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
        json.dumps(feature_payload),
        company_id,
    )
    return True


async def ensure_client_mapping(
    conn,
    company_id: str,
    client_user_id: str,
    client_email: str,
) -> None:
    """Ensure client user has company mapping."""
    # Company mapping for the seeded client user.
    await conn.execute(
        """
        UPDATE companies
        SET owner_id = $1,
            status = 'approved',
            approved_at = COALESCE(approved_at, NOW())
        WHERE id = $2
        """,
        client_user_id,
        company_id,
    )

    # Keep an explicit company-user mapping record for notification targets.
    client_row = await conn.fetchrow("SELECT id FROM clients WHERE user_id = $1", client_user_id)
    if client_row:
        await conn.execute(
            """
            UPDATE clients
            SET company_id = $1,
                name = $2
            WHERE user_id = $3
            """,
            company_id,
            "IR Seed Client Admin",
            client_user_id,
        )
    else:
        await conn.execute(
            """
            INSERT INTO clients (user_id, company_id, name)
            VALUES ($1, $2, $3)
            """,
            client_user_id,
            company_id,
            "IR Seed Client Admin",
        )

    print(f"Mapped client user {client_email} to company {company_id}")


async def ensure_location(conn, company_id: str, location_name: str) -> tuple[str, str]:
    """Ensure one business location exists for the company."""
    existing = await conn.fetchrow(
        """
        SELECT id, name
        FROM business_locations
        WHERE company_id = $1 AND name = $2
        ORDER BY created_at
        LIMIT 1
        """,
        company_id,
        location_name,
    )
    if existing:
        return str(existing["id"]), existing["name"]

    created = await conn.fetchrow(
        """
        INSERT INTO business_locations (company_id, name, address, city, state, county, zipcode, is_active)
        VALUES ($1, $2, $3, $4, $5, $6, $7, true)
        RETURNING id, name
        """,
        company_id,
        location_name,
        "100 Seed Campus Dr",
        "Austin",
        "TX",
        "Travis",
        "78701",
    )
    return str(created["id"]), created["name"]


async def ensure_employees(
    conn,
    company_id: str,
    password: str,
) -> list[dict[str, Any]]:
    """Create/update employee users and employee records."""
    employee_rows: list[dict[str, Any]] = []

    for seed in EMPLOYEES:
        user_id, user_action = await ensure_user(conn, seed.email, "employee", password)

        existing = await conn.fetchrow(
            """
            SELECT id
            FROM employees
            WHERE org_id = $1 AND email = $2
            ORDER BY created_at
            LIMIT 1
            """,
            company_id,
            seed.email,
        )

        if existing:
            employee_id = str(existing["id"])
            await conn.execute(
                """
                UPDATE employees
                SET user_id = $1,
                    first_name = $2,
                    last_name = $3,
                    work_state = $4,
                    employment_type = $5,
                    start_date = $6,
                    phone = $7,
                    updated_at = NOW()
                WHERE id = $8
                """,
                user_id,
                seed.first_name,
                seed.last_name,
                seed.work_state,
                seed.employment_type,
                seed.start_date,
                seed.phone,
                employee_id,
            )
            employee_action = "updated"
        else:
            created = await conn.fetchrow(
                """
                INSERT INTO employees (
                    org_id, user_id, email, first_name, last_name,
                    work_state, employment_type, start_date, phone
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                company_id,
                user_id,
                seed.email,
                seed.first_name,
                seed.last_name,
                seed.work_state,
                seed.employment_type,
                seed.start_date,
                seed.phone,
            )
            employee_id = str(created["id"])
            employee_action = "created"

        print(
            f"Employee {seed.first_name} {seed.last_name} ({seed.email}): "
            f"user={user_action}, employee={employee_action}"
        )

        employee_rows.append(
            {
                "employee_id": employee_id,
                "user_id": user_id,
                "email": seed.email,
                "first_name": seed.first_name,
                "last_name": seed.last_name,
            }
        )

    # Assign manager relationship: first employee manages remaining employees.
    if len(employee_rows) >= 2:
        manager_id = employee_rows[0]["employee_id"]
        for subordinate in employee_rows[1:]:
            await conn.execute(
                "UPDATE employees SET manager_id = $1, updated_at = NOW() WHERE id = $2",
                manager_id,
                subordinate["employee_id"],
            )

    return employee_rows


async def ensure_incident(
    conn,
    *,
    company_id: str,
    location_id: str,
    admin_user_id: str,
    incident_data: dict[str, Any],
) -> tuple[str, str]:
    """Upsert one incident by (company_id, title)."""
    existing = await conn.fetchrow(
        """
        SELECT id, incident_number
        FROM ir_incidents
        WHERE company_id = $1 AND title = $2
        ORDER BY created_at
        LIMIT 1
        """,
        company_id,
        incident_data["title"],
    )

    resolved_at = datetime.now(timezone.utc).replace(tzinfo=None) if incident_data["status"] in {"resolved", "closed"} else None

    if existing:
        await conn.execute(
            """
            UPDATE ir_incidents
            SET description = $1,
                incident_type = $2,
                severity = $3,
                status = $4,
                occurred_at = $5,
                location = $6,
                reported_by_name = $7,
                reported_by_email = $8,
                assigned_to = $9,
                witnesses = $10,
                category_data = $11,
                root_cause = $12,
                corrective_actions = $13,
                location_id = $14,
                created_by = $15,
                resolved_at = $16,
                updated_at = NOW()
            WHERE id = $17
            """,
            incident_data["description"],
            incident_data["incident_type"],
            incident_data["severity"],
            incident_data["status"],
            incident_data["occurred_at"],
            incident_data["location"],
            incident_data["reported_by_name"],
            incident_data["reported_by_email"],
            admin_user_id,
            json.dumps(incident_data.get("witnesses", [])),
            json.dumps(incident_data.get("category_data", {})),
            incident_data.get("root_cause"),
            incident_data.get("corrective_actions"),
            location_id,
            admin_user_id,
            resolved_at,
            existing["id"],
        )
        return str(existing["id"]), "updated"

    created = await conn.fetchrow(
        """
        INSERT INTO ir_incidents (
            incident_number, title, description, incident_type, severity, status,
            occurred_at, location, reported_by_name, reported_by_email,
            assigned_to, witnesses, category_data, root_cause, corrective_actions,
            company_id, location_id, created_by, resolved_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10,
            $11, $12, $13, $14, $15,
            $16, $17, $18, $19
        )
        RETURNING id
        """,
        _incident_number(),
        incident_data["title"],
        incident_data["description"],
        incident_data["incident_type"],
        incident_data["severity"],
        incident_data["status"],
        incident_data["occurred_at"],
        incident_data["location"],
        incident_data["reported_by_name"],
        incident_data["reported_by_email"],
        admin_user_id,
        json.dumps(incident_data.get("witnesses", [])),
        json.dumps(incident_data.get("category_data", {})),
        incident_data.get("root_cause"),
        incident_data.get("corrective_actions"),
        company_id,
        location_id,
        admin_user_id,
        resolved_at,
    )
    return str(created["id"]), "created"


async def ensure_incident_documents(
    conn,
    *,
    incident_id: str,
    admin_user_id: str,
    documents: list[dict[str, Any]],
) -> tuple[int, int]:
    """Upsert incident documents by (incident_id, filename)."""
    created = 0
    updated = 0

    for document in documents:
        existing = await conn.fetchrow(
            "SELECT id FROM ir_incident_documents WHERE incident_id = $1 AND filename = $2",
            incident_id,
            document["filename"],
        )

        if existing:
            await conn.execute(
                """
                UPDATE ir_incident_documents
                SET document_type = $1,
                    file_path = $2,
                    mime_type = $3,
                    file_size = $4,
                    uploaded_by = $5
                WHERE id = $6
                """,
                document["document_type"],
                f"ir-seed/{incident_id}/{document['filename']}",
                document["mime_type"],
                document["file_size"],
                admin_user_id,
                existing["id"],
            )
            updated += 1
        else:
            await conn.execute(
                """
                INSERT INTO ir_incident_documents (
                    incident_id, document_type, filename, file_path, mime_type, file_size, uploaded_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                incident_id,
                document["document_type"],
                document["filename"],
                f"ir-seed/{incident_id}/{document['filename']}",
                document["mime_type"],
                document["file_size"],
                admin_user_id,
            )
            created += 1

    return created, updated


async def ensure_incident_analysis(
    conn,
    *,
    incident_id: str,
    admin_user_id: str,
    analysis_map: dict[str, dict[str, Any]],
) -> None:
    """Upsert cached analysis rows for one incident."""
    for analysis_type, payload in analysis_map.items():
        data = dict(payload)
        data.setdefault("generated_at", _now_iso())

        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data, generated_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (incident_id, analysis_type)
            DO UPDATE SET
                analysis_data = EXCLUDED.analysis_data,
                generated_by = EXCLUDED.generated_by,
                generated_at = NOW()
            """,
            incident_id,
            analysis_type,
            json.dumps(data),
            admin_user_id,
        )


async def seed_ir_test_account(args: argparse.Namespace) -> None:
    settings = load_settings()
    await init_pool(settings.database_url)

    summary = {
        "incidents_created": 0,
        "incidents_updated": 0,
        "docs_created": 0,
        "docs_updated": 0,
    }

    try:
        async with get_connection() as conn:
            async with conn.transaction():
                company_id, company_name = await ensure_company(conn, args.company_id, args.company_name)
                client_user_id, client_action = await ensure_user(conn, args.client_email, "client", args.password)
                print(f"Client {args.client_email}: {client_action}")

                await ensure_client_mapping(conn, company_id, client_user_id, args.client_email)
                features_set = await set_limited_feature_set(conn, company_id)
                if features_set:
                    print("Set limited features: incidents, er_copilot, offer_letters, policies")
                else:
                    print("Skipped feature set: companies.enabled_features column not found")

                location_id, location_name = await ensure_location(conn, company_id, args.location_name)
                print(f"Using location: {location_name} ({location_id})")

                employee_rows = await ensure_employees(conn, company_id, args.password)
                incident_templates = _incident_templates(employee_rows)

                for incident_data in incident_templates:
                    incident_id, action = await ensure_incident(
                        conn,
                        company_id=company_id,
                        location_id=location_id,
                        admin_user_id=client_user_id,
                        incident_data=incident_data,
                    )
                    summary[f"incidents_{action}"] += 1

                    docs_created, docs_updated = await ensure_incident_documents(
                        conn,
                        incident_id=incident_id,
                        admin_user_id=client_user_id,
                        documents=incident_data.get("documents", []),
                    )
                    summary["docs_created"] += docs_created
                    summary["docs_updated"] += docs_updated

                    await ensure_incident_analysis(
                        conn,
                        incident_id=incident_id,
                        admin_user_id=client_user_id,
                        analysis_map=incident_data.get("analysis", {}),
                    )

                    await conn.execute(
                        """
                        INSERT INTO ir_audit_log (incident_id, user_id, action, entity_type, entity_id, details)
                        VALUES ($1, $2, $3, 'incident', $1, $4)
                        """,
                        incident_id,
                        client_user_id,
                        "incident_seeded",
                        json.dumps({"title": incident_data["title"], "seed_action": action}),
                    )

        print("\n" + "=" * 64)
        print("IR TEST ACCOUNT SEED COMPLETE")
        print("=" * 64)
        print(f"Company: {company_name} ({company_id})")
        print(f"Client login: {args.client_email}")
        print(f"Password: {args.password}")
        print(f"Employees: {', '.join(e.email for e in EMPLOYEES)}")
        print(f"Incidents created: {summary['incidents_created']}")
        print(f"Incidents updated: {summary['incidents_updated']}")
        print(f"Documents created: {summary['docs_created']}")
        print(f"Documents updated: {summary['docs_updated']}")
        print("Route: /app/ir")
        print("=" * 64)
    finally:
        await close_pool()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed IR test account with org + business mappings.")
    parser.add_argument("--company-id", help="Target existing company UUID.")
    parser.add_argument(
        "--company-name",
        help="Target company name. If not found, it will be created. Ignored when --company-id is provided.",
    )
    parser.add_argument("--client-email", default=DEFAULT_CLIENT_EMAIL, help="Client login email to create/update.")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password applied to client + employee users.")
    parser.add_argument("--location-name", default=DEFAULT_LOCATION_NAME, help="Business location name to create/use.")
    return parser


if __name__ == "__main__":
    asyncio.run(seed_ir_test_account(build_parser().parse_args()))
