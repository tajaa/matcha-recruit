"""Thread-scoped file uploads: images, generic files, resume batches (+ batch
interview send/sync), and inventory documents.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import asyncio
import json
import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.config import get_settings
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work._shared import (
    RESUME_UPLOAD_EXTENSIONS,
    RESUME_UPLOAD_MAX_BYTES,
    THREAD_FILE_EXTENSIONS,
    THREAD_FILE_MAX_BYTES,
    _row_to_message,
    _sse_data,
)
from app.matcha.models.matcha_work import SendInterviewsRequest, SendMessageResponse
from app.matcha.services import matcha_work_document as doc_svc
from app.matcha.services import token_budget_service
from app.matcha.services.er_document_parser import ERDocumentParser
from app.matcha.services.matcha_work_ai import _build_company_context, _infer_skill_from_state, get_ai_provider

logger = logging.getLogger(__name__)
router = APIRouter()

INVENTORY_UPLOAD_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls", ".doc", ".docx", ".txt"}

INVENTORY_UPLOAD_MAX_BYTES = 15 * 1024 * 1024

INVENTORY_TEXT_CAP = 15_000

@router.post("/threads/{thread_id}/images")
async def upload_thread_images(
    thread_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload up to 4 images for a workbook thread's presentation (10 MB each)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        thread["current_state"] = await doc_svc.ensure_matcha_work_thread_storage_scope(
            thread_id,
            company_id,
            thread.get("current_state") or {},
        )
        existing: list[str] = (thread.get("current_state") or {}).get("images") or []
        if len(existing) + len(files) > 4:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum 4 images allowed. You already have {len(existing)}.",
            )

        uploaded_urls: list[str] = []
        for file in files:
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail=f"'{file.filename}' is not an image")
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"'{file.filename}' exceeds 10 MB limit")
            url = await get_storage().upload_file(
                content,
                file.filename or "image.jpg",
                prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "images"),
                content_type=file.content_type,
            )
            uploaded_urls.append(url)

        new_images = existing + uploaded_urls
        await doc_svc.apply_update(thread_id, {"images": new_images}, diff_summary="Added presentation images")
        return {"images": new_images, "uploaded_count": len(uploaded_urls)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload images for thread %s: %s", thread_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload images. Please try again.")

@router.delete("/threads/{thread_id}/images")
async def remove_thread_image(
    thread_id: UUID,
    url: str = Query(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a single image from a workbook thread by URL."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    current_images: list[str] = (thread.get("current_state") or {}).get("images") or []
    if url not in current_images:
        raise HTTPException(status_code=404, detail="Image not found in thread")

    updated_images = [u for u in current_images if u != url]
    await doc_svc.apply_update(thread_id, {"images": updated_images}, diff_summary="Removed presentation image")

    # Best-effort S3 deletion — don't fail the request if this errors
    try:
        await get_storage().delete_file(url)
    except Exception:
        pass

    return {"images": updated_images}

@router.post("/threads/{thread_id}/files")
async def upload_thread_files(
    thread_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generic file attach for a thread message — stores to S3 and returns
    refs. Deliberately does NOT extract or analyze: the dropped file is a
    plain attachment until the user sends an instruction with it. Extraction
    + AI context happens at send time (see send_message), and a file sent
    with no instruction yields a clarifying reply, not an auto-analysis.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread["status"] in ("finalized", "archived"):
        raise HTTPException(status_code=400, detail=f"Cannot upload to a {thread['status']} thread")

    storage = get_storage()
    prefix = doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "files")
    out: list[dict] = []
    for f in files:
        fname = f.filename or "file"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in THREAD_FILE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {fname}")
        raw = await f.read()
        if len(raw) > THREAD_FILE_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"File exceeds 10 MB limit: {fname}")
        ct = f.content_type or "application/octet-stream"
        url = await storage.upload_file(raw, fname, prefix=prefix, content_type=ct)
        out.append({"url": url, "filename": fname, "content_type": ct, "size": len(raw)})
    return {"attachments": out}

@router.post("/threads/{thread_id}/resume/upload")
async def upload_thread_resume(
    thread_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload one or more resumes, extract structured candidate data, and stream batch insights."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread["status"] in ("finalized", "archived"):
        raise HTTPException(status_code=400, detail=f"Cannot upload to a {thread['status']} thread")

    if current_user.role != "admin":
        await token_budget_service.check_token_budget(company_id)

    # Validate all files upfront
    parsed_files: list[tuple[str, bytes, str]] = []  # (filename, content, content_type)
    for f in files:
        fname = f.filename or "resume"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in RESUME_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {fname}")
        raw = await f.read()
        if len(raw) > RESUME_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"File exceeds 10 MB limit: {fname}")
        parsed_files.append((fname, raw, f.content_type or "application/octet-stream"))

    file_count = len(parsed_files)
    filenames = [f[0] for f in parsed_files]

    # Save a single user message for the batch
    user_content = f"[Resume batch: {file_count} files]\n" + "\n".join(f"- {fn}" for fn in filenames)
    user_msg = await doc_svc.add_message(thread_id, "user", user_content)

    async def event_stream():
        try:
            from app.matcha.services.resume_parser import (
                extract_resume_text,
                parse_resume_text,
                ResumeParseError,
            )

            existing_candidates = list((thread.get("current_state") or {}).get("candidates") or [])
            new_candidates = []
            errors = []

            for idx, (fname, raw, ct) in enumerate(parsed_files, 1):
                yield _sse_data({"type": "status", "message": f"Extracting text from {fname} ({idx}/{file_count})..."})

                # Extract text via the shared helper
                try:
                    text = await extract_resume_text(raw, fname)
                except Exception:
                    errors.append(fname)
                    continue

                # Upload raw file to S3 (best-effort)
                resume_url = None
                try:
                    resume_url = await get_storage().upload_file(
                        raw, fname,
                        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "resumes"),
                        content_type=ct,
                    )
                except Exception:
                    pass

                # Structured extraction via shared helper
                yield _sse_data({"type": "status", "message": f"Analyzing {fname} ({idx}/{file_count})..."})
                candidate_id = os.urandom(8).hex()
                try:
                    data = await parse_resume_text(text)
                    candidate = {
                        "id": candidate_id,
                        "filename": fname,
                        "resume_url": resume_url,
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
                    }
                except ResumeParseError as e:
                    logger.warning("AI extraction failed for %s: %s", fname, e)
                    candidate = {
                        "id": candidate_id,
                        "filename": fname,
                        "resume_url": resume_url,
                        "status": "error",
                    }

                new_candidates.append(candidate)

                # Update name in status if available
                name = candidate.get("name") or fname
                yield _sse_data({"type": "status", "message": f"Analyzed {name} ({idx}/{file_count})"})

            # Accumulate into state
            all_candidates = existing_candidates + new_candidates
            analyzed = sum(1 for c in all_candidates if c.get("status") == "analyzed")
            result = await doc_svc.apply_update(thread_id, {
                "candidates": all_candidates,
                "batch_status": "ready",
                "total_count": len(all_candidates),
                "analyzed_count": analyzed,
            })
            current_state = result["current_state"]
            current_version = result["version"]

            # Generate batch summary
            yield _sse_data({"type": "status", "message": "Generating batch insights..."})
            summaries = []
            for c in new_candidates:
                if c.get("status") != "analyzed":
                    continue
                summaries.append(
                    f"- {c.get('name', 'Unknown')}: {c.get('current_title', 'N/A')}, "
                    f"{c.get('experience_years', '?')} yrs, {c.get('location', 'N/A')}. "
                    f"{c.get('summary', '')}"
                )

            if summaries:
                batch_prompt = (
                    f"I just uploaded {len(new_candidates)} resumes. Here are the candidates:\n\n"
                    + "\n".join(summaries)
                    + "\n\nProvide a brief batch overview:\n"
                    "1. Quick summary of the candidate pool (experience range, common skills, locations)\n"
                    "2. Top standout candidates and why\n"
                    "3. Any common gaps or concerns\n"
                    "Keep it concise — 2-3 short paragraphs max."
                )
                ai_provider = get_ai_provider()
                profile = await doc_svc.get_company_profile_for_ai(company_id)
                ctx = _build_company_context(profile)
                ai_resp = await ai_provider.generate(
                    [{"role": "user", "content": batch_prompt}],
                    current_state,
                    company_context=ctx,
                )
                batch_reply = ai_resp.assistant_reply
            else:
                batch_reply = f"Uploaded {file_count} files."
                if errors:
                    batch_reply += f" Could not process: {', '.join(errors)}."

            assistant_msg = await doc_svc.add_message(thread_id, "assistant", batch_reply)

            response = SendMessageResponse(
                user_message=_row_to_message(user_msg),
                assistant_message=_row_to_message(assistant_msg),
                current_state=current_state,
                version=current_version,
                task_type=_infer_skill_from_state(current_state),
                pdf_url=None,
                token_usage=None,
            )
            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})
        except Exception as e:
            logger.error("Resume batch failed for thread %s: %s", thread_id, e, exc_info=True)
            yield _sse_data({"type": "error", "message": "Failed to process resumes. Please try again."})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/threads/{thread_id}/resume/send-interviews")
async def send_resume_batch_interviews(
    thread_id: UUID,
    body: SendInterviewsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create screening interviews for selected candidates and send invite emails."""
    import secrets as _secrets
    from app.core.services.email import EmailService

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    current_state = thread.get("current_state") or {}
    candidates = current_state.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates in this batch")

    async with get_connection() as conn:
        company_row = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
    company_name = company_row["name"] if company_row else "the company"

    position_title = body.position_title or "Open Position"
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
            failed.append({"id": cid, "error": "Candidate not found in batch"})
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
                "resume_batch_thread_id": str(thread_id),
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
            logger.error("Failed to create interview for candidate %s: %s", cid, e, exc_info=True)
            failed.append({"id": cid, "error": str(e)})

    if sent:
        await doc_svc.apply_update(thread_id, {"candidates": updated_candidates})

    return {"sent": sent, "failed": failed}

