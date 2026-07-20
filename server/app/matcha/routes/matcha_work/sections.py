"""Project sections (CRUD, reorder, revisions, email, comments), AI diagram
editing, and the legacy thread-scoped project endpoints kept for backward
compatibility (init/sections/images under /threads/{id}/project/*).

Holds two order-sensitive route pairs -- in each family, the `reorder`
static route must stay registered before the `{section_id}` param route
(Starlette matches in registration order). Both pairs are kept in their
original relative order below; do not reorder within this file.

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import logging
import os
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.models.auth import CurrentUser
from app.core.services.email import get_email_service
from app.core.services.storage import get_storage
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work.pdf_export import _render_project_pdf
from app.matcha.routes.matcha_work._shared import _strip_markdown, _verify_project_access
from app.matcha.services import matcha_work_document as doc_svc

logger = logging.getLogger(__name__)
router = APIRouter()

async def _convert_svgs_to_images(content: str, company_id, project_id) -> tuple[str, list[dict]]:
    """Convert inline SVGs to uploaded <img> tags. Returns (html, diagram_data_list)."""
    import re as _re

    storage = get_storage()
    prefix = f"matcha-work/{company_id}/{project_id}/diagrams"
    counter = 0
    diagrams: list[dict] = []

    async def _upload_svg(svg_str: str) -> str:
        nonlocal counter
        counter += 1
        svg_bytes = svg_str.encode("utf-8")
        url = await storage.upload_file(svg_bytes, f"diagram-{counter}.svg", prefix=prefix, content_type="image/svg+xml")
        diagrams.append({"svg_source": svg_str, "storage_url": url, "created_from": "ai_generation"})
        return f'<img src="{url}" alt="Diagram" data-diagram-index="{len(diagrams) - 1}" style="max-width:100%;margin:8px 0;" />'

    result = content

    # 1. Fenced code blocks: ```svg ... ``` or ```xml ... ``` containing <svg
    fenced_pattern = _re.compile(r'```(?:svg|xml)\s*\n([\s\S]*?)\n```', _re.IGNORECASE)
    fenced_matches = list(fenced_pattern.finditer(result))
    for match in reversed(fenced_matches):
        inner = match.group(1).strip()
        if '<svg' in inner.lower():
            img_tag = await _upload_svg(inner)
            result = result[:match.start()] + img_tag + result[match.end():]

    # 2. Inline <svg>...</svg> blocks
    svg_pattern = _re.compile(r'<svg[\s\S]*?</svg>', _re.IGNORECASE)
    svg_matches = list(svg_pattern.finditer(result))
    for match in reversed(svg_matches):
        img_tag = await _upload_svg(match.group(0))
        result = result[:match.start()] + img_tag + result[match.end():]

    # 3. Markdown image references to data URIs: ![...](data:image/svg+xml;base64,...)
    data_uri_pattern = _re.compile(r'!\[([^\]]*)\]\(data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)\)')
    data_matches = list(data_uri_pattern.finditer(result))
    for match in reversed(data_matches):
        import base64
        try:
            svg_str = base64.b64decode(match.group(2)).decode("utf-8")
            img_tag = await _upload_svg(svg_str)
            result = result[:match.start()] + img_tag + result[match.end():]
        except Exception:
            pass

    return result, diagrams

@router.post("/projects/{project_id}/sections")
async def add_project_section_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a section to the project."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    company_id = await get_client_company_id(current_user)
    raw_content = body.get("content", "")

    # Convert inline SVGs to uploaded images so TipTap can render them
    raw_content, diagrams = await _convert_svgs_to_images(raw_content, company_id, project_id)

    section_data = {**body, "content": raw_content}
    if diagrams:
        section_data["diagram_data"] = diagrams
    return await proj_svc.add_section(project_id, section_data)

@router.put("/projects/{project_id}/sections/reorder")
async def reorder_project_sections_endpoint(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reorder project sections."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.reorder_sections(project_id, body.get("section_ids", []))

@router.put("/projects/{project_id}/sections/{section_id}")
async def update_project_section_endpoint(
    project_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a project section."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    actor_name = await proj_svc._resolve_actor_name(current_user.id)
    return await proj_svc.update_section(
        project_id, section_id, body,
        actor_user_id=current_user.id, actor_name=actor_name,
    )

@router.delete("/projects/{project_id}/sections/{section_id}")
async def delete_project_section_endpoint(
    project_id: UUID,
    section_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a project section."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.delete_section(project_id, section_id)

@router.post("/projects/{project_id}/sections/{section_id}/accept_revision")
async def accept_project_section_revision_endpoint(
    project_id: UUID,
    section_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Promote a section's pending AI revision into its live content."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    actor_name = await proj_svc._resolve_actor_name(current_user.id)
    return await proj_svc.accept_section_revision(
        project_id, section_id,
        actor_user_id=current_user.id, actor_name=actor_name,
    )

@router.post("/projects/{project_id}/sections/{section_id}/reject_revision")
async def reject_project_section_revision_endpoint(
    project_id: UUID,
    section_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Discard a section's pending AI revision, leaving live content untouched."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.reject_section_revision(project_id, section_id)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@router.post("/projects/{project_id}/sections/{section_id}/email")
async def email_project_section_endpoint(
    project_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Email a single note as a PDF attachment.

    Body: {recipients: [email,…], subject?: str, message?: str}.
    Recipients are a mix of project collaborators (picked client-side) and
    free-text addresses — both arrive here as plain email strings. The note
    markdown is rendered to PDF via the shared project-PDF path (wrapping the
    one note as a single-section document) and attached. Sends immediately;
    scheduling is intentionally out of scope for v1.
    """
    import base64 as _b64
    import html

    project, _role = await _verify_project_access(project_id, current_user)

    section = next((s for s in (project.get("sections") or []) if s.get("id") == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail="Note not found")

    raw_recipients = body.get("recipients") or []
    if not isinstance(raw_recipients, list):
        raise HTTPException(status_code=400, detail="recipients must be a list")
    # Normalize + validate + dedupe (preserve order).
    seen: set[str] = set()
    recipients: list[str] = []
    for r in raw_recipients:
        email = str(r or "").strip().lower()
        if not email:
            continue
        if not _EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail=f"Invalid email address: {r}")
        if email not in seen:
            seen.add(email)
            recipients.append(email)
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")

    note_title = (section.get("title") or "").strip() or "Untitled note"
    subject = (str(body.get("subject") or "").strip()) or note_title
    cover_message = str(body.get("message") or "").strip()

    # Render the note as a one-section document so it reuses the project PDF
    # path (markdown → HTML, inlined images, WeasyPrint). h1 = note title.
    pdf_doc = {
        "id": str(project_id),
        "title": note_title,
        "sections": [{"content": section.get("content", "") or ""}],
    }
    pdf_bytes = await _render_project_pdf(pdf_doc)
    pdf_b64 = _b64.b64encode(pdf_bytes).decode()

    def _safe_filename(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", name).strip() or "note"
        return f"{cleaned[:80]}.pdf"

    filename = _safe_filename(note_title)
    sender_name = await _resolve_actor_name_safe(current_user.id)

    html_body = f"""
    <div style="font-family: -apple-system, Segoe UI, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a;">
        <p style="font-size: 14px;">{html.escape(sender_name)} shared a note with you from Matcha Work:
        <strong>{html.escape(note_title)}</strong>.</p>
        {f'<p style="font-size: 14px; white-space: pre-wrap; color: #334155;">{html.escape(cover_message)}</p>' if cover_message else ''}
        <p style="font-size: 13px; color: #64748b;">The full note is attached as a PDF.</p>
    </div>
    """
    text_body = (
        f"{sender_name} shared a note with you from Matcha Work: {note_title}.\n\n"
        + (f"{cover_message}\n\n" if cover_message else "")
        + "The full note is attached as a PDF."
    )

    email_svc = get_email_service()
    if not email_svc.is_configured():
        raise HTTPException(status_code=503, detail="Email is not configured on the server.")

    # Send via the Gmail→MailerSend fallback so it uses whichever backend is
    # live (dev typically has MailerSend but no Gmail token). Both carry the
    # PDF attachment.
    attachment = {"filename": filename, "content": pdf_b64, "disposition": "attachment"}
    sent: list[str] = []
    failed: list[str] = []
    for email in recipients:
        try:
            ok = await email_svc.send_email_with_fallback(
                to_email=email,
                to_name=email.split("@")[0],
                subject=subject,
                html_content=html_body,
                text_content=text_body,
                attachments=[attachment],
            )
        except Exception as exc:
            logger.warning("Failed to email note %s to %s: %s", section_id, email, exc)
            ok = False
        (sent if ok else failed).append(email)

    return {"ok": len(sent) > 0, "sent": sent, "failed": failed}

async def _resolve_actor_name_safe(user_id) -> str:
    """Best-effort display name for the current user; falls back to 'Someone'."""
    try:
        from app.matcha.services import project_service as proj_svc
        name = await proj_svc._resolve_actor_name(user_id)
        return name or "Someone"
    except Exception:
        return "Someone"

@router.get("/projects/{project_id}/sections/{section_id}/comments")
async def list_section_comments_endpoint(
    project_id: UUID,
    section_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Comments on a single note, oldest first."""
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import project_comment_service as cmt_svc
    return await cmt_svc.list_section_comments(project_id, section_id)

@router.post("/projects/{project_id}/sections/{section_id}/comments")
async def create_section_comment_endpoint(
    project_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a comment to a note. Body: {content, reply_to_comment_id?,
    anchor_start?, anchor_end?, quoted_text?}. The anchor fields attach the
    comment to a highlighted text range (omit them for a whole-note comment)."""
    project, _role = await _verify_project_access(project_id, current_user)

    content = str(body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    if len(content) > 10_000:
        raise HTTPException(status_code=400, detail="Comment is too long")

    reply_raw = body.get("reply_to_comment_id")
    try:
        reply_to = UUID(reply_raw) if reply_raw else None
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid reply_to_comment_id")

    # Optional anchor (highlight range). Both ends must be present, ordered,
    # and non-negative to count — otherwise treated as a general comment.
    anchor_start = anchor_end = None
    quoted_text = None
    try:
        a_raw = body.get("anchor_start")
        b_raw = body.get("anchor_end")
        if a_raw is not None and b_raw is not None:
            a, b = int(a_raw), int(b_raw)
            if a >= 0 and b > a:
                anchor_start, anchor_end = a, b
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid anchor offsets")
    if anchor_start is not None:
        qt = body.get("quoted_text")
        if isinstance(qt, str) and qt:
            quoted_text = qt[:500]

    company_id = await get_client_company_id(current_user)

    from app.matcha.services import project_comment_service as cmt_svc
    comment = await cmt_svc.create_section_comment(
        project_id=project_id,
        section_id=section_id,
        company_id=company_id,
        user_id=current_user.id,
        content=content,
        reply_to_comment_id=reply_to,
        anchor_start=anchor_start,
        anchor_end=anchor_end,
        quoted_text=quoted_text,
    )

    # Notify the note's last editor and, on a reply, the parent comment's
    # author — excluding the commenter themselves. Best-effort.
    try:
        section = next(
            (s for s in (project.get("sections") or []) if s.get("id") == section_id),
            None,
        )
        note_title = (section.get("title") if section else None) or "a note"
        targets: set = set()
        if section and section.get("last_edited_by"):
            targets.add(str(section["last_edited_by"]))
        if reply_to:
            parent_author = await cmt_svc.get_comment_author(reply_to)
            if parent_author:
                targets.add(str(parent_author))
        targets.discard(str(current_user.id))
        if targets and company_id:
            from app.matcha.services import notification_service as notif_svc
            actor = await _resolve_actor_name_safe(current_user.id)
            for uid in targets:
                await notif_svc.create_notification(
                    user_id=UUID(uid),
                    company_id=company_id,
                    type="section_comment",
                    title=f"New comment on {note_title}",
                    body=f"{actor}: {content[:140]}",
                    link=f"/work?project={project_id}",
                    metadata={"project_id": str(project_id), "section_id": section_id},
                )
    except Exception as exc:
        logger.warning("Failed to send section-comment notifications: %s", exc)

    return comment

@router.delete("/projects/{project_id}/sections/{section_id}/comments/{comment_id}")
async def delete_section_comment_endpoint(
    project_id: UUID,
    section_id: str,
    comment_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete one of your own comments."""
    await _verify_project_access(project_id, current_user)
    from app.matcha.services import project_comment_service as cmt_svc
    ok = await cmt_svc.delete_section_comment(comment_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"ok": True}

@router.patch("/projects/{project_id}/sections/{section_id}/comments/{comment_id}/resolve")
async def resolve_section_comment_endpoint(
    project_id: UUID,
    section_id: str,
    comment_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resolve / unresolve a comment. Body: {resolved: bool}. Any collaborator
    with project access may resolve (mirrors doc-comment conventions)."""
    await _verify_project_access(project_id, current_user)
    resolved = bool(body.get("resolved", True))
    from app.matcha.services import project_comment_service as cmt_svc
    comment = await cmt_svc.set_section_comment_resolved(comment_id, project_id, resolved)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment

@router.post("/projects/{project_id}/sections/{section_id}/edit-diagram")
async def edit_diagram_ai(
    project_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Use AI to modify a diagram based on a natural language instruction."""
    from app.matcha.services import project_service as proj_svc

    await _verify_project_access(project_id, current_user)
    company_id = await get_client_company_id(current_user)
    instruction = body.get("instruction", "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Instruction is required")

    project = await proj_svc.get_project(project_id, company_id)
    section = next((s for s in project.get("sections", []) if s.get("id") == section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    diagram_data = section.get("diagram_data")
    if not diagram_data or not isinstance(diagram_data, list) or len(diagram_data) == 0:
        raise HTTPException(status_code=400, detail="No diagram data found in this section")

    svg_source = diagram_data[0].get("svg_source", "")
    if not svg_source:
        raise HTTPException(status_code=400, detail="No SVG source available for editing")

    # Optional region selection (percentages of image dimensions)
    region = body.get("region")  # { x, y, width, height } in %

    # Call Gemini to modify the SVG
    from app.core.services.genai_client import get_genai_client
    import re as _re_vb
    from app.config import get_settings
    settings = get_settings()

    client = get_genai_client(api_key=settings.gemini_api_key)

    # Build prompt — region-constrained or full edit
    if region and isinstance(region, dict):
        # Parse viewBox to convert % region to absolute SVG coordinates
        vb_match = _re_vb.search(r'viewBox=["\']([^"\']+)["\']', svg_source)
        if vb_match:
            vb_parts = vb_match.group(1).split()
            vb_x, vb_y, vb_w, vb_h = float(vb_parts[0]), float(vb_parts[1]), float(vb_parts[2]), float(vb_parts[3])
        else:
            w_match = _re_vb.search(r'\bwidth=["\'](\d+)', svg_source)
            h_match = _re_vb.search(r'\bheight=["\'](\d+)', svg_source)
            vb_x, vb_y = 0.0, 0.0
            vb_w = float(w_match.group(1)) if w_match else 480.0
            vb_h = float(h_match.group(1)) if h_match else 300.0

        rx, ry, rw, rh = float(region["x"]), float(region["y"]), float(region["width"]), float(region["height"])
        abs_x1 = vb_x + (rx / 100) * vb_w
        abs_y1 = vb_y + (ry / 100) * vb_h
        abs_x2 = vb_x + ((rx + rw) / 100) * vb_w
        abs_y2 = vb_y + ((ry + rh) / 100) * vb_h

        prompt = f"""You are an SVG diagram editor. Here is an SVG diagram:

{svg_source}

IMPORTANT CONSTRAINT — REGION-ONLY EDIT:
The user has selected a specific region of the diagram for editing.
The selected region in SVG coordinates is: top-left ({abs_x1:.1f}, {abs_y1:.1f}) to bottom-right ({abs_x2:.1f}, {abs_y2:.1f}).

Rules:
1. ONLY modify SVG elements that are within or overlap this bounding box.
2. DO NOT move, resize, restyle, recolor, or delete ANY element outside this region.
3. DO NOT change the viewBox, overall SVG dimensions, or add new elements outside this region.
4. Elements partially inside the region may be modified, but preserve their parts outside the region as much as possible.
5. The rest of the SVG MUST remain EXACTLY as-is, character for character.

User's instruction (applies ONLY to the selected region):
{instruction}

Return ONLY the modified SVG code, nothing else. No markdown fences, no explanation. Just the raw <svg>...</svg> content."""
    else:
        prompt = f"""You are an SVG diagram editor. Here is an SVG diagram:

{svg_source}

Modify this SVG according to the following instruction:
{instruction}

Return ONLY the modified SVG code, nothing else. No markdown fences, no explanation. Just the raw <svg>...</svg> content."""

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        new_svg = response.text.strip()
        # Clean up any markdown fences
        if new_svg.startswith("```"):
            new_svg = new_svg.split("\n", 1)[1] if "\n" in new_svg else new_svg
        if new_svg.endswith("```"):
            new_svg = new_svg.rsplit("```", 1)[0].strip()
        if not new_svg.startswith("<svg"):
            raise HTTPException(status_code=500, detail="AI did not return valid SVG")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI diagram edit failed: {e}")

    # Upload new SVG
    storage = get_storage()
    prefix = f"matcha-work/{company_id}/{project_id}/diagrams"
    svg_bytes = new_svg.encode("utf-8")
    new_url = await storage.upload_file(svg_bytes, f"diagram-edited-{section_id[:8]}.svg", prefix=prefix, content_type="image/svg+xml")

    # Update section content — replace old img with new
    import re as _re
    new_img = f'<img src="{new_url}" alt="Diagram" data-diagram-index="0" style="max-width:100%;margin:8px 0;" />'
    old_content = section.get("content", "")
    updated_content = _re.sub(r'<img[^>]*data-diagram-index[^>]*/>', new_img, old_content)
    if updated_content == old_content:
        # Fallback: replace first img with diagram alt
        updated_content = _re.sub(r'<img[^>]*alt="Diagram"[^>]*/>', new_img, old_content, count=1)
    if updated_content == old_content:
        updated_content = old_content + new_img

    edit_source = "ai_region_edit" if (region and isinstance(region, dict)) else "ai_edit"
    new_diagram_data = [{"svg_source": new_svg, "storage_url": new_url, "created_from": edit_source}]
    await proj_svc.update_section(project_id, section_id, {
        "content": updated_content,
        "diagram_data": new_diagram_data,
    })

    updated = await proj_svc.get_project(project_id, company_id)
    return updated

@router.post("/projects/{project_id}/sections/{section_id}/edit-diagram-text")
async def edit_diagram_text(
    project_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Edit text labels in a diagram by direct string replacement."""
    from app.matcha.services import project_service as proj_svc

    await _verify_project_access(project_id, current_user)
    company_id = await get_client_company_id(current_user)
    edits = body.get("edits", [])
    if not edits:
        raise HTTPException(status_code=400, detail="No edits provided")

    project = await proj_svc.get_project(project_id, company_id)
    section = next((s for s in project.get("sections", []) if s.get("id") == section_id), None)
    if not section or not section.get("diagram_data"):
        raise HTTPException(status_code=404, detail="Section or diagram not found")

    svg_source = section["diagram_data"][0].get("svg_source", "")
    if not svg_source:
        raise HTTPException(status_code=400, detail="No SVG source")

    new_svg = svg_source
    for edit in edits:
        old_text = edit.get("old_text", "")
        new_text = edit.get("new_text", "")
        if old_text:
            new_svg = new_svg.replace(f">{old_text}<", f">{new_text}<")

    storage = get_storage()
    prefix = f"matcha-work/{company_id}/{project_id}/diagrams"
    new_url = await storage.upload_file(new_svg.encode("utf-8"), f"diagram-textedit-{section_id[:8]}.svg", prefix=prefix, content_type="image/svg+xml")

    import re as _re
    new_img = f'<img src="{new_url}" alt="Diagram" data-diagram-index="0" style="max-width:100%;margin:8px 0;" />'
    old_content = section.get("content", "")
    updated_content = _re.sub(r'<img[^>]*alt="Diagram"[^>]*/>', new_img, old_content, count=1)

    await proj_svc.update_section(project_id, section_id, {
        "content": updated_content,
        "diagram_data": [{"svg_source": new_svg, "storage_url": new_url, "created_from": "text_edit"}],
    })
    return await proj_svc.get_project(project_id, company_id)

@router.post("/projects/{project_id}/sections/{section_id}/save-diagram")
async def save_diagram(
    project_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Save a diagram from the visual editor (Excalidraw SVG export)."""
    from app.matcha.services import project_service as proj_svc

    await _verify_project_access(project_id, current_user)
    company_id = await get_client_company_id(current_user)
    svg = body.get("svg", "").strip()
    if not svg or "<svg" not in svg.lower():
        raise HTTPException(status_code=400, detail="Invalid SVG")

    storage = get_storage()
    prefix = f"matcha-work/{company_id}/{project_id}/diagrams"
    new_url = await storage.upload_file(svg.encode("utf-8"), f"diagram-visual-{section_id[:8]}.svg", prefix=prefix, content_type="image/svg+xml")

    import re as _re
    new_img = f'<img src="{new_url}" alt="Diagram" data-diagram-index="0" style="max-width:100%;margin:8px 0;" />'

    project = await proj_svc.get_project(project_id, company_id)
    section = next((s for s in project.get("sections", []) if s.get("id") == section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    old_content = section.get("content", "")
    updated_content = _re.sub(r'<img[^>]*alt="Diagram"[^>]*/>', new_img, old_content, count=1)

    await proj_svc.update_section(project_id, section_id, {
        "content": updated_content,
        "diagram_data": [{"svg_source": svg, "storage_url": new_url, "created_from": "visual_editor"}],
    })
    return await proj_svc.get_project(project_id, company_id)

@router.post("/threads/{thread_id}/project/init")
async def init_project(
    thread_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Initialize a project document with a title."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    result = await doc_svc.apply_update(thread_id, {
        "project_title": body.get("title", "Untitled Project"),
        "project_sections": (thread.get("current_state") or {}).get("project_sections") or [],
        "project_status": "drafting",
    })
    return {"current_state": result["current_state"], "version": result["version"]}

@router.post("/threads/{thread_id}/project/sections")
async def add_project_section(
    thread_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a section to the project."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    current_state = thread.get("current_state") or {}
    sections = list(current_state.get("project_sections") or [])

    raw_content = body.get("content", "")
    # Strip markdown when content comes from chat AI responses
    if body.get("source_message_id"):
        raw_content = _strip_markdown(raw_content)

    new_section = {
        "id": os.urandom(8).hex(),
        "title": body.get("title"),
        "content": raw_content,
        "source_message_id": body.get("source_message_id"),
    }
    sections.append(new_section)

    # Auto-init project if not already
    updates = {"project_sections": sections}
    if not current_state.get("project_title"):
        updates["project_title"] = "Untitled Project"
        updates["project_status"] = "drafting"

    result = await doc_svc.apply_update(thread_id, updates)
    return {"section": new_section, "current_state": result["current_state"], "version": result["version"]}

@router.put("/threads/{thread_id}/project/sections/reorder")
async def reorder_project_sections(
    thread_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reorder project sections by providing an ordered list of section IDs."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    sections = list((thread.get("current_state") or {}).get("project_sections") or [])
    section_map = {s["id"]: s for s in sections}
    ordered_ids = body.get("section_ids", [])

    reordered = [section_map[sid] for sid in ordered_ids if sid in section_map]
    # Append any sections not in the ordered list
    seen = set(ordered_ids)
    for s in sections:
        if s["id"] not in seen:
            reordered.append(s)

    result = await doc_svc.apply_update(thread_id, {"project_sections": reordered})
    return {"current_state": result["current_state"], "version": result["version"]}

@router.put("/threads/{thread_id}/project/sections/{section_id}")
async def update_project_section(
    thread_id: UUID,
    section_id: str,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a project section's title or content."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    sections = list((thread.get("current_state") or {}).get("project_sections") or [])
    found = False
    for i, s in enumerate(sections):
        if s.get("id") == section_id:
            if "title" in body:
                sections[i] = {**s, "title": body["title"]}
            if "content" in body:
                sections[i] = {**sections[i], "content": body["content"]}
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Section not found")

    result = await doc_svc.apply_update(thread_id, {"project_sections": sections})
    return {"current_state": result["current_state"], "version": result["version"]}

@router.delete("/threads/{thread_id}/project/sections/{section_id}")
async def delete_project_section(
    thread_id: UUID,
    section_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a section from the project."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    sections = list((thread.get("current_state") or {}).get("project_sections") or [])
    sections = [s for s in sections if s.get("id") != section_id]

    result = await doc_svc.apply_update(thread_id, {"project_sections": sections})
    return {"current_state": result["current_state"], "version": result["version"]}

@router.post("/threads/{thread_id}/project/images")
async def upload_project_image(
    thread_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload an image for use in a project section. Returns the URL to embed as markdown."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image exceeds 10 MB limit")

    filename = file.filename or "image.png"
    url = await get_storage().upload_file(
        content,
        filename,
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "project-images"),
        content_type=file.content_type,
    )
    return {"url": url, "filename": filename}
