"""
Multi-signal candidate ranking service.

Combines three signals:
  1. Screening performance  (30%) — from interviews.screening_analysis.overall_score
  2. Culture alignment      (40%) — from CandidateMatcher (existing Gemini flow)
  3. Conversation quality   (30%) — avg of coverage_completeness + response_depth scores

Candidates without interview data fall back to culture-alignment-only (100%).
"""
import json
from typing import Any, Optional
from uuid import UUID

from ..services.candidate_matcher import CandidateMatcher
from ...database import get_connection

# Weights for candidates WITH interview data
WEIGHT_SCREENING = 0.30
WEIGHT_CULTURE = 0.40
WEIGHT_CONVERSATION = 0.30

# Fallback: resume-only
WEIGHT_CULTURE_ONLY = 1.00


def _parse(value: Any) -> Any:
    """Parse JSONB value from asyncpg."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


class RankingService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.0-flash",
    ):
        self.matcher = CandidateMatcher(
            api_key=api_key,
            vertex_project=vertex_project,
            vertex_location=vertex_location,
            model=model,
        )

    async def run_ranking(
        self,
        company_id: UUID,
        candidate_ids: Optional[list[UUID]] = None,
    ) -> list[dict[str, Any]]:
        """
        Run multi-signal ranking for a company.

        Returns list of ranked result dicts sorted by overall_rank_score desc.
        Also upserts results into ranked_results table.
        """
        async with get_connection() as conn:
            # Load culture profile
            profile_row = await conn.fetchrow(
                "SELECT profile_data FROM culture_profiles WHERE company_id = $1",
                company_id,
            )
            if not profile_row:
                raise ValueError("Company has no culture profile")

            culture_profile = _parse(profile_row["profile_data"])

            # Load candidates
            if candidate_ids:
                placeholders = ", ".join(f"${i + 1}" for i in range(len(candidate_ids)))
                candidates = await conn.fetch(
                    f"SELECT id, name, parsed_data FROM candidates WHERE id IN ({placeholders})",
                    *candidate_ids,
                )
            else:
                # Scope to candidates connected to this company — either via a completed
                # interview or an existing match result. Avoids hitting Gemini for every
                # unrelated candidate in the database.
                candidates = await conn.fetch(
                    """
                    SELECT DISTINCT c.id, c.name, c.parsed_data
                    FROM candidates c
                    WHERE c.id IN (
                        SELECT candidate_id FROM interviews
                        WHERE company_id = $1 AND candidate_id IS NOT NULL AND status = 'completed'
                        UNION
                        SELECT candidate_id FROM match_results
                        WHERE company_id = $1
                    )
                    """,
                    company_id,
                )

            if not candidates:
                return []

            # Load cached match_results for culture scores (avoid re-running Gemini if possible)
            all_candidate_ids = [c["id"] for c in candidates]
            placeholders = ", ".join(f"${i + 1}" for i in range(len(all_candidate_ids)))
            cached_matches = await conn.fetch(
                f"""
                SELECT candidate_id, match_score, culture_fit_breakdown
                FROM match_results
                WHERE company_id = ${len(all_candidate_ids) + 1}
                  AND candidate_id IN ({placeholders})
                """,
                *all_candidate_ids,
                company_id,
            )
            culture_cache: dict[UUID, dict] = {
                row["candidate_id"]: {
                    "match_score": row["match_score"],
                    "culture_fit_breakdown": _parse(row["culture_fit_breakdown"]),
                }
                for row in cached_matches
            }

            results = []
            for candidate in candidates:
                cand_id = candidate["id"]
                cand_name = candidate["name"]
                parsed_data = _parse(candidate["parsed_data"]) or {}

                # --- Signal 1 & 3: Interview data ---
                # Primary lookup: by candidate_id FK (set by seed / interview creation).
                # Fallback: interviews inserted before the FK existed may have NULL candidate_id
                # but store the candidate name in interviewer_name. Match those too and backfill
                # the FK so subsequent ranking runs use the fast path.
                interview_rows = await conn.fetch(
                    """
                    SELECT id, screening_analysis, conversation_analysis
                    FROM interviews
                    WHERE company_id = $1
                      AND status = 'completed'
                      AND (candidate_id = $2 OR (candidate_id IS NULL AND interviewer_name = $3))
                    ORDER BY created_at DESC
                    """,
                    company_id,
                    cand_id,
                    cand_name,
                )

                # Backfill candidate_id for any rows matched by name fallback
                if interview_rows and cand_name:
                    unlinked_ids = [
                        row["id"] for row in interview_rows
                        # asyncpg returns UUID objects; compare directly
                    ]
                    if unlinked_ids:
                        await conn.execute(
                            """
                            UPDATE interviews
                            SET candidate_id = $1
                            WHERE id = ANY($2::uuid[])
                              AND candidate_id IS NULL
                            """,
                            cand_id,
                            unlinked_ids,
                        )

                screening_score: Optional[float] = None
                conversation_score: Optional[float] = None
                has_interview_data = False
                interview_ids = []
                screening_breakdown: Optional[dict] = None
                conversation_breakdown: Optional[dict] = None

                if interview_rows:
                    # Use the most recent interview that has screening_analysis
                    for row in interview_rows:
                        sa = _parse(row["screening_analysis"])
                        ca = _parse(row["conversation_analysis"])

                        if sa and sa.get("overall_score") is not None:
                            screening_score = float(sa["overall_score"])
                            screening_breakdown = {
                                "communication_clarity": sa.get("communication_clarity", {}).get("score"),
                                "engagement_energy": sa.get("engagement_energy", {}).get("score"),
                                "critical_thinking": sa.get("critical_thinking", {}).get("score"),
                                "professionalism": sa.get("professionalism", {}).get("score"),
                                "recommendation": sa.get("recommendation"),
                            }
                            has_interview_data = True

                        if ca:
                            cov = ca.get("coverage_completeness", {}).get("overall_score")
                            dep = ca.get("response_depth", {}).get("overall_score")
                            if cov is not None and dep is not None:
                                conversation_score = (float(cov) + float(dep)) / 2.0
                                conversation_breakdown = {
                                    "coverage_completeness": float(cov),
                                    "response_depth": float(dep),
                                }
                                has_interview_data = True

                        interview_ids.append(str(row["id"]))
                        if screening_score is not None and conversation_score is not None:
                            break  # got all we need from this interview

                # --- Signal 2: Culture alignment ---
                if cand_id in culture_cache:
                    culture_score = float(culture_cache[cand_id]["match_score"] or 50)
                    fit_breakdown = culture_cache[cand_id]["culture_fit_breakdown"]
                else:
                    # No cached result — run matcher
                    match_result = await self.matcher.match_candidate(culture_profile, parsed_data)
                    culture_score = float(match_result.get("match_score", 50))
                    fit_breakdown = match_result.get("culture_fit_breakdown")

                    # Cache it in match_results
                    await conn.execute(
                        """
                        INSERT INTO match_results (company_id, candidate_id, match_score, match_reasoning, culture_fit_breakdown)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (company_id, candidate_id)
                        DO UPDATE SET match_score = $3, match_reasoning = $4, culture_fit_breakdown = $5, created_at = NOW()
                        """,
                        company_id,
                        cand_id,
                        culture_score,
                        match_result.get("match_reasoning", ""),
                        json.dumps(fit_breakdown) if fit_breakdown else None,
                    )

                # --- Compute weighted overall score ---
                if has_interview_data and screening_score is not None and conversation_score is not None:
                    overall = (
                        screening_score * WEIGHT_SCREENING
                        + culture_score * WEIGHT_CULTURE
                        + conversation_score * WEIGHT_CONVERSATION
                    )
                    signal_breakdown = {
                        "screening": {
                            "score": screening_score,
                            "weight": WEIGHT_SCREENING,
                            "weighted_contribution": round(screening_score * WEIGHT_SCREENING, 2),
                            "sub_scores": screening_breakdown,
                        },
                        "culture_alignment": {
                            "score": culture_score,
                            "weight": WEIGHT_CULTURE,
                            "weighted_contribution": round(culture_score * WEIGHT_CULTURE, 2),
                            "culture_fit_breakdown": fit_breakdown,
                        },
                        "conversation_quality": {
                            "score": conversation_score,
                            "weight": WEIGHT_CONVERSATION,
                            "weighted_contribution": round(conversation_score * WEIGHT_CONVERSATION, 2),
                            "sub_scores": conversation_breakdown,
                        },
                        "mode": "full_signal",
                    }
                elif has_interview_data and (screening_score is not None or conversation_score is not None):
                    # Partial interview data — use what we have, weight remaining to culture
                    parts = {"culture": (culture_score, WEIGHT_CULTURE)}
                    total_weight = WEIGHT_CULTURE
                    if screening_score is not None:
                        parts["screening"] = (screening_score, WEIGHT_SCREENING)
                        total_weight += WEIGHT_SCREENING
                    if conversation_score is not None:
                        parts["conversation"] = (conversation_score, WEIGHT_CONVERSATION)
                        total_weight += WEIGHT_CONVERSATION

                    overall = (
                        sum(score * weight for score, weight in parts.values()) / total_weight
                        if total_weight > 0
                        else culture_score
                    )
                    signal_breakdown = {
                        "screening": {
                            "score": screening_score,
                            "weight": WEIGHT_SCREENING if screening_score is not None else 0,
                            "weighted_contribution": round((screening_score or 0) * WEIGHT_SCREENING, 2),
                            "sub_scores": screening_breakdown,
                        },
                        "culture_alignment": {
                            "score": culture_score,
                            "weight": WEIGHT_CULTURE,
                            "weighted_contribution": round(culture_score * WEIGHT_CULTURE, 2),
                            "culture_fit_breakdown": fit_breakdown,
                        },
                        "conversation_quality": {
                            "score": conversation_score,
                            "weight": WEIGHT_CONVERSATION if conversation_score is not None else 0,
                            "weighted_contribution": round((conversation_score or 0) * WEIGHT_CONVERSATION, 2),
                            "sub_scores": conversation_breakdown,
                        },
                        "mode": "partial_signal",
                    }
                else:
                    # Resume-only fallback
                    overall = culture_score
                    signal_breakdown = {
                        "culture_alignment": {
                            "score": culture_score,
                            "weight": WEIGHT_CULTURE_ONLY,
                            "weighted_contribution": round(culture_score * WEIGHT_CULTURE_ONLY, 2),
                            "culture_fit_breakdown": fit_breakdown,
                        },
                        "mode": "resume_only",
                    }

                overall = round(overall, 2)

                # Upsert into ranked_results
                row = await conn.fetchrow(
                    """
                    INSERT INTO ranked_results (
                        company_id, candidate_id, overall_rank_score,
                        screening_score, conversation_score, culture_alignment_score,
                        signal_breakdown, has_interview_data, interview_ids
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (company_id, candidate_id)
                    DO UPDATE SET
                        overall_rank_score = $3,
                        screening_score = $4,
                        conversation_score = $5,
                        culture_alignment_score = $6,
                        signal_breakdown = $7,
                        has_interview_data = $8,
                        interview_ids = $9,
                        created_at = NOW()
                    RETURNING id, created_at
                    """,
                    company_id,
                    cand_id,
                    overall,
                    screening_score,
                    conversation_score,
                    culture_score,
                    json.dumps(signal_breakdown),
                    has_interview_data,
                    json.dumps(interview_ids),
                )

                results.append({
                    "id": row["id"],
                    "company_id": company_id,
                    "candidate_id": cand_id,
                    "candidate_name": cand_name,
                    "overall_rank_score": overall,
                    "screening_score": screening_score,
                    "conversation_score": conversation_score,
                    "culture_alignment_score": culture_score,
                    "has_interview_data": has_interview_data,
                    "signal_breakdown": signal_breakdown,
                    "interview_ids": interview_ids,
                    "created_at": row["created_at"],
                })

        results.sort(key=lambda x: x["overall_rank_score"], reverse=True)
        return results
