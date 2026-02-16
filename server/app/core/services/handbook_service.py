from datetime import date, datetime, timedelta
import html
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection
from .storage import get_storage
from ..models.handbook import (
    CompanyHandbookProfileInput,
    CompanyHandbookProfileResponse,
    HandbookAcknowledgementSummary,
    HandbookChangeRequestResponse,
    HandbookCreateRequest,
    HandbookDetailResponse,
    HandbookDistributionResponse,
    HandbookListItemResponse,
    HandbookPublishResponse,
    HandbookScopeInput,
    HandbookScopeResponse,
    HandbookSectionInput,
    HandbookSectionResponse,
    HandbookUpdateRequest,
)


STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}


def _normalize_scope(scope: HandbookScopeInput) -> dict[str, Any]:
    return {
        "state": scope.state.upper(),
        "city": scope.city,
        "zipcode": scope.zipcode,
        "location_id": scope.location_id,
    }


def _normalize_profile(profile: CompanyHandbookProfileInput) -> dict[str, Any]:
    return {
        "legal_name": profile.legal_name.strip(),
        "dba": profile.dba.strip() if profile.dba else None,
        "ceo_or_president": profile.ceo_or_president.strip(),
        "headcount": profile.headcount,
        "remote_workers": profile.remote_workers,
        "minors": profile.minors,
        "tipped_employees": profile.tipped_employees,
        "union_employees": profile.union_employees,
        "federal_contracts": profile.federal_contracts,
        "group_health_insurance": profile.group_health_insurance,
        "background_checks": profile.background_checks,
        "hourly_employees": profile.hourly_employees,
        "salaried_employees": profile.salaried_employees,
        "commissioned_employees": profile.commissioned_employees,
        "tip_pooling": profile.tip_pooling,
    }


def _build_core_sections(profile: dict[str, Any], mode: str, states: list[str]) -> list[dict[str, Any]]:
    legal_name = profile["legal_name"]
    dba = profile.get("dba")
    ceo = profile["ceo_or_president"]
    scope_desc = ", ".join([STATE_NAMES.get(s, s) for s in states]) if states else "applicable jurisdictions"
    company_ref = f"{legal_name} (DBA {dba})" if dba else legal_name
    employment_mix = []
    if profile.get("hourly_employees"):
        employment_mix.append("hourly")
    if profile.get("salaried_employees"):
        employment_mix.append("salaried")
    if profile.get("commissioned_employees"):
        employment_mix.append("commissioned")
    mix_text = ", ".join(employment_mix) if employment_mix else "varied"

    remote_clause = (
        "Remote and hybrid work arrangements are permitted for eligible roles and remain subject to business need."
        if profile.get("remote_workers")
        else "The company primarily operates in-person roles; remote arrangements require prior written approval."
    )
    minors_clause = (
        "Because the company employs minors, scheduling and duties will comply with all youth-employment limits."
        if profile.get("minors")
        else "This handbook assumes no minor employment arrangements unless policy updates are issued."
    )
    tipped_clause = (
        "Tipped positions must follow cash wage, tip-credit, and tip retention rules for each covered jurisdiction."
        if profile.get("tipped_employees")
        else "No tipped-employee programs are active unless communicated in writing."
    )
    union_clause = (
        "Where a collective bargaining agreement applies, the CBA controls in case of conflict with this handbook."
        if profile.get("union_employees")
        else "No union-specific terms apply unless a collective bargaining relationship is established."
    )
    federal_contract_clause = (
        "Federal-contract obligations may add or supersede handbook requirements for covered teams."
        if profile.get("federal_contracts")
        else "No federal-contract specific labor clauses are incorporated at this time."
    )

    sections: list[dict[str, Any]] = [
        {
            "section_key": "welcome",
            "title": "Welcome and Scope",
            "section_order": 10,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                f"This Employee Handbook is adopted by {company_ref} and applies to employees working in {scope_desc}. "
                f"It summarizes employment expectations and workplace standards. "
                f"{ceo} is the executive sponsor of this handbook program."
            ),
        },
        {
            "section_key": "employment_relationship",
            "title": "Employment Relationship",
            "section_order": 20,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                f"This handbook is a statement of policies and is not a contract of employment. "
                f"Employment classifications currently include {mix_text} roles. "
                "Policy interpretations are administered by company leadership and HR."
            ),
        },
        {
            "section_key": "equal_opportunity",
            "title": "Equal Employment Opportunity and Anti-Harassment",
            "section_order": 30,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "The company provides equal employment opportunity and prohibits discrimination, harassment, and retaliation. "
                "All employees must report concerns promptly through designated reporting channels."
            ),
        },
        {
            "section_key": "hours_and_pay",
            "title": "Hours, Pay, and Timekeeping",
            "section_order": 40,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employees must accurately record time worked and meal/rest periods where required. "
                f"{tipped_clause} "
                f"{federal_contract_clause}"
            ),
        },
        {
            "section_key": "attendance_and_remote",
            "title": "Attendance, Work Location, and Scheduling",
            "section_order": 50,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Regular attendance and punctuality are required unless approved leave or accommodation applies. "
                f"{remote_clause} "
                f"{minors_clause}"
            ),
        },
        {
            "section_key": "benefits_and_leave",
            "title": "Benefits and Leave",
            "section_order": 60,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Benefit eligibility and leave rights follow company plans and applicable law. "
                + (
                    "Group health coverage is offered to eligible employees under current plan terms. "
                    if profile.get("group_health_insurance")
                    else "Group health coverage is not currently offered through company-sponsored plans. "
                )
            ),
        },
        {
            "section_key": "workplace_standards",
            "title": "Workplace Conduct and Safety",
            "section_order": 70,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employees are expected to maintain professional conduct, protect confidential information, "
                "and follow all safety rules for their role and work location."
            ),
        },
        {
            "section_key": "investigations",
            "title": "Investigations, Background Checks, and Corrective Action",
            "section_order": 80,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "The company may investigate policy violations and implement corrective action when needed. "
                + (
                    "Background checks may be conducted for eligible roles in accordance with applicable law. "
                    if profile.get("background_checks")
                    else "Background checks are not part of standard hiring/retention practices unless stated otherwise. "
                )
                + f"{union_clause}"
            ),
        },
        {
            "section_key": "acknowledgement",
            "title": "Employee Acknowledgement",
            "section_order": 90,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employees must acknowledge receipt of this handbook and agree to comply with these policies. "
                "Future updates may require renewed acknowledgement."
            ),
        },
    ]

    return sections


