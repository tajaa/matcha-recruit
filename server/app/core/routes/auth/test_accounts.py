"""auth/test_accounts.py (split of the pre-2026-07-25 auth.py monolith)."""


import asyncio
import json
import logging
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, status
from pydantic import BaseModel, EmailStr, Field

from app.database import get_connection
from uuid import UUID

from app.core.models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister, EmployeeRegister,
    BusinessRegister, TestAccountRegister, TestAccountProvisionResponse,
    AdminProfile, ClientProfile, CandidateProfile, EmployeeProfile,
    BrokerTermsAcceptanceRequest, BrokerTermsAcceptanceResponse,
    BrokerClientInviteDetailsResponse, BrokerClientInviteAcceptRequest,
    BrokerBrandingRuntimeResponse,
    CurrentUser, TokenPayload,
    ChangePasswordRequest, ChangeEmailRequest, UpdateProfileRequest,
    CandidateBetaInfo, CandidateBetaListResponse, BetaToggleRequest,
    TokenAwardRequest, AllowedRolesRequest, CandidateSessionSummary
)
from app.core.services.auth import (
    hash_password, verify_password, verify_password_async,
    create_access_token, create_refresh_token, decode_token,
    create_email_verify_token, decode_email_verify_token,
)
from app.core.dependencies import (
    get_current_user, require_admin, require_broker, get_token_payload,
    session_revoked, revoke_user_sessions,
)
from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    default_company_features_json,
    merge_company_features,
)
from app.core.services.platform_settings import get_visible_features
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.config import get_settings


from app.core.routes.auth._shared import *  # noqa: F401,F403


TEST_ACCOUNT_FEATURES = {
    "policies": True,
    "handbooks": True,
    "compliance": True,
    "employees": True,
    "er_copilot": True,
    "incidents": True,
    "time_off": True,
    "accommodations": True,
    "training": True,
    "i9": True,
    "cobra": True,
    "separation_agreements": True,
}



def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        return "Test", "User"
    if len(parts) == 1:
        return parts[0], "User"
    return parts[0], " ".join(parts[1:])



