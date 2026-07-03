"""Recruiting: recruiting-client CRUD, project chats, job posting, candidate
shortlist/dismiss/reject, resume upload/analyze, and interview send/sync.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import asyncio
import json
import logging
import os
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.matcha_work import RejectCandidateRequest, SendInterviewsRequest
from app.matcha.routes.matcha_work._shared import (
    RESUME_UPLOAD_EXTENSIONS,
    RESUME_UPLOAD_MAX_BYTES,
    _sse_data,
    _strip_markdown,
    _verify_project_access,
)
from app.matcha.services.er_document_parser import ERDocumentParser
from app.matcha.services.matcha_work_ai import get_ai_provider

logger = logging.getLogger(__name__)
router = APIRouter()

RESUME_TEXT_CAP = 15_000

RESUME_EXTRACT_PROMPT = """Extract candidate information from this resume. Return ONLY valid JSON with these fields:
{"name":"...","email":"...","phone":"...","location":"...","current_title":"...","experience_years":0,"skills":["..."],"education":"highest degree - school","certifications":["..."],"summary":"1-2 sentence professional summary","strengths":["top 3 strengths"],"flags":["any concerns or gaps"]}

Resume text:
---
%s
---"""

@router.get("/recruiting-clients")
async def list_recruiting_clients_endpoint(
    include_archived: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    return await rc_svc.list_clients(company_id, include_archived=include_archived)

@router.post("/recruiting-clients", status_code=201)
async def create_recruiting_client_endpoint(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    return await rc_svc.create_client(
        company_id,
        current_user.id,
        name=name,
        website=body.get("website"),
        logo_url=body.get("logo_url"),
        notes=body.get("notes"),
    )

@router.get("/recruiting-clients/{client_id}")
async def get_recruiting_client_endpoint(
    client_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    rc = await rc_svc.get_client(client_id, company_id)
    if not rc:
        raise HTTPException(status_code=404, detail="Not found")
    return rc

@router.patch("/recruiting-clients/{client_id}")
async def update_recruiting_client_endpoint(
    client_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    rc = await rc_svc.update_client(client_id, company_id, body)
    if not rc:
        raise HTTPException(status_code=404, detail="Not found")
    return rc

@router.post("/recruiting-clients/{client_id}/archive")
async def archive_recruiting_client_endpoint(
    client_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    ok = await rc_svc.archive_client(client_id, company_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "archived"}

@router.post("/recruiting-clients/{client_id}/unarchive")
async def unarchive_recruiting_client_endpoint(
    client_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    ok = await rc_svc.unarchive_client(client_id, company_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "active"}

@router.get("/projects/{project_id}/chats")
async def list_project_chats_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List AI chat threads in a project visible to the current user.

    Private-per-person: returns threads the user created in this project plus
    any project thread shared with them. Access to the project itself is
    verified first.
    """
    from app.matcha.services import project_service as proj_svc
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = project.get("company_id")
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    return await proj_svc.list_project_chats(project_id, company_id, current_user.id)

