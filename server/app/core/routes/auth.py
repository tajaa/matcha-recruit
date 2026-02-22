import json
import logging
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request, status

from ...database import get_connection
from uuid import UUID

from ..models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister, EmployeeRegister,
    BusinessRegister, TestAccountRegister, TestAccountProvisionResponse,
    AdminProfile, ClientProfile, CandidateProfile, EmployeeProfile,
    BrokerTermsAcceptanceRequest, BrokerTermsAcceptanceResponse,
    BrokerClientInviteDetailsResponse, BrokerClientInviteAcceptRequest,
    BrokerBrandingRuntimeResponse,
    CurrentUser,
    ChangePasswordRequest, ChangeEmailRequest, UpdateProfileRequest,
    CandidateBetaInfo, CandidateBetaListResponse, BetaToggleRequest,
    TokenAwardRequest, AllowedRolesRequest, CandidateSessionSummary
)
from ..services.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from ..dependencies import get_current_user, require_admin, require_broker
from ..feature_flags import (
    default_company_features_json,
    merge_company_features,
)
from ...config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

TEST_ACCOUNT_FEATURES = {
    "offer_letters": True,
    "policies": True,
    "handbooks": True,
    "compliance": True,
    "compliance_plus": True,
    "employees": True,
    "vibe_checks": True,
    "enps": True,
    "performance_reviews": True,
    "er_copilot": True,
    "incidents": True,
    "time_off": True,
    "accommodations": True,
    "internal_mobility": True,
}

BROKER_BRANDING_KEY_RE = re.compile(r"^[a-z0-9-]{2,120}$")


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.strip().split() if part]
    if not parts:
        return "Test", "User"
    if len(parts) == 1:
        return parts[0], "User"
    return parts[0], " ".join(parts[1:])


