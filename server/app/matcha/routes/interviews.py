from typing import Optional
from uuid import UUID
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query

from ...core.dependencies import get_current_user, require_admin
from ...core.models.auth import CurrentUser

from ...database import get_connection
from ..models.interview import (
    InterviewCreate,
    InterviewResponse,
    InterviewStart,
    ConversationAnalysis,
    TutorSessionCreate,
    TutorSessionSummary,
    TutorSessionDetail,
    TutorMetricsAggregate,
    TutorProgressResponse,
    TutorProgressDataPoint,
    TutorSessionComparison,
    TutorVocabularyStats,
    VocabularyWord,
    VocabularySuggestion,
)
from ...core.services.gemini_session import GeminiLiveSession
from ...core.services.auth import (
    create_interview_ws_token,
    decode_interview_ws_token,
    decode_token,
)
from ..services.culture_analyzer import CultureAnalyzer
from ..services.conversation_analyzer import ConversationAnalyzer
from ...protocol import (
    MessageType,
    parse_text_message,
    parse_audio_from_client,
    frame_audio_for_client,
    ConversationMessage,
)
from ...config import get_settings

router = APIRouter()


@router.post("/companies/{company_id}/interviews", response_model=InterviewStart)
async def create_interview(company_id: UUID, interview: InterviewCreate):
    """Create a new interview session for a company."""
    async with get_connection() as conn:
        # Verify company exists
        company = await conn.fetchrow(
            "SELECT id FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Flow enforcement: candidate (culture-fit) interviews require culture profile
        if interview.interview_type == "candidate":
            culture_profile = await conn.fetchrow(
                "SELECT id FROM culture_profiles WHERE company_id = $1",
                company_id,
            )
            if not culture_profile:
                raise HTTPException(
                    status_code=400,
                    detail="Culture interview must be completed first. Complete at least one culture interview and aggregate the culture profile before running candidate interviews."
                )

        # Create interview record
        row = await conn.fetchrow(
            """
            INSERT INTO interviews (company_id, interviewer_name, interviewer_role, interview_type, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id
            """,
            company_id,
            interview.interviewer_name,
            interview.interviewer_role,
            interview.interview_type,
        )
        interview_id = row["id"]

        return InterviewStart(
            interview_id=interview_id,
            websocket_url=f"/api/ws/interview/{interview_id}",
            ws_auth_token=create_interview_ws_token(interview_id),
        )


@router.post("/tutor/sessions", response_model=InterviewStart)
async def create_tutor_session(
    request: TutorSessionCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create a unified practice/interview session."""
    company_modes = {"culture", "candidate", "screening"}
    is_company_mode = request.mode in company_modes

    # Validate required mode-specific fields first
    if request.mode == "interview_prep" and not request.interview_role:
        raise HTTPException(status_code=400, detail="Interview role must be specified for interview prep mode")

    if request.mode == "language_test" and not request.language:
        raise HTTPException(status_code=400, detail="Language must be specified for language test mode")

    if is_company_mode and not request.company_id:
        raise HTTPException(status_code=400, detail="Company ID must be specified for company interview modes")

    # For candidates: only allow interview_prep mode and require beta + tokens.
    if current_user.role == "candidate":
        if request.mode != "interview_prep":
            raise HTTPException(
                status_code=403,
                detail="This interview mode is not available for your account."
            )
        # Check beta access and tokens
        has_beta = current_user.beta_features.get("interview_prep", False)
        if not has_beta:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to Interview Prep. Contact support for beta access."
            )
        if current_user.interview_prep_tokens <= 0:
            raise HTTPException(
                status_code=403,
                detail="You have no interview prep tokens remaining."
            )
        # Enforce role allowlist server-side (frontend checks are insufficient)
        if request.interview_role not in current_user.allowed_interview_roles:
            raise HTTPException(
                status_code=403,
                detail="This interview role is not available for your account."
            )

    if is_company_mode and current_user.role not in ("admin", "client"):
        raise HTTPException(
            status_code=403,
            detail="Company interview modes are only available for admin and client users."
        )

    # interviewer_name always stores user email for ownership checks.
    interviewer_name = current_user.email
    if request.mode == "interview_prep":
        interview_type = "tutor_interview"
        interviewer_role = request.interview_role  # Store the role being practiced
        company_id = None
    elif request.mode == "language_test":
        interview_type = "tutor_language"
        interviewer_role = request.language  # Store the language for language mode
        company_id = None
    else:
        interview_type = request.mode
        interviewer_role = None
        company_id = request.company_id

    async with get_connection() as conn:
        if is_company_mode:
            company = await conn.fetchrow(
                "SELECT id FROM companies WHERE id = $1",
                request.company_id,
            )
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            if current_user.role == "client":
                has_access = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM clients
                        WHERE user_id = $1 AND company_id = $2
                    )
                    """,
                    current_user.id,
                    request.company_id,
                )
                if not has_access:
                    raise HTTPException(
                        status_code=403,
                        detail="You do not have access to this company."
                    )

            # Flow enforcement remains for candidate (culture-fit) interviews.
            if request.mode == "candidate":
                culture_profile = await conn.fetchrow(
                    "SELECT id FROM culture_profiles WHERE company_id = $1",
                    request.company_id,
                )
                if not culture_profile:
                    raise HTTPException(
                        status_code=400,
                        detail="Culture interview must be completed first. Complete at least one culture interview and aggregate the culture profile before running candidate interviews."
                    )

        async with conn.transaction():
            # For candidates using interview prep, consume a token atomically.
            if current_user.role == "candidate" and request.mode == "interview_prep":
                token_row = await conn.fetchrow(
                    """
                    UPDATE users
                    SET interview_prep_tokens = interview_prep_tokens - 1
                    WHERE id = $1 AND interview_prep_tokens > 0
                    RETURNING interview_prep_tokens
                    """,
                    current_user.id,
                )
                if not token_row:
                    raise HTTPException(
                        status_code=403,
                        detail="You have no interview prep tokens remaining."
                    )

            # For tutor sessions, company_id is NULL. For company interview modes, company_id is required.
            row = await conn.fetchrow(
                """
                INSERT INTO interviews (company_id, interviewer_name, interviewer_role, interview_type, status)
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING id
                """,
                company_id,
                interviewer_name,
                interviewer_role,
                interview_type,
            )
            interview_id = row["id"]

        # Calculate duration in seconds
        # Default: 5 min for interview prep, 2 min for language test, 8 min for company interview modes.
        if request.duration_minutes:
            duration_seconds = request.duration_minutes * 60
        elif request.mode == "language_test":
            duration_seconds = 2 * 60
        elif request.mode == "interview_prep":
            duration_seconds = 5 * 60
        else:
            duration_seconds = 8 * 60

        return InterviewStart(
            interview_id=interview_id,
            websocket_url=f"/api/ws/interview/{interview_id}",
            ws_auth_token=create_interview_ws_token(interview_id),
            max_session_duration_seconds=duration_seconds,
        )


# Admin Tutor Metrics Endpoints

@router.get("/tutor/sessions", response_model=list[TutorSessionSummary])
async def list_tutor_sessions(
    mode: Optional[str] = None,  # "interview_prep", "language_test", "company_tool", "culture", "screening", "candidate"
    company_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    _current_user: CurrentUser = Depends(require_admin),
):
    """List all tutor + company interview sessions (admin only)."""
    mode_to_types = {
        "interview_prep": ["tutor_interview"],
        "language_test": ["tutor_language"],
        "company_tool": ["culture", "screening", "candidate"],
        "culture": ["culture"],
        "screening": ["screening"],
        "candidate": ["candidate"],
    }
    all_types = ["tutor_interview", "tutor_language", "culture", "screening", "candidate"]

    if mode and mode not in mode_to_types:
        raise HTTPException(status_code=400, detail="Invalid mode filter")

    interview_type_filters = mode_to_types[mode] if mode else all_types

    async with get_connection() as conn:
        query = """
            SELECT i.id, i.company_id, c.name as company_name, i.interview_type,
                   i.interviewer_role as language, i.status, i.tutor_analysis,
                   i.conversation_analysis, i.screening_analysis,
                   i.created_at, i.completed_at
            FROM interviews i
            LEFT JOIN companies c ON i.company_id = c.id
            WHERE i.interview_type = ANY($1::text[])
        """
        params = [interview_type_filters]

        if company_id:
            query += " AND i.company_id = $2"
            params.append(company_id)
            query += f" ORDER BY i.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
            params.extend([limit, offset])
        else:
            query += " ORDER BY i.created_at DESC LIMIT $2 OFFSET $3"
            params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        sessions = []
        for row in rows:
            # Extract mode-appropriate score:
            # - User tool (language/interview prep): tutor_analysis
            # - Company tool (culture/screening/candidate): conversation/screening analysis
            overall_score = None
            interview_type = row["interview_type"]

            if interview_type in ("tutor_interview", "tutor_language") and row["tutor_analysis"]:
                analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]
                if interview_type == "tutor_interview":
                    overall_score = analysis.get("communication_skills", {}).get("overall_score")
                else:
                    overall_score = analysis.get("fluency_pace", {}).get("overall_score")
            elif interview_type in ("culture", "candidate") and row["conversation_analysis"]:
                conv = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
                overall_score = conv.get("coverage_completeness", {}).get("overall_score")
            elif interview_type == "screening" and row["screening_analysis"]:
                screening = json.loads(row["screening_analysis"]) if isinstance(row["screening_analysis"], str) else row["screening_analysis"]
                overall_score = screening.get("overall_score")

            score_value = None
            if isinstance(overall_score, (int, float)):
                score_value = int(round(overall_score))

            sessions.append(TutorSessionSummary(
                id=row["id"],
                interview_type=interview_type,
                company_id=row["company_id"],
                company_name=row["company_name"],
                language=row["language"] if interview_type == "tutor_language" else None,
                status=row["status"],
                overall_score=score_value,
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ))

        return sessions