@router.post("/projects/{project_id}/chats")
async def create_project_chat_endpoint(
    project_id: UUID,
    body: dict = {},
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new chat within a project."""
    from app.matcha.services import project_service as proj_svc
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = project.get("company_id")
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    return await proj_svc.create_project_chat(project_id, company_id, current_user.id, body.get("title"))

@router.post("/projects/{project_id}/posting/from-chat")
async def populate_posting_from_chat(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Extract structured posting fields from a chat message using AI."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    content = body.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided")

    # Use AI to extract structured fields
    ai_provider = get_ai_provider()
    prompt = (
        "Extract job posting fields from this text. Return ONLY valid JSON with these fields "
        "(use null for missing fields):\n"
        '{"title":"...","description":"...","requirements":"...","compensation":"...",'
        '"location":"...","employment_type":"full-time|part-time|contract"}\n\n'
        f"Text:\n---\n{content[:5000]}\n---"
    )
    ai_resp = await ai_provider.generate(
        [{"role": "user", "content": prompt}], {}, company_context=""
    )

    # Parse the AI response
    raw = ai_resp.assistant_reply.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        fields = json.loads(raw)
    except Exception:
        # Fallback: put everything in description
        fields = {"description": _strip_markdown(content)}

    # Merge with existing posting (don't overwrite non-null fields with null)
    existing = (project.get("project_data") or {}).get("posting") or {}
    merged = {**existing}
    for k, v in fields.items():
        if v is not None and str(v).strip():
            merged[k] = v

    result = await proj_svc.update_project_data(project_id, {"posting": merged})
    return result

@router.put("/projects/{project_id}/posting")
async def update_project_posting(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update the job posting data for a recruiting project."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.update_project_data(project_id, {"posting": body})

@router.post("/projects/{project_id}/shortlist/{candidate_id}")
async def toggle_project_shortlist(
    project_id: UUID,
    candidate_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Toggle a candidate on/off the shortlist."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.toggle_shortlist(project_id, candidate_id)

@router.post("/projects/{project_id}/dismiss/{candidate_id}")
async def toggle_project_dismiss(
    project_id: UUID,
    candidate_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Toggle a candidate on/off the dismissed list."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.toggle_dismiss(project_id, candidate_id)

@router.post("/projects/{project_id}/reject/{candidate_id}")
async def reject_project_candidate(
    project_id: UUID,
    candidate_id: str,
    body: RejectCandidateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reject a candidate, optionally sending a polite rejection email.

    When `send_email=false` this is equivalent to dismissing the candidate
    with a `status='rejected'` marker — no email goes out.
    """
    from app.matcha.services import project_service as proj_svc
    from app.core.services.email import EmailService

    project, _role = await _verify_project_access(project_id, current_user)
    data = project.get("project_data") or {}
    candidates = list(data.get("candidates") or [])

    candidate_idx = next(
        (i for i, c in enumerate(candidates) if c.get("id") == candidate_id),
        None,
    )
    if candidate_idx is None:
        raise HTTPException(status_code=404, detail="Candidate not found in project")

    candidate = candidates[candidate_idx]
    name = candidate.get("name") or candidate.get("filename", "Candidate")
    email = candidate.get("email")

    # Idempotency guard: if the candidate was already rejected + hidden, don't
    # re-send the email. Return the current project so the caller's state stays
    # in sync but the `email_sent` flag is honest.
    dismissed_ids = list(data.get("dismissed_ids") or [])
    already_rejected = (
        candidate.get("status") == "rejected" and candidate_id in dismissed_ids
    )
    if already_rejected:
        return {"project": project, "email_sent": False, "already_rejected": True}

    email_sent = False
    if body.send_email and email:
        company_id = project.get("company_id")
        async with get_connection() as conn:
            company_row = await conn.fetchrow(
                "SELECT name FROM companies WHERE id = $1", company_id
            )
        company_name = company_row["name"] if company_row else "the company"
        position_title = project.get("title") or "Open Position"

        email_svc = EmailService()
        try:
            email_sent = await email_svc.send_candidate_rejection_email(
                to_email=email,
                to_name=name,
                company_name=company_name,
                position_title=position_title,
                custom_message=body.custom_message,
            )
        except Exception as e:
            logger.error("Rejection email failed for %s: %s", email, e, exc_info=True)
            email_sent = False

    # Mutate candidate: mark rejected, store internal reason
    candidates[candidate_idx] = {
        **candidate,
        "status": "rejected",
        "rejection_reason": body.rejection_reason,
    }

    # Add to dismissed_ids so existing filters hide the candidate by default
    if candidate_id not in dismissed_ids:
        dismissed_ids.append(candidate_id)

    updated_project = await proj_svc.update_project_data(
        project_id,
        {"candidates": candidates, "dismissed_ids": dismissed_ids},
    )

    return {
        "project": updated_project,
        "email_sent": email_sent,
    }

@router.post("/projects/{project_id}/resume/upload")
async def upload_project_resumes(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload resumes to a recruiting project — extract candidates into project_data."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    # Require finalized posting before accepting resumes
    data = project.get("project_data") or {}
    posting = data.get("posting") or {}
    if not posting.get("finalized"):
        raise HTTPException(status_code=400, detail="Finalize the job posting before uploading resumes")

    # Validate files
    parsed_files: list[tuple[str, bytes, str]] = []
    for f in files:
        fname = f.filename or "resume"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in RESUME_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {fname}")
        raw = await f.read()
        if len(raw) > RESUME_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"File exceeds 10 MB limit: {fname}")
        parsed_files.append((fname, raw, f.content_type or "application/octet-stream"))

    async def event_stream():
        try:
            from google import genai as _genai
            from google.genai import types as _types

            api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
            client = _genai.Client(api_key=api_key)
            extract_model = "gemini-3.1-flash-lite"
            parser = ERDocumentParser()
            new_candidates = []

            for idx, (fname, raw, ct) in enumerate(parsed_files, 1):
                yield _sse_data({"type": "status", "message": f"Extracting text from {fname} ({idx}/{len(parsed_files)})..."})
                try:
                    text, _ = parser.extract_text_from_bytes(raw, fname)
                except Exception:
                    continue
                if not text or len(text.strip()) < 50:
                    continue

                yield _sse_data({"type": "status", "message": f"Analyzing {fname} ({idx}/{len(parsed_files)})..."})
                capped = text[:RESUME_TEXT_CAP]
                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            lambda t=capped: client.models.generate_content(
                                model=extract_model,
                                contents=[_types.Content(role="user", parts=[_types.Part.from_text(text=RESUME_EXTRACT_PROMPT % t)])],
                                config=_types.GenerateContentConfig(temperature=0.1),
                            )
                        ),
                        timeout=60,
                    )
                    raw_json = (resp.text or "").strip()
                    if raw_json.startswith("```"):
                        raw_json = raw_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    data = json.loads(raw_json)
                    new_candidates.append({
                        "id": os.urandom(8).hex(),
                        "filename": fname,
                        "name": data.get("name"),
                        "email": data.get("email"),
                        "phone": data.get("phone"),
                        "location": data.get("location"),
                        "current_title": data.get("current_title"),
                        "experience_years": data.get("experience_years"),
                        "skills": data.get("skills"),
                        "education": data.get("education"),
                        "certifications": data.get("certifications"),
                        "summary": data.get("summary"),
                        "strengths": data.get("strengths"),
                        "flags": data.get("flags"),
                        "status": "analyzed",
                    })
                except Exception as e:
                    logger.warning("Resume extraction failed for %s: %s", fname, e)

            if new_candidates:
                yield _sse_data({"type": "status", "message": f"Adding {len(new_candidates)} candidates to project..."})
                result = await proj_svc.add_candidates_to_project(project_id, new_candidates)
                yield _sse_data({"type": "complete", "data": {"candidates_added": len(new_candidates), "project": result}})
            else:
                yield _sse_data({"type": "complete", "data": {"candidates_added": 0}})
        except Exception as e:
            logger.error("Project resume upload failed: %s", e, exc_info=True)
            yield _sse_data({"type": "error", "message": "Failed to process resumes."})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/placeholder-questions")