async def _table_exists(conn, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table_name))


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = $1 AND column_name = $2
            )
            """,
            table_name,
            column_name,
        )
    )


async def _upsert_business_headcount_profile(
    conn,
    *,
    company_id: UUID,
    company_name: str,
    owner_name: str,
    headcount: int,
    updated_by: UUID,
) -> None:
    if not await _table_exists(conn, "company_handbook_profiles"):
        logger.warning(
            "Skipping headcount profile seed for company %s because company_handbook_profiles table is missing",
            company_id,
        )
        return

    legal_name = company_name.strip() or "Company"
    ceo_or_president = owner_name.strip() or "Company Leadership"

    await conn.execute(
        """
        INSERT INTO company_handbook_profiles (
            company_id, legal_name, dba, ceo_or_president, headcount,
            remote_workers, minors, tipped_employees, union_employees, federal_contracts,
            group_health_insurance, background_checks, hourly_employees,
            salaried_employees, commissioned_employees, tip_pooling, updated_by, updated_at
        )
        VALUES (
            $1, $2, NULL, $3, $4,
            false, false, false, false, false,
            false, false, true,
            false, false, false, $5, NOW()
        )
        ON CONFLICT (company_id)
        DO UPDATE SET
            legal_name = EXCLUDED.legal_name,
            headcount = EXCLUDED.headcount,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
        """,
        company_id,
        legal_name,
        ceo_or_president,
        headcount,
        updated_by,
    )


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

    if await _table_exists(conn, "vibe_check_configs"):
        await conn.execute(
            """
            INSERT INTO vibe_check_configs (org_id, frequency, enabled, is_anonymous, questions)
            VALUES ($1, 'weekly', true, true, $2::jsonb)
            ON CONFLICT (org_id) DO UPDATE SET
                frequency = EXCLUDED.frequency,
                enabled = EXCLUDED.enabled,
                is_anonymous = EXCLUDED.is_anonymous,
                questions = EXCLUDED.questions,
                updated_at = NOW()
            """,
            company_id,
            json.dumps(
                [
                    {"id": "mood", "text": "How are you feeling this week?", "type": "rating"},
                    {"id": "blockers", "text": "Any blockers or concerns to share?", "type": "text"},
                ]
            ),
        )

    if sample_employee_id and await _table_exists(conn, "vibe_check_responses"):
        await conn.execute(
            """
            INSERT INTO vibe_check_responses (org_id, employee_id, mood_rating, comment, sentiment_analysis)
            VALUES ($1, $2, 4, $3, $4::jsonb)
            """,
            company_id,
            sample_employee_id,
            "Team collaboration improved after process updates.",
            json.dumps({"sentiment_score": 0.61, "themes": ["collaboration", "clarity"]}),
        )

    enps_survey_id = None
    if await _table_exists(conn, "enps_surveys"):
        survey = await conn.fetchrow(
            """
            INSERT INTO enps_surveys (
                org_id, title, description, start_date, end_date, status, is_anonymous, custom_question, created_by
            )
            VALUES ($1, $2, $3, $4, $5, 'active', true, $6, $7)
            RETURNING id
            """,
            company_id,
            "Quarterly eNPS Pulse",
            "Quick pulse survey to track employee advocacy and engagement.",
            today - timedelta(days=2),
            today + timedelta(days=14),
            "What is one thing we could improve this quarter?",
            client_user_id,
        )
        enps_survey_id = survey["id"] if survey else None

    if enps_survey_id and sample_employee_id and await _table_exists(conn, "enps_responses"):
        await conn.execute(
            """
            INSERT INTO enps_responses (survey_id, employee_id, score, reason, category, sentiment_analysis)
            VALUES ($1, $2, 9, $3, 'promoter', $4::jsonb)
            ON CONFLICT (survey_id, employee_id) DO NOTHING
            """,
            enps_survey_id,
            sample_employee_id,
            "Great team support and clear direction from leadership.",
            json.dumps({"sentiment_score": 0.74, "themes": ["leadership", "support"]}),
        )

    review_template_id = None
    if await _table_exists(conn, "review_templates"):
        template = await conn.fetchrow(
            """
            INSERT INTO review_templates (org_id, name, description, categories, is_active)
            VALUES ($1, $2, $3, $4::jsonb, true)
            RETURNING id
            """,
            company_id,
            "Core Competency Review",
            "Standard performance review covering execution, communication, and ownership.",
            json.dumps(
                [
                    {"id": "execution", "label": "Execution"},
                    {"id": "communication", "label": "Communication"},
                    {"id": "ownership", "label": "Ownership"},
                ]
            ),
        )
        review_template_id = template["id"] if template else None

    review_cycle_id = None
    if review_template_id and await _table_exists(conn, "review_cycles"):
        cycle = await conn.fetchrow(
            """
            INSERT INTO review_cycles (org_id, title, description, start_date, end_date, status, template_id)
            VALUES ($1, $2, $3, $4, $5, 'active', $6)
            RETURNING id
            """,
            company_id,
            "Q1 Performance Cycle",
            "Quarterly performance cycle for active employees.",
            today - timedelta(days=7),
            today + timedelta(days=21),
            review_template_id,
        )
        review_cycle_id = cycle["id"] if cycle else None

    if (
        review_cycle_id
        and sample_employee_id
        and manager_employee_id
        and await _table_exists(conn, "performance_reviews")
    ):
        await conn.execute(
            """
            INSERT INTO performance_reviews (cycle_id, employee_id, manager_id, status)
            VALUES ($1, $2, $3, 'pending')
            ON CONFLICT (cycle_id, employee_id) DO NOTHING
            """,
            review_cycle_id,
            sample_employee_id,
            manager_employee_id,
        )

    return {
        "seeded_manager_email": seeded_manager_email,
        "seeded_employee_email": seeded_employee_email,
        "seeded_portal_password": seeded_portal_password,
    }


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate user and return tokens."""
    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, password_hash, role, is_active, created_at, last_login FROM users WHERE email = $1",
            request.email
        )

        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled"
            )

        # Update last login
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE id = $1",
            user["id"]
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=user["last_login"]
            )
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    async with get_connection() as conn:
        user = await conn.fetchrow(
            "SELECT id, email, role, is_active, created_at, last_login FROM users WHERE id = $1",
            payload.sub
        )

        if not user or not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        new_refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=user["last_login"]
            )
        )