@router.get("/tutor/sessions/{session_id}", response_model=TutorSessionDetail)
async def get_tutor_session(
    session_id: UUID,
    _current_user: CurrentUser = Depends(require_admin),
):
    """Get a single tutor session with full analysis (admin only)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, interview_type, interviewer_role as language, transcript,
                   tutor_analysis, status, created_at, completed_at
            FROM interviews
            WHERE id = $1 AND interview_type IN ('tutor_interview', 'tutor_language')
            """,
            session_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Tutor session not found")

        tutor_analysis = None
        if row["tutor_analysis"]:
            tutor_analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]

        return TutorSessionDetail(
            id=row["id"],
            interview_type=row["interview_type"],
            language=row["language"] if row["interview_type"] == "tutor_language" else None,
            transcript=row["transcript"],
            tutor_analysis=tutor_analysis,
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


@router.delete("/tutor/sessions/{session_id}")
async def delete_tutor_session(
    session_id: UUID,
    _current_user: CurrentUser = Depends(require_admin),
):
    """Delete a tutor/company interview session (admin only)."""
    async with get_connection() as conn:
        # Verify session exists and is part of the unified interview system.
        row = await conn.fetchrow(
            """
            SELECT id FROM interviews
            WHERE id = $1
              AND interview_type IN ('tutor_interview', 'tutor_language', 'culture', 'screening', 'candidate')
            """,
            session_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Tutor session not found")

        # Delete the session
        await conn.execute(
            "DELETE FROM interviews WHERE id = $1",
            session_id,
        )

        return {"status": "deleted", "session_id": str(session_id)}


@router.get("/tutor/metrics/aggregate", response_model=TutorMetricsAggregate)
async def get_tutor_aggregate_metrics(
    company_id: Optional[UUID] = None,
    _current_user: CurrentUser = Depends(require_admin),
):
    """Get aggregate metrics across user-tool and company-tool interview sessions (admin only)."""
    async with get_connection() as conn:
        # Build base filter
        where_clause = "WHERE status = 'completed'"
        params = []
        if company_id:
            where_clause += " AND company_id = $1"
            params.append(company_id)

        # Get interview prep stats
        interview_prep_rows = await conn.fetch(
            f"""
            SELECT tutor_analysis, status
            FROM interviews
            {where_clause} AND interview_type = 'tutor_interview'
            """,
            *params
        )

        interview_prep_stats = {
            "total_sessions": len(interview_prep_rows),
            "avg_response_quality": 0,
            "avg_communication_score": 0,
            "common_improvement_areas": [],
        }

        if interview_prep_rows:
            response_scores = []
            comm_scores = []
            improvement_areas: dict[str, int] = {}

            for row in interview_prep_rows:
                if row["tutor_analysis"]:
                    analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]
                    if "response_quality" in analysis:
                        response_scores.append(analysis["response_quality"].get("overall_score", 0))
                    if "communication_skills" in analysis:
                        comm_scores.append(analysis["communication_skills"].get("overall_score", 0))
                    for suggestion in analysis.get("improvement_suggestions", []):
                        area = suggestion.get("area", "Unknown")
                        improvement_areas[area] = improvement_areas.get(area, 0) + 1

            if response_scores:
                interview_prep_stats["avg_response_quality"] = round(sum(response_scores) / len(response_scores), 1)
            if comm_scores:
                interview_prep_stats["avg_communication_score"] = round(sum(comm_scores) / len(comm_scores), 1)

            # Get top 5 improvement areas
            sorted_areas = sorted(improvement_areas.items(), key=lambda x: x[1], reverse=True)[:5]
            interview_prep_stats["common_improvement_areas"] = [{"area": a, "count": c} for a, c in sorted_areas]

        # Get language test stats
        language_test_rows = await conn.fetch(
            f"""
            SELECT tutor_analysis, interviewer_role as language, status
            FROM interviews
            {where_clause} AND interview_type = 'tutor_language'
            """,
            *params
        )

        language_test_stats = {
            "total_sessions": len(language_test_rows),
            "by_language": {},
            "avg_fluency_score": 0,
            "avg_grammar_score": 0,
            "common_grammar_errors": [],
        }

        if language_test_rows:
            fluency_scores = []
            grammar_scores = []
            grammar_error_types: dict[str, int] = {}
            lang_counts: dict[str, dict] = {}

            for row in language_test_rows:
                lang = row["language"] or "unknown"
                if lang not in lang_counts:
                    lang_counts[lang] = {"count": 0, "proficiency_levels": []}
                lang_counts[lang]["count"] += 1

                if row["tutor_analysis"]:
                    analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]
                    if "fluency_pace" in analysis:
                        fluency_scores.append(analysis["fluency_pace"].get("overall_score", 0))
                    if "grammar" in analysis:
                        grammar_scores.append(analysis["grammar"].get("overall_score", 0))
                        for error in analysis["grammar"].get("common_errors", []):
                            error_type = error.get("type", "other")
                            grammar_error_types[error_type] = grammar_error_types.get(error_type, 0) + 1
                    if "overall_proficiency" in analysis:
                        level = analysis["overall_proficiency"].get("level")
                        if level:
                            lang_counts[lang]["proficiency_levels"].append(level)

            if fluency_scores:
                language_test_stats["avg_fluency_score"] = round(sum(fluency_scores) / len(fluency_scores), 1)
            if grammar_scores:
                language_test_stats["avg_grammar_score"] = round(sum(grammar_scores) / len(grammar_scores), 1)

            # Calculate average proficiency per language
            for lang, data in lang_counts.items():
                levels = data["proficiency_levels"]
                # Simple mode calculation for most common proficiency level
                most_common = max(set(levels), key=levels.count) if levels else None
                language_test_stats["by_language"][lang] = {
                    "count": data["count"],
                    "avg_proficiency": most_common,
                }

            # Get top 5 grammar error types
            sorted_errors = sorted(grammar_error_types.items(), key=lambda x: x[1], reverse=True)[:5]
            language_test_stats["common_grammar_errors"] = [{"type": t, "count": c} for t, c in sorted_errors]

        # Company interview metrics (kept separate from language/user coaching metrics).
        company_rows = await conn.fetch(
            f"""
            SELECT interview_type, conversation_analysis, screening_analysis
            FROM interviews
            {where_clause} AND interview_type IN ('culture', 'candidate', 'screening')
            """,
            *params
        )

        culture_scores: list[float] = []
        culture_depth_scores: list[float] = []
        culture_missed_dimensions: dict[str, int] = {}

        candidate_scores: list[float] = []
        candidate_depth_scores: list[float] = []
        candidate_missed_dimensions: dict[str, int] = {}

        screening_scores: list[float] = []
        screening_communication_scores: list[float] = []
        screening_recommendations: dict[str, int] = {}

        for row in company_rows:
            interview_type = row["interview_type"]
            if interview_type in ("culture", "candidate") and row["conversation_analysis"]:
                analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
                coverage_score = analysis.get("coverage_completeness", {}).get("overall_score")
                response_depth = analysis.get("response_depth", {}).get("overall_score")
                missed_dimensions = analysis.get("coverage_completeness", {}).get("dimensions_missed", [])

                if isinstance(coverage_score, (int, float)):
                    if interview_type == "culture":
                        culture_scores.append(float(coverage_score))
                    else:
                        candidate_scores.append(float(coverage_score))

                if isinstance(response_depth, (int, float)):
                    if interview_type == "culture":
                        culture_depth_scores.append(float(response_depth))
                    else:
                        candidate_depth_scores.append(float(response_depth))

                target_dimensions = culture_missed_dimensions if interview_type == "culture" else candidate_missed_dimensions
                for dim in missed_dimensions:
                    if not isinstance(dim, str):
                        continue
                    target_dimensions[dim] = target_dimensions.get(dim, 0) + 1

            elif interview_type == "screening" and row["screening_analysis"]:
                analysis = json.loads(row["screening_analysis"]) if isinstance(row["screening_analysis"], str) else row["screening_analysis"]
                overall = analysis.get("overall_score")
                communication = analysis.get("communication_clarity", {}).get("score")
                recommendation = analysis.get("recommendation")

                if isinstance(overall, (int, float)):
                    screening_scores.append(float(overall))
                if isinstance(communication, (int, float)):
                    screening_communication_scores.append(float(communication))
                if isinstance(recommendation, str):
                    screening_recommendations[recommendation] = screening_recommendations.get(recommendation, 0) + 1

        company_interview_stats = {
            "culture": {
                "total_sessions": sum(1 for r in company_rows if r["interview_type"] == "culture"),
                "avg_coverage_score": round(sum(culture_scores) / len(culture_scores), 1) if culture_scores else 0,
                "avg_response_depth": round(sum(culture_depth_scores) / len(culture_depth_scores), 1) if culture_depth_scores else 0,
                "common_missed_dimensions": [
                    {"dimension": dim, "count": count}
                    for dim, count in sorted(culture_missed_dimensions.items(), key=lambda x: x[1], reverse=True)[:5]
                ],
            },
            "candidate": {
                "total_sessions": sum(1 for r in company_rows if r["interview_type"] == "candidate"),
                "avg_coverage_score": round(sum(candidate_scores) / len(candidate_scores), 1) if candidate_scores else 0,
                "avg_response_depth": round(sum(candidate_depth_scores) / len(candidate_depth_scores), 1) if candidate_depth_scores else 0,
                "common_missed_dimensions": [
                    {"dimension": dim, "count": count}
                    for dim, count in sorted(candidate_missed_dimensions.items(), key=lambda x: x[1], reverse=True)[:5]
                ],
            },
            "screening": {
                "total_sessions": sum(1 for r in company_rows if r["interview_type"] == "screening"),
                "avg_overall_score": round(sum(screening_scores) / len(screening_scores), 1) if screening_scores else 0,
                "avg_communication_score": round(sum(screening_communication_scores) / len(screening_communication_scores), 1) if screening_communication_scores else 0,
                "recommendation_breakdown": screening_recommendations,
            },
        }

        return TutorMetricsAggregate(
            interview_prep=interview_prep_stats,
            language_test=language_test_stats,
            company_interviews=company_interview_stats,
        )