async def generate_placeholder_questions(
    body: dict,
    _current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate human-friendly questions for each placeholder using AI."""
    placeholders = body.get("placeholders") or []  # [{placeholder, label}]
    if not placeholders:
        return {"questions": []}

    items = "\n".join(
        f"- Placeholder: {p['placeholder']}, Context: \"{p.get('label', p['placeholder'])}\""
        for p in placeholders
    )

    try:
        from google import genai as _genai
        from google.genai import types as _types

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        client = _genai.Client(api_key=api_key)
        resp = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[_types.Content(role="user", parts=[_types.Part.from_text(
                    text=f"Generate a short, friendly question for each placeholder below. The question should help someone fill in the blank in a job posting. Return ONE question per line, in order, no numbering or bullets.\n\n{items}"
                )])],
                config=_types.GenerateContentConfig(temperature=0.3),
            )
        )
        lines = [l.strip() for l in (resp.text or "").strip().split("\n") if l.strip()]
        # Pair questions with placeholders
        questions = []
        for i, p in enumerate(placeholders):
            q = lines[i] if i < len(lines) else f"What's the {p['placeholder']}?"
            questions.append({"placeholder": p["placeholder"], "label": p.get("label", ""), "question": q})
        return {"questions": questions}
    except Exception as e:
        logger.warning("Placeholder question generation failed: %s", e)
        # Fallback to raw names
        return {"questions": [
            {"placeholder": p["placeholder"], "label": p.get("label", ""), "question": f"What's the {p['placeholder']}?"}
            for p in placeholders
        ]}

@router.post("/projects/extract-value")
async def extract_placeholder_value(
    body: dict,
    _current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Extract a clean replacement value from a user's natural-language answer."""
    user_input = (body.get("input") or "").strip()
    placeholder = body.get("placeholder") or ""
    context = body.get("context") or ""

    if not user_input:
        return {"value": user_input}

    # Simple case: short input (≤ 3 words) — use directly
    if len(user_input.split()) <= 3:
        return {"value": user_input}

    # Complex input: use Gemini flash lite to extract the actual value
    try:
        from google import genai as _genai
        from google.genai import types as _types

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        client = _genai.Client(api_key=api_key)
        resp = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[_types.Content(role="user", parts=[_types.Part.from_text(
                    text=f"Extract the exact value to fill in the placeholder {placeholder} from this user answer: \"{user_input}\"\n"
                         f"Context from the document: \"{context}\"\n"
                         f"Return ONLY the extracted value — no quotes, no explanation, just the value itself."
                )])],
                config=_types.GenerateContentConfig(temperature=0.0),
            )
        )
        extracted = (resp.text or "").strip().strip('"').strip("'")
        return {"value": extracted if extracted else user_input}
    except Exception as e:
        logger.warning("Value extraction failed, using raw input: %s", e)
        return {"value": user_input}