@router.post("/register/admin", response_model=TokenResponse, dependencies=[Depends(require_admin)])
async def register_admin(request: AdminRegister):
    """Register a new admin (admin only)."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'admin')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create admin profile
        await conn.execute(
            "INSERT INTO admins (user_id, name) VALUES ($1, $2)",
            user["id"], request.name
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=None
            )
        )


@router.post("/register/client", response_model=TokenResponse)
async def register_client(request: ClientRegister):
    """Register a new client linked to a company."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", request.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'client')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create client profile
        await conn.execute(
            """
            INSERT INTO clients (user_id, company_id, name, phone, job_title)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user["id"], request.company_id, request.name, request.phone, request.job_title
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=None
            )
        )


@router.get("/business-invite/{token}")
async def validate_business_invite(token: str):
    """Validate a business invite token (public, no auth required)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, expires_at, note
            FROM business_invitations
            WHERE token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invite not found or invalid")

        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Invite is no longer valid (status: {row['status']})")

        if row["expires_at"] < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Invite has expired")

        return {
            "valid": True,
            "expires_at": row["expires_at"].isoformat(),
            "note": row["note"],
        }


@router.get("/broker-branding/{broker_key}", response_model=BrokerBrandingRuntimeResponse)
async def get_broker_branding_runtime(broker_key: str):
    """Resolve broker branding config by broker slug or login subdomain."""
    key = (broker_key or "").strip().lower()
    if not BROKER_BRANDING_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="broker_key must be 2-120 chars [a-z0-9-]")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                b.id as broker_id,
                b.slug as broker_slug,
                b.name as broker_name,
                COALESCE(cfg.branding_mode, 'direct') as branding_mode,
                COALESCE(NULLIF(cfg.brand_display_name, ''), b.name) as brand_display_name,
                cfg.brand_legal_name,
                cfg.logo_url,
                cfg.favicon_url,
                cfg.primary_color,
                cfg.secondary_color,
                cfg.login_subdomain,
                cfg.custom_login_url,
                cfg.support_email,
                cfg.support_phone,
                cfg.support_url,
                cfg.email_from_name,
                cfg.email_from_address,
                COALESCE(cfg.powered_by_badge, true) as powered_by_badge,
                COALESCE(cfg.hide_matcha_identity, false) as hide_matcha_identity,
                COALESCE(cfg.mobile_branding_enabled, false) as mobile_branding_enabled,
                COALESCE(cfg.theme, '{}'::jsonb) as theme,
                CASE WHEN cfg.login_subdomain = $1 THEN 'subdomain' ELSE 'slug' END as resolved_by
            FROM brokers b
            LEFT JOIN broker_branding_configs cfg ON cfg.broker_id = b.id
            WHERE b.status = 'active'
              AND (b.slug = $1 OR cfg.login_subdomain = $1)
            ORDER BY CASE WHEN cfg.login_subdomain = $1 THEN 0 ELSE 1 END, b.created_at ASC
            LIMIT 1
            """,
            key,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Broker branding not found")

    return BrokerBrandingRuntimeResponse(
        broker_id=row["broker_id"],
        broker_slug=row["broker_slug"],
        broker_name=row["broker_name"],
        branding_mode=row["branding_mode"],
        brand_display_name=row["brand_display_name"],
        brand_legal_name=row["brand_legal_name"],
        logo_url=row["logo_url"],
        favicon_url=row["favicon_url"],
        primary_color=row["primary_color"],
        secondary_color=row["secondary_color"],
        login_subdomain=row["login_subdomain"],
        custom_login_url=row["custom_login_url"],
        support_email=row["support_email"],
        support_phone=row["support_phone"],
        support_url=row["support_url"],
        email_from_name=row["email_from_name"],
        email_from_address=row["email_from_address"],
        powered_by_badge=bool(row["powered_by_badge"]),
        hide_matcha_identity=bool(row["hide_matcha_identity"]),
        mobile_branding_enabled=bool(row["mobile_branding_enabled"]),
        theme=_json_object(row["theme"]),
        resolved_by="subdomain" if row["resolved_by"] == "subdomain" else "slug",
    )


@router.get("/broker-client-invite/{token}", response_model=BrokerClientInviteDetailsResponse)
async def validate_broker_client_invite(token: str):
    """Validate a broker-generated client onboarding invite token."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                s.id, s.broker_id, s.company_id, s.status, s.invite_expires_at, s.contact_email,
                c.name as company_name,
                b.name as broker_name
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            JOIN brokers b ON b.id = s.broker_id
            WHERE s.invite_token = $1
            """,
            token,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Invite not found or invalid")

        if row["status"] != "invited":
            raise HTTPException(status_code=400, detail=f"Invite is no longer valid (status: {row['status']})")

        if not row["invite_expires_at"] or row["invite_expires_at"] < datetime.utcnow():
            await conn.execute(
                """
                UPDATE broker_client_setups
                SET status = 'expired',
                    expired_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                row["id"],
            )
            await conn.execute(
                """
                UPDATE broker_company_links
                SET status = 'terminated',
                    terminated_at = COALESCE(terminated_at, NOW()),
                    updated_at = NOW()
                WHERE broker_id = $1
                  AND company_id = $2
                  AND status = 'pending'
                """,
                row["broker_id"],
                row["company_id"],
            )
            raise HTTPException(status_code=400, detail="Invite has expired")

        if not row["contact_email"]:
            raise HTTPException(status_code=400, detail="Invite is missing contact email")

        return BrokerClientInviteDetailsResponse(
            valid=True,
            broker_name=row["broker_name"],
            company_name=row["company_name"],
            contact_email=row["contact_email"],
            invite_expires_at=row["invite_expires_at"],
        )