@router.get("/tutor/progress", response_model=TutorProgressResponse)
async def get_tutor_progress(
    language: Optional[str] = None,
    limit: int = 20,
    _current_user: CurrentUser = Depends(require_admin),
):
    """Get session scores over time for progress tracking."""
    async with get_connection() as conn:
        query = """
            SELECT id, created_at, tutor_analysis, interviewer_role as language
            FROM interviews
            WHERE interview_type = 'tutor_language'
                AND status = 'completed'
                AND tutor_analysis IS NOT NULL
        """
        params = []
        if language:
            query += f" AND interviewer_role = ${len(params) + 1}"
            params.append(language)

        query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1}"
        params.append(limit)

        rows = await conn.fetch(query, *params)

        data_points = []
        for row in rows:
            analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]
            data_points.append(TutorProgressDataPoint(
                session_id=row["id"],
                date=row["created_at"],
                fluency_score=analysis.get("fluency_pace", {}).get("overall_score"),
                grammar_score=analysis.get("grammar", {}).get("overall_score"),
                vocabulary_score=analysis.get("vocabulary", {}).get("overall_score"),
                proficiency_level=analysis.get("overall_proficiency", {}).get("level"),
            ))

        # Reverse to show oldest to newest for charting
        return TutorProgressResponse(
            sessions=list(reversed(data_points)),
            language=language
        )