@router.post("/threads/{thread_id}/resume/sync-interviews")
async def sync_resume_batch_interviews(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Sync interview statuses back into the resume batch candidates."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    current_state = thread.get("current_state") or {}
    candidates = current_state.get("candidates") or []

    # Collect interview IDs from candidates
    interview_ids = [c.get("interview_id") for c in candidates if c.get("interview_id")]
    if not interview_ids:
        return {"updated": 0}

    # Fetch interview statuses + screening analysis
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

        # Extract score from screening_analysis if available
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
        await doc_svc.apply_update(thread_id, {"candidates": updated_candidates})

    return {"updated": updated}

INVENTORY_EXTRACT_PROMPT = """Extract inventory line items from this document (vendor invoice, inventory count, or order sheet).
Return ONLY valid JSON — an array of items:
[{"product_name":"...","sku":"...","category":"protein|produce|dairy|dry_goods|beverages|supplies|equipment|other","quantity":0,"unit":"case|lb|each|gal|oz|bag|box|doz|pack","unit_cost":0.00,"total_cost":0.00,"vendor":"..."}]

If this is a vendor invoice, extract the vendor name from the header or line items.
If quantities or costs are missing, use null. Compute total_cost as quantity * unit_cost when possible.

Document text:
---
%s
---"""

@router.post("/threads/{thread_id}/inventory/upload")
async def upload_thread_inventory(
    thread_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload invoices/spreadsheets, extract structured inventory items, and stream batch insights."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread["status"] in ("finalized", "archived"):
        raise HTTPException(status_code=400, detail=f"Cannot upload to a {thread['status']} thread")

    if current_user.role != "admin":
        await token_budget_service.check_token_budget(company_id)

    parsed_files: list[tuple[str, bytes, str]] = []
    for f in files:
        fname = f.filename or "document"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in INVENTORY_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {fname}")
        raw = await f.read()
        if len(raw) > INVENTORY_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"File exceeds 15 MB limit: {fname}")
        parsed_files.append((fname, raw, f.content_type or "application/octet-stream"))

    file_count = len(parsed_files)
    filenames = [pf[0] for pf in parsed_files]
    user_content = f"[Inventory batch: {file_count} file{'s' if file_count != 1 else ''}]\n" + "\n".join(f"- {fn}" for fn in filenames)
    user_msg = await doc_svc.add_message(thread_id, "user", user_content)

    async def event_stream():
        try:
            from google import genai as _genai
            from google.genai import types as _types

            api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
            client = _genai.Client(api_key=api_key)
            extract_model = "gemini-3.1-flash-lite"

            parser = ERDocumentParser()
            existing_items = list((thread.get("current_state") or {}).get("inventory_items") or [])
            new_items = []

            for idx, (fname, raw, ct) in enumerate(parsed_files, 1):
                yield _sse_data({"type": "status", "message": f"Reading {fname} ({idx}/{file_count})..."})

                # Extract text — CSV/TXT read directly, PDF/DOCX via parser
                ext = os.path.splitext(fname)[1].lower()
                try:
                    if ext == ".csv":
                        text = raw.decode("utf-8", errors="replace")
                    elif ext in (".xlsx", ".xls"):
                        # Excel files are binary — extract cell values via openpyxl
                        import io as _io
                        try:
                            import openpyxl
                            wb = openpyxl.load_workbook(_io.BytesIO(raw), read_only=True, data_only=True)
                            rows = []
                            ws = wb.active
                            for row in ws.iter_rows(values_only=True):
                                rows.append(",".join(str(c) if c is not None else "" for c in row))
                            wb.close()
                            text = "\n".join(rows)
                        except ImportError:
                            logger.warning("openpyxl not installed — cannot read Excel files")
                            yield _sse_data({"type": "status", "message": f"Cannot read Excel files (openpyxl not installed), skipping {fname}..."})
                            continue
                    else:
                        text, _ = parser.extract_text_from_bytes(raw, fname)
                except Exception:
                    yield _sse_data({"type": "status", "message": f"Could not read {fname}, skipping..."})
                    continue

                if not text or len(text.strip()) < 10:
                    continue

                # Upload to S3
                try:
                    await get_storage().upload_file(
                        raw, fname,
                        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "inventory"),
                        content_type=ct,
                    )
                except Exception:
                    pass

                # AI extraction
                yield _sse_data({"type": "status", "message": f"Extracting items from {fname} ({idx}/{file_count})..."})
                capped = text[:INVENTORY_TEXT_CAP]

                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            lambda t=capped: client.models.generate_content(
                                model=extract_model,
                                contents=[_types.Content(role="user", parts=[_types.Part.from_text(text=INVENTORY_EXTRACT_PROMPT % t)])],
                                config=_types.GenerateContentConfig(temperature=0.1),
                            )
                        ),
                        timeout=60,
                    )
                    raw_json = (resp.text or "").strip()
                    if raw_json.startswith("```"):
                        raw_json = raw_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    items_data = json.loads(raw_json)
                    if not isinstance(items_data, list):
                        items_data = [items_data]

                    for item in items_data:
                        new_items.append({
                            "id": os.urandom(8).hex(),
                            "filename": fname,
                            "product_name": item.get("product_name"),
                            "sku": item.get("sku"),
                            "category": item.get("category"),
                            "quantity": item.get("quantity"),
                            "unit": item.get("unit"),
                            "unit_cost": item.get("unit_cost"),
                            "total_cost": item.get("total_cost"),
                            "vendor": item.get("vendor"),
                            "status": "extracted",
                        })
                    yield _sse_data({"type": "status", "message": f"Extracted {len(items_data)} items from {fname}"})
                except Exception as e:
                    logger.warning("Inventory AI extraction failed for %s: %s", fname, e)
                    yield _sse_data({"type": "status", "message": f"Could not extract items from {fname}"})

            # Accumulate
            all_items = existing_items + new_items
            total_cost = sum(i.get("total_cost") or 0 for i in all_items)
            vendors = sorted(set(i.get("vendor") for i in all_items if i.get("vendor")))

            result = await doc_svc.apply_update(thread_id, {
                "inventory_items": all_items,
                "inventory_status": "ready",
                "inventory_total_count": len(all_items),
                "inventory_total_cost": round(total_cost, 2),
                "inventory_vendors": vendors,
            })
            current_state = result["current_state"]
            current_version = result["version"]

            # Batch summary
            yield _sse_data({"type": "status", "message": "Generating inventory insights..."})
            if new_items:
                # Build vendor breakdown
                vendor_totals: dict[str, float] = {}
                cat_totals: dict[str, int] = {}
                for i in new_items:
                    v = i.get("vendor") or "Unknown"
                    vendor_totals[v] = vendor_totals.get(v, 0) + (i.get("total_cost") or 0)
                    c = i.get("category") or "other"
                    cat_totals[c] = cat_totals.get(c, 0) + 1

                vendor_lines = ", ".join(f"{v}: ${t:,.2f}" for v, t in sorted(vendor_totals.items(), key=lambda x: -x[1]))
                cat_lines = ", ".join(f"{c}: {n}" for c, n in sorted(cat_totals.items(), key=lambda x: -x[1]))
                new_cost = sum(i.get("total_cost") or 0 for i in new_items)

                batch_reply = (
                    f"**Processed {len(new_items)} items** from {file_count} file{'s' if file_count != 1 else ''}\n\n"
                    f"**Total cost:** ${new_cost:,.2f}\n\n"
                    f"**By vendor:** {vendor_lines}\n\n"
                    f"**By category:** {cat_lines}"
                )
                if len(all_items) > len(new_items):
                    batch_reply += f"\n\n*Running total: {len(all_items)} items, ${total_cost:,.2f} across all uploads.*"
            else:
                batch_reply = f"Processed {file_count} file{'s' if file_count != 1 else ''} but could not extract any line items."

            assistant_msg = await doc_svc.add_message(thread_id, "assistant", batch_reply)

            response = SendMessageResponse(
                user_message=_row_to_message(user_msg),
                assistant_message=_row_to_message(assistant_msg),
                current_state=current_state,
                version=current_version,
                task_type=_infer_skill_from_state(current_state),
                pdf_url=None,
                token_usage=None,
            )
            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})
        except Exception as e:
            logger.error("Inventory batch failed for thread %s: %s", thread_id, e, exc_info=True)
            yield _sse_data({"type": "error", "message": "Failed to process inventory files. Please try again."})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
