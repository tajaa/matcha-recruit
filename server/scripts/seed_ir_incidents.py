#!/usr/bin/env python3
"""Seed script for IR Incidents test data.

Creates 5 incident reports with realistic data, documents, and analysis results.

Usage:
    cd server
    python scripts/seed_ir_incidents.py
"""

import asyncio
import json
import os
import secrets
import sys
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha_recruit")


def generate_incident_number() -> str:
    """Generate a unique incident number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"IR-{now.year}-{now.month:02d}-{random_suffix}"


# =============================================================================
# Sample Incident Data
# =============================================================================

INCIDENTS = [
    {
        "type": "safety",
        "title": "Warehouse Forklift Collision",
        "description": "Forklift operator collided with racking in Aisle 4, causing minor structural damage and falling inventory. No injuries reported.",
        "incident_type": "safety",
        "severity": "medium",
        "location": "Warehouse B, Aisle 4",
        "reported_by_name": "John Smith",
        "reported_by_email": "john.smith@acme.com",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "status": "investigating",
        "witnesses": [
            {"name": "Sarah Jones", "role": "Packer", "email": "sarah.jones@acme.com", "phone": "555-0101"},
            {"name": "Mike Brown", "role": "Supervisor", "email": "mike.brown@acme.com", "phone": "555-0102"}
        ],
        "category_data": {
            "equipment_involved": ["Forklift #42"],
            "environmental_factors": ["Poor lighting in Aisle 4"],
            "safety_gear_worn": True
        },
        "documents": {
            "incident_report.pdf": "Official incident report form filled out by supervisor.",
            "damage_photos.jpg": "Photos of the damaged racking and spilled inventory."
        },
        "analysis": {
            "categorization": {
                "suggested_type": "safety",
                "confidence": 0.95,
                "reasoning": "Incident involves machinery operation and property damage.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "severity": {
                "suggested_severity": "medium",
                "factors": ["Property damage > $1000", "Potential for injury", "No actual injury"],
                "reasoning": "While no one was hurt, the potential for serious injury was high due to falling inventory.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "root_cause": {
                "primary_cause": "Operator Error / Fatigue",
                "contributing_factors": ["Poor lighting", "Rushing to meet quota"],
                "prevention_suggestions": ["Install better lighting in Aisle 4", "Review quota expectations", "Refresher training for operator"],
                "reasoning": "Operator admitted to misjudging the turn due to shadows.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    },
    {
        "type": "harassment",
        "title": "Verbal Harassment in Breakroom",
        "description": "Employee reported being subjected to derogatory comments about their appearance by a coworker during lunch break.",
        "incident_type": "behavioral",
        "severity": "high",
        "location": "Main Office Breakroom",
        "reported_by_name": "Anonymous",
        "reported_by_email": "anonymous@acme.com",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "status": "reported",
        "witnesses": [
            {"name": "David Lee", "role": "Accountant", "email": "david.lee@acme.com", "phone": "555-0103"}
        ],
        "category_data": {
            "harassment_type": "Verbal",
            "protected_class": "Gender",
            "frequency": "One-time"
        },
        "documents": {
            "complaint_email.txt": "Copy of the email sent to HR."
        },
        "analysis": {
            "categorization": {
                "suggested_type": "behavioral",
                "confidence": 0.98,
                "reasoning": "Description matches definition of verbal harassment.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "severity": {
                "suggested_severity": "high",
                "factors": ["Impact on victim", "Violation of code of conduct", "Potential legal liability"],
                "reasoning": "Allegations involve protected class characteristics.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    },
    {
        "type": "security",
        "title": "Unpiggybacked Entry Breach",
        "description": "Unknown individual observed following an employee through the secure rear entrance without badging in.",
        "incident_type": "other",
        "severity": "medium",
        "location": "Rear Entrance, Building A",
        "reported_by_name": "Security Desk",
        "reported_by_email": "security@acme.com",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "status": "resolved",
        "witnesses": [],
        "category_data": {
            "entry_point": "Rear Door",
            "time_of_day": "After hours"
        },
        "root_cause": "Employee negligence / Tailgating",
        "corrective_actions": "Employee received warning; security memo sent to all staff.",
        "documents": {
            "cctv_log.txt": "Log of CCTV footage review."
        },
        "analysis": {
            "recommendations": {
                "recommendations": [
                    {"action": "Send company-wide reminder about tailgating", "priority": "short_term", "owner": "Security Chief"},
                    {"action": "Install audible alarm for held doors", "priority": "long_term", "owner": "Facilities"}
                ],
                "summary": "Standard tailgating incident. Reinforce policy.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    },
    {
        "type": "conduct",
        "title": "Insubordination - Finance Team",
        "description": "Senior analyst refused direct order from manager to complete month-end report, citing 'unreasonable deadlines'. shouted at manager in open office.",
        "incident_type": "behavioral",
        "severity": "medium",
        "location": "Finance Department",
        "reported_by_name": "Alice Cooper",
        "reported_by_email": "alice.cooper@acme.com",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "status": "closed",
        "witnesses": [
            {"name": "Team Members", "role": "Various", "email": "finance.team@acme.com", "phone": ""}
        ],
        "category_data": {
            "conduct_type": "Insubordination",
            "public_incident": True
        },
        "documents": {
            "manager_statement.pdf": "Statement from the manager detailing the interaction."
        },
        "analysis": {
             "severity": {
                "suggested_severity": "medium",
                "factors": ["Public disruption", "Refusal of work duties"],
                "reasoning": "While disruptive, no violence or threats were involved.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    },
    {
        "type": "theft",
        "title": "Missing Laptop from IT Inventory",
        "description": "During quarterly audit, one MacBook Pro (Asset #IT-9988) was found missing from the secure storage locker.",
        "incident_type": "property",
        "severity": "high",
        "location": "IT Secure Storage",
        "reported_by_name": "Kevin Flynn",
        "reported_by_email": "kevin.flynn@acme.com",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "status": "investigating",
        "witnesses": [],
        "category_data": {
            "asset_value": 2500,
            "data_sensitivity": "Low (New device)"
        },
        "documents": {
            "audit_log.csv": "Inventory audit log showing discrepancy."
        },
        "analysis": {
            "root_cause": {
                "primary_cause": "Access Control Failure",
                "contributing_factors": ["Shared key access", "Lack of checkout log enforcement"],
                "prevention_suggestions": ["Implement digital badge access for locker", "Strict checkout logging"],
                "reasoning": "Too many people had access to the physical key.",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    }
]


async def seed_ir_incidents():
    """Seed IR Incidents with test data."""
    print("Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Get or create admin user
        admin = await conn.fetchrow("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if not admin:
            print("ERROR: No admin user found. Please create one first.")
            return

        admin_id = str(admin["id"])
        print(f"Using admin user: {admin_id}")

        created_count = 0

        for incident_data in INCIDENTS:
            incident_number = generate_incident_number()
            print(f"\nCreating incident: {incident_data['title']} ({incident_number})")

            # Create incident
            row = await conn.fetchrow(
                """
                INSERT INTO ir_incidents (
                    incident_number, title, description, incident_type, severity,
                    occurred_at, location, reported_by_name, reported_by_email,
                    witnesses, category_data, status,
                    root_cause, corrective_actions, created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING id
                """,
                incident_number,
                incident_data["title"],
                incident_data["description"],
                incident_data["incident_type"],
                incident_data["severity"],
                datetime.fromisoformat(incident_data["occurred_at"]).replace(tzinfo=None),
                incident_data["location"],
                incident_data["reported_by_name"],
                incident_data["reported_by_email"],
                json.dumps([w for w in incident_data.get("witnesses", [])]),
                json.dumps(incident_data.get("category_data", {})),
                incident_data["status"],
                incident_data.get("root_cause"),
                incident_data.get("corrective_actions"),
                admin_id
            )
            incident_id = str(row["id"])

            # Log creation
            await conn.execute(
                """
                INSERT INTO ir_audit_log (incident_id, user_id, action, entity_type, entity_id, details)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                incident_id, admin_id, "incident_created", "incident", incident_id,
                json.dumps({"title": incident_data["title"]})
            )

            # Add documents
            for doc_name, doc_desc in incident_data.get("documents", {}).items():
                doc_type = "report" if "report" in doc_name else "evidence"
                await conn.execute(
                    """
                    INSERT INTO ir_incident_documents (
                        incident_id, document_type, filename, file_path,
                        mime_type, file_size, uploaded_by
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    incident_id,
                    "other",
                    doc_name,
                    f"ir-incidents/{incident_id}/{doc_name}",
                    "application/octet-stream",
                    1024, # Dummy size
                    admin_id
                )
                print(f"  - Added document: {doc_name}")

            # Add analysis
            for analysis_type, analysis_data in incident_data.get("analysis", {}).items():
                await conn.execute(
                    """
                    INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
                    VALUES ($1, $2, $3)
                    """,
                    incident_id,
                    analysis_type,
                    json.dumps(analysis_data)
                )
                print(f"  - Added analysis: {analysis_type}")

            created_count += 1

        print("\n" + "=" * 60)
        print(f"SEED COMPLETE: Created {created_count} incidents")
        print("=" * 60)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed_ir_incidents())