@router.get("/tutor/sessions/{session_id}/comparison", response_model=TutorSessionComparison)
async def get_session_comparison(
    session_id: UUID,
    _current_user: CurrentUser = Depends(require_admin),
):
    """Get comparison of this session with previous sessions."""
    async with get_connection() as conn:
        # Get the current session
        current = await conn.fetchrow(
            """
            SELECT id, created_at, tutor_analysis, interviewer_role as language
            FROM interviews WHERE id = $1
            """,
            session_id
        )
        if not current:
            raise HTTPException(status_code=404, detail="Session not found")

        if not current["tutor_analysis"]:
            return TutorSessionComparison(
                previous_session_count=0
            )

        language = current["language"]
        current_analysis = json.loads(current["tutor_analysis"]) if isinstance(current["tutor_analysis"], str) else current["tutor_analysis"]

        # Get previous sessions for comparison
        previous = await conn.fetch(
            """
            SELECT tutor_analysis
            FROM interviews
            WHERE interview_type = 'tutor_language'
                AND status = 'completed'
                AND interviewer_role = $1
                AND created_at < $2
                AND tutor_analysis IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 5
            """,
            language, current["created_at"]
        )

        # Extract current scores
        current_fluency = current_analysis.get("fluency_pace", {}).get("overall_score")
        current_grammar = current_analysis.get("grammar", {}).get("overall_score")
        current_vocabulary = current_analysis.get("vocabulary", {}).get("overall_score")

        # Calculate averages from previous sessions
        if previous:
            prev_analyses = [json.loads(r["tutor_analysis"]) if isinstance(r["tutor_analysis"], str) else r["tutor_analysis"] for r in previous]
            prev_fluency = [a.get("fluency_pace", {}).get("overall_score") for a in prev_analyses if a.get("fluency_pace", {}).get("overall_score")]
            prev_grammar = [a.get("grammar", {}).get("overall_score") for a in prev_analyses if a.get("grammar", {}).get("overall_score")]
            prev_vocabulary = [a.get("vocabulary", {}).get("overall_score") for a in prev_analyses if a.get("vocabulary", {}).get("overall_score")]

            avg_prev_fluency = round(sum(prev_fluency) / len(prev_fluency), 1) if prev_fluency else None
            avg_prev_grammar = round(sum(prev_grammar) / len(prev_grammar), 1) if prev_grammar else None
            avg_prev_vocabulary = round(sum(prev_vocabulary) / len(prev_vocabulary), 1) if prev_vocabulary else None
        else:
            avg_prev_fluency = None
            avg_prev_grammar = None
            avg_prev_vocabulary = None

        return TutorSessionComparison(
            current_fluency=current_fluency,
            current_grammar=current_grammar,
            current_vocabulary=current_vocabulary,
            avg_previous_fluency=avg_prev_fluency,
            avg_previous_grammar=avg_prev_grammar,
            avg_previous_vocabulary=avg_prev_vocabulary,
            previous_session_count=len(previous),
            fluency_change=round(current_fluency - avg_prev_fluency, 1) if current_fluency and avg_prev_fluency else None,
            grammar_change=round(current_grammar - avg_prev_grammar, 1) if current_grammar and avg_prev_grammar else None,
            vocabulary_change=round(current_vocabulary - avg_prev_vocabulary, 1) if current_vocabulary and avg_prev_vocabulary else None,
        )