@router.post("/projects/{project_id}/resume/analyze")
async def analyze_project_candidates(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Rank candidates against the job posting using AI."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    # Build posting text from sections (strip HTML tags for clean AI input)
    sections = project.get("sections") or []
    def _strip_html(html: str) -> str:
        return re.sub(r'<[^>]+>', '', html).strip()

    posting_text = "\n\n".join(
        f"{s.get('title', 'Untitled')}:\n{_strip_html(s.get('content', ''))}"
        for s in sections
    )
    if not posting_text.strip():
        raise HTTPException(status_code=400, detail="No posting content to analyze against")

    data = project.get("project_data") or {}
    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates to analyze")

    # Build candidate summaries for the prompt
    candidate_entries = []
    for c in candidates:
        if c.get("status") not in ("analyzed", "interview_sent", "interview_completed", "interview_in_progress"):
            continue
        entry = f"ID: {c['id']}\nName: {c.get('name', 'Unknown')}\n"
        if c.get("current_title"):
            entry += f"Title: {c['current_title']}\n"
        if c.get("experience_years") is not None:
            entry += f"Experience: {c['experience_years']} years\n"
        if c.get("skills"):
            entry += f"Skills: {', '.join(c['skills'][:15])}\n"
        if c.get("education"):
            entry += f"Education: {c['education']}\n"
        if c.get("certifications"):
            entry += f"Certifications: {', '.join(c['certifications'])}\n"
        if c.get("summary"):
            entry += f"Summary: {c['summary']}\n"
        if c.get("strengths"):
            entry += f"Strengths: {', '.join(c['strengths'])}\n"
        if c.get("flags"):
            entry += f"Flags: {', '.join(c['flags'])}\n"
        candidate_entries.append(entry)

    if not candidate_entries:
        raise HTTPException(status_code=400, detail="No analyzed candidates to rank")

    try:
        from google import genai as _genai
        from google.genai import types as _types

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        client = _genai.Client(api_key=api_key)

        prompt = (
            "You are a recruiting analyst. Given the job posting and candidate profiles below, "
            "score each candidate on how well they match the posting (0-100). "
            "Return ONLY valid JSON — an array of objects with these exact fields:\n"
            '  [{"id": "<candidate_id>", "score": <0-100>, "summary": "<1-2 sentence reason>"}]\n'
            "Order by score descending (best match first).\n\n"
            f"=== JOB POSTING ===\n{posting_text}\n\n"
            f"=== CANDIDATES ===\n" + "\n---\n".join(candidate_entries)
        )

        resp = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=[_types.Content(role="user", parts=[_types.Part.from_text(text=prompt)])],
                    config=_types.GenerateContentConfig(temperature=0.1),
                )
            ),
            timeout=60,
        )

        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        rankings = json.loads(raw)

        # Merge scores into candidates
        score_map = {r["id"]: r for r in rankings}
        updated_candidates = []
        for c in candidates:
            match = score_map.get(c["id"])
            if match:
                updated_candidates.append({
                    **c,
                    "match_score": match.get("score"),
                    "match_summary": match.get("summary"),
                })
            else:
                updated_candidates.append(c)

        # Sort by match_score descending
        updated_candidates.sort(key=lambda x: x.get("match_score") or 0, reverse=True)

        await proj_svc.update_project_data(project_id, {"candidates": updated_candidates})
        return {"analyzed": len(rankings), "candidates": updated_candidates}

    except json.JSONDecodeError as e:
        logger.error("Failed to parse ranking JSON: %s", e)
        raise HTTPException(status_code=500, detail="Failed to parse AI ranking response")
    except Exception as e:
        logger.error("Candidate analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/projects/{project_id}/resume/send-interviews")