@router.post("/broker-client-invite/{token}/accept")
async def accept_broker_client_invite(token: str, request: BrokerClientInviteAcceptRequest):
    """Accept a broker client invite and provision the first company client admin user."""
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    async with get_connection() as conn:
        async with conn.transaction():
            invite = await conn.fetchrow(
                """
                SELECT
                    s.id, s.broker_id, s.company_id, s.status, s.invite_expires_at,
                    s.contact_name, s.contact_email, s.contact_phone,
                    c.name as company_name,
                    b.name as broker_name
                FROM broker_client_setups s
                JOIN companies c ON c.id = s.company_id
                JOIN brokers b ON b.id = s.broker_id
                WHERE s.invite_token = $1
                FOR UPDATE
                """,
                token,
            )
            if not invite:
                raise HTTPException(status_code=404, detail="Invite not found or invalid")

            if invite["status"] != "invited":
                raise HTTPException(status_code=400, detail=f"Invite is no longer valid (status: {invite['status']})")

            if not invite["invite_expires_at"] or invite["invite_expires_at"] < datetime.utcnow():
                await conn.execute(
                    """
                    UPDATE broker_client_setups
                    SET status = 'expired',
                        expired_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    invite["id"],
                )
                await conn.execute(
                    """
                    UPDATE broker_company_links
                    SET status = 'terminated',
                        terminated_at = COALESCE(terminated_at, NOW()),
                        updated_at = NOW()
                    WHERE broker_id = $1
                      AND company_id = $2
                      AND status = 'pending'
                    """,
                    invite["broker_id"],
                    invite["company_id"],
                )
                raise HTTPException(status_code=400, detail="Invite has expired")

            email = invite["contact_email"]
            if not email:
                raise HTTPException(status_code=400, detail="Invite is missing contact email")

            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", email)
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="An account with this email already exists. Please sign in or contact support.",
                )

            display_name = (request.name or invite["contact_name"] or email.split("@")[0]).strip()
            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'client')
                RETURNING id, email, role, is_active, created_at
                """,
                email,
                password_hash,
            )

            await conn.execute(
                """
                INSERT INTO clients (user_id, company_id, name, phone, job_title)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user["id"],
                invite["company_id"],
                display_name,
                request.phone or invite["contact_phone"],
                request.job_title,
            )

            await conn.execute(
                """
                UPDATE companies
                SET owner_id = $1,
                    status = 'approved',
                    approved_at = COALESCE(approved_at, NOW()),
                    rejection_reason = NULL
                WHERE id = $2
                """,
                user["id"],
                invite["company_id"],
            )

            await conn.execute(
                """
                UPDATE broker_client_setups
                SET status = 'activated',
                    activated_at = NOW(),
                    updated_at = NOW(),
                    updated_by = $1
                WHERE id = $2
                """,
                user["id"],
                invite["id"],
            )

            await conn.execute(
                """
                INSERT INTO broker_company_links (
                    broker_id, company_id, status, linked_at, activated_at, created_by, updated_at
                )
                VALUES ($1, $2, 'active', NOW(), NOW(), $3, NOW())
                ON CONFLICT (broker_id, company_id)
                DO UPDATE SET
                    status = 'active',
                    activated_at = COALESCE(broker_company_links.activated_at, NOW()),
                    terminated_at = NULL,
                    updated_at = NOW()
                """,
                invite["broker_id"],
                invite["company_id"],
                user["id"],
            )

            settings = get_settings()
            access_token = create_access_token(user["id"], user["email"], user["role"])
            refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": settings.jwt_access_token_expire_minutes * 60,
                "user": {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "role": user["role"],
                    "is_active": user["is_active"],
                    "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                    "last_login": None,
                },
                "company_status": "approved",
                "company_name": invite["company_name"],
                "broker_name": invite["broker_name"],
                "message": "Welcome! Your company onboarding has been activated.",
            }


@router.post("/register/business")
async def register_business(request: BusinessRegister):
    """
    Register a new business with first admin/client user.
    This creates:
    1. A new company (status='approved' if invite token provided, else 'pending')
    2. A client user linked to that company
    3. Returns auth tokens for immediate login

    If no invite_token, the business will need admin approval before accessing full features.
    """
    from ..services.email import get_email_service

    async with get_connection() as conn:
        async with conn.transaction():
            # Check if email already exists
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Validate and atomically reserve invite token if provided
            invitation = None
            if request.invite_token:
                invitation = await conn.fetchrow(
                    """UPDATE business_invitations
                       SET status = 'used', used_at = NOW()
                       WHERE token = $1 AND status = 'pending' AND expires_at > NOW()
                       RETURNING id""",
                    request.invite_token,
                )
                if not invitation:
                    raise HTTPException(status_code=400, detail="Invalid, expired, or already-used invite link")

            # Determine company status based on invite
            company_status = "approved" if invitation else "pending"

            # Step 1: Create company
            company = await conn.fetchrow(
                """INSERT INTO companies (name, industry, size, status, approved_at, enabled_features)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                   RETURNING id, name""",
                request.company_name, request.industry, request.company_size,
                company_status,
                datetime.utcnow() if invitation else None,
                default_company_features_json(),
            )
            company_id = company["id"]

            # Step 2: Create user with 'client' role
            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role)
                   VALUES ($1, $2, 'client')
                   RETURNING id, email, role, is_active, created_at""",
                request.email, password_hash
            )

            # Step 3: Create client profile linked to company
            await conn.execute(
                """INSERT INTO clients (user_id, company_id, name, phone, job_title)
                   VALUES ($1, $2, $3, $4, $5)""",
                user["id"], company_id, request.name, request.phone, request.job_title
            )

            # Step 4: Update company.owner_id to link back to user
            await conn.execute(
                "UPDATE companies SET owner_id = $1 WHERE id = $2",
                user["id"], company_id
            )

            # Seed profile data used by handbook/compliance flows.
            await _upsert_business_headcount_profile(
                conn,
                company_id=company_id,
                company_name=request.company_name,
                owner_name=request.name,
                headcount=request.headcount,
                updated_by=user["id"],
            )

            # Step 5: Link invitation to the new company
            if invitation:
                await conn.execute(
                    "UPDATE business_invitations SET used_by_company_id = $1 WHERE id = $2",
                    company_id, invitation["id"],
                )

            # Generate tokens
            settings = get_settings()
            access_token = create_access_token(user["id"], user["email"], user["role"])
            refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

            # Send appropriate email
            email_service = get_email_service()
            if invitation:
                await email_service.send_business_approved_email(
                    to_email=user["email"],
                    to_name=request.name,
                    company_name=request.company_name
                )
            else:
                await email_service.send_business_registration_pending_email(
                    to_email=user["email"],
                    to_name=request.name,
                    company_name=request.company_name
                )

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": settings.jwt_access_token_expire_minutes * 60,
                "user": {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "role": user["role"],
                    "is_active": user["is_active"],
                    "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                    "last_login": None
                },
                "company_status": company_status,
                "message": (
                    "Welcome! Your business account is approved and ready to use."
                    if invitation else
                    "Your business registration is pending approval. You will be notified once it's reviewed."
                ),
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