def _build_state_sections(states: list[str], profile: dict[str, Any]) -> list[dict[str, Any]]:
    state_sections: list[dict[str, Any]] = []
    for i, state in enumerate(states):
        state_name = STATE_NAMES.get(state, state)
        tip_pooling_clause = (
            "Tip pooling practices are used and must follow local restrictions."
            if profile.get("tip_pooling")
            else "No tip pooling practices are currently configured."
        )
        state_sections.append(
            {
                "section_key": f"state_addendum_{state.lower()}",
                "title": f"{state_name} State Addendum",
                "section_order": 200 + i,
                "section_type": "state",
                "jurisdiction_scope": {"states": [state]},
                "content": (
                    f"This addendum applies to employees working in {state_name}. "
                    "State-specific wage and hour, leave, posting, and employee-notice requirements apply. "
                    f"{tip_pooling_clause}"
                ),
            }
        )
    return state_sections


def _build_template_sections(
    mode: str,
    scopes: list[dict[str, Any]],
    profile: dict[str, Any],
    custom_sections: list[HandbookSectionInput],
) -> list[dict[str, Any]]:
    unique_states = sorted({scope["state"] for scope in scopes})
    base_sections = _build_core_sections(profile, mode, unique_states)
    state_sections = _build_state_sections(unique_states, profile)
    custom = [
        {
            "section_key": section.section_key,
            "title": section.title,
            "section_order": section.section_order,
            "section_type": section.section_type,
            "jurisdiction_scope": section.jurisdiction_scope or {},
            "content": section.content,
        }
        for section in custom_sections
    ]
    return sorted(base_sections + state_sections + custom, key=lambda item: item["section_order"])


def _handbook_filename(title: str, version_number: int) -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    sanitized = sanitized or "handbook"
    return f"{sanitized}-v{version_number}.pdf"