@router.get("/tutor/vocabulary", response_model=TutorVocabularyStats)
async def get_vocabulary_stats(
    language: str = "es",
    limit: int = 10,
    _current_user: CurrentUser = Depends(require_admin),
):
    """Get vocabulary statistics across all language sessions."""
    async with get_connection() as conn:
        # Get all completed language sessions for this language
        rows = await conn.fetch(
            """
            SELECT tutor_analysis
            FROM interviews
            WHERE interview_type = 'tutor_language'
                AND status = 'completed'
                AND interviewer_role = $1
                AND tutor_analysis IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 20
            """,
            language
        )

        # Aggregate vocabulary from all sessions
        word_stats: dict[str, dict] = {}
        all_suggestions: list[dict] = []

        for row in rows:
            analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]

            # Extract vocabulary_used
            for vocab in analysis.get("vocabulary_used", []):
                word = vocab.get("word", "").lower()
                if not word:
                    continue

                if word not in word_stats:
                    word_stats[word] = {
                        "word": vocab.get("word"),
                        "category": vocab.get("category"),
                        "times_used": 0,
                        "times_correct": 0,
                        "context": vocab.get("context"),
                        "correction": vocab.get("correction"),
                        "difficulty": vocab.get("difficulty"),
                    }
                word_stats[word]["times_used"] += 1
                if vocab.get("used_correctly"):
                    word_stats[word]["times_correct"] += 1

            # Collect suggestions
            for suggestion in analysis.get("vocabulary_suggestions", []):
                all_suggestions.append(suggestion)

        # Categorize words
        mastered_words = []
        words_to_review = []

        for word, stats in word_stats.items():
            word_obj = VocabularyWord(
                word=stats["word"],
                category=stats["category"],
                used_correctly=stats["times_correct"] / stats["times_used"] >= 0.8 if stats["times_used"] > 0 else None,
                context=stats["context"],
                correction=stats["correction"],
                difficulty=stats["difficulty"],
                times_used=stats["times_used"],
            )

            if stats["times_used"] >= 2 and stats["times_correct"] / stats["times_used"] >= 0.8:
                mastered_words.append(word_obj)
            elif stats["times_correct"] < stats["times_used"]:
                words_to_review.append(word_obj)

        # Sort and limit
        mastered_words.sort(key=lambda w: w.times_used, reverse=True)
        words_to_review.sort(key=lambda w: w.times_used, reverse=True)

        # Dedupe suggestions
        seen_suggestions = set()
        unique_suggestions = []
        for s in all_suggestions:
            word = s.get("word", "").lower()
            if word and word not in seen_suggestions:
                seen_suggestions.add(word)
                unique_suggestions.append(VocabularySuggestion(
                    word=s.get("word"),
                    meaning=s.get("meaning"),
                    example=s.get("example"),
                    difficulty=s.get("difficulty"),
                ))

        return TutorVocabularyStats(
            total_unique_words=len(word_stats),
            mastered_words=mastered_words[:limit],
            words_to_review=words_to_review[:limit],
            suggested_vocabulary=unique_suggestions[:limit],
            language=language,
        )


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: UUID):
    """Get an interview by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, company_id, interviewer_name, interviewer_role, interview_type,
                   transcript, raw_culture_data, conversation_analysis, screening_analysis,
                   tutor_analysis, status, created_at, completed_at
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        raw_culture_data = None
        if row["raw_culture_data"]:
            raw_culture_data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]

        conversation_analysis = None
        if row["conversation_analysis"]:
            conversation_analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]

        screening_analysis = None
        if row["screening_analysis"]:
            screening_analysis = json.loads(row["screening_analysis"]) if isinstance(row["screening_analysis"], str) else row["screening_analysis"]

        tutor_analysis = None
        if row["tutor_analysis"]:
            tutor_analysis = json.loads(row["tutor_analysis"]) if isinstance(row["tutor_analysis"], str) else row["tutor_analysis"]

        return InterviewResponse(
            id=row["id"],
            company_id=row["company_id"],
            interviewer_name=row["interviewer_name"],
            interviewer_role=row["interviewer_role"],
            interview_type=row["interview_type"] or "culture",
            transcript=row["transcript"],
            raw_culture_data=raw_culture_data,
            conversation_analysis=conversation_analysis,
            screening_analysis=screening_analysis,
            tutor_analysis=tutor_analysis,
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


@router.get("/companies/{company_id}/interviews", response_model=list[InterviewResponse])
async def list_company_interviews(company_id: UUID):
    """List all interviews for a company."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, company_id, interviewer_name, interviewer_role, interview_type,
                   transcript, raw_culture_data, conversation_analysis, screening_analysis,
                   status, created_at, completed_at
            FROM interviews
            WHERE company_id = $1
            ORDER BY created_at DESC
            """,
            company_id,
        )
        results = []
        for row in rows:
            raw_culture_data = None
            if row["raw_culture_data"]:
                raw_culture_data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]
            conversation_analysis = None
            if row["conversation_analysis"]:
                conversation_analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
            screening_analysis = None
            if row["screening_analysis"]:
                screening_analysis = json.loads(row["screening_analysis"]) if isinstance(row["screening_analysis"], str) else row["screening_analysis"]
            results.append(InterviewResponse(
                id=row["id"],
                company_id=row["company_id"],
                interviewer_name=row["interviewer_name"],
                interviewer_role=row["interviewer_role"],
                interview_type=row["interview_type"] or "culture",
                transcript=row["transcript"],
                raw_culture_data=raw_culture_data,
                conversation_analysis=conversation_analysis,
                screening_analysis=screening_analysis,
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            ))
        return results


@router.post("/companies/{company_id}/aggregate-culture")
async def aggregate_culture(company_id: UUID):
    """Aggregate all interview culture data into a company profile."""
    settings = get_settings()
    analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    async with get_connection() as conn:
        # Get all completed interviews for this company
        rows = await conn.fetch(
            """
            SELECT raw_culture_data
            FROM interviews
            WHERE company_id = $1 AND interview_type = 'culture' AND status = 'completed' AND raw_culture_data IS NOT NULL
            """,
            company_id,
        )

        if not rows:
            raise HTTPException(status_code=400, detail="No completed interviews with culture data")

        # Parse culture data from all interviews
        culture_data_list = []
        for row in rows:
            if row["raw_culture_data"]:
                data = json.loads(row["raw_culture_data"]) if isinstance(row["raw_culture_data"], str) else row["raw_culture_data"]
                culture_data_list.append(data)

        # Aggregate using the analyzer
        aggregated = await analyzer.aggregate_culture_profiles(culture_data_list)

        # Upsert the culture profile
        await conn.execute(
            """
            INSERT INTO culture_profiles (company_id, profile_data, last_updated)
            VALUES ($1, $2, NOW())
            ON CONFLICT (company_id)
            DO UPDATE SET profile_data = $2, last_updated = NOW()
            """,
            company_id,
            json.dumps(aggregated),
        )

        return {"status": "aggregated", "profile": aggregated}


@router.post("/companies/{company_id}/aggregate-culture/async")
async def aggregate_culture_async(company_id: UUID):
    """
    Queue culture aggregation for background processing.

    Returns immediately with a task_id. Subscribe to WebSocket /ws/notifications
    for real-time completion notification.
    """
    from app.workers.tasks.culture_aggregation import aggregate_culture_async as aggregate_task

    async with get_connection() as conn:
        # Verify there are interviews to aggregate
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM interviews
            WHERE company_id = $1 AND interview_type = 'culture' AND status = 'completed' AND raw_culture_data IS NOT NULL
            """,
            company_id,
        )
        if count == 0:
            raise HTTPException(status_code=400, detail="No completed interviews with culture data")

    task = aggregate_task.delay(company_id=str(company_id))

    return {
        "task_id": task.id,
        "status": "processing",
        "message": "Culture aggregation task queued. Subscribe to WebSocket notifications for updates.",
    }