@router.post("/register/employee", response_model=TokenResponse)
async def register_employee(request: EmployeeRegister):
    """Register a new employee."""
    async with get_connection() as conn:
        # Check if email exists
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Verify company exists
        company = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", request.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'employee')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Create employee profile
        await conn.execute(
            """
            INSERT INTO employees (user_id, org_id, email, first_name, last_name, work_state, employment_type, start_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            user["id"], request.company_id, request.email, request.first_name, request.last_name,
            request.work_state, request.employment_type, request.start_date
        )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=None
            )
        )


@router.post("/register/candidate", response_model=TokenResponse)
async def register_candidate(request: CandidateRegister):
    """Register a new candidate."""
    async with get_connection() as conn:
        # Check if email exists in users
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(request.password)
        user = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES ($1, $2, 'candidate')
            RETURNING id, email, role, is_active, created_at
            """,
            request.email, password_hash
        )

        # Check if candidate record exists with this email (from resume upload)
        candidate = await conn.fetchrow(
            "SELECT id FROM candidates WHERE email = $1",
            request.email
        )

        if candidate:
            # Link existing candidate to user
            await conn.execute(
                "UPDATE candidates SET user_id = $1, name = COALESCE(name, $2), phone = COALESCE(phone, $3) WHERE id = $4",
                user["id"], request.name, request.phone, candidate["id"]
            )
        else:
            # Create new candidate record
            await conn.execute(
                "INSERT INTO candidates (user_id, name, email, phone) VALUES ($1, $2, $3, $4)",
                user["id"], request.name, request.email, request.phone
            )

        settings = get_settings()
        access_token = create_access_token(user["id"], user["email"], user["role"])
        refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                last_login=None
            )
        )


