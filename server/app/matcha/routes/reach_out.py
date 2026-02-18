"""Reach-out email drafting and sending for ranked candidates."""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...config import get_settings
from ...database import get_connection
from ...core.dependencies import get_current_user
from ...core.services.email import get_email_service
from ..dependencies import require_admin_or_client
from ..models.reach_out import ReachOutDraftResponse, ReachOutSendRequest, ReachOutSendResponse

router = APIRouter()

REACH_OUT_PROMPT = """You are an HR recruiter at {company_name}. Draft a concise, warm meeting-request email to {candidate_name}.

Their evaluation shows: overall {overall_score}/100, screening score {screening_score}, culture alignment {culture_score}.
Key strengths based on their evaluation: {strengths_text}

Return ONLY a JSON object (no markdown, no extra text):
{{"subject": "...", "body": "..."}}

The body should have 3-4 short paragraphs:
1. Friendly greeting
2. Why they stood out (mention specific qualities, NOT raw scores)
3. Propose a 30-minute call to connect
4. Sign-off as {admin_name} at {company_name}

Keep it warm, professional, and genuine. Do not mention numerical scores."""


def _parse_json(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def _extract_strengths(signal_breakdown: dict | None) -> str:
    """Extract top 2-3 strength phrases from the culture fit breakdown."""
    if not signal_breakdown:
        return "strong communication skills and cultural alignment"

    culture_fit = signal_breakdown.get("culture_fit_breakdown", {})
    if not culture_fit:
        return "strong communication skills and cultural alignment"

    # Collect (score, reasoning) pairs
    items = []
    for key, val in culture_fit.items():
        if isinstance(val, dict) and val.get("score") is not None:
            score = val.get("score", 0)
            reasoning = val.get("reasoning", "")
            if reasoning:
                items.append((score, reasoning))

    if not items:
        return "strong communication skills and cultural alignment"

    # Sort by score descending, take top 3
    items.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in items[:3]]
    return "; ".join(top)


@router.post(
    "/companies/{company_id}/candidates/{candidate_id}/draft-reach-out",
    response_model=ReachOutDraftResponse,
)
async def draft_reach_out(
    company_id: UUID,
    candidate_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Use Gemini to draft a personalized meeting-request email for a ranked candidate."""
    settings = get_settings()

    async with get_connection() as conn:
        # Fetch candidate
        candidate = await conn.fetchrow(
            "SELECT name, email FROM candidates WHERE id = $1",
            candidate_id,
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        # Fetch company name
        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Fetch ranked result for this company+candidate
        ranked = await conn.fetchrow(
            """
            SELECT overall_rank_score, screening_score, culture_alignment_score, signal_breakdown
            FROM ranked_results
            WHERE company_id = $1 AND candidate_id = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            company_id,
            candidate_id,
        )

    candidate_name = candidate["name"] or "there"
    candidate_email = candidate["email"]
    company_name = company["name"]

    # Get admin's display name for sign-off (name is on profile, not CurrentUser directly)
    profile = getattr(current_user, "profile", None)
    admin_name = getattr(profile, "name", None) or current_user.email or "the hiring team"

    # Build signal context
    overall_score = 0
    screening_score = "N/A"
    culture_score = "N/A"
    signal_breakdown = None

    if ranked:
        overall_score = round(ranked["overall_rank_score"] or 0)
        screening_score = round(ranked["screening_score"]) if ranked["screening_score"] is not None else "N/A"
        culture_score = round(ranked["culture_alignment_score"]) if ranked["culture_alignment_score"] is not None else "N/A"
        signal_breakdown = _parse_json(ranked["signal_breakdown"])

    strengths_text = _extract_strengths(signal_breakdown)

    prompt = REACH_OUT_PROMPT.format(
        company_name=company_name,
        candidate_name=candidate_name,
        overall_score=overall_score,
        screening_score=screening_score,
        culture_score=culture_score,
        strengths_text=strengths_text,
        admin_name=admin_name,
    )

    # Call Gemini
    try:
        from google import genai

        if settings.vertex_project:
            client = genai.Client(
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location or "us-central1",
            )
        elif settings.gemini_api_key:
            client = genai.Client(api_key=settings.gemini_api_key)
        else:
            raise HTTPException(status_code=500, detail="AI service not configured")

        model = settings.analysis_model or "gemini-2.0-flash"
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
        )
        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text

        draft = json.loads(raw_text)
        subject = draft.get("subject", f"Let's connect — {company_name}")
        body = draft.get("body", "")

    except json.JSONDecodeError:
        # Fallback: use the raw text as the body
        subject = f"Let's connect — {company_name}"
        body = raw_text if "raw_text" in dir() else "We'd love to set up a quick call to learn more about you."
    except Exception as e:
        print(f"[ReachOut] Gemini error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate email draft")

    return ReachOutDraftResponse(
        to_email=candidate_email,
        to_name=candidate_name,
        subject=subject,
        body=body,
    )


@router.post(
    "/companies/{company_id}/candidates/{candidate_id}/send-reach-out",
    response_model=ReachOutSendResponse,
)
async def send_reach_out(
    company_id: UUID,
    candidate_id: UUID,
    body: ReachOutSendRequest,
    current_user=Depends(require_admin_or_client),
):
    """Send the (possibly admin-edited) reach-out email to the candidate."""
    async with get_connection() as conn:
        candidate = await conn.fetchrow(
            "SELECT name FROM candidates WHERE id = $1",
            candidate_id,
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        company = await conn.fetchrow(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    profile = getattr(current_user, "profile", None)
    admin_name = getattr(profile, "name", None) or current_user.email or "The Hiring Team"

    email_service = get_email_service()
    sent = await email_service.send_candidate_reach_out_email(
        to_email=body.to_email,
        to_name=candidate["name"] or body.to_email,
        subject=body.subject,
        body=body.body,
        from_name=admin_name,
        from_company=company["name"],
    )

    if sent:
        return ReachOutSendResponse(success=True, message="Email sent successfully")
    else:
        return ReachOutSendResponse(success=False, message="Failed to send email. Check email service configuration.")