@router.get("/interviews/{interview_id}/analysis")
async def get_interview_analysis(interview_id: UUID):
    """Get the conversation analysis for an interview."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT conversation_analysis
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        if not row["conversation_analysis"]:
            raise HTTPException(status_code=404, detail="Analysis not yet generated for this interview")

        analysis = json.loads(row["conversation_analysis"]) if isinstance(row["conversation_analysis"], str) else row["conversation_analysis"]
        return analysis


@router.post("/interviews/{interview_id}/analyze")
async def analyze_interview(interview_id: UUID):
    """Generate or regenerate conversation analysis for an interview."""
    settings = get_settings()

    async with get_connection() as conn:
        # Fetch interview
        row = await conn.fetchrow(
            """
            SELECT id, company_id, interview_type, transcript, status
            FROM interviews
            WHERE id = $1
            """,
            interview_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Interview not found")

        if row["status"] != "completed":
            raise HTTPException(status_code=400, detail="Interview must be completed before analysis")

        if not row["transcript"]:
            raise HTTPException(status_code=400, detail="Interview has no transcript to analyze")

        # Run analysis
        conv_analyzer = ConversationAnalyzer(
            api_key=settings.gemini_api_key,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
            model=settings.analysis_model,
        )

        interview_type = row["interview_type"] or "culture"

        if interview_type == "screening":
            # Screening interviews use a different analysis method
            analysis = await conv_analyzer.analyze_screening_interview(
                transcript=row["transcript"],
            )
            # Store in screening_analysis column
            await conn.execute(
                """
                UPDATE interviews
                SET screening_analysis = $1
                WHERE id = $2
                """,
                json.dumps(analysis),
                interview_id,
            )
        else:
            # Culture and candidate interviews use conversation analysis
            culture_profile = None
            if interview_type == "candidate":
                culture_row = await conn.fetchrow(
                    "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                    row["company_id"],
                )
                if culture_row and culture_row["profile_data"]:
                    culture_profile = json.loads(culture_row["profile_data"]) if isinstance(culture_row["profile_data"], str) else culture_row["profile_data"]

            analysis = await conv_analyzer.analyze_interview(
                transcript=row["transcript"],
                interview_type=interview_type,
                culture_profile=culture_profile,
            )
            # Store in conversation_analysis column
            await conn.execute(
                """
                UPDATE interviews
                SET conversation_analysis = $1
                WHERE id = $2
                """,
                json.dumps(analysis),
                interview_id,
            )

        return analysis


# WebSocket endpoint for voice interviews
@router.websocket("/ws/interview/{interview_id}")
async def interview_websocket(
    websocket: WebSocket,
    interview_id: UUID,
    token: str = Query(...),
):
    """WebSocket endpoint for voice interview sessions."""
    await websocket.accept()

    settings = get_settings()
    cancelled = False
    gemini_session: Optional[GeminiLiveSession] = None
    analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    # Get interview and company info
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id, i.company_id, i.interviewer_name, i.interviewer_role, i.interview_type, c.name as company_name
            FROM interviews i
            LEFT JOIN companies c ON i.company_id = c.id
            WHERE i.id = $1
            """,
            interview_id,
        )
        if not row:
            await websocket.close(code=4004, reason="Interview not found")
            return

        interview_type = row["interview_type"] or "culture"

        # Allow either:
        # 1) short-lived interview websocket token (for public invite flows), or
        # 2) authenticated app access token (for internal flows).
        ws_token_interview_id = decode_interview_ws_token(token)
        if ws_token_interview_id:
            if ws_token_interview_id != interview_id:
                await websocket.close(code=4003, reason="Token not valid for this interview")
                return
        else:
            user_payload = decode_token(token)
            if not user_payload:
                await websocket.close(code=4001, reason="Invalid or expired token")
                return

            try:
                user_id = UUID(user_payload.sub)
            except ValueError:
                await websocket.close(code=4001, reason="Invalid token subject")
                return

            user_row = await conn.fetchrow(
                """
                SELECT id, email, role, is_active
                FROM users
                WHERE id = $1
                """,
                user_id,
            )
            if not user_row or not user_row["is_active"]:
                await websocket.close(code=4001, reason="Invalid or inactive user")
                return

            # Tutor sessions are private to their owner (or admin).
            if interview_type in ("tutor_interview", "tutor_language") and user_row["role"] != "admin":
                owner_email = (row["interviewer_name"] or "").strip().lower()
                if owner_email != (user_row["email"] or "").strip().lower():
                    await websocket.close(code=4003, reason="Not authorized for this tutor session")
                    return

        company_name = row["company_name"] or "Practice Session"
        interviewer_name = row["interviewer_name"] or "HR Representative"
        interviewer_role = row["interviewer_role"]  # May contain language for tutor sessions

        # For tutor sessions, extract the appropriate fields
        tutor_language = None
        tutor_interview_role = None
        if interview_type == "tutor_language":
            tutor_language = interviewer_role  # "en" or "es"
            interviewer_role = "Tutor"
        elif interview_type == "tutor_interview":
            tutor_interview_role = interviewer_role  # The role being practiced for

        # For candidate interviews, fetch the company's culture profile
        culture_profile = None
        if interview_type == "candidate" and row["company_id"]:
            culture_row = await conn.fetchrow(
                "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                row["company_id"],
            )
            if culture_row and culture_row["profile_data"]:
                culture_profile = json.loads(culture_row["profile_data"]) if isinstance(culture_row["profile_data"], str) else culture_row["profile_data"]

        # Update interview status
        await conn.execute(
            "UPDATE interviews SET status = 'in_progress' WHERE id = $1",
            interview_id,
        )

    async def send_message(msg_type: str, content: str):
        msg = ConversationMessage.create(msg_type, content)
        await websocket.send_text(msg.to_json())

    await send_message(MessageType.SYSTEM, f"Connected to interview for {company_name}")

    try:
        # Create Gemini session
        gemini_session = GeminiLiveSession(
            model=settings.live_model,
            voice=settings.voice,
            api_key=settings.gemini_api_key,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
        )

        # Connect with appropriate interview prompt
        await gemini_session.connect(
            company_name=company_name,
            interviewer_name=interviewer_name,
            interviewer_role=interviewer_role or "HR",
            interview_type=interview_type,
            culture_profile=culture_profile,
            tutor_language=tutor_language,
            tutor_interview_role=tutor_interview_role,
        )

        await send_message(MessageType.STATUS, "Session started")

        # Trigger the model to speak first
        if interview_type == "tutor_interview":
            role_msg = f" for a {tutor_interview_role} position" if tutor_interview_role else ""
            await gemini_session.send_text(f"Please start the coaching session now. Greet them warmly and explain you'll help them practice interview questions{role_msg}.")
        elif interview_type == "tutor_language":
            if tutor_language == "es":
                await gemini_session.send_text("Por favor, comienza la sesión de práctica. Saluda calurosamente y pregunta cómo pueden ayudarte a practicar español hoy.")
            else:
                await gemini_session.send_text("Please start the practice session now. Greet them warmly and ask how you can help them practice English today.")
        elif interview_type in ("candidate", "screening"):
            await gemini_session.send_text("Please start the interview now. Greet the candidate warmly and begin.")
        else:
            await gemini_session.send_text(f"Please start the interview now. Say hello to {interviewer_name} and begin.")

        # Start response forwarding task
        import asyncio

        async def forward_responses():
            async for response in gemini_session.receive_responses():
                if response.type == "audio" and response.audio_data:
                    await websocket.send_bytes(frame_audio_for_client(response.audio_data))
                elif response.type == "transcription":
                    if response.is_input_transcription:
                        await send_message(MessageType.USER, response.text)
                    else:
                        await send_message(MessageType.ASSISTANT, response.text)
                elif response.type == "turn_complete":
                    await send_message(MessageType.STATUS, "ready")

        forward_task = asyncio.create_task(forward_responses())

        # Handle incoming messages
        audio_frame_count = 0
        while True:
            message = await websocket.receive()

            if "text" in message:
                cmd = parse_text_message(message["text"])
                if cmd and cmd.command == "cancel_session":
                    cancelled = True
                    break
                elif cmd and cmd.command == "stop_session":
                    break
                elif cmd and cmd.command == "send_text":
                    # Allow sending text messages (for testing)
                    if hasattr(cmd, "text") and cmd.text:
                        await gemini_session.send_text(cmd.text)

            elif "bytes" in message:
                audio_data = parse_audio_from_client(message["bytes"])
                if audio_data:
                    audio_frame_count += 1
                    if audio_frame_count % 50 == 0:
                        print(f"[Interview {interview_id}] Audio frame #{audio_frame_count}: {len(audio_data)} bytes")
                    await gemini_session.send_audio(audio_data)

    except WebSocketDisconnect:
        print(f"[Interview {interview_id}] Client disconnected")
    except RuntimeError as e:
        if "disconnect" in str(e).lower() or "receive" in str(e).lower():
            print(f"[Interview {interview_id}] Client disconnected (RuntimeError)")
        else:
            print(f"[Interview {interview_id}] RuntimeError: {e}")
            try:
                await send_message(MessageType.SYSTEM, f"Error: {str(e)}")
            except Exception:
                pass
    except Exception as e:
        print(f"[Interview {interview_id}] Error: {e}")
        try:
            await send_message(MessageType.SYSTEM, f"Error: {str(e)}")
        except Exception:
            pass
    finally:
        if gemini_session:
            transcript_text = gemini_session.get_transcript_text()

            if cancelled:
                # User cancelled — save transcript but skip analysis
                async with get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE interviews
                        SET transcript = $1, status = 'cancelled', completed_at = NOW()
                        WHERE id = $2
                        """,
                        transcript_text,
                        interview_id,
                    )
                print(f"[Interview {interview_id}] Session cancelled by user, skipping analysis")
            else:
                # Save transcript with 'analyzing' status - analysis will run in background worker
                async with get_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE interviews
                        SET transcript = $1, status = 'analyzing', completed_at = NOW()
                        WHERE id = $2
                        """,
                        transcript_text,
                        interview_id,
                    )

                # Queue analysis task for Celery worker
                if transcript_text:
                    from app.workers.tasks.interview_analysis import analyze_interview_async

                    analyze_interview_async.delay(
                        interview_id=str(interview_id),
                        interview_type=interview_type,
                        transcript=transcript_text,
                        company_id=str(row["company_id"]) if row["company_id"] else None,
                        culture_profile=culture_profile,
                        language=tutor_language,  # Pass language for tutor_language sessions
                    )
                    print(f"[Interview {interview_id}] Queued analysis task for background processing")
                else:
                    # No transcript, mark as completed without analysis
                    async with get_connection() as conn:
                        await conn.execute(
                            "UPDATE interviews SET status = 'completed' WHERE id = $1",
                            interview_id,
                        )

            await gemini_session.close()

        if "forward_task" in dir() and forward_task:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass

        print(f"[Interview {interview_id}] Session ended")