@router.get("/me")
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user with full profile."""
    async with get_connection() as conn:
        if current_user.role == "admin":
            profile = await conn.fetchrow(
                "SELECT id, user_id, name, created_at FROM admins WHERE user_id = $1",
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "name": profile["name"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "client":
            profile = await conn.fetchrow(
                """
                SELECT c.id, c.user_id, c.company_id, comp.name as company_name,
                       comp.status as company_status, comp.rejection_reason,
                       COALESCE(comp.enabled_features, '{"offer_letters": true}'::jsonb) as enabled_features,
                       c.name, c.phone, c.job_title, c.created_at
                FROM clients c
                JOIN companies comp ON c.company_id = comp.id
                WHERE c.user_id = $1
                """,
                current_user.id
            )

            # Compute which enabled features still need onboarding setup
            onboarding_needed = {}
            if profile:
                enabled_features = merge_company_features(profile["enabled_features"])
                company_id = profile["company_id"]

                if enabled_features.get("compliance"):
                    has_locations = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM business_locations WHERE company_id = $1 AND is_active = true)",
                        company_id
                    )
                    if not has_locations:
                        onboarding_needed["compliance"] = True

            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "company_id": str(profile["company_id"]),
                    "company_name": profile["company_name"],
                    "company_status": profile["company_status"] or "approved",
                    "rejection_reason": profile["rejection_reason"],
                    "enabled_features": merge_company_features(profile["enabled_features"]),
                    "name": profile["name"],
                    "phone": profile["phone"],
                    "job_title": profile["job_title"],
                    "email": current_user.email,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None,
                "onboarding_needed": onboarding_needed,
            }

        elif current_user.role == "candidate":
            profile = await conn.fetchrow(
                """
                SELECT id, user_id, name, email, phone, skills, experience_years, created_at
                FROM candidates WHERE user_id = $1
                """,
                current_user.id
            )
            skills_data = json.loads(profile["skills"]) if profile and profile["skills"] else []
            return {
                "user": {
                    "id": str(current_user.id),
                    "email": current_user.email,
                    "role": current_user.role,
                    "beta_features": current_user.beta_features,
                    "interview_prep_tokens": current_user.interview_prep_tokens,
                    "allowed_interview_roles": current_user.allowed_interview_roles
                },
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]) if profile["user_id"] else None,
                    "name": profile["name"],
                    "email": profile["email"],
                    "phone": profile["phone"],
                    "skills": skills_data,
                    "experience_years": profile["experience_years"],
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "employee":
            profile = await conn.fetchrow(
                """
                SELECT e.id, e.user_id, e.org_id, c.name as company_name,
                       COALESCE(c.enabled_features, '{"offer_letters": true}'::jsonb) as enabled_features,
                       e.first_name, e.last_name, e.email, e.work_state,
                       e.employment_type, e.start_date, e.manager_id, e.created_at
                FROM employees e
                JOIN companies c ON e.org_id = c.id
                WHERE e.user_id = $1
                """,
                current_user.id
            )
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "company_id": str(profile["org_id"]),
                    "company_name": profile["company_name"],
                    "enabled_features": merge_company_features(profile["enabled_features"]),
                    "first_name": profile["first_name"],
                    "last_name": profile["last_name"],
                    "email": profile["email"],
                    "work_state": profile["work_state"],
                    "employment_type": profile["employment_type"],
                    "start_date": profile["start_date"].isoformat() if profile["start_date"] else None,
                    "manager_id": str(profile["manager_id"]) if profile["manager_id"] else None,
                    "created_at": profile["created_at"].isoformat()
                } if profile else None
            }

        elif current_user.role == "broker":
            profile = await conn.fetchrow(
                """
                SELECT
                    bm.id, bm.user_id, bm.broker_id, bm.role as member_role, bm.created_at,
                    b.name as broker_name, b.slug as broker_slug, b.status as broker_status,
                    b.billing_mode, b.invoice_owner, b.support_routing,
                    COALESCE(bb.branding_mode, 'direct') as branding_mode,
                    COALESCE(NULLIF(bb.brand_display_name, ''), b.name) as brand_display_name,
                    COALESCE(b.terms_required_version, 'v1') as terms_required_version,
                    ta.accepted_at as terms_accepted_at
                FROM broker_members bm
                JOIN brokers b ON bm.broker_id = b.id
                LEFT JOIN broker_branding_configs bb ON bb.broker_id = bm.broker_id
                LEFT JOIN broker_terms_acceptances ta
                    ON ta.broker_id = bm.broker_id
                    AND ta.user_id = bm.user_id
                    AND ta.terms_version = COALESCE(b.terms_required_version, 'v1')
                WHERE bm.user_id = $1 AND bm.is_active = true
                ORDER BY bm.created_at ASC
                LIMIT 1
                """,
                current_user.id
            )
            terms_accepted = bool(profile and profile["terms_accepted_at"] is not None)
            return {
                "user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role},
                "profile": {
                    "id": str(profile["id"]),
                    "user_id": str(profile["user_id"]),
                    "broker_id": str(profile["broker_id"]),
                    "broker_name": profile["broker_name"],
                    "broker_slug": profile["broker_slug"],
                    "branding_mode": profile["branding_mode"],
                    "brand_display_name": profile["brand_display_name"],
                    "member_role": profile["member_role"],
                    "broker_status": profile["broker_status"],
                    "billing_mode": profile["billing_mode"],
                    "invoice_owner": profile["invoice_owner"],
                    "support_routing": profile["support_routing"],
                    "terms_required_version": profile["terms_required_version"],
                    "terms_accepted": terms_accepted,
                    "terms_accepted_at": profile["terms_accepted_at"].isoformat() if profile["terms_accepted_at"] else None,
                    "created_at": profile["created_at"].isoformat(),
                } if profile else None,
                "onboarding_needed": {"broker_terms": not terms_accepted} if profile else {},
            }

    return {"user": {"id": str(current_user.id), "email": current_user.email, "role": current_user.role}, "profile": None}


@router.post("/broker/accept-terms", response_model=BrokerTermsAcceptanceResponse)
async def accept_broker_terms(
    payload: BrokerTermsAcceptanceRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_broker),
):
    """Record broker partner terms acceptance for the active broker membership."""
    async with get_connection() as conn:
        membership = await conn.fetchrow(
            """
            SELECT
                bm.broker_id,
                b.status,
                COALESCE(b.terms_required_version, 'v1') as terms_required_version
            FROM broker_members bm
            JOIN brokers b ON bm.broker_id = b.id
            WHERE bm.user_id = $1 AND bm.is_active = true
            ORDER BY bm.created_at ASC
            LIMIT 1
            """,
            current_user.id,
        )

        if not membership:
            raise HTTPException(status_code=404, detail="Broker membership not found")

        if membership["status"] != "active":
            raise HTTPException(status_code=403, detail="Broker account is not active")

        terms_version = (payload.terms_version or membership["terms_required_version"] or "v1").strip() or "v1"
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        accepted_at = await conn.fetchval(
            """
            INSERT INTO broker_terms_acceptances (
                broker_id, user_id, terms_version, ip_address, user_agent
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (broker_id, user_id, terms_version)
            DO UPDATE SET
                accepted_at = NOW(),
                ip_address = EXCLUDED.ip_address,
                user_agent = EXCLUDED.user_agent
            RETURNING accepted_at
            """,
            membership["broker_id"],
            current_user.id,
            terms_version,
            ip_address,
            user_agent,
        )

    return BrokerTermsAcceptanceResponse(
        status="accepted",
        broker_id=membership["broker_id"],
        terms_version=terms_version,
        accepted_at=accepted_at,
    )


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Logout endpoint (for audit/future token blacklist)."""
    return {"status": "logged_out"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change password for current user."""
    async with get_connection() as conn:
        # Get current password hash
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not verify_password(request.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # Validate new password
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters"
            )

        # Update password
        new_hash = hash_password(request.new_password)
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash, current_user.id
        )

        return {"status": "password_changed"}


@router.post("/change-email")
async def change_email(
    request: ChangeEmailRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Change email for current user."""
    async with get_connection() as conn:
        # Verify password
        user = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1",
            current_user.id
        )

        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is incorrect"
            )

        # Check if new email is already taken
        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1 AND id != $2",
            request.new_email, current_user.id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use"
            )

        # Update email in users table
        await conn.execute(
            "UPDATE users SET email = $1 WHERE id = $2",
            request.new_email, current_user.id
        )

        # Also update email in role-specific table if applicable
        if current_user.role == "candidate":
            await conn.execute(
                "UPDATE candidates SET email = $1 WHERE user_id = $2",
                request.new_email, current_user.id
            )

        # Generate new tokens with updated email
        settings = get_settings()
        access_token = create_access_token(current_user.id, request.new_email, current_user.role)
        refresh_token = create_refresh_token(current_user.id, request.new_email, current_user.role)

        return {
            "status": "email_changed",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.jwt_access_token_expire_minutes * 60
        }