async def send_project_interviews(
    project_id: UUID,
    body: SendInterviewsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create screening interviews for selected project candidates and send invite emails."""
    import secrets as _secrets
    from app.matcha.services import project_service as proj_svc
    from app.core.services.email import EmailService

    project, _role = await _verify_project_access(project_id, current_user)

    data = project.get("project_data") or {}
    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates in this project")

    company_id = project.get("company_id")
    async with get_connection() as conn:
        company_row = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
    company_name = company_row["name"] if company_row else "the company"

    position_title = body.position_title or project.get("title") or "Open Position"
    email_svc = EmailService()
    settings = get_settings()

    sent = []
    failed = []
    updated_candidates = list(candidates)

    for cid in body.candidate_ids:
        candidate = None
        candidate_idx = None
        for idx, c in enumerate(updated_candidates):
            if c.get("id") == cid:
                candidate = c
                candidate_idx = idx
                break

        if candidate is None:
            failed.append({"id": cid, "error": "Candidate not found in project"})
            continue

        email = candidate.get("email")
        name = candidate.get("name") or candidate.get("filename", "Candidate")
        if not email:
            failed.append({"id": cid, "error": f"No email for {name}"})
            continue

        try:
            invite_token = _secrets.token_urlsafe(32)
            interview_data = json.dumps({
                "invite_token": invite_token,
                "candidate_name": name,
                "candidate_email": email,
                "position_title": position_title,
                "company_name": company_name,
                "resume_batch_project_id": str(project_id),
                "resume_batch_candidate_id": cid,
            })

            async with get_connection() as interview_conn:
                interview_row = await interview_conn.fetchrow(
                    """
                    INSERT INTO interviews (id, company_id, interviewer_name, interview_type, raw_culture_data, status, created_at)
                    VALUES (gen_random_uuid(), $1, $2, 'screening', $3, 'pending', NOW())
                    RETURNING id
                    """,
                    company_id,
                    name,
                    interview_data,
                )
            interview_id = interview_row["id"]

            invite_url = f"{settings.app_base_url}/candidate-interview/{invite_token}"
            email_sent = await email_svc.send_candidate_interview_invite_email(
                to_email=email,
                to_name=name,
                company_name=company_name,
                position_title=position_title,
                invite_url=invite_url,
                custom_message=body.custom_message,
            )

            updated_candidates[candidate_idx] = {
                **candidate,
                "status": "interview_sent",
                "interview_id": str(interview_id),
            }

            sent.append({
                "id": cid,
                "name": name,
                "email": email,
                "interview_id": str(interview_id),
                "email_sent": email_sent,
            })
        except Exception as e:
            logger.error("Failed to create interview for project candidate %s: %s", cid, e, exc_info=True)
            failed.append({"id": cid, "error": str(e)})

    if sent:
        await proj_svc.update_project_data(project_id, {"candidates": updated_candidates})

    return {"sent": sent, "failed": failed}

@router.post("/projects/{project_id}/resume/sync-interviews")
async def sync_project_interviews(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Sync interview statuses back into project candidates."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    data = project.get("project_data") or {}
    candidates = data.get("candidates") or []

    interview_ids = [c.get("interview_id") for c in candidates if c.get("interview_id")]
    if not interview_ids:
        return {"updated": 0}

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, status, screening_analysis
            FROM interviews
            WHERE id = ANY($1::uuid[])
            """,
            interview_ids,
        )

    interview_map = {str(r["id"]): r for r in rows}
    updated = 0
    updated_candidates = list(candidates)

    for idx, c in enumerate(updated_candidates):
        iid = c.get("interview_id")
        if not iid or iid not in interview_map:
            continue
        row = interview_map[iid]
        new_status = c.get("status")
        interview_status = row["status"]

        # Treat analyzing as completed for UI purposes — interview is over,
        # only the AI analysis is still running. The review modal handles the
        # "no analysis yet" state gracefully.
        if interview_status in ("completed", "analyzed", "analyzing") and c.get("status") != "interview_completed":
            new_status = "interview_completed"
        elif interview_status == "in_progress" and c.get("status") == "interview_sent":
            new_status = "interview_in_progress"

        score = None
        summary = None
        analysis = row.get("screening_analysis")
        if analysis:
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            score = analysis.get("overall_score") or analysis.get("score")
            summary = analysis.get("summary") or analysis.get("overall_assessment")

        if new_status != c.get("status") or score or summary:
            updated_candidates[idx] = {
                **c,
                "status": new_status,
                "interview_status": interview_status,
                "interview_score": score,
                "interview_summary": summary,
            }
            updated += 1

    if updated > 0:
        await proj_svc.update_project_data(project_id, {"candidates": updated_candidates})

    return {"updated": updated}