async def _seed_test_account_data(
    conn,
    *,
    company_id: UUID,
    client_user_id: UUID,
    owner_name: str,
    owner_email: str,
    company_name: str,
    seed_password: str,
) -> dict[str, str | None]:
    """Seed representative data for enabled product features."""
    today = datetime.utcnow().date()
    suffix = str(company_id).split("-")[0]
    manager_seed_email = f"manager+{suffix}@matcha-seed.dev"
    sample_seed_email = f"employee+{suffix}@matcha-seed.dev"
    owner_first, owner_last = _split_name(owner_name)

    manager_employee_id = None
    sample_employee_id = None
    leave_request_id = None
    location_id = None
    er_case_id = None
    seeded_manager_email: str | None = None
    seeded_employee_email: str | None = None
    seeded_portal_password: str | None = None

    if await _table_exists(conn, "employees"):
        employees_has_user_id = await _column_exists(conn, "employees", "user_id")
        manager_user_id = None
        sample_user_id = None

        if employees_has_user_id and await _table_exists(conn, "users"):
            manager_user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'employee')
                RETURNING id
                """,
                manager_seed_email,
                hash_password(seed_password),
            )
            sample_user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'employee')
                RETURNING id
                """,
                sample_seed_email,
                hash_password(seed_password),
            )
            manager_user_id = manager_user["id"] if manager_user else None
            sample_user_id = sample_user["id"] if sample_user else None
            if manager_user_id:
                seeded_manager_email = manager_seed_email
            if sample_user_id:
                seeded_employee_email = sample_seed_email
            if manager_user_id or sample_user_id:
                seeded_portal_password = seed_password

        if employees_has_user_id and manager_user_id:
            manager = await conn.fetchrow(
                """
                INSERT INTO employees (
                    org_id, user_id, email, first_name, last_name, work_state, employment_type, start_date
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                company_id,
                manager_user_id,
                manager_seed_email,
                owner_first,
                owner_last,
                "CA",
                "full_time",
                today - timedelta(days=420),
            )
        else:
            manager = await conn.fetchrow(
                """
                INSERT INTO employees (org_id, email, first_name, last_name, work_state, employment_type, start_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                company_id,
                manager_seed_email,
                owner_first,
                owner_last,
                "CA",
                "full_time",
                today - timedelta(days=420),
            )
        manager_employee_id = manager["id"] if manager else None

        if employees_has_user_id and sample_user_id:
            sample = await conn.fetchrow(
                """
                INSERT INTO employees (
                    org_id, user_id, email, first_name, last_name, work_state, employment_type, start_date, manager_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                company_id,
                sample_user_id,
                sample_seed_email,
                "Jordan",
                "Case",
                "CA",
                "full_time",
                today - timedelta(days=210),
                manager_employee_id,
            )
        else:
            sample = await conn.fetchrow(
                """
                INSERT INTO employees (org_id, email, first_name, last_name, work_state, employment_type, start_date, manager_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                company_id,
                sample_seed_email,
                "Jordan",
                "Case",
                "CA",
                "full_time",
                today - timedelta(days=210),
                manager_employee_id,
            )
        sample_employee_id = sample["id"] if sample else None

    if await _table_exists(conn, "employee_career_profiles"):
        if sample_employee_id:
            await conn.execute(
                """
                INSERT INTO employee_career_profiles (
                    employee_id, org_id, target_roles, target_departments, skills, interests, mobility_opt_in, visibility
                )
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, true, 'private')
                ON CONFLICT (employee_id)
                DO UPDATE SET
                    target_roles = EXCLUDED.target_roles,
                    target_departments = EXCLUDED.target_departments,
                    skills = EXCLUDED.skills,
                    interests = EXCLUDED.interests,
                    mobility_opt_in = EXCLUDED.mobility_opt_in,
                    visibility = EXCLUDED.visibility,
                    updated_at = NOW()
                """,
                sample_employee_id,
                company_id,
                json.dumps(["Senior Data Analyst", "Analytics Manager"]),
                json.dumps(["Data", "Operations"]),
                json.dumps(["SQL", "Python", "A/B Testing", "Stakeholder Communication"]),
                json.dumps(["forecasting", "process improvement", "cross-functional projects"]),
            )

        if manager_employee_id:
            await conn.execute(
                """
                INSERT INTO employee_career_profiles (
                    employee_id, org_id, target_roles, target_departments, skills, interests, mobility_opt_in, visibility
                )
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, false, 'manager_visible')
                ON CONFLICT (employee_id)
                DO UPDATE SET
                    target_roles = EXCLUDED.target_roles,
                    target_departments = EXCLUDED.target_departments,
                    skills = EXCLUDED.skills,
                    interests = EXCLUDED.interests,
                    mobility_opt_in = EXCLUDED.mobility_opt_in,
                    visibility = EXCLUDED.visibility,
                    updated_at = NOW()
                """,
                manager_employee_id,
                company_id,
                json.dumps(["People Manager"]),
                json.dumps(["Operations"]),
                json.dumps(["Coaching", "Project Planning", "Stakeholder Management"]),
                json.dumps(["leadership development", "retention"]),
            )

    role_opportunity_id = None
    project_opportunity_id = None
    if await _table_exists(conn, "internal_opportunities"):
        role_row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunities (
                org_id, type, title, department, description,
                required_skills, preferred_skills, duration_weeks, status, created_by
            )
            VALUES ($1, 'role', $2, $3, $4, $5::jsonb, $6::jsonb, NULL, 'active', $7)
            RETURNING id
            """,
            company_id,
            "Senior Data Analyst (Internal Mobility Pilot)",
            "Data",
            (
                "Partner with Product and Operations to shape KPI strategy, "
                "run experiments, and deliver monthly leadership insights."
            ),
            json.dumps(["SQL", "Python", "Stakeholder Communication"]),
            json.dumps(["Looker", "Experimentation", "Roadmapping"]),
            client_user_id,
        )
        role_opportunity_id = role_row["id"] if role_row else None

        project_row = await conn.fetchrow(
            """
            INSERT INTO internal_opportunities (
                org_id, type, title, department, description,
                required_skills, preferred_skills, duration_weeks, status, created_by
            )
            VALUES ($1, 'project', $2, $3, $4, $5::jsonb, $6::jsonb, 10, 'active', $7)
            RETURNING id
            """,
            company_id,
            "Revenue Operations Sprint",
            "Operations",
            (
                "Join a 10-week cross-functional sprint to redesign lead routing, "
                "instrument conversion metrics, and improve handoff quality."
            ),
            json.dumps(["SQL", "Process Mapping", "Cross-functional Collaboration"]),
            json.dumps(["CRM Analytics", "Change Management"]),
            client_user_id,
        )
        project_opportunity_id = project_row["id"] if project_row else None

        await conn.execute(
            """
            INSERT INTO internal_opportunities (
                org_id, type, title, department, description,
                required_skills, preferred_skills, duration_weeks, status, created_by
            )
            VALUES ($1, 'role', $2, $3, $4, $5::jsonb, $6::jsonb, NULL, 'draft', $7)
            """,
            company_id,
            "People Analytics Lead",
            "People",
            "Draft opening planned for next quarter to stand up workforce planning analytics.",
            json.dumps(["Workforce Analytics", "SQL", "Storytelling"]),
            json.dumps(["Tableau", "Org Design"]),
            client_user_id,
        )

    if sample_employee_id and await _table_exists(conn, "internal_opportunity_matches"):
        if role_opportunity_id:
            await conn.execute(
                """
                INSERT INTO internal_opportunity_matches (
                    employee_id, opportunity_id, match_score, reasons, status
                )
                VALUES ($1, $2, 92.4, $3::jsonb, 'applied')
                ON CONFLICT (employee_id, opportunity_id)
                DO UPDATE SET
                    match_score = EXCLUDED.match_score,
                    reasons = EXCLUDED.reasons,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                """,
                sample_employee_id,
                role_opportunity_id,
                json.dumps(
                    {
                        "matched_skills": ["SQL", "Python", "Stakeholder Communication"],
                        "missing_skills": [],
                        "preferred_matched_skills": ["Experimentation"],
                        "alignment_signals": ["target_role_match", "target_department_match"],
                        "component_scores": {
                            "required_skill_fit": 100.0,
                            "preferred_skill_fit": 33.3,
                            "interest_alignment": 100.0,
                            "level_fit": 88.0,
                        },
                    }
                ),
            )

        if project_opportunity_id:
            await conn.execute(
                """
                INSERT INTO internal_opportunity_matches (
                    employee_id, opportunity_id, match_score, reasons, status
                )
                VALUES ($1, $2, 84.1, $3::jsonb, 'saved')
                ON CONFLICT (employee_id, opportunity_id)
                DO UPDATE SET
                    match_score = EXCLUDED.match_score,
                    reasons = EXCLUDED.reasons,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                """,
                sample_employee_id,
                project_opportunity_id,
                json.dumps(
                    {
                        "matched_skills": ["SQL", "Cross-functional Collaboration"],
                        "missing_skills": ["Process Mapping"],
                        "preferred_matched_skills": [],
                        "alignment_signals": ["target_department_match", "interest_match"],
                        "component_scores": {
                            "required_skill_fit": 66.7,
                            "preferred_skill_fit": 0.0,
                            "interest_alignment": 100.0,
                            "level_fit": 90.0,
                        },
                    }
                ),
            )

    if (
        sample_employee_id
        and role_opportunity_id
        and await _table_exists(conn, "internal_opportunity_applications")
    ):
        await conn.execute(
            """
            INSERT INTO internal_opportunity_applications (
                employee_id, opportunity_id, status, employee_notes,
                submitted_at, reviewed_by, reviewed_at, manager_notified_at
            )
            VALUES ($1, $2, 'in_review', $3, NOW() - INTERVAL '2 days', $4, NOW() - INTERVAL '1 day', NOW() - INTERVAL '12 hours')
            ON CONFLICT (employee_id, opportunity_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                employee_notes = EXCLUDED.employee_notes,
                submitted_at = EXCLUDED.submitted_at,
                reviewed_by = EXCLUDED.reviewed_by,
                reviewed_at = EXCLUDED.reviewed_at,
                manager_notified_at = EXCLUDED.manager_notified_at,
                updated_at = NOW()
            """,
            sample_employee_id,
            role_opportunity_id,
            "I have led weekly KPI reviews and want broader ownership across Product and Operations.",
            client_user_id,
        )

    if sample_employee_id and await _table_exists(conn, "pto_balances"):
        current_year = today.year
        await conn.execute(
            """
            INSERT INTO pto_balances (employee_id, balance_hours, accrued_hours, used_hours, year)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (employee_id, year) DO NOTHING
            """,
            sample_employee_id,
            96,
            120,
            24,
            current_year,
        )

        if manager_employee_id:
            await conn.execute(
                """
                INSERT INTO pto_balances (employee_id, balance_hours, accrued_hours, used_hours, year)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (employee_id, year) DO NOTHING
                """,
                manager_employee_id,
                128,
                140,
                12,
                current_year,
            )

    if sample_employee_id and await _table_exists(conn, "pto_requests"):
        await conn.execute(
            """
            INSERT INTO pto_requests (
                employee_id, request_type, start_date, end_date, hours, reason, status, approved_by, approved_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """,
            sample_employee_id,
            "vacation",
            today + timedelta(days=21),
            today + timedelta(days=23),
            24,
            "Family travel",
            "approved",
            manager_employee_id,
        )

    if sample_employee_id and await _table_exists(conn, "leave_requests"):
        leave_row = await conn.fetchrow(
            """
            INSERT INTO leave_requests (
                employee_id, org_id, leave_type, reason,
                start_date, end_date, expected_return_date,
                status, intermittent, hours_approved, reviewed_by, reviewed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'requested', false, $8, $9, NOW())
            RETURNING id
            """,
            sample_employee_id,
            company_id,
            "medical",
            "Recovery from a non-work-related injury.",
            today + timedelta(days=10),
            today + timedelta(days=24),
            today + timedelta(days=25),
            120,
            client_user_id,
        )
        leave_request_id = leave_row["id"] if leave_row else None

        if await _column_exists(conn, "leave_requests", "eligibility_data"):
            await conn.execute(
                """
                UPDATE leave_requests
                SET eligibility_data = $2::jsonb
                WHERE id = $1
                """,
                leave_request_id,
                json.dumps(
                    {
                        "fmla": {
                            "eligible": True,
                            "program": "fmla",
                            "label": "Family and Medical Leave Act (FMLA)",
                            "reasons": [],
                        }
                    }
                ),
            )

    if sample_employee_id and await _table_exists(conn, "employee_hours_log"):
        await conn.execute(
            """
            INSERT INTO employee_hours_log (employee_id, org_id, period_start, period_end, hours_worked, source)
            VALUES ($1, $2, $3, $4, $5, 'manual')
            ON CONFLICT (employee_id, period_start, period_end) DO NOTHING
            """,
            sample_employee_id,
            company_id,
            today - timedelta(days=28),
            today - timedelta(days=1),
            160,
        )

    if leave_request_id and await _table_exists(conn, "leave_deadlines"):
        await conn.execute(
            """
            INSERT INTO leave_deadlines (leave_request_id, org_id, deadline_type, due_date, status, notes)
            VALUES ($1, $2, $3, $4, 'pending', $5)
            """,
            leave_request_id,
            company_id,
            "initial_notice",
            today + timedelta(days=5),
            "Send rights & responsibilities notice to employee.",
        )

    if await _table_exists(conn, "policies"):
        await conn.execute(
            """
            INSERT INTO policies (company_id, title, description, content, version, status, created_by)
            VALUES ($1, $2, $3, $4, '1.0', 'active', $5)
            """,
            company_id,
            "Code of Conduct",
            "Behavior and workplace standards for all employees.",
            (
                "# Code of Conduct\n\n"
                "All team members must maintain respectful communication, avoid retaliation, "
                "and report concerns promptly through approved channels."
            ),
            client_user_id,
        )

    if await _table_exists(conn, "offer_letters"):
        has_offer_company_id = await _column_exists(conn, "offer_letters", "company_id")
        if has_offer_company_id:
            await conn.execute(
                """
                INSERT INTO offer_letters (
                    candidate_name, position_title, company_name, company_id, status,
                    salary, start_date, employment_type, location, benefits,
                    manager_name, manager_title, expiration_date, company_logo_url
                )
                VALUES ($1, $2, $3, $4, 'draft', $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                "Morgan Riley",
                "Operations Specialist",
                company_name,
                company_id,
                "$82,000",
                datetime.utcnow() + timedelta(days=20),
                "Full-time",
                "Los Angeles, CA",
                "Medical, dental, vision, 401(k), PTO",
                owner_name,
                "HR Lead",
                datetime.utcnow() + timedelta(days=35),
                "https://placehold.co/200x60?text=Company+Logo",
            )

    if await _table_exists(conn, "business_locations"):
        location_row = await conn.fetchrow(
            """
            INSERT INTO business_locations (company_id, name, address, city, state, county, zipcode, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, true)
            RETURNING id
            """,
            company_id,
            "HQ - Los Angeles",
            "100 Main St",
            "Los Angeles",
            "CA",
            "Los Angeles",
            "90012",
        )
        location_id = location_row["id"] if location_row else None

    if location_id and await _table_exists(conn, "compliance_requirements"):
        req_row = await conn.fetchrow(
            """
            INSERT INTO compliance_requirements (
                location_id, category, jurisdiction_level, jurisdiction_name,
                title, description, current_value, source_name, source_url
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            location_id,
            "minimum_wage",
            "state",
            "California",
            "California Minimum Wage",
            "Minimum hourly wage requirement for exempt and non-exempt employees.",
            "$16.00/hour",
            "CA DIR",
            "https://www.dir.ca.gov/dlse/minimum_wage.htm",
        )
        requirement_id = req_row["id"] if req_row else None

        if await _table_exists(conn, "compliance_alerts"):
            await conn.execute(
                """
                INSERT INTO compliance_alerts (
                    location_id, company_id, requirement_id, title, message, severity, status, category, source_name
                )
                VALUES ($1, $2, $3, $4, $5, 'warning', 'unread', 'minimum_wage', 'CA DIR')
                """,
                location_id,
                company_id,
                requirement_id,
                "Minimum wage update review due",
                "California minimum wage rules were refreshed. Confirm payroll settings are aligned.",
            )

    if location_id and await _table_exists(conn, "ir_incidents"):
        incident_number = f"IR-{datetime.utcnow().year}-{suffix.upper()[:6]}"
        await conn.execute(
            """
            INSERT INTO ir_incidents (
                incident_number, title, description, incident_type, severity, status,
                occurred_at, location, reported_by_name, reported_by_email,
                witnesses, category_data, company_id, location_id, created_by
            )
            VALUES (
                $1, $2, $3, $4, $5, 'reported',
                $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12, $13, $14
            )
            """,
            incident_number,
            "Slip in warehouse aisle",
            "Employee reported a slip hazard near receiving; no severe injuries.",
            "safety",
            "medium",
            datetime.utcnow() - timedelta(days=2),
            "Receiving - Aisle B",
            owner_name,
            owner_email,
            json.dumps([{"name": "Jordan Case", "contact": "employee witness"}]),
            json.dumps({"hazard_type": "spill", "ppe_used": True}),
            company_id,
            location_id,
            client_user_id,
        )

    if await _table_exists(conn, "er_cases"):
        has_er_company_id = await _column_exists(conn, "er_cases", "company_id")
        er_insert_query = """
            INSERT INTO er_cases (case_number, title, description, status, created_by, company_id)
            VALUES ($1, $2, $3, 'open', $4, $5)
            RETURNING id
        """ if has_er_company_id else """
            INSERT INTO er_cases (case_number, title, description, status, created_by)
            VALUES ($1, $2, $3, 'open', $4)
            RETURNING id
        """
        er_case = await conn.fetchrow(
            er_insert_query,
            f"ER-{datetime.utcnow().year}-{today.month:02d}-{suffix.upper()[:4]}",
            "Sample ER Investigation",
            "Conflict between witness statements during an employee complaint review.",
            client_user_id,
            company_id,
        ) if has_er_company_id else await conn.fetchrow(
            er_insert_query,
            f"ER-{datetime.utcnow().year}-{today.month:02d}-{suffix.upper()[:4]}",
            "Sample ER Investigation",
            "Conflict between witness statements during an employee complaint review.",
            client_user_id,
        )
        er_case_id = er_case["id"] if er_case else None

    if er_case_id and await _table_exists(conn, "er_case_documents"):
        er_doc = await conn.fetchrow(
            """
            INSERT INTO er_case_documents (
                case_id, document_type, filename, file_path, mime_type,
                file_size, pii_scrubbed, original_text, scrubbed_text,
                processing_status, parsed_at, uploaded_by
            )
            VALUES (
                $1, 'email', $2, $3, 'text/plain',
                $4, true, $5, $6, 'completed', NOW(), $7
            )
            RETURNING id
            """,
            er_case_id,
            "witness-summary.txt",
            f"er-documents/{er_case_id}/witness-summary.txt",
            2048,
            (
                "Witness A stated the manager was frustrated and raised their voice.\n"
                "Witness B stated the manager remained calm and professional."
            ),
            (
                "Witness A stated the manager was frustrated and raised their voice.\n"
                "Witness B stated the manager remained calm and professional."
            ),
            client_user_id,
        )
        er_doc_id = er_doc["id"] if er_doc else None

        if er_doc_id and await _table_exists(conn, "er_evidence_chunks"):
            await conn.execute(
                """
                INSERT INTO er_evidence_chunks (document_id, case_id, chunk_index, content, speaker, line_start, line_end, metadata)
                VALUES ($1, $2, 0, $3, 'Witness A', 1, 2, $4::jsonb)
                """,
                er_doc_id,
                er_case_id,
                "Witness A: I observed the manager visibly frustrated during the meeting.",
                json.dumps({"search_mode": "seed", "source": "demo"}),
            )
            await conn.execute(
                """
                INSERT INTO er_evidence_chunks (document_id, case_id, chunk_index, content, speaker, line_start, line_end, metadata)
                VALUES ($1, $2, 1, $3, 'Witness B', 3, 4, $4::jsonb)
                """,
                er_doc_id,
                er_case_id,
                "Witness B: The manager stayed calm and focused on problem solving.",
                json.dumps({"search_mode": "seed", "source": "demo"}),
            )

        if await _table_exists(conn, "er_case_analysis"):
            source_docs = json.dumps([str(er_doc_id)]) if er_doc_id else json.dumps([])
            await conn.execute(
                """
                INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, source_documents, generated_by)
                VALUES ($1, 'timeline', $2::jsonb, $3::jsonb, $4)
                ON CONFLICT (case_id, analysis_type) DO NOTHING
                """,
                er_case_id,
                json.dumps(
                    {
                        "events": [
                            {
                                "date": str(today - timedelta(days=3)),
                                "description": "Witness interviews captured conflicting accounts.",
                                "participants": ["Witness A", "Witness B"],
                                "source_document_id": str(er_doc_id) if er_doc_id else "seed-doc",
                                "source_location": "Lines 1-4",
                                "confidence": "medium",
                                "evidence_quote": "Accounts differ on manager tone and behavior.",
                            }
                        ],
                        "gaps_identified": ["No camera footage was provided."],
                        "timeline_summary": "Statements conflict on key behavior details and require follow-up.",
                    }
                ),
                source_docs,
                client_user_id,
            )
            await conn.execute(
                """
                INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, source_documents, generated_by)
                VALUES ($1, 'discrepancies', $2::jsonb, $3::jsonb, $4)
                ON CONFLICT (case_id, analysis_type) DO NOTHING
                """,
                er_case_id,
                json.dumps(
                    {
                        "discrepancies": [
                            {
                                "type": "contradiction",
                                "severity": "medium",
                                "description": "Witnesses describe opposite manager demeanor.",
                                "statement_1": {
                                    "source_document_id": str(er_doc_id) if er_doc_id else "seed-doc",
                                    "speaker": "Witness A",
                                    "quote": "The manager seemed frustrated.",
                                    "location": "Line 1",
                                },
                                "statement_2": {
                                    "source_document_id": str(er_doc_id) if er_doc_id else "seed-doc",
                                    "speaker": "Witness B",
                                    "quote": "The manager stayed calm.",
                                    "location": "Line 3",
                                },
                                "analysis": "Additional corroboration is required before conclusions.",
                            }
                        ],
                        "credibility_notes": [],
                        "summary": "At least one key discrepancy was identified for review.",
                    }
                ),
                source_docs,
                client_user_id,
            )
            await conn.execute(
                """
                INSERT INTO er_case_analysis (case_id, analysis_type, analysis_data, source_documents, generated_by)
                VALUES ($1, 'policy_check', $2::jsonb, $3::jsonb, $4)
                ON CONFLICT (case_id, analysis_type) DO NOTHING
                """,
                er_case_id,
                json.dumps(
                    {
                        "violations": [
                            {
                                "policy_section": "Respectful Workplace",
                                "policy_text": "All leaders must maintain professional conduct.",
                                "severity": "minor",
                                "evidence": [
                                    {
                                        "source_document_id": str(er_doc_id) if er_doc_id else "seed-doc",
                                        "quote": "Witness noted frustration during the meeting.",
                                        "location": "Line 1",
                                        "how_it_violates": "Potentially inconsistent with conduct expectations.",
                                    }
                                ],
                                "analysis": "Monitor and coach communication behaviors.",
                            }
                        ],
                        "policies_potentially_applicable": ["Code of Conduct", "Respectful Workplace"],
                        "summary": "Potential low-severity conduct risk found.",
                    }
                ),
                source_docs,
                client_user_id,
            )

    if sample_employee_id and await _table_exists(conn, "accommodation_cases"):
        await conn.execute(
            """
            INSERT INTO accommodation_cases (
                case_number, org_id, employee_id, linked_leave_id, title, description,
                disability_category, requested_accommodation, status, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'requested', $9)
            """,
            f"AC-{datetime.utcnow().strftime('%Y%m%d-%H%M')}-{suffix.upper()[:4]}",
            company_id,
            sample_employee_id,
            leave_request_id,
            "Standing desk and modified duties",
            "Employee requested temporary duty modifications while recovering.",
            "Physical",
            "Standing desk and reduced lifting requirements for 30 days.",
            client_user_id,
        )

    return {
        "seeded_manager_email": seeded_manager_email,
        "seeded_employee_email": seeded_employee_email,
        "seeded_portal_password": seeded_portal_password,
    }



@router.post("/register/test-account", response_model=TestAccountProvisionResponse)
async def register_test_account(
    request: TestAccountRegister,
    current_admin: CurrentUser = Depends(require_admin),
):
    """Provision an approved client test account with seeded data (admin only)."""
    company_name = (request.company_name or "").strip() or f"{request.name.strip() or 'Test User'} Test Account"
    generated_password = not bool(request.password and request.password.strip())
    password = request.password.strip() if request.password else secrets.token_urlsafe(12)

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            company = await conn.fetchrow(
                """
                INSERT INTO companies (name, industry, size, status, approved_at, enabled_features)
                VALUES ($1, $2, $3, 'approved', NOW(), $4::jsonb)
                RETURNING id
                """,
                company_name,
                request.industry,
                request.company_size,
                json.dumps(TEST_ACCOUNT_FEATURES),
            )
            company_id = company["id"]

            password_hash = hash_password(password)
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'client')
                RETURNING id, email, role, is_active, created_at
                """,
                request.email,
                password_hash,
            )

            await conn.execute(
                """
                INSERT INTO clients (user_id, company_id, name, phone, job_title)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user["id"],
                company_id,
                request.name,
                request.phone,
                request.job_title,
            )

            await conn.execute(
                "UPDATE companies SET owner_id = $1 WHERE id = $2",
                user["id"],
                company_id,
            )

            seeded_data = await _seed_test_account_data(
                conn,
                company_id=company_id,
                client_user_id=user["id"],
                owner_name=request.name,
                owner_email=request.email,
                company_name=company_name,
                seed_password=password,
            )

            logger.info(
                "Admin %s created seeded test account for %s (company=%s)",
                current_admin.email,
                request.email,
                company_id,
            )

        return TestAccountProvisionResponse(
            status="created",
            message="Test account created with seeded feature data",
            company_id=company_id,
            company_name=company_name,
            user_id=user["id"],
            email=user["email"],
            password=password,
            generated_password=generated_password,
            seeded_manager_email=seeded_data.get("seeded_manager_email"),
            seeded_employee_email=seeded_data.get("seeded_employee_email"),
            seeded_portal_password=seeded_data.get("seeded_portal_password"),
        )

