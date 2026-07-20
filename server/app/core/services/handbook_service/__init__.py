import asyncio
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import html
import logging
import re
import secrets
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

import asyncpg

if TYPE_CHECKING:  # type-only: the service never depends on FastAPI at runtime
    from fastapi import BackgroundTasks

from app.config import get_settings
from app.database import get_connection
from app.core.services.storage import get_storage
from app.core.models.handbook import (
    CompanyHandbookProfileInput,
    CompanyHandbookProfileResponse,
    HandbookAcknowledgementSummary,
    HandbookChangeRequestResponse,
    HandbookCoverageByState,
    HandbookCoverageResponse,
    HandbookCoverageSummary,
    HandbookCreateRequest,
    HandbookDetailResponse,
    HandbookDistributionRecipientResponse,
    HandbookDistributionResponse,
    HandbookFreshnessCheckResponse,
    HandbookFreshnessFindingResponse,
    HandbookGuidedDraftRequest,
    HandbookGuidedDraftResponse,
    HandbookGuidedQuestion,
    HandbookGuidedSectionSuggestion,
    HandbookListItemResponse,
    HandbookMissingSectionResponse,
    HandbookPublishResponse,
    HandbookScopeInput,
    HandbookScopeResponse,
    HandbookSectionInput,
    HandbookSectionResponse,
    HandbookUpdateRequest,
    HandbookWizardDraftResponse,
)

logger = logging.getLogger(__name__)

# Constants + module helpers split out (J6). Re-imported so the class below and
# external `from ...handbook_service import ...` callers keep working.
from app.core.services.handbook_service._constants import *  # noqa: F401,F403
from app.core.services.handbook_service._helpers import *  # noqa: F401,F403






































































































