@router.put("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update profile information for current user."""
    async with get_connection() as conn:
        if current_user.role == "admin":
            if request.name:
                await conn.execute(
                    "UPDATE admins SET name = $1 WHERE user_id = $2",
                    request.name, current_user.id
                )
        elif current_user.role == "client":
            updates = []
            values = []
            if request.name:
                updates.append("name = $" + str(len(values) + 1))
                values.append(request.name)
            if request.phone:
                updates.append("phone = $" + str(len(values) + 1))
                values.append(request.phone)
            if updates:
                values.append(current_user.id)
                await conn.execute(
                    f"UPDATE clients SET {', '.join(updates)} WHERE user_id = ${len(values)}",
                    *values
                )
        elif current_user.role == "candidate":
            updates = []
            values = []
            if request.name:
                updates.append("name = $" + str(len(values) + 1))
                values.append(request.name)
            if request.phone:
                updates.append("phone = $" + str(len(values) + 1))
                values.append(request.phone)
            if updates:
                values.append(current_user.id)
                await conn.execute(
                    f"UPDATE candidates SET {', '.join(updates)} WHERE user_id = ${len(values)}",
                    *values
                )

        return {"status": "profile_updated"}


# ===========================================
# Admin Beta Access Management
# ===========================================

@router.get("/admin/candidates/beta", response_model=CandidateBetaListResponse, dependencies=[Depends(require_admin)])
async def list_candidates_beta():
    """List all candidates with beta access info and interview prep stats."""
    async with get_connection() as conn:
        # Get all candidates with their user info and interview prep stats
        rows = await conn.fetch("""
            SELECT
                u.id as user_id,
                u.email,
                c.name,
                COALESCE(u.beta_features, '{}'::jsonb) as beta_features,
                COALESCE(u.interview_prep_tokens, 0) as interview_prep_tokens,
                COALESCE(u.allowed_interview_roles, '[]'::jsonb) as allowed_interview_roles,
                COUNT(i.id) FILTER (WHERE i.interview_type = 'tutor_interview') as total_sessions,
                AVG(
                    CASE
                        WHEN i.tutor_analysis IS NOT NULL
                        AND i.tutor_analysis->'interview'->>'response_quality_score' IS NOT NULL
                        THEN (i.tutor_analysis->'interview'->>'response_quality_score')::float
                        ELSE NULL
                    END
                ) as avg_score,
                MAX(i.created_at) FILTER (WHERE i.interview_type = 'tutor_interview') as last_session_at
            FROM users u
            JOIN candidates c ON c.user_id = u.id
            LEFT JOIN interviews i ON i.interviewer_name = u.email AND i.interview_type = 'tutor_interview'
            WHERE u.role = 'candidate'
            GROUP BY u.id, u.email, c.name, u.beta_features, u.interview_prep_tokens, u.allowed_interview_roles
            ORDER BY c.name
        """)

        candidates = []
        for row in rows:
            beta_features = row["beta_features"] if row["beta_features"] else {}
            if isinstance(beta_features, str):
                beta_features = json.loads(beta_features)

            allowed_roles = row["allowed_interview_roles"] if row["allowed_interview_roles"] else []
            if isinstance(allowed_roles, str):
                allowed_roles = json.loads(allowed_roles)

            candidates.append(CandidateBetaInfo(
                user_id=row["user_id"],
                email=row["email"],
                name=row["name"],
                beta_features=beta_features,
                interview_prep_tokens=row["interview_prep_tokens"],
                allowed_interview_roles=allowed_roles,
                total_sessions=row["total_sessions"] or 0,
                avg_score=round(row["avg_score"], 1) if row["avg_score"] else None,
                last_session_at=row["last_session_at"]
            ))

        return CandidateBetaListResponse(candidates=candidates, total=len(candidates))


@router.patch("/admin/candidates/{user_id}/beta", dependencies=[Depends(require_admin)])
async def toggle_candidate_beta(user_id: UUID, request: BetaToggleRequest):
    """Toggle a beta feature for a candidate."""
    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role, beta_features FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        # Update beta features
        current_features = user["beta_features"] if user["beta_features"] else {}
        if isinstance(current_features, str):
            current_features = json.loads(current_features)

        if request.enabled:
            current_features[request.feature] = True
        else:
            current_features.pop(request.feature, None)

        await conn.execute(
            "UPDATE users SET beta_features = $1::jsonb WHERE id = $2",
            json.dumps(current_features), user_id
        )

        return {"status": "updated", "beta_features": current_features}


@router.post("/admin/candidates/{user_id}/tokens", dependencies=[Depends(require_admin)])
async def award_tokens(user_id: UUID, request: TokenAwardRequest):
    """Award interview prep tokens to a candidate."""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role, interview_prep_tokens FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        new_total = (user["interview_prep_tokens"] or 0) + request.amount
        await conn.execute(
            "UPDATE users SET interview_prep_tokens = $1 WHERE id = $2",
            new_total, user_id
        )

        return {"status": "awarded", "new_total": new_total}


@router.put("/admin/candidates/{user_id}/roles", dependencies=[Depends(require_admin)])
async def update_allowed_roles(user_id: UUID, request: AllowedRolesRequest):
    """Update allowed interview roles for a candidate."""
    async with get_connection() as conn:
        # Verify user exists and is a candidate
        user = await conn.fetchrow(
            "SELECT id, role FROM users WHERE id = $1",
            user_id
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user["role"] != "candidate":
            raise HTTPException(status_code=400, detail="User is not a candidate")

        await conn.execute(
            "UPDATE users SET allowed_interview_roles = $1::jsonb WHERE id = $2",
            json.dumps(request.roles), user_id
        )

        return {"status": "updated", "allowed_interview_roles": request.roles}


@router.get("/admin/candidates/{user_id}/sessions", response_model=list[CandidateSessionSummary], dependencies=[Depends(require_admin)])
async def get_candidate_sessions(user_id: UUID):
    """Get interview prep sessions for a specific candidate."""
    async with get_connection() as conn:
        # Get user email
        user = await conn.fetchrow("SELECT email FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get interview prep sessions (using interviewer_name = email pattern from tutor)
        rows = await conn.fetch("""
            SELECT
                id as session_id,
                interviewer_role as interview_role,
                EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - created_at)) / 60 as duration_minutes,
                status,
                created_at,
                tutor_analysis
            FROM interviews
            WHERE interviewer_name = $1
            AND interview_type = 'tutor_interview'
            ORDER BY created_at DESC
            LIMIT 50
        """, user["email"])

        sessions = []
        for row in rows:
            analysis = row["tutor_analysis"]
            response_score = None
            communication_score = None

            if analysis:
                if isinstance(analysis, str):
                    analysis = json.loads(analysis)
                interview_data = analysis.get("interview", {})
                response_score = interview_data.get("response_quality_score")
                communication_score = interview_data.get("communication_score")

            sessions.append(CandidateSessionSummary(
                session_id=row["session_id"],
                interview_role=row["interview_role"],
                duration_minutes=int(row["duration_minutes"] or 0),
                status=row["status"],
                created_at=row["created_at"],
                response_quality_score=response_score,
                communication_score=communication_score
            ))

        return sessions