async def _get_employee_document_columns(conn) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'employee_documents'
        """
    )
    return {row["column_name"] for row in rows}


def _validate_handbook_file_reference(file_url: Optional[str]) -> None:
    if not file_url:
        return
    storage = get_storage()
    if not storage.is_supported_storage_path(file_url):
        raise ValueError("Invalid handbook file reference")


class HandbookService:
    @staticmethod
    async def _upsert_profile_with_conn(
        conn,
        company_id: str,
        profile: CompanyHandbookProfileInput,
        updated_by: Optional[str] = None,
    ) -> CompanyHandbookProfileResponse:
        data = _normalize_profile(profile)
        await conn.execute(
            """
            INSERT INTO company_handbook_profiles (
                company_id, legal_name, dba, ceo_or_president, headcount,
                remote_workers, minors, tipped_employees, union_employees, federal_contracts,
                group_health_insurance, background_checks, hourly_employees,
                salaried_employees, commissioned_employees, tip_pooling, updated_by, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13,
                $14, $15, $16, $17, NOW()
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                legal_name = EXCLUDED.legal_name,
                dba = EXCLUDED.dba,
                ceo_or_president = EXCLUDED.ceo_or_president,
                headcount = EXCLUDED.headcount,
                remote_workers = EXCLUDED.remote_workers,
                minors = EXCLUDED.minors,
                tipped_employees = EXCLUDED.tipped_employees,
                union_employees = EXCLUDED.union_employees,
                federal_contracts = EXCLUDED.federal_contracts,
                group_health_insurance = EXCLUDED.group_health_insurance,
                background_checks = EXCLUDED.background_checks,
                hourly_employees = EXCLUDED.hourly_employees,
                salaried_employees = EXCLUDED.salaried_employees,
                commissioned_employees = EXCLUDED.commissioned_employees,
                tip_pooling = EXCLUDED.tip_pooling,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            company_id,
            data["legal_name"],
            data["dba"],
            data["ceo_or_president"],
            data["headcount"],
            data["remote_workers"],
            data["minors"],
            data["tipped_employees"],
            data["union_employees"],
            data["federal_contracts"],
            data["group_health_insurance"],
            data["background_checks"],
            data["hourly_employees"],
            data["salaried_employees"],
            data["commissioned_employees"],
            data["tip_pooling"],
            updated_by,
        )
        row = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1",
            company_id,
        )
        return CompanyHandbookProfileResponse(**dict(row))

    @staticmethod
    async def get_or_default_profile(company_id: str) -> CompanyHandbookProfileResponse:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM company_handbook_profiles
                WHERE company_id = $1
                """,
                company_id,
            )
            if row:
                return CompanyHandbookProfileResponse(**dict(row))

            company_name = await conn.fetchval(
                "SELECT name FROM companies WHERE id = $1",
                company_id,
            ) or "Company"
            headcount = await conn.fetchval(
                "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
                company_id,
            )
            fallback = {
                "company_id": UUID(company_id),
                "legal_name": company_name,
                "dba": None,
                "ceo_or_president": "Company Leadership",
                "headcount": int(headcount or 0),
                "remote_workers": False,
                "minors": False,
                "tipped_employees": False,
                "union_employees": False,
                "federal_contracts": False,
                "group_health_insurance": False,
                "background_checks": False,
                "hourly_employees": True,
                "salaried_employees": False,
                "commissioned_employees": False,
                "tip_pooling": False,
                "updated_by": None,
                "updated_at": datetime.utcnow(),
            }
            return CompanyHandbookProfileResponse(**fallback)

    @staticmethod
    async def upsert_profile(
        company_id: str,
        profile: CompanyHandbookProfileInput,
        updated_by: Optional[str] = None,
    ) -> CompanyHandbookProfileResponse:
        async with get_connection() as conn:
            return await HandbookService._upsert_profile_with_conn(
                conn,
                company_id,
                profile,
                updated_by,
            )

    @staticmethod
    async def list_handbooks(company_id: str) -> list[HandbookListItemResponse]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    h.*,
                    COALESCE(
                        ARRAY_AGG(DISTINCT hs.state) FILTER (WHERE hs.state IS NOT NULL),
                        '{}'::varchar[]
                    ) AS scope_states,
                    COALESCE(
                        COUNT(DISTINCT hcr.id) FILTER (WHERE hcr.status = 'pending'),
                        0
                    ) AS pending_changes_count
                FROM handbooks h
                LEFT JOIN handbook_scopes hs ON hs.handbook_id = h.id
                LEFT JOIN handbook_change_requests hcr ON hcr.handbook_id = h.id
                WHERE h.company_id = $1
                GROUP BY h.id
                ORDER BY h.updated_at DESC
                """,
                company_id,
            )
            return [HandbookListItemResponse(**dict(row)) for row in rows]

    @staticmethod
    async def create_handbook(
        company_id: str,
        data: HandbookCreateRequest,
        created_by: Optional[str] = None,
    ) -> HandbookDetailResponse:
        normalized_scopes = [_normalize_scope(scope) for scope in data.scopes]
        profile = _normalize_profile(data.profile)
        profile_row: Optional[CompanyHandbookProfileResponse] = None
        _validate_handbook_file_reference(data.file_url)

        async with get_connection() as conn:
            async with conn.transaction():
                profile_row = await HandbookService._upsert_profile_with_conn(
                    conn,
                    company_id,
                    data.profile,
                    created_by,
                )
                handbook_id = await conn.fetchval(
                    """
                    INSERT INTO handbooks (
                        company_id, title, status, mode, source_type, active_version,
                        file_url, file_name, created_by, created_at, updated_at
                    )
                    VALUES ($1, $2, 'draft', $3, $4, 1, $5, $6, $7, NOW(), NOW())
                    RETURNING id
                    """,
                    company_id,
                    data.title,
                    data.mode,
                    data.source_type,
                    data.file_url,
                    data.file_name,
                    created_by,
                )

                for scope in normalized_scopes:
                    await conn.execute(
                        """
                        INSERT INTO handbook_scopes (handbook_id, state, city, zipcode, location_id, created_at)
                        VALUES ($1, $2, $3, $4, $5, NOW())
                        """,
                        handbook_id,
                        scope["state"],
                        scope["city"],
                        scope["zipcode"],
                        scope["location_id"],
                    )

                version_id = await conn.fetchval(
                    """
                    INSERT INTO handbook_versions (
                        handbook_id, version_number, summary, is_published, created_by, created_at
                    )
                    VALUES ($1, 1, $2, false, $3, NOW())
                    RETURNING id
                    """,
                    handbook_id,
                    "Initial handbook draft",
                    created_by,
                )

                if data.source_type == "template":
                    sections = _build_template_sections(
                        data.mode,
                        normalized_scopes,
                        profile,
                        data.custom_sections,
                    )
                else:
                    sections = [
                        {
                            "section_key": "uploaded_handbook",
                            "title": "Uploaded Employee Handbook",
                            "section_order": 10,
                            "section_type": "uploaded",
                            "jurisdiction_scope": {},
                            "content": (
                                "This handbook was uploaded as a company-authored document. "
                                "Use the file attachment for the canonical text."
                            ),
                        }
                    ]

                for section in sections:
                    await conn.execute(
                        """
                        INSERT INTO handbook_sections (
                            handbook_version_id, section_key, title, section_order,
                            section_type, jurisdiction_scope, content, created_at, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, NOW(), NOW())
                        """,
                        version_id,
                        section["section_key"],
                        section["title"],
                        section["section_order"],
                        section["section_type"],
                        section["jurisdiction_scope"],
                        section["content"],
                    )

        handbook = await HandbookService.get_handbook_by_id(str(handbook_id), company_id)
        if handbook is None:
            raise ValueError("Failed to create handbook")
        if profile_row is not None:
            handbook.profile = profile_row
        return handbook

    @staticmethod
    async def _get_active_version_id(conn, handbook_id: str, active_version: int) -> Optional[UUID]:
        return await conn.fetchval(
            """
            SELECT id
            FROM handbook_versions
            WHERE handbook_id = $1 AND version_number = $2
            """,
            handbook_id,
            active_version,
        )

    @staticmethod
    async def get_handbook_by_id(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookDetailResponse]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM handbooks
                WHERE id = $1 AND company_id = $2
                """,
                handbook_id,
                company_id,
            )
            if not row:
                return None

            active_version_id = await HandbookService._get_active_version_id(
                conn,
                str(row["id"]),
                row["active_version"],
            )
            if active_version_id is None:
                active_version_id = await conn.fetchval(
                    """
                    SELECT id
                    FROM handbook_versions
                    WHERE handbook_id = $1
                    ORDER BY version_number DESC
                    LIMIT 1
                    """,
                    row["id"],
                )

            scope_rows = await conn.fetch(
                """
                SELECT id, state, city, zipcode, location_id
                FROM handbook_scopes
                WHERE handbook_id = $1
                ORDER BY state, city NULLS LAST, zipcode NULLS LAST
                """,
                row["id"],
            )
            section_rows = await conn.fetch(
                """
                SELECT id, section_key, title, content, section_order, section_type, jurisdiction_scope
                FROM handbook_sections
                WHERE handbook_version_id = $1
                ORDER BY section_order ASC, created_at ASC
                """,
                active_version_id,
            )

            profile = await HandbookService.get_or_default_profile(company_id)

            return HandbookDetailResponse(
                id=row["id"],
                company_id=row["company_id"],
                title=row["title"],
                status=row["status"],
                mode=row["mode"],
                source_type=row["source_type"],
                active_version=row["active_version"],
                file_url=row["file_url"],
                file_name=row["file_name"],
                scopes=[HandbookScopeResponse(**dict(scope)) for scope in scope_rows],
                profile=profile,
                sections=[HandbookSectionResponse(**dict(section)) for section in section_rows],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                published_at=row["published_at"],
                created_by=row["created_by"],
            )

    @staticmethod
    async def update_handbook(
        handbook_id: str,
        company_id: str,
        data: HandbookUpdateRequest,
        updated_by: Optional[str] = None,
    ) -> Optional[HandbookDetailResponse]:
        async with get_connection() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbooks
                    WHERE id = $1 AND company_id = $2
                    """,
                    handbook_id,
                    company_id,
                )
                if not current:
                    return None

                if data.mode is not None or data.scopes is not None:
                    next_mode = data.mode or current["mode"]
                    if data.scopes is None:
                        scope_count = await conn.fetchval(
                            "SELECT COUNT(*) FROM handbook_scopes WHERE handbook_id = $1",
                            handbook_id,
                        )
                        scope_count = int(scope_count or 0)
                    else:
                        scope_count = len(data.scopes)
                    if next_mode == "single_state" and scope_count != 1:
                        raise ValueError("Single-state handbooks must have exactly one scope")
                    if next_mode == "multi_state" and scope_count < 2:
                        raise ValueError("Multi-state handbooks must include at least two scopes")

                _validate_handbook_file_reference(data.file_url)
                should_invalidate_cached_file = (
                    current["source_type"] == "template"
                    and any(
                        value is not None
                        for value in (data.title, data.mode, data.scopes, data.sections, data.profile)
                    )
                    and data.file_url is None
                    and data.file_name is None
                )

                updates: list[str] = []
                params: list[Any] = []
                idx = 3

                if data.title is not None:
                    updates.append(f"title = ${idx}")
                    params.append(data.title)
                    idx += 1
                if data.mode is not None:
                    updates.append(f"mode = ${idx}")
                    params.append(data.mode)
                    idx += 1
                if data.file_url is not None:
                    updates.append(f"file_url = ${idx}")
                    params.append(data.file_url)
                    idx += 1
                if data.file_name is not None:
                    updates.append(f"file_name = ${idx}")
                    params.append(data.file_name)
                    idx += 1
                if should_invalidate_cached_file:
                    updates.append("file_url = NULL")
                    updates.append("file_name = NULL")

                if updates:
                    updates.append("updated_at = NOW()")
                    query = f"UPDATE handbooks SET {', '.join(updates)} WHERE id = $1 AND company_id = $2"
                    await conn.execute(query, handbook_id, company_id, *params)
                else:
                    await conn.execute(
                        "UPDATE handbooks SET updated_at = NOW() WHERE id = $1 AND company_id = $2",
                        handbook_id,
                        company_id,
                    )

                if data.scopes is not None:
                    await conn.execute("DELETE FROM handbook_scopes WHERE handbook_id = $1", handbook_id)
                    for scope in data.scopes:
                        normalized = _normalize_scope(scope)
                        await conn.execute(
                            """
                            INSERT INTO handbook_scopes (handbook_id, state, city, zipcode, location_id, created_at)
                            VALUES ($1, $2, $3, $4, $5, NOW())
                            """,
                            handbook_id,
                            normalized["state"],
                            normalized["city"],
                            normalized["zipcode"],
                            normalized["location_id"],
                        )

                if data.sections is not None:
                    version_id = await HandbookService._get_active_version_id(
                        conn,
                        handbook_id,
                        current["active_version"],
                    )
                    if version_id:
                        await conn.execute(
                            "DELETE FROM handbook_sections WHERE handbook_version_id = $1",
                            version_id,
                        )
                        for section in data.sections:
                            await conn.execute(
                                """
                                INSERT INTO handbook_sections (
                                    handbook_version_id, section_key, title, content, section_order,
                                    section_type, jurisdiction_scope, created_at, updated_at
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW(), NOW())
                                """,
                                version_id,
                                section.section_key,
                                section.title,
                                section.content,
                                section.section_order,
                                section.section_type,
                                section.jurisdiction_scope or {},
                            )

                if data.profile is not None:
                    await HandbookService._upsert_profile_with_conn(
                        conn,
                        company_id,
                        data.profile,
                        updated_by,
                    )

        return await HandbookService.get_handbook_by_id(handbook_id, company_id)

    @staticmethod
    async def publish_handbook(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookPublishResponse]:
        async with get_connection() as conn:
            async with conn.transaction():
                target = await conn.fetchrow(
                    """
                    SELECT id, active_version
                    FROM handbooks
                    WHERE id = $1 AND company_id = $2
                    """,
                    handbook_id,
                    company_id,
                )
                if not target:
                    return None

                await conn.execute(
                    """
                    UPDATE handbooks
                    SET status = 'archived', updated_at = NOW()
                    WHERE company_id = $1
                      AND status = 'active'
                      AND id <> $2
                    """,
                    company_id,
                    handbook_id,
                )
                await conn.execute(
                    """
                    UPDATE handbooks
                    SET status = 'active',
                        published_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1 AND company_id = $2
                    """,
                    handbook_id,
                    company_id,
                )
                await conn.execute(
                    """
                    UPDATE handbook_versions
                    SET is_published = (version_number = $2)
                    WHERE handbook_id = $1
                    """,
                    handbook_id,
                    target["active_version"],
                )

                row = await conn.fetchrow(
                    """
                    SELECT id, status, active_version, published_at
                    FROM handbooks
                    WHERE id = $1
                    """,
                    handbook_id,
                )
                return HandbookPublishResponse(**dict(row))

    @staticmethod
    async def archive_handbook(handbook_id: str, company_id: str) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                """
                UPDATE handbooks
                SET status = 'archived', updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                """,
                handbook_id,
                company_id,
            )
            return result == "UPDATE 1"

    @staticmethod
    async def list_change_requests(
        handbook_id: str,
        company_id: str,
    ) -> list[HandbookChangeRequestResponse]:
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not exists:
                return []

            rows = await conn.fetch(
                """
                SELECT *
                FROM handbook_change_requests
                WHERE handbook_id = $1
                ORDER BY
                    CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                    created_at DESC
                """,
                handbook_id,
            )
            return [HandbookChangeRequestResponse(**dict(row)) for row in rows]

    @staticmethod
    async def resolve_change_request(
        handbook_id: str,
        company_id: str,
        change_id: str,
        new_status: str,
        resolved_by: Optional[str] = None,
    ) -> Optional[HandbookChangeRequestResponse]:
        if new_status not in {"accepted", "rejected"}:
            return None

        async with get_connection() as conn:
            async with conn.transaction():
                handbook = await conn.fetchrow(
                    "SELECT id, active_version FROM handbooks WHERE id = $1 AND company_id = $2",
                    handbook_id,
                    company_id,
                )
                if not handbook:
                    return None

                change = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbook_change_requests
                    WHERE id = $1 AND handbook_id = $2
                    """,
                    change_id,
                    handbook_id,
                )
                if not change:
                    return None

                accepted_content_change = False
                if new_status == "accepted" and change["section_key"]:
                    version_id = await HandbookService._get_active_version_id(
                        conn,
                        handbook_id,
                        handbook["active_version"],
                    )
                    if version_id:
                        await conn.execute(
                            """
                            UPDATE handbook_sections
                            SET content = $1, updated_at = NOW()
                            WHERE handbook_version_id = $2 AND section_key = $3
                            """,
                            change["proposed_content"],
                            version_id,
                            change["section_key"],
                        )
                        accepted_content_change = True

                updated = await conn.fetchrow(
                    """
                    UPDATE handbook_change_requests
                    SET status = $1, resolved_by = $2, resolved_at = NOW()
                    WHERE id = $3
                    RETURNING *
                    """,
                    new_status,
                    resolved_by,
                    change_id,
                )
                if accepted_content_change:
                    await conn.execute(
                        "UPDATE handbooks SET updated_at = NOW(), file_url = NULL, file_name = NULL WHERE id = $1",
                        handbook_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE handbooks SET updated_at = NOW() WHERE id = $1",
                        handbook_id,
                    )

        return HandbookChangeRequestResponse(**dict(updated)) if updated else None

    @staticmethod
    async def _ensure_handbook_pdf(
        handbook_id: str,
        company_id: str,
    ) -> tuple[str, str, int]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            raise ValueError("Handbook not found")

        if handbook.file_url:
            _validate_handbook_file_reference(handbook.file_url)
            return handbook.file_url, (handbook.file_name or ""), handbook.active_version

        pdf_bytes, filename = await HandbookService.generate_handbook_pdf_bytes(handbook_id, company_id)
        storage = get_storage()
        file_url = await storage.upload_file(
            pdf_bytes,
            filename,
            prefix="handbooks",
            content_type="application/pdf",
        )

        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE handbooks
                SET file_url = $1, file_name = $2, updated_at = NOW()
                WHERE id = $3 AND company_id = $4
                """,
                file_url,
                filename,
                handbook_id,
                company_id,
            )
        return file_url, filename, handbook.active_version

    @staticmethod
    async def distribute_to_employees(
        handbook_id: str,
        company_id: str,
        distributed_by: Optional[str] = None,
    ) -> Optional[HandbookDistributionResponse]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None
        if handbook.status != "active":
            raise ValueError("Only active handbooks can be distributed for acknowledgement")

        file_url, _, version_number = await HandbookService._ensure_handbook_pdf(handbook_id, company_id)
        doc_type = f"handbook:{handbook_id}:{version_number}"

        async with get_connection() as conn:
            async with conn.transaction():
                employee_rows = await conn.fetch(
                    """
                    SELECT id
                    FROM employees
                    WHERE org_id = $1
                      AND termination_date IS NULL
                    ORDER BY created_at ASC
                    """,
                    company_id,
                )
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"handbook-distribute:{company_id}:{doc_type}",
                )

                columns = await _get_employee_document_columns(conn)
                existing_employee_rows = await conn.fetch(
                    """
                    SELECT employee_id
                    FROM employee_documents
                    WHERE org_id = $1 AND doc_type = $2
                      AND status IN ('pending_signature', 'signed')
                    """,
                    company_id,
                    doc_type,
                )
                existing_employee_ids = {row["employee_id"] for row in existing_employee_rows}
                insertable = {
                    "org_id": UUID(company_id),
                    "doc_type": doc_type,
                    "title": f"{handbook.title} (v{version_number})",
                    "description": f"Employee handbook acknowledgement for {handbook.title}",
                    "storage_path": file_url,
                    "status": "pending_signature",
                    "expires_at": date.today() + timedelta(days=365),
                    "assigned_by": UUID(distributed_by) if distributed_by else None,
                    "updated_at": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                }

                assigned = 0
                skipped = 0
                for employee in employee_rows:
                    if employee["id"] in existing_employee_ids:
                        skipped += 1
                        continue

                    record = {"employee_id": employee["id"]}
                    record.update(insertable)
                    cols = [col for col in record.keys() if col in columns]
                    values = [record[col] for col in cols]
                    placeholders = ", ".join(f"${idx}" for idx in range(1, len(cols) + 1))
                    col_sql = ", ".join(cols)
                    result = await conn.execute(
                        (
                            f"INSERT INTO employee_documents ({col_sql}) VALUES ({placeholders}) "
                            "ON CONFLICT (employee_id, doc_type) "
                            "WHERE status IN ('pending_signature', 'signed') DO NOTHING"
                        ),
                        *values,
                    )
                    if result == "INSERT 0 1":
                        assigned += 1
                    else:
                        skipped += 1

                await conn.execute(
                    """
                    INSERT INTO handbook_distribution_runs (
                        handbook_id, handbook_version_id, distributed_by, distributed_at, employee_count
                    )
                    VALUES (
                        $1,
                        (
                            SELECT id FROM handbook_versions
                            WHERE handbook_id = $1 AND version_number = $2
                            LIMIT 1
                        ),
                        $3,
                        NOW(),
                        $4
                    )
                    """,
                    handbook_id,
                    version_number,
                    distributed_by,
                    assigned,
                )

        return HandbookDistributionResponse(
            handbook_id=UUID(handbook_id),
            handbook_version=version_number,
            assigned_count=assigned,
            skipped_existing_count=skipped,
            distributed_at=datetime.utcnow(),
        )

    @staticmethod
    async def get_acknowledgement_summary(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookAcknowledgementSummary]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None

        doc_type = f"handbook:{handbook_id}:{handbook.active_version}"
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int AS assigned_count,
                    COUNT(*) FILTER (WHERE status = 'signed')::int AS signed_count,
                    COUNT(*) FILTER (WHERE status = 'pending_signature')::int AS pending_count,
                    COUNT(*) FILTER (WHERE status = 'expired')::int AS expired_count
                FROM employee_documents
                WHERE org_id = $1 AND doc_type = $2
                """,
                company_id,
                doc_type,
            )

        return HandbookAcknowledgementSummary(
            handbook_id=UUID(handbook_id),
            handbook_version=handbook.active_version,
            assigned_count=row["assigned_count"] if row else 0,
            signed_count=row["signed_count"] if row else 0,
            pending_count=row["pending_count"] if row else 0,
            expired_count=row["expired_count"] if row else 0,
        )

    @staticmethod
    async def generate_handbook_pdf_bytes(
        handbook_id: str,
        company_id: str,
    ) -> tuple[bytes, str]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            raise ValueError("Handbook not found")

        scope_label = ", ".join(sorted({scope.state for scope in handbook.scopes})) or "N/A"
        section_html = "".join(
            f"""
            <section class="section">
                <h2>{html.escape(section.title)}</h2>
                <div class="content">{html.escape(section.content).replace("\n", "<br/>")}</div>
            </section>
            """
            for section in handbook.sections
        )

        html_content = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    color: #111827;
                    margin: 40px;
                    line-height: 1.45;
                }}
                h1 {{
                    margin: 0 0 6px 0;
                    font-size: 26px;
                }}
                .meta {{
                    color: #4b5563;
                    font-size: 12px;
                    margin-bottom: 20px;
                }}
                .profile {{
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin-bottom: 16px;
                    font-size: 12px;
                }}
                .section {{
                    margin-top: 18px;
                    page-break-inside: avoid;
                }}
                .section h2 {{
                    font-size: 16px;
                    margin-bottom: 6px;
                    border-bottom: 1px solid #e5e7eb;
                    padding-bottom: 4px;
                }}
                .content {{
                    font-size: 12px;
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>
            <h1>{html.escape(handbook.title)}</h1>
            <div class="meta">Version {handbook.active_version} • Scope: {html.escape(scope_label)} • Status: {html.escape(handbook.status)}</div>
            <div class="profile">
                <div><strong>Legal Name:</strong> {html.escape(handbook.profile.legal_name)}</div>
                <div><strong>DBA:</strong> {html.escape(handbook.profile.dba or "N/A")}</div>
                <div><strong>CEO/President:</strong> {html.escape(handbook.profile.ceo_or_president)}</div>
                <div><strong>Headcount:</strong> {html.escape(str(handbook.profile.headcount) if handbook.profile.headcount is not None else "N/A")}</div>
            </div>
            {section_html}
        </body>
        </html>
        """

        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError("PDF generation is not available because WeasyPrint is not installed") from exc

        pdf_bytes = HTML(string=html_content).write_pdf()
        filename = _handbook_filename(handbook.title, handbook.active_version)
        return pdf_bytes, filename