class HandbookService:
    @staticmethod
    def _is_missing_freshness_table_error(exc: BaseException) -> bool:
        if not isinstance(exc, asyncpg.UndefinedTableError):
            return False
        msg = str(exc).lower()
        return (
            "handbook_freshness_checks" in msg
            or "handbook_freshness_findings" in msg
        )

    @staticmethod
    async def _ensure_freshness_tables(conn) -> None:
        checks_exists = await conn.fetchval(
            "SELECT to_regclass('public.handbook_freshness_checks') IS NOT NULL"
        )
        findings_exists = await conn.fetchval(
            "SELECT to_regclass('public.handbook_freshness_findings') IS NOT NULL"
        )
        if checks_exists and findings_exists:
            return

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handbook_freshness_checks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                triggered_by UUID REFERENCES users(id),
                check_type VARCHAR(20) NOT NULL DEFAULT 'manual'
                    CHECK (check_type IN ('manual', 'scheduled')),
                status VARCHAR(20) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
                is_outdated BOOLEAN NOT NULL DEFAULT false,
                impacted_sections INTEGER NOT NULL DEFAULT 0,
                changes_created INTEGER NOT NULL DEFAULT 0,
                requirements_fingerprint VARCHAR(128),
                previous_fingerprint VARCHAR(128),
                requirements_last_updated_at TIMESTAMPTZ,
                data_staleness_days INTEGER,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_handbook_created
            ON handbook_freshness_checks(handbook_id, created_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_company_created
            ON handbook_freshness_checks(company_id, created_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handbook_freshness_findings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                freshness_check_id UUID NOT NULL REFERENCES handbook_freshness_checks(id) ON DELETE CASCADE,
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                section_key VARCHAR(120),
                finding_type VARCHAR(40) NOT NULL,
                summary TEXT NOT NULL,
                old_content TEXT,
                proposed_content TEXT,
                source_url VARCHAR(1000),
                effective_date DATE,
                change_request_id UUID REFERENCES handbook_change_requests(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_check
            ON handbook_freshness_findings(freshness_check_id)
            """
        )

        # Enable RLS on dynamically-created tables
        await conn.execute(
            "ALTER TABLE handbook_freshness_checks ENABLE ROW LEVEL SECURITY"
        )
        await conn.execute(
            "ALTER TABLE handbook_freshness_checks FORCE ROW LEVEL SECURITY"
        )
        await conn.execute("""
            DO $$ BEGIN
                CREATE POLICY tenant_isolation ON handbook_freshness_checks
                    USING (company_id::text = current_setting('app.current_tenant_id', true));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_handbook
            ON handbook_freshness_findings(handbook_id)
            """
        )

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
    async def get_wizard_draft(
        company_id: str,
        user_id: str,
    ) -> Optional[HandbookWizardDraftResponse]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, company_id, user_id, draft_state, created_at, updated_at
                FROM handbook_wizard_drafts
                WHERE company_id = $1 AND user_id = $2
                """,
                company_id,
                user_id,
            )
            if not row:
                return None
            payload = dict(row)
            raw = payload.pop("draft_state", {}) or {}
            payload["state"] = json.loads(raw) if isinstance(raw, str) else raw
            return HandbookWizardDraftResponse(**payload)

    @staticmethod
    async def upsert_wizard_draft(
        company_id: str,
        user_id: str,
        state: dict[str, Any],
    ) -> HandbookWizardDraftResponse:
        normalized_state = _sanitize_wizard_draft_state(state)
        try:
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO handbook_wizard_drafts (
                        company_id, user_id, draft_state, created_at, updated_at
                    )
                    VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                    ON CONFLICT (company_id, user_id)
                    DO UPDATE SET
                        draft_state = EXCLUDED.draft_state,
                        updated_at = NOW()
                    RETURNING id, company_id, user_id, draft_state, created_at, updated_at
                    """,
                    company_id,
                    user_id,
                    json.dumps(normalized_state),
                )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

        payload = dict(row)
        raw = payload.pop("draft_state", {}) or {}
        payload["state"] = json.loads(raw) if isinstance(raw, str) else raw
        return HandbookWizardDraftResponse(**payload)

    @staticmethod
    async def delete_wizard_draft(
        company_id: str,
        user_id: str,
    ) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                """
                DELETE FROM handbook_wizard_drafts
                WHERE company_id = $1 AND user_id = $2
                """,
                company_id,
                user_id,
            )
            return result == "DELETE 1"

    @staticmethod
    async def _generate_guided_draft_ai_payload(
        *,
        company_name: str,
        industry_key: str,
        industry_label: str,
        title: str,
        mode: str,
        scopes: list[dict[str, Any]],
        normalized_profile: dict[str, Any],
        answers: dict[str, str],
        baseline_questions: list[dict[str, Any]],
        baseline_sections: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        try:
            settings = get_settings()
        except Exception:
            return None

        if not settings.gemini_api_key:
            return None

        try:
            from google import genai
            from app.core.services.genai_client import get_genai_client
        except Exception:
            return None

        try:
            from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

            await get_rate_limiter().check_limit("handbook_guided_draft", industry_key)
        except RateLimitExceeded as exc:
            raise GuidedDraftRateLimitError(
                "Guided draft rate limit exceeded. Please retry later."
            ) from exc
        except Exception:
            pass

        states = sorted({(scope.get("state") or "").upper() for scope in scopes if scope.get("state")})
        states_text = ", ".join(states) if states else "No states selected"

        prompt = (
            "You are an HR policy drafting assistant. "
            "Generate practical handbook setup guidance for an HR manager.\n\n"
            f"Company: {company_name}\n"
            f"Handbook title: {title}\n"
            f"Industry: {industry_label}\n"
            f"Mode: {mode}\n"
            f"States: {states_text}\n"
            f"Current profile flags: {json.dumps(normalized_profile)}\n"
            f"Known answers from HR manager: {json.dumps(answers)}\n"
            f"Baseline follow-up questions: {json.dumps(baseline_questions)}\n"
            f"Baseline suggested sections: {json.dumps(baseline_sections)}\n\n"
            "Return ONLY JSON with this shape:\n"
            "{\n"
            '  "summary": "one short paragraph",\n'
            '  "questions": [\n'
            '    {"id":"snake_case","question":"text","placeholder":"optional","required":true}\n'
            "  ],\n"
            '  "profile_updates": {\n'
            '    "remote_workers": false,\n'
            '    "tipped_employees": false,\n'
            '    "union_employees": false,\n'
            '    "federal_contracts": false,\n'
            '    "group_health_insurance": false,\n'
            '    "background_checks": false,\n'
            '    "hourly_employees": true,\n'
            '    "salaried_employees": false,\n'
            '    "commissioned_employees": false,\n'
            '    "tip_pooling": false\n'
            "  },\n"
            '  "suggested_sections": [\n'
            '    {"section_key":"snake_case","title":"text","content":"enforceable policy text","section_order":320}\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Provide at most 6 questions and at most 6 suggested sections.\n"
            "- Questions should help complete missing operational/legal hooks.\n"
            "- Suggested sections must be enforceable policy language, not summaries.\n"
            "- Use placeholders like [HR_CONTACT_EMAIL], [HARASSMENT_REPORTING_HOTLINE], [WORKWEEK_START_DAY] when details are unknown.\n"
            "- Keep content neutral, non-retaliatory, and suitable for legal review.\n"
        )

        try:
            client = get_genai_client(api_key=settings.gemini_api_key)
        except Exception:
            return None

        model_name = settings.analysis_model or "gemini-3-flash-preview"
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                ),
                timeout=45,
            )
            raw_text = (getattr(response, "text", None) or "").strip()
            parsed = _extract_json_payload(raw_text)
            if not parsed:
                return None
            try:
                from app.core.services.rate_limiter import get_rate_limiter

                await get_rate_limiter().record_call("handbook_guided_draft", industry_key)
            except Exception:
                pass
            return parsed
        except Exception:
            return None

    @staticmethod
    async def generate_guided_draft(
        company_id: str,
        data: HandbookGuidedDraftRequest,
    ) -> HandbookGuidedDraftResponse:
        normalized_scopes = [_normalize_scope(scope) for scope in data.scopes]
        normalized_profile = _normalize_profile(data.profile)
        answers = _sanitize_answer_map(data.answers)

        company_name = normalized_profile.get("legal_name") or "Company"
        company_industry = None
        async with get_connection() as conn:
            company_row = await conn.fetchrow(
                "SELECT name, industry FROM companies WHERE id = $1",
                company_id,
            )
            if company_row:
                company_name = company_row.get("name") or company_name
                company_industry = company_row.get("industry")

        industry_key = _normalize_industry(data.industry, company_industry)
        playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, GUIDED_INDUSTRY_PLAYBOOK["general"])
        industry_label = playbook.get("label", "General Employer")
        baseline_summary = playbook.get("summary", GUIDED_INDUSTRY_PLAYBOOK["general"]["summary"])

        baseline_questions = _build_guided_question_list(industry_key)
        unanswered_baseline_questions = _filter_unanswered_questions(baseline_questions, answers)
        baseline_profile_updates = _default_profile_updates_for_industry(industry_key, normalized_profile)
        baseline_sections = _build_default_section_suggestions(industry_key)

        ai_payload = await HandbookService._generate_guided_draft_ai_payload(
            company_name=company_name,
            industry_key=industry_key,
            industry_label=industry_label,
            title=(data.title or "").strip() or "Employee Handbook",
            mode=data.mode,
            scopes=normalized_scopes,
            normalized_profile=normalized_profile,
            answers=answers,
            baseline_questions=baseline_questions,
            baseline_sections=baseline_sections,
        )

        ai_summary = None
        ai_questions: list[dict[str, Any]] = []
        ai_profile_updates: dict[str, Any] = {}
        ai_sections: list[dict[str, Any]] = []

        if ai_payload:
            if isinstance(ai_payload.get("summary"), str):
                ai_summary = ai_payload["summary"].strip()
            ai_questions = _sanitize_guided_questions(ai_payload.get("questions") or [])
            ai_profile_updates = _sanitize_guided_profile_updates(
                ai_payload.get("profile_updates") or {},
                normalized_profile,
            )
            ai_sections = _sanitize_guided_sections(ai_payload.get("suggested_sections") or [])

        combined_profile_updates = {**baseline_profile_updates, **ai_profile_updates}

        combined_questions = _sanitize_guided_questions([*unanswered_baseline_questions, *ai_questions])
        unanswered_questions = _filter_unanswered_questions(combined_questions, answers)

        merged_sections = _merge_guided_sections(
            data.existing_custom_sections,
            baseline_sections=baseline_sections,
            ai_sections=ai_sections,
        )

        summary = ai_summary or baseline_summary
        if unanswered_questions:
            summary = (
                f"{summary} Answer the follow-up questions to finalize policy hooks before publishing."
            )

        return HandbookGuidedDraftResponse(
            industry=industry_key,
            summary=summary,
            clarification_needed=bool(unanswered_questions),
            questions=[HandbookGuidedQuestion(**question) for question in unanswered_questions],
            profile_updates=combined_profile_updates,
            suggested_sections=[HandbookGuidedSectionSuggestion(**section) for section in merged_sections],
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
        if data.auto_scope_from_employees and not normalized_scopes:
            async with get_connection() as _conn:
                auto_scopes = await derive_handbook_scopes_from_employees(_conn, company_id)
            normalized_scopes = [_normalize_scope(HandbookScopeInput(**s)) for s in auto_scopes]
        profile = _normalize_profile(data.profile)
        guided_answers = _sanitize_answer_map(data.guided_answers)
        profile_row: Optional[CompanyHandbookProfileResponse] = None
        _validate_handbook_file_reference(data.file_url)

        # Pre-flight: auto-research missing jurisdiction data for hospitality handbooks
        auto_researched = False
        if data.source_type == "template":
            async with get_connection() as pre_conn:
                company_industry = await pre_conn.fetchval(
                    "SELECT industry FROM companies WHERE id = $1", company_id,
                )
                industry_key = _normalize_industry(data.industry, company_industry)
                if industry_key in STRICT_TEMPLATE_INDUSTRIES:
                    pre_map = await _fetch_state_requirements(
                        pre_conn, normalized_scopes, written_policy_only=True,
                    )
                    unique_states, _, _ = _collect_state_city_scope(normalized_scopes)
                    missing = _find_missing_state_topics(industry_key, unique_states, pre_map)
                    if missing:
                        logger.info("Auto-researching missing handbook topics: %s", missing)
                        await _auto_research_missing_handbook_topics(missing, company_id=company_id)
                        auto_researched = True

        try:
            async with get_connection() as conn:
                async with conn.transaction():
                    company_industry = await conn.fetchval(
                        "SELECT industry FROM companies WHERE id = $1",
                        company_id,
                    )
                    industry_key = _normalize_industry(data.industry, company_industry)

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
                            file_url, file_name, created_by, guided_answers, workbook_type,
                            created_at, updated_at
                        )
                        VALUES ($1, $2, 'draft', $3, $4, 1, $5, $6, $7, $8, $9, NOW(), NOW())
                        RETURNING id
                        """,
                        company_id,
                        data.title,
                        data.mode,
                        data.source_type,
                        data.file_url,
                        data.file_name,
                        created_by,
                        json.dumps(guided_answers),
                        data.workbook_type,
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
                        state_requirement_map = await _fetch_state_requirements(
                            conn,
                            normalized_scopes,
                            written_policy_only=True,
                        )
                        sections = _build_template_sections(
                            data.mode,
                            normalized_scopes,
                            profile,
                            data.custom_sections,
                            industry_key=industry_key,
                            state_requirement_map=state_requirement_map,
                            guided_answers=guided_answers,
                            allow_fallback=auto_researched,
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
                            json.dumps(section["jurisdiction_scope"] or {}),
                            section["content"],
                        )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

        handbook = await HandbookService.get_handbook_by_id(str(handbook_id), company_id)
        if handbook is None:
            raise ValueError("Failed to create handbook")
        if profile_row is not None:
            handbook.profile = profile_row
        return handbook

    @staticmethod
    async def create_handbook_from_sections(
        company_id: str,
        title: str,
        scopes: list[dict[str, Any]],
        sections: list[dict[str, Any]],
        created_by: Optional[str] = None,
    ) -> HandbookDetailResponse:
        """Create a new draft handbook from pre-authored section bodies.

        The promotion target for Handbook Pilot: sections come already-written
        (AI-drafted + human-reviewed) instead of being assembled from the
        template builders, but the handbook/version/scope invariants are the
        same as ``create_handbook`` so the result edits/publishes normally.
        Sections land as ``section_type='custom'`` unless one specifies its own.
        """
        # Validate + normalize scopes through the same path create_handbook uses
        # (HandbookScopeInput enforces a 2-char state), instead of silently
        # dropping malformed rows. Dedupe by (state, city).
        norm_scopes: list[dict[str, Any]] = []
        seen_scope: set[tuple] = set()
        for s in scopes or []:
            try:
                normalized = _normalize_scope(HandbookScopeInput(
                    state=s.get("state"),
                    city=s.get("city") or None,
                    zipcode=s.get("zipcode") or None,
                    location_id=s.get("location_id") or None,
                ))
            except Exception:  # noqa: BLE001 - a bad stored scope shouldn't 500 the promote
                logger.warning("Skipping invalid handbook-pilot scope: %r", s)
                continue
            key = (normalized["state"], normalized["city"])
            if key in seen_scope:
                continue
            seen_scope.add(key)
            norm_scopes.append(normalized)
        if not norm_scopes:
            raise ValueError(
                "This session has no valid work locations. Add employee work "
                "locations before promoting handbook sections."
            )
        # Keep the (mode, scope-count) invariant validate_shape/update_handbook
        # enforce: single_state == exactly one scope; multi_state == >= 2 scopes.
        if len({s["state"] for s in norm_scopes}) > 1:
            mode = "multi_state"
        else:
            mode = "single_state"
            norm_scopes = norm_scopes[:1]

        try:
            async with get_connection() as conn:
                async with conn.transaction():
                    handbook_id = await conn.fetchval(
                        """
                        INSERT INTO handbooks (
                            company_id, title, status, mode, source_type, active_version,
                            created_by, created_at, updated_at
                        )
                        VALUES ($1, $2, 'draft', $3, 'template', 1, $4, NOW(), NOW())
                        RETURNING id
                        """,
                        company_id, title[:500], mode, created_by,
                    )
                    for scope in norm_scopes:
                        await conn.execute(
                            """
                            INSERT INTO handbook_scopes (handbook_id, state, city, zipcode, location_id, created_at)
                            VALUES ($1, $2, $3, $4, $5, NOW())
                            """,
                            handbook_id, scope["state"], scope["city"],
                            scope["zipcode"], scope["location_id"],
                        )
                    version_id = await conn.fetchval(
                        """
                        INSERT INTO handbook_versions (
                            handbook_id, version_number, summary, is_published, created_by, created_at
                        )
                        VALUES ($1, 1, $2, false, $3, NOW())
                        RETURNING id
                        """,
                        handbook_id, "Drafted with Handbook Pilot", created_by,
                    )
                    seen_keys: set[str] = set()
                    for order, section in enumerate(sections or [], start=1):
                        base_key = _slugify_key(
                            section.get("section_key") or section.get("title") or f"section_{order}",
                            max_len=110,
                        ) or f"section_{order}"
                        # UNIQUE(handbook_version_id, section_key) — disambiguate
                        # collisions the way _normalize_custom_sections does:
                        # shrink the base so the suffix always fits (no infinite
                        # loop when base_key is already at the length cap).
                        key = base_key
                        suffix = 2
                        while key in seen_keys:
                            suffix_token = f"_{suffix}"
                            key = f"{base_key[: max(1, 120 - len(suffix_token))]}{suffix_token}"
                            suffix += 1
                        seen_keys.add(key)
                        await conn.execute(
                            """
                            INSERT INTO handbook_sections (
                                handbook_version_id, section_key, title, section_order,
                                section_type, jurisdiction_scope, content, created_at, updated_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, NOW(), NOW())
                            """,
                            version_id, key,
                            str(section.get("title") or "Untitled Section")[:255],
                            order,
                            str(section.get("section_type") or "custom"),
                            json.dumps(section.get("jurisdiction_scope") or {}),
                            str(section.get("content") or ""),
                        )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

        handbook = await HandbookService.get_handbook_by_id(str(handbook_id), company_id)
        if handbook is None:
            raise ValueError("Failed to create handbook")
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
                SELECT id, section_key, title, content, section_order, section_type, jurisdiction_scope, last_reviewed_at
                FROM handbook_sections
                WHERE handbook_version_id = $1
                ORDER BY section_order ASC, created_at ASC
                """,
                active_version_id,
            )

            profile = await HandbookService.get_or_default_profile(company_id)

            section_models: list[HandbookSectionResponse] = []
            for section in section_rows:
                section_dict = dict(section)
                section_dict["jurisdiction_scope"] = _coerce_jurisdiction_scope(
                    section_dict.get("jurisdiction_scope")
                )
                section_models.append(HandbookSectionResponse(**section_dict))

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
                sections=section_models,
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
        try:
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
                    if data.workbook_type is not None:
                        updates.append(f"workbook_type = ${idx}")
                        params.append(data.workbook_type)
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
                        seen_keys: set[str] = set()
                        for section in data.sections:
                            key = section.section_key.strip()
                            if key in seen_keys:
                                raise ValueError(f"Duplicate section key '{key}' in handbook update")
                            seen_keys.add(key)

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
                                    json.dumps(section.jurisdiction_scope or {}),
                                )

                    if data.profile is not None:
                        await HandbookService._upsert_profile_with_conn(
                            conn,
                            company_id,
                            data.profile,
                            updated_by,
                        )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

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
                    "SELECT id, active_version, guided_answers FROM handbooks WHERE id = $1 AND company_id = $2",
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
                        # Safety net: resolve any lingering operational hook
                        # placeholders (e.g. from change requests created before
                        # the freshness-check hook-resolution fix).
                        resolved_content = change["proposed_content"]
                        _all_hook_tokens = list(LEGAL_OPERATIONAL_HOOKS.values()) + [ATTENDANCE_NOTICE_WINDOW_HOOK]
                        if resolved_content and any(
                            token in resolved_content
                            for token in _all_hook_tokens
                        ):
                            profile = await HandbookService.get_or_default_profile(company_id)
                            profile_data = profile.model_dump(
                                exclude={"company_id", "updated_by", "updated_at"},
                            )
                            norm_profile = _normalize_profile(CompanyHandbookProfileInput(**profile_data))
                            stored_ga = handbook.get("guided_answers") or {}
                            if isinstance(stored_ga, str):
                                stored_ga = json.loads(stored_ga) if stored_ga else {}
                            hv = _build_operational_hook_values(norm_profile, stored_ga)
                            resolved_content = _apply_hooks_to_content(resolved_content, hv)
                        await conn.execute(
                            """
                            UPDATE handbook_sections
                            SET content = $1, updated_at = NOW()
                            WHERE handbook_version_id = $2 AND section_key = $3
                            """,
                            resolved_content,
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
    def _build_freshness_response(
        check_row: dict[str, Any],
        findings_rows: list[dict[str, Any]],
    ) -> HandbookFreshnessCheckResponse:
        findings = [
            HandbookFreshnessFindingResponse(
                section_key=row.get("section_key"),
                finding_type=row.get("finding_type") or "info",
                summary=row.get("summary") or "",
                change_request_id=row.get("change_request_id"),
                source_url=row.get("source_url"),
                effective_date=row.get("effective_date"),
                age_days=row.get("age_days"),
            )
            for row in findings_rows
        ]

        checked_at = check_row.get("completed_at") or check_row.get("created_at") or datetime.utcnow()
        return HandbookFreshnessCheckResponse(
            check_id=check_row["id"],
            handbook_id=check_row["handbook_id"],
            check_type=check_row["check_type"],
            status=check_row["status"],
            is_outdated=bool(check_row.get("is_outdated")),
            impacted_sections=int(check_row.get("impacted_sections") or 0),
            new_change_requests_count=int(check_row.get("changes_created") or 0),
            requirements_last_updated_at=check_row.get("requirements_last_updated_at"),
            data_staleness_days=check_row.get("data_staleness_days"),
            current_fingerprint=check_row.get("requirements_fingerprint"),
            previous_fingerprint=check_row.get("previous_fingerprint"),
            checked_at=checked_at,
            findings=findings,
        )

    @staticmethod
    async def get_latest_freshness_check(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookFreshnessCheckResponse]:
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not exists:
                return None

            await HandbookService._ensure_freshness_tables(conn)

            try:
                check_row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbook_freshness_checks
                    WHERE handbook_id = $1 AND company_id = $2
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    handbook_id,
                    company_id,
                )
            except asyncpg.UndefinedTableError as exc:
                if not HandbookService._is_missing_freshness_table_error(exc):
                    raise
                await HandbookService._ensure_freshness_tables(conn)
                check_row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbook_freshness_checks
                    WHERE handbook_id = $1 AND company_id = $2
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    handbook_id,
                    company_id,
                )
            if not check_row:
                return None

            try:
                finding_rows = await conn.fetch(
                    """
                    SELECT section_key, finding_type, summary, change_request_id, source_url, effective_date, age_days
                    FROM handbook_freshness_findings
                    WHERE freshness_check_id = $1
                    ORDER BY created_at ASC
                    """,
                    check_row["id"],
                )
            except asyncpg.UndefinedTableError as exc:
                if not HandbookService._is_missing_freshness_table_error(exc):
                    raise
                await HandbookService._ensure_freshness_tables(conn)
                finding_rows = await conn.fetch(
                    """
                    SELECT section_key, finding_type, summary, change_request_id, source_url, effective_date, age_days
                    FROM handbook_freshness_findings
                    WHERE freshness_check_id = $1
                    ORDER BY created_at ASC
                    """,
                    check_row["id"],
                )
            return HandbookService._build_freshness_response(
                dict(check_row),
                [dict(row) for row in finding_rows],
            )

    @staticmethod
    async def run_freshness_check(
        handbook_id: str,
        company_id: str,
        triggered_by: Optional[str] = None,
        check_type: str = "manual",
    ) -> Optional[HandbookFreshnessCheckResponse]:
        if check_type not in {"manual", "scheduled"}:
            raise ValueError("Invalid freshness check type")

        async with get_connection() as conn:
            handbook_exists = await conn.fetchval(
                "SELECT 1 FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not handbook_exists:
                return None

            await HandbookService._ensure_freshness_tables(conn)

            try:
                check_id = await conn.fetchval(
                    """
                    INSERT INTO handbook_freshness_checks (
                        handbook_id,
                        company_id,
                        triggered_by,
                        check_type,
                        status,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4, 'running', NOW())
                    RETURNING id
                    """,
                    handbook_id,
                    company_id,
                    triggered_by,
                    check_type,
                )
            except asyncpg.UndefinedTableError as exc:
                if not HandbookService._is_missing_freshness_table_error(exc):
                    raise
                await HandbookService._ensure_freshness_tables(conn)
                check_id = await conn.fetchval(
                    """
                    INSERT INTO handbook_freshness_checks (
                        handbook_id,
                        company_id,
                        triggered_by,
                        check_type,
                        status,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4, 'running', NOW())
                    RETURNING id
                    """,
                    handbook_id,
                    company_id,
                    triggered_by,
                    check_type,
                )

            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1))",
                        f"handbook-freshness:{company_id}:{handbook_id}",
                    )

                    handbook_row = await conn.fetchrow(
                        "SELECT id, active_version, mode, guided_answers FROM handbooks WHERE id = $1 AND company_id = $2",
                        handbook_id,
                        company_id,
                    )
                    if not handbook_row:
                        raise ValueError("Handbook not found")

                    version_id = await HandbookService._get_active_version_id(
                        conn,
                        handbook_id,
                        handbook_row["active_version"],
                    )
                    if version_id is None:
                        raise ValueError("Active handbook version not found")

                    scope_rows = await conn.fetch(
                        """
                        SELECT state, city, zipcode, location_id
                        FROM handbook_scopes
                        WHERE handbook_id = $1
                        ORDER BY state, city NULLS LAST, zipcode NULLS LAST
                        """,
                        handbook_id,
                    )
                    scopes = [dict(row) for row in scope_rows]

                    profile = await HandbookService.get_or_default_profile(company_id)
                    profile_data = profile.model_dump(
                        exclude={"company_id", "updated_by", "updated_at"},
                    )
                    normalized_profile = _normalize_profile(CompanyHandbookProfileInput(**profile_data))
                    stored_answers = handbook_row.get("guided_answers") or {}
                    if isinstance(stored_answers, str):
                        stored_answers = json.loads(stored_answers) if stored_answers else {}
                    hook_values = _build_operational_hook_values(normalized_profile, stored_answers)
                    all_hook_tokens = list(LEGAL_OPERATIONAL_HOOKS.values()) + [ATTENDANCE_NOTICE_WINDOW_HOOK]
                    _using_generic_fallbacks = not stored_answers
                    profile_fingerprint = sha256(
                        json.dumps(normalized_profile, sort_keys=True, default=str).encode()
                    ).hexdigest()

                    requirement_map = await _fetch_state_requirements(conn, scopes, written_policy_only=True)
                    current_fingerprint, latest_requirement_update, _ = _build_requirements_fingerprint(
                        requirement_map
                    )
                    previous_fingerprint = await conn.fetchval(
                        """
                        SELECT requirements_fingerprint
                        FROM handbook_freshness_checks
                        WHERE handbook_id = $1
                          AND company_id = $2
                          AND status = 'completed'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        handbook_id,
                        company_id,
                    )
                    previous_profile_fingerprint = await conn.fetchval(
                        """
                        SELECT profile_fingerprint
                        FROM handbook_freshness_checks
                        WHERE handbook_id = $1
                          AND company_id = $2
                          AND status = 'completed'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        handbook_id,
                        company_id,
                    )

                    section_rows = await conn.fetch(
                        """
                        SELECT section_key, content, section_type, title,
                               last_reviewed_at, updated_at, created_at
                        FROM handbook_sections
                        WHERE handbook_version_id = $1
                        """,
                        version_id,
                    )
                    sections_by_key = {row["section_key"]: row["content"] for row in section_rows}

                    states, selected_cities_by_state, _ = _collect_state_city_scope(scopes)
                    impacted_sections = 0
                    changes_created = 0

                    for state in states:
                        section_key = _state_section_key(state)
                        if section_key not in sections_by_key:
                            continue

                        requirements = requirement_map.get(state, [])
                        proposed_content = _build_state_addendum_content(
                            state=state,
                            state_name=STATE_NAMES.get(state, state),
                            profile=normalized_profile,
                            requirements=requirements,
                            selected_cities=selected_cities_by_state.get(state),
                        )
                        old_content = sections_by_key.get(section_key) or ""
                        if _using_generic_fallbacks and old_content:
                            extracted = _extract_hooks_from_existing_content(
                                proposed_content, old_content, all_hook_tokens,
                            )
                            if extracted:
                                proposed_content = _apply_hooks_to_content(
                                    proposed_content, {**hook_values, **extracted},
                                )
                            else:
                                proposed_content = _apply_hooks_to_content(proposed_content, hook_values)
                        else:
                            proposed_content = _apply_hooks_to_content(proposed_content, hook_values)
                        if _normalize_section_content(old_content) == _normalize_section_content(proposed_content):
                            continue

                        impacted_sections += 1
                        source_url = _select_finding_source_url(requirements)
                        effective_date = _select_latest_effective_date(requirements)

                        existing_pending_change_id = await conn.fetchval(
                            """
                            SELECT id
                            FROM handbook_change_requests
                            WHERE handbook_id = $1
                              AND handbook_version_id = $2
                              AND section_key = $3
                              AND status = 'pending'
                              AND proposed_content = $4
                            LIMIT 1
                            """,
                            handbook_id,
                            version_id,
                            section_key,
                            proposed_content,
                        )

                        change_request_id = existing_pending_change_id
                        finding_type = "already_pending" if existing_pending_change_id else "change_request_created"
                        summary = (
                            f"{STATE_NAMES.get(state, state)} addendum appears outdated based on current jurisdiction requirements."
                        )

                        if not existing_pending_change_id:
                            change_request_id = await conn.fetchval(
                                """
                                INSERT INTO handbook_change_requests (
                                    handbook_id,
                                    handbook_version_id,
                                    section_key,
                                    old_content,
                                    proposed_content,
                                    rationale,
                                    source_url,
                                    effective_date,
                                    status,
                                    created_at
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', NOW())
                                RETURNING id
                                """,
                                handbook_id,
                                version_id,
                                section_key,
                                old_content,
                                proposed_content,
                                "Automated handbook freshness check detected newer statutory baseline language.",
                                source_url,
                                effective_date,
                            )
                            changes_created += 1

                        await conn.execute(
                            """
                            INSERT INTO handbook_freshness_findings (
                                freshness_check_id,
                                handbook_id,
                                section_key,
                                finding_type,
                                summary,
                                old_content,
                                proposed_content,
                                source_url,
                                effective_date,
                                change_request_id,
                                created_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                            """,
                            check_id,
                            handbook_id,
                            section_key,
                            finding_type,
                            summary,
                            old_content,
                            proposed_content,
                            source_url,
                            effective_date,
                            change_request_id,
                        )

                    # --- Core section re-evaluation ---
                    handbook_mode = handbook_row.get("mode") or "single_state"
                    regenerated_core = _build_core_sections(normalized_profile, handbook_mode, states)
                    for core_sec in regenerated_core:
                        core_key = core_sec["section_key"]
                        old_core = sections_by_key.get(core_key)
                        if old_core is None:
                            continue
                        if _using_generic_fallbacks and old_core:
                            extracted = _extract_hooks_from_existing_content(
                                core_sec["content"], old_core, all_hook_tokens,
                            )
                            if extracted:
                                proposed_core = _apply_hooks_to_content(
                                    core_sec["content"], {**hook_values, **extracted},
                                )
                            else:
                                proposed_core = _apply_hooks_to_content(core_sec["content"], hook_values)
                        else:
                            proposed_core = _apply_hooks_to_content(core_sec["content"], hook_values)
                        if _normalize_section_content(old_core) == _normalize_section_content(proposed_core):
                            continue

                        impacted_sections += 1

                        existing_core_change = await conn.fetchval(
                            """
                            SELECT id
                            FROM handbook_change_requests
                            WHERE handbook_id = $1
                              AND handbook_version_id = $2
                              AND section_key = $3
                              AND status = 'pending'
                              AND proposed_content = $4
                            LIMIT 1
                            """,
                            handbook_id,
                            version_id,
                            core_key,
                            proposed_core,
                        )

                        core_cr_id = existing_core_change
                        core_finding_type = "already_pending" if existing_core_change else "change_request_created"

                        if not existing_core_change:
                            core_cr_id = await conn.fetchval(
                                """
                                INSERT INTO handbook_change_requests (
                                    handbook_id,
                                    handbook_version_id,
                                    section_key,
                                    old_content,
                                    proposed_content,
                                    rationale,
                                    status,
                                    created_at
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
                                RETURNING id
                                """,
                                handbook_id,
                                version_id,
                                core_key,
                                old_core,
                                proposed_core,
                                "Company profile changes require core section updates.",
                            )
                            changes_created += 1

                        await conn.execute(
                            """
                            INSERT INTO handbook_freshness_findings (
                                freshness_check_id,
                                handbook_id,
                                section_key,
                                finding_type,
                                summary,
                                old_content,
                                proposed_content,
                                change_request_id,
                                created_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                            """,
                            check_id,
                            handbook_id,
                            core_key,
                            core_finding_type,
                            f"Core section '{core_sec['title']}' content differs from current company profile.",
                            old_core,
                            proposed_core,
                            core_cr_id,
                        )

                    # --- Custom/uploaded section age tracking ---
                    now_utc = datetime.utcnow()
                    for sec_row in section_rows:
                        sec_type = (sec_row.get("section_type") or "").strip().lower()
                        if sec_type not in ("custom", "uploaded"):
                            continue
                        review_anchor = (
                            sec_row.get("last_reviewed_at")
                            or sec_row.get("updated_at")
                            or sec_row.get("created_at")
                        )
                        if review_anchor is None:
                            continue
                        age_days = (now_utc - review_anchor.replace(tzinfo=None)).days
                        if age_days <= 365:
                            continue

                        months = age_days // 30
                        sec_title = sec_row.get("title") or sec_row.get("section_key") or "Untitled"
                        impacted_sections += 1

                        await conn.execute(
                            """
                            INSERT INTO handbook_freshness_findings (
                                freshness_check_id,
                                handbook_id,
                                section_key,
                                finding_type,
                                summary,
                                age_days,
                                created_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, NOW())
                            """,
                            check_id,
                            handbook_id,
                            sec_row["section_key"],
                            "review_recommended",
                            f"'{sec_title}' has not been reviewed in {months} months.",
                            age_days,
                        )

                    is_outdated = bool(
                        impacted_sections > 0
                        or (
                            previous_fingerprint
                            and current_fingerprint
                            and previous_fingerprint != current_fingerprint
                        )
                        or (
                            previous_profile_fingerprint
                            and profile_fingerprint
                            and previous_profile_fingerprint != profile_fingerprint
                        )
                    )
                    data_staleness_days = (
                        (datetime.utcnow().date() - latest_requirement_update.date()).days
                        if latest_requirement_update
                        else None
                    )

                    await conn.execute(
                        """
                        UPDATE handbook_freshness_checks
                        SET
                            status = 'completed',
                            is_outdated = $1,
                            impacted_sections = $2,
                            changes_created = $3,
                            requirements_fingerprint = $4,
                            previous_fingerprint = $5,
                            requirements_last_updated_at = $6,
                            data_staleness_days = $7,
                            profile_fingerprint = $8,
                            completed_at = NOW()
                        WHERE id = $9
                        """,
                        is_outdated,
                        impacted_sections,
                        changes_created,
                        current_fingerprint,
                        previous_fingerprint,
                        latest_requirement_update,
                        data_staleness_days,
                        profile_fingerprint,
                        check_id,
                    )

                    if changes_created > 0:
                        await conn.execute(
                            """
                            UPDATE handbooks
                            SET updated_at = NOW(), file_url = NULL, file_name = NULL
                            WHERE id = $1
                            """,
                            handbook_id,
                        )

                    check_row = await conn.fetchrow(
                        "SELECT * FROM handbook_freshness_checks WHERE id = $1",
                        check_id,
                    )
                    finding_rows = await conn.fetch(
                        """
                        SELECT section_key, finding_type, summary, change_request_id, source_url, effective_date, age_days
                        FROM handbook_freshness_findings
                        WHERE freshness_check_id = $1
                        ORDER BY created_at ASC
                        """,
                        check_id,
                    )

                return HandbookService._build_freshness_response(
                    dict(check_row),
                    [dict(row) for row in finding_rows],
                )
            except Exception as exc:
                await conn.execute(
                    """
                    UPDATE handbook_freshness_checks
                    SET status = 'failed', error_message = $1, completed_at = NOW()
                    WHERE id = $2
                    """,
                    str(exc),
                    check_id,
                )
                raise

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
        employee_ids: Optional[list[str]] = None,
        background_tasks: Optional["BackgroundTasks"] = None,
    ) -> Optional[HandbookDistributionResponse]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None
        if handbook.status != "active":
            raise ValueError("Only active handbooks can be distributed for acknowledgement")

        file_url, _, version_number = await HandbookService._ensure_handbook_pdf(handbook_id, company_id)
        doc_type = HandbookService.build_doc_type(handbook_id, version_number)

        async with get_connection() as conn:
            async with conn.transaction():
                selected_employee_ids: list[UUID] = []
                if employee_ids is not None:
                    dedup: set[UUID] = set()
                    for raw_id in employee_ids:
                        parsed_id = UUID(str(raw_id))
                        if parsed_id in dedup:
                            continue
                        dedup.add(parsed_id)
                        selected_employee_ids.append(parsed_id)
                    if not selected_employee_ids:
                        raise ValueError("Select at least one employee to send this handbook.")

                if selected_employee_ids:
                    employee_rows = await conn.fetch(
                        """
                        SELECT id, email, first_name, last_name
                        FROM employees
                        WHERE org_id = $1
                          AND termination_date IS NULL
                          AND email IS NOT NULL
                          AND id = ANY($2::uuid[])
                        ORDER BY created_at ASC
                        """,
                        company_id,
                        selected_employee_ids,
                    )
                    found_ids = {row["id"] for row in employee_rows}
                    missing_ids = [employee_id for employee_id in selected_employee_ids if employee_id not in found_ids]
                    if missing_ids:
                        raise ValueError("Some selected employees are no longer active for this company.")
                else:
                    employee_rows = await conn.fetch(
                        """
                        SELECT id, email, first_name, last_name
                        FROM employees
                        WHERE org_id = $1
                          AND termination_date IS NULL
                          AND email IS NOT NULL
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
                notify_rows: list[dict] = []
                for employee in employee_rows:
                    if employee["id"] in existing_employee_ids:
                        skipped += 1
                        continue

                    sign_token = secrets.token_urlsafe(32)
                    record = {"employee_id": employee["id"], "sign_token": sign_token}
                    record.update(insertable)
                    cols = [col for col in record.keys() if col in columns]
                    # Only advertise the public link if the column that stores it
                    # actually exists (migration signdoc01 applied). Pre-migration
                    # the token is filtered out of the INSERT above and stored NULL,
                    # so emailing it would 404 — fall the email back to the portal.
                    token_persisted = "sign_token" in cols
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
                        # Carries the public sign link's token — no login required to
                        # acknowledge — but only when it was actually persisted, so the
                        # email can never link to a token the DB doesn't hold.
                        notify_rows.append({
                            **dict(employee),
                            "sign_token": sign_token if token_persisted else None,
                        })
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

        # Deferred, never awaited here: a roster-wide send is N sequential calls
        # to an external mail API, and holding the response open for it times the
        # admin out on a distribution that already committed. A caller that
        # passes no scheduler gets no email — employees still see the document
        # waiting in their portal, which is the durable signal.
        if background_tasks is not None and notify_rows:
            background_tasks.add_task(
                HandbookService._notify_handbook_recipients,
                company_id,
                handbook.title,
                notify_rows,
            )

        return HandbookDistributionResponse(
            handbook_id=UUID(handbook_id),
            handbook_version=version_number,
            assigned_count=assigned,
            skipped_existing_count=skipped,
            distributed_at=datetime.utcnow(),
        )

    @staticmethod
    async def _notify_handbook_recipients(
        company_id: str,
        handbook_title: str,
        recipients: list[dict],
    ) -> None:
        try:
            from app.core.services.email import get_email_service

            async with get_connection() as conn:
                company_name = await conn.fetchval(
                    "SELECT name FROM companies WHERE id = $1", company_id
                )
            email_service = get_email_service()
            for row in recipients:
                if not row.get("email"):
                    continue
                name = " ".join(
                    part for part in [row.get("first_name"), row.get("last_name")] if part
                ).strip()
                try:
                    await email_service.send_handbook_acknowledgement_email(
                        to_email=row["email"],
                        to_name=name or None,
                        company_name=company_name or "Your employer",
                        handbook_title=handbook_title,
                        sign_token=row.get("sign_token"),
                    )
                except Exception as exc:  # one bad address must not stop the rest
                    logger.warning(
                        "Handbook acknowledgement email failed for %s: %s", row["email"], exc
                    )
        except Exception as exc:
            logger.warning("Handbook acknowledgement notification pass failed: %s", exc)

    @staticmethod
    async def list_distribution_recipients(
        handbook_id: str,
        company_id: str,
    ) -> Optional[list[HandbookDistributionRecipientResponse]]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None
        if handbook.status != "active":
            raise ValueError("Only active handbooks can be distributed for acknowledgement")

        doc_type = HandbookService.build_doc_type(handbook_id, handbook.active_version)
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    e.id AS employee_id,
                    COALESCE(NULLIF(TRIM(e.first_name || ' ' || e.last_name), ''), e.email) AS name,
                    e.email,
                    (
                        SELECT status
                        FROM employee_invitations
                        WHERE employee_id = e.id
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) AS invitation_status,
                    EXISTS (
                        SELECT 1
                        FROM employee_documents ed
                        WHERE ed.org_id = $1
                          AND ed.employee_id = e.id
                          AND ed.doc_type = $2
                          AND ed.status IN ('pending_signature', 'signed')
                    ) AS already_assigned
                FROM employees e
                WHERE e.org_id = $1
                  AND e.termination_date IS NULL
                  AND e.email IS NOT NULL
                ORDER BY e.created_at ASC
                """,
                company_id,
                doc_type,
            )

        return [
            HandbookDistributionRecipientResponse(
                employee_id=row["employee_id"],
                name=row["name"],
                email=row["email"],
                invitation_status=row["invitation_status"],
                already_assigned=bool(row["already_assigned"]),
            )
            for row in rows
        ]

    @staticmethod
    async def get_acknowledgement_summary(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookAcknowledgementSummary]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None

        doc_type = HandbookService.build_doc_type(handbook_id, handbook.active_version)
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

    # ------------------------------------------------------------------ #
    # Public share links — a published handbook, readable by anyone holding
    # the URL. See migration hbshare01.
    # ------------------------------------------------------------------ #

    # The `handbook:<id>:<version>` employee_documents.doc_type format is minted
    # here (see distribute_to_employees / get_acknowledgement_summary), so it is
    # decoded here too — a route that hand-parses it drifts the moment the format
    # grows a segment.
    DOC_TYPE_PREFIX = "handbook"

    @staticmethod
    def build_doc_type(handbook_id: str, version_number: int) -> str:
        return f"{HandbookService.DOC_TYPE_PREFIX}:{handbook_id}:{version_number}"

    @staticmethod
    def parse_doc_type(doc_type: Optional[str]) -> Optional[tuple[str, int]]:
        """`handbook:<uuid>:<version>` → (handbook_id, version), else None.

        Returns None for any non-handbook or malformed value — including a
        non-UUID id, which would otherwise reach asyncpg as a UUID-typed
        parameter and raise DataError (a 500) rather than a clean 400.
        """
        parts = (doc_type or "").split(":")
        if len(parts) != 3 or parts[0] != HandbookService.DOC_TYPE_PREFIX:
            return None
        try:
            UUID(parts[1])
            return parts[1], int(parts[2])
        except ValueError:
            return None

    @staticmethod
    async def get_sections_for_version(
        handbook_id: str,
        company_id: str,
        version_number: int,
    ) -> Optional[dict]:
        """Readable content of a specific handbook version.

        Version-pinned on purpose: an employee acknowledges the text that was
        distributed to them, not whatever the current draft happens to say.
        """
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT id, title FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not row:
                return None
            version_id = await HandbookService._get_active_version_id(
                conn, str(row["id"]), version_number
            )
            if version_id is None:
                return None
            sections = await conn.fetch(
                """
                SELECT title, content, section_order
                FROM handbook_sections
                WHERE handbook_version_id = $1
                ORDER BY section_order ASC, created_at ASC
                """,
                version_id,
            )
        return {
            "title": row["title"],
            "version": version_number,
            "sections": [dict(s) for s in sections],
        }

    @staticmethod
    async def get_share_link(handbook_id: str, company_id: str) -> Optional[dict]:
        """The handbook's live (unrevoked, unexpired) share link, if any."""
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT token, created_at, expires_at, view_count, last_viewed_at
                FROM handbook_share_links
                WHERE handbook_id = $1 AND company_id = $2
                  AND revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > now())
                """,
                handbook_id,
                company_id,
            )
        return dict(row) if row else None

    @staticmethod
    async def create_share_link(
        handbook_id: str,
        company_id: str,
        created_by: Optional[str],
        expires_in_days: Optional[int] = None,
    ) -> Optional[dict]:
        """Mint a share link for a published handbook.

        Idempotent: an existing live link is returned rather than minting a
        second valid URL for the same handbook. Returns None if the handbook
        isn't this company's, or isn't published — an unpublished draft has no
        business being world-readable.
        """
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            if expires_in_days
            else None
        )
        async with get_connection() as conn:
            status = await conn.fetchval(
                "SELECT status FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if status != "active":
                return None

            # Sweep expired-but-unrevoked rows first: the partial unique index
            # keys on revoked_at alone (now() can't live in an index predicate),
            # so a lapsed link would otherwise block a re-share.
            await conn.execute(
                """
                UPDATE handbook_share_links SET revoked_at = now()
                WHERE handbook_id = $1 AND revoked_at IS NULL
                  AND expires_at IS NOT NULL AND expires_at <= now()
                """,
                handbook_id,
            )
            # Let the partial unique index arbitrate, rather than checking for an
            # existing row first: two concurrent creates both pass a check-then-
            # insert and the loser raises UniqueViolation. DO NOTHING makes the
            # loser return no row, and we then read back whichever link won.
            row = await conn.fetchrow(
                """
                INSERT INTO handbook_share_links
                    (handbook_id, company_id, token, created_by, expires_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (handbook_id) WHERE revoked_at IS NULL DO NOTHING
                RETURNING token, created_at, expires_at, view_count, last_viewed_at
                """,
                handbook_id,
                company_id,
                secrets.token_urlsafe(32),
                created_by,
                expires_at,
            )
            if row is None:
                row = await conn.fetchrow(
                    """
                    SELECT token, created_at, expires_at, view_count, last_viewed_at
                    FROM handbook_share_links
                    WHERE handbook_id = $1 AND revoked_at IS NULL
                    """,
                    handbook_id,
                )
        return dict(row) if row else None

    @staticmethod
    async def revoke_share_link(handbook_id: str, company_id: str) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                """
                UPDATE handbook_share_links SET revoked_at = now()
                WHERE handbook_id = $1 AND company_id = $2 AND revoked_at IS NULL
                """,
                handbook_id,
                company_id,
            )
        return result.endswith(" 1")

    @staticmethod
    async def get_handbook_by_share_token(token: str) -> Optional[dict]:
        """Resolve a share token to the published handbook's readable content.

        No company scoping — the token *is* the authorization. Returns None for
        an unknown, revoked, or expired token, and for a handbook that has since
        been unpublished (archived or reverted to draft), so taking a handbook
        down takes the public link down with it.
        """
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT h.id, h.title, h.active_version, h.published_at, c.name AS company_name
                FROM handbook_share_links l
                JOIN handbooks h ON h.id = l.handbook_id
                JOIN companies c ON c.id = h.company_id
                WHERE l.token = $1
                  AND l.revoked_at IS NULL
                  AND (l.expires_at IS NULL OR l.expires_at > now())
                  AND h.status = 'active'
                """,
                token,
            )
            if not row:
                return None

            version_id = await HandbookService._get_active_version_id(
                conn, str(row["id"]), row["active_version"]
            )
            if version_id is None:
                # Legacy rows can point at an active_version with no matching
                # handbook_versions row; get_handbook_by_id falls back the same
                # way. Without this the share link serves a 200 with zero
                # sections, which reads as "they published an empty handbook".
                version_id = await conn.fetchval(
                    """
                    SELECT id FROM handbook_versions
                    WHERE handbook_id = $1
                    ORDER BY version_number DESC
                    LIMIT 1
                    """,
                    row["id"],
                )
            if version_id is None:
                return None

            sections = await conn.fetch(
                """
                SELECT title, content, section_order
                FROM handbook_sections
                WHERE handbook_version_id = $1
                ORDER BY section_order ASC, created_at ASC
                """,
                version_id,
            )
            await conn.execute(
                """
                UPDATE handbook_share_links
                SET view_count = view_count + 1, last_viewed_at = now()
                WHERE token = $1
                """,
                token,
            )

        return {
            "title": row["title"],
            "company_name": row["company_name"],
            "published_at": row["published_at"],
            "version": row["active_version"],
            "sections": [dict(s) for s in sections],
        }

    @staticmethod
    async def generate_handbook_pdf_bytes(
        handbook_id: str,
        company_id: str,
    ) -> tuple[bytes, str]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            raise ValueError("Handbook not found")

        scope_label = ", ".join(sorted({scope.state for scope in handbook.scopes})) or "N/A"
        _br = "<br/>"
        _nl = "\n"
        section_html = "".join(
            f"""
            <section class="section">
                <h2>{html.escape(section.title)}</h2>
                <div class="content">{html.escape(section.content).replace(_nl, _br)}</div>
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
            from app.core.services.pdf import render_pdf
        except ImportError as exc:
            raise RuntimeError("PDF generation is not available because WeasyPrint is not installed") from exc

        pdf_bytes = render_pdf(html_content)
        filename = _handbook_filename(handbook.title, handbook.active_version)
        return pdf_bytes, filename

    @staticmethod
    def compute_coverage(
        handbook: HandbookDetailResponse,
        company_industry: Optional[str] = None,
    ) -> HandbookCoverageResponse:
        scopes = handbook.scopes
        profile = handbook.profile

        # Uploaded handbooks have only a placeholder section — score them
        # as unscored so the UI doesn't report misleading numbers.
        if handbook.source_type == "upload":
            scoped_states = sorted({s.state.upper() for s in scopes})
            industry_key = _normalize_industry(None, company_industry)
            playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, {})
            return HandbookCoverageResponse(
                handbook_id=handbook.id,
                strength_score=0,
                strength_label="Weak",
                total_sections=len(handbook.sections),
                core_sections=0,
                state_sections=0,
                custom_sections=0,
                uploaded_sections=len(handbook.sections),
                federal_core_count=0,
                state_level_count=len(scoped_states),
                city_level_count=sum(1 for s in scopes if s.city),
                state_coverage=[],
                missing_sections=[HandbookMissingSectionResponse(
                    section_key="uploaded_not_scored",
                    title="Uploaded handbook",
                    reason="Uploaded handbooks cannot be scored — only template-based handbooks are analyzed",
                    priority="recommended",
                )],
                industry=industry_key,
                industry_label=playbook.get("label", industry_key.replace("_", " ").title()),
            )

        sections = handbook.sections

        section_keys = {s.section_key for s in sections}
        all_text = "\n".join(
            f"{s.section_key} {s.title} {s.content}".lower() for s in sections
        )

        # ── 1. Core sections (30 pts) ──
        CORE_KEYS = {
            "welcome", "employment_relationship", "equal_opportunity",
            "hours_and_pay", "attendance_and_remote", "benefits_and_leave",
            "workplace_standards", "investigations", "acknowledgement",
        }
        present_core = sum(1 for k in CORE_KEYS if k in section_keys)
        core_score = (present_core / len(CORE_KEYS)) * 30

        # ── 2. State addenda (30 pts) ──
        # _build_state_addendum_content always emits heading text containing
        # category keywords (e.g. "Paid Sick Leave") even when no compliance
        # data exists, plus a fallback review line. We strip out heading lines
        # and fallback lines so only actual requirement data drives coverage.
        _fallback_lower = ADDENDUM_FALLBACK_REVIEW_LINE.lower()

        scoped_states = sorted({s.state.upper() for s in scopes})
        state_coverage_list: list[HandbookCoverageByState] = []
        state_scores: list[float] = []
        for st in scoped_states:
            addendum_key = f"state_addendum_{st.lower()}"
            has_addendum = any(
                s.section_key == addendum_key or s.section_key.startswith(f"state_addendum_{st.lower()}_")
                for s in sections
            )
            # Collect only substantive content lines: exclude numbered
            # headings (e.g. "1) Wage...") and the fallback review line.
            raw_lines: list[str] = []
            for s in sections:
                if s.section_key == addendum_key or s.section_key.startswith(f"state_addendum_{st.lower()}_"):
                    for line in s.content.lower().split("\n"):
                        stripped = line.strip().lstrip("- ")
                        if not stripped:
                            continue
                        if _fallback_lower in stripped:
                            continue
                        if re.match(r"^\d+\)\s", stripped):
                            continue
                        raw_lines.append(stripped)
            addendum_content = "\n".join(raw_lines)
            covered = []
            missing = []
            for cat, keywords in MANDATORY_STATE_TOPIC_RULES.items():
                if any(kw in addendum_content for kw in keywords):
                    covered.append(cat)
                else:
                    missing.append(cat)
            cat_coverage = len(covered) / len(MANDATORY_STATE_TOPIC_RULES) if MANDATORY_STATE_TOPIC_RULES else 1.0
            state_scores.append(cat_coverage)
            city_scopes = sorted({s.city for s in scopes if s.state.upper() == st and s.city})
            state_coverage_list.append(HandbookCoverageByState(
                state=st,
                state_name=STATE_NAMES.get(st, st),
                has_addendum=has_addendum,
                covered_categories=covered,
                missing_categories=missing,
                city_scopes=city_scopes,
            ))
        avg_state = sum(state_scores) / len(state_scores) if state_scores else 1.0
        state_score = avg_state * 30

        # ── 3. Profile requirements (25 pts) ──
        PROFILE_GAP_RULES = [
            ("tipped_employees", ["tip"], "Tipped employees flagged but no tip compliance policy"),
            ("tip_pooling", ["tip pool"], "Tip pooling enabled but no tip pool governance section"),
            ("union_employees", ["union", "collective bargaining"], "Union employees but no CBA/union policy section"),
            ("federal_contracts", ["federal contract"], "Federal contracts but no contractor compliance section"),
            ("remote_workers", ["remote work"], "Remote workers but no remote work compliance section"),
            ("background_checks", ["background check", "fair chance"], "Background checks enabled but no background check policy"),
            ("group_health_insurance", ["health insurance", "benefits enrollment"], "Group health insurance but no benefits enrollment section"),
        ]
        missing_sections: list[HandbookMissingSectionResponse] = []
        total_profile_checks = 0
        profile_missing_count = 0

        for flag, keywords, reason in PROFILE_GAP_RULES:
            if getattr(profile, flag, False):
                total_profile_checks += 1
                if not any(kw in all_text for kw in keywords):
                    profile_missing_count += 1
                    missing_sections.append(HandbookMissingSectionResponse(
                        section_key=flag,
                        title=reason.split(" but ")[0] if " but " in reason else flag.replace("_", " ").title(),
                        reason=reason,
                        priority="required",
                    ))

        # Special case: minors — check per-state
        if getattr(profile, "minors", False):
            for st in scoped_states:
                total_profile_checks += 1
                addendum_text_st = "\n".join(
                    f"{s.section_key} {s.title} {s.content}".lower()
                    for s in sections
                    if s.section_key.startswith(f"state_addendum_{st.lower()}")
                )
                minor_keywords = MANDATORY_STATE_TOPIC_RULES.get("minor_work_permit", ())
                if not any(kw in addendum_text_st for kw in minor_keywords):
                    profile_missing_count += 1
                    missing_sections.append(HandbookMissingSectionResponse(
                        section_key=f"minors_{st.lower()}",
                        title=f"Youth employment coverage for {STATE_NAMES.get(st, st)}",
                        reason=f"Minors employed but no youth employment coverage for {STATE_NAMES.get(st, st)}",
                        priority="required",
                    ))

        if total_profile_checks == 0:
            profile_score = 25.0
        else:
            profile_score = ((total_profile_checks - profile_missing_count) / total_profile_checks) * 25

        # ── 4. Industry sections (15 pts) ──
        industry_key = _normalize_industry(None, company_industry)
        playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, {})
        industry_label = playbook.get("label", industry_key.replace("_", " ").title())
        expected_industry_sections = playbook.get("sections", [])
        industry_found = 0
        for exp in expected_industry_sections:
            exp_title = exp.get("title", "")
            slug = re.sub(r"[^a-z0-9]+", "_", exp_title.lower()).strip("_")
            if any(
                slug in s.section_key or slug in re.sub(r"[^a-z0-9]+", "_", s.title.lower()).strip("_")
                for s in sections
            ):
                industry_found += 1
            else:
                missing_sections.append(HandbookMissingSectionResponse(
                    section_key=slug,
                    title=exp_title,
                    reason=f"Industry playbook ({industry_label}) recommends this section",
                    priority="recommended",
                ))
        if expected_industry_sections:
            industry_score = (industry_found / len(expected_industry_sections)) * 15
        else:
            industry_score = 15.0

        # ── Final score ──
        strength_score = min(100, max(0, round(core_score + state_score + profile_score + industry_score)))
        if strength_score >= 80:
            strength_label = "Strong"
        elif strength_score >= 50:
            strength_label = "Moderate"
        else:
            strength_label = "Weak"

        core_count = sum(1 for s in sections if s.section_type == "core")
        state_count = sum(1 for s in sections if s.section_type == "state")
        custom_count = sum(1 for s in sections if s.section_type == "custom")
        uploaded_count = sum(1 for s in sections if s.section_type == "uploaded")

        federal_core_count = core_count
        state_level_count = len(scoped_states)
        city_level_count = sum(1 for s in scopes if s.city)

        return HandbookCoverageResponse(
            handbook_id=handbook.id,
            strength_score=strength_score,
            strength_label=strength_label,
            total_sections=len(sections),
            core_sections=core_count,
            state_sections=state_count,
            custom_sections=custom_count,
            uploaded_sections=uploaded_count,
            federal_core_count=federal_core_count,
            state_level_count=state_level_count,
            city_level_count=city_level_count,
            state_coverage=state_coverage_list,
            missing_sections=missing_sections,
            industry=industry_key,
            industry_label=industry_label,
        )

    @staticmethod
    async def compute_coverage_summaries(company_ids: list[str]) -> list[HandbookCoverageSummary]:
        if not company_ids:
            return []

        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    h.id AS handbook_id,
                    h.title AS handbook_title,
                    h.company_id,
                    c.name AS company_name,
                    c.industry,
                    h.active_version,
                    h.source_type,
                    hs2.section_key,
                    hs2.title AS section_title,
                    hs2.content,
                    hs2.section_type,
                    hsc.state AS scope_state,
                    hsc.city AS scope_city
                FROM handbooks h
                JOIN companies c ON c.id = h.company_id
                JOIN handbook_versions hv
                    ON hv.handbook_id = h.id AND hv.version_number = h.active_version
                LEFT JOIN handbook_sections hs2 ON hs2.handbook_version_id = hv.id
                LEFT JOIN handbook_scopes hsc ON hsc.handbook_id = h.id
                WHERE h.company_id = ANY($1::uuid[])
                  AND h.status = 'active'
                  AND h.source_type = 'template'
                ORDER BY h.company_id, h.id
                """,
                company_ids,
            )

        # Group by handbook
        from collections import defaultdict
        _fallback_lower = ADDENDUM_FALLBACK_REVIEW_LINE.lower()
        hb_data: dict[str, dict] = {}
        hb_sections: dict[str, dict[str, dict]] = defaultdict(dict)
        hb_scopes: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            hb_id = str(row["handbook_id"])
            if hb_id not in hb_data:
                hb_data[hb_id] = {
                    "handbook_id": hb_id,
                    "handbook_title": row["handbook_title"],
                    "company_id": str(row["company_id"]),
                    "company_name": row["company_name"],
                    "industry": row["industry"],
                }
            if row["section_key"]:
                hb_sections[hb_id][row["section_key"]] = {
                    "section_key": row["section_key"],
                    "title": row["section_title"] or "",
                    "content": row["content"] or "",
                    "section_type": row["section_type"] or "custom",
                }
            if row["scope_state"]:
                hb_scopes[hb_id].add(row["scope_state"].upper())

        summaries: list[HandbookCoverageSummary] = []
        for hb_id, meta in hb_data.items():
            secs = list(hb_sections[hb_id].values())
            states = hb_scopes[hb_id]
            section_keys = {s["section_key"] for s in secs}

            CORE_KEYS = {
                "welcome", "employment_relationship", "equal_opportunity",
                "hours_and_pay", "attendance_and_remote", "benefits_and_leave",
                "workplace_standards", "investigations", "acknowledgement",
            }
            core_score = (sum(1 for k in CORE_KEYS if k in section_keys) / len(CORE_KEYS)) * 30

            state_scores_l: list[float] = []
            for st in states:
                raw_lines: list[str] = []
                for s in secs:
                    if s["section_key"].startswith(f"state_addendum_{st.lower()}"):
                        for line in s["content"].lower().split("\n"):
                            stripped = line.strip().lstrip("- ")
                            if not stripped or _fallback_lower in stripped or re.match(r"^\d+\)\s", stripped):
                                continue
                            raw_lines.append(stripped)
                addendum_content = "\n".join(raw_lines)
                covered = sum(
                    1 for keywords in MANDATORY_STATE_TOPIC_RULES.values()
                    if any(kw in addendum_content for kw in keywords)
                )
                state_scores_l.append(covered / len(MANDATORY_STATE_TOPIC_RULES) if MANDATORY_STATE_TOPIC_RULES else 1.0)
            avg_state = sum(state_scores_l) / len(state_scores_l) if state_scores_l else 1.0
            state_score = avg_state * 30

            industry_key = _normalize_industry(None, meta["industry"])
            playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, {})
            expected = playbook.get("sections", [])
            ind_found = 0
            ind_missing = 0
            for exp in expected:
                slug = re.sub(r"[^a-z0-9]+", "_", exp.get("title", "").lower()).strip("_")
                if any(slug in s["section_key"] or slug in re.sub(r"[^a-z0-9]+", "_", s["title"].lower()).strip("_") for s in secs):
                    ind_found += 1
                else:
                    ind_missing += 1
            industry_score = (ind_found / len(expected)) * 15 if expected else 15.0

            # Profile score: simplified — award full 25 for broker summary
            profile_score = 25.0

            total_score = min(100, max(0, round(core_score + state_score + profile_score + industry_score)))
            label = "Strong" if total_score >= 80 else ("Moderate" if total_score >= 50 else "Weak")

            summaries.append(HandbookCoverageSummary(
                handbook_id=hb_id,
                handbook_title=meta["handbook_title"],
                company_id=meta["company_id"],
                company_name=meta["company_name"],
                strength_score=total_score,
                strength_label=label,
                total_sections=len(secs),
                state_count=len(states),
                missing_section_count=ind_missing,
            ))

        return summaries
