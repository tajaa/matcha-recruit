"""AI-turn helpers: field validation, phantom-claim scrubbing, offer-draft
detection, onboarding provisioning, slide/blog/recruiting context injection,
and _apply_ai_updates_and_operations (the core AI-response-to-DB-write step).

No routes in this module. Extracted from the original flat matcha_work.py
during the package split (2026-07-03). See matcha_work/CLAUDE.md.
"""
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.core.services.email import get_email_service
from app.core.services.handbook_service import HandbookService
from app.database import get_connection
from app.matcha.models.matcha_work import (
    HandbookDocument,
    InventoryDocument,
    OfferLetterDocument,
    OnboardingDocument,
    PolicyDocument,
    PresentationDocument,
    ProjectDocument,
    ResumeBatchDocument,
    ReviewDocument,
    WorkbookDocument,
)
from app.matcha.routes.matcha_work._shared import _json_object
from app.matcha.services import matcha_work_document as doc_svc
from app.matcha.services.matcha_work_ai import _infer_skill_from_state
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)

logger = logging.getLogger(__name__)

VALID_OFFER_LETTER_FIELDS = set(OfferLetterDocument.model_fields.keys()) - {"company_logo_url"}

VALID_REVIEW_FIELDS = set(ReviewDocument.model_fields.keys())

VALID_WORKBOOK_FIELDS = set(WorkbookDocument.model_fields.keys()) - {"images"}

VALID_ONBOARDING_FIELDS = set(OnboardingDocument.model_fields.keys())

VALID_PRESENTATION_FIELDS = set(PresentationDocument.model_fields.keys()) - {"cover_image_url"}

HANDBOOK_UPLOAD_MANAGED_FIELDS = {
    "handbook_source_type",
    "handbook_upload_status",
    "handbook_uploaded_file_url",
    "handbook_uploaded_filename",
    "handbook_blocking_error",
    "handbook_review_locations",
    "handbook_red_flags",
    "handbook_green_flags",
    "handbook_jurisdiction_summaries",
    "handbook_analysis_generated_at",
    "handbook_strength_score",
    "handbook_strength_label",
    "handbook_analysis_progress",
    "handbook_total_red_flag_count",
}

VALID_HANDBOOK_FIELDS = set(HandbookDocument.model_fields.keys()) - HANDBOOK_UPLOAD_MANAGED_FIELDS

VALID_POLICY_FIELDS = set(PolicyDocument.model_fields.keys())

VALID_RESUME_BATCH_FIELDS = set(ResumeBatchDocument.model_fields.keys())

VALID_INVENTORY_FIELDS = set(InventoryDocument.model_fields.keys())

VALID_PROJECT_FIELDS = set(ProjectDocument.model_fields.keys())

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

def _validate_updates_for_skill(skill: str, updates: dict) -> dict:
    """Filter AI updates to known fields for the inferred skill."""
    if skill == "offer_letter":
        valid_fields = VALID_OFFER_LETTER_FIELDS
    elif skill == "review":
        valid_fields = VALID_REVIEW_FIELDS
    elif skill == "onboarding":
        valid_fields = VALID_ONBOARDING_FIELDS
    elif skill == "workbook":
        valid_fields = VALID_WORKBOOK_FIELDS
    elif skill == "presentation":
        valid_fields = VALID_PRESENTATION_FIELDS
    elif skill == "handbook":
        valid_fields = VALID_HANDBOOK_FIELDS
    elif skill == "policy":
        valid_fields = VALID_POLICY_FIELDS
    elif skill == "resume_batch":
        valid_fields = VALID_RESUME_BATCH_FIELDS
    elif skill == "inventory":
        valid_fields = VALID_INVENTORY_FIELDS
    elif skill == "project":
        valid_fields = VALID_PROJECT_FIELDS
    elif skill == "blog":
        from app.matcha.services.matcha_work_ai import BLOG_FIELDS as _BLOG_FIELDS
        valid_fields = set(_BLOG_FIELDS)
    else:
        return {}
    return {k: v for k, v in updates.items() if k in valid_fields}

def _append_action_note(reply: str, note: Optional[str]) -> str:
    clean_note = (note or "").strip()
    if not clean_note:
        return reply
    clean_reply = (reply or "").strip()
    if not clean_reply:
        return clean_note
    return f"{clean_reply}\n\n{clean_note}"

_PHANTOM_SURFACE_PHRASES = [
    "project document",
    "project panel",
    "project canvas",
    "draft panel",
    "document panel",
    "separate project",
    "new project",
    "a project for",
    "project for you",
    "project for this",
    "project workspace",
]

_PHANTOM_FALLBACK_REPLY = (
    "This is a plain chat — I can't create projects or documents from here. "
    "If you want me to draft something, just tell me what and I'll write it directly in this chat. "
    "Or create a Project from the + button next to Projects in the sidebar for a persistent document workspace."
)

def _scrub_phantom_surface_claims(reply: str, project_id: Optional[UUID]) -> str:
    """Strip sentences that reference a project surface that doesn't exist.

    Plain threads are just chats (no project attached). The AI keeps
    hallucinating it has created/saved something in a 'project document' /
    'project panel' — none of which exist for a plain thread. Strip any
    sentence containing one of those phrases. If scrubbing leaves nothing,
    return a plain-thread fallback so the user sees something actionable
    instead of the hallucinated claim.

    For threads inside a project, leave replies alone — the project's
    surfaces are real.
    """
    if project_id is not None or not reply:
        return reply
    lower_phrases = [p.lower() for p in _PHANTOM_SURFACE_PHRASES]
    out_lines: list[str] = []
    for line in reply.splitlines():
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = [p for p in parts if not any(ph in p.lower() for ph in lower_phrases)]
        out_lines.append(" ".join(kept))
    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        return _PHANTOM_FALLBACK_REPLY
    # If scrubbing produced a stub (short, no real content left), replace it
    # too. Heuristic: under 40 chars with no alphanumeric draft signal.
    if len(cleaned) < 40 and not re.search(r"[A-Za-z]{5,}.*[A-Za-z]{5,}.*[A-Za-z]{5,}", cleaned):
        return _PHANTOM_FALLBACK_REPLY
    return cleaned

def _extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []
    return doc_svc.normalize_recipient_emails(EMAIL_REGEX.findall(text))

def _looks_like_send_draft_command(content: str) -> bool:
    text = (content or "").lower()
    if not text:
        return False
    has_send = bool(re.search(r"\b(send|email)\b", text))
    has_draft_context = bool(re.search(r"\b(draft|offer(?:\s+letter)?)\b", text))
    has_email = bool(_extract_emails_from_text(content))
    return has_send and has_draft_context and has_email

def _collect_offer_draft_recipients(
    *,
    structured_update: Optional[dict],
    current_state: dict,
    user_message: str,
) -> list[str]:
    collected: list[str] = []

    if isinstance(structured_update, dict):
        raw_recipients = structured_update.get("recipient_emails")
        if isinstance(raw_recipients, list):
            collected.extend(str(v) for v in raw_recipients if str(v).strip())
        elif isinstance(raw_recipients, str) and raw_recipients.strip():
            collected.append(raw_recipients)

        for key in ("candidate_email", "review_recipient_email"):
            raw_email = structured_update.get(key)
            if isinstance(raw_email, str) and raw_email.strip():
                collected.append(raw_email)

    state_recipients = current_state.get("recipient_emails")
    if isinstance(state_recipients, list):
        collected.extend(str(v) for v in state_recipients if str(v).strip())

    candidate_email = current_state.get("candidate_email")
    if isinstance(candidate_email, str) and candidate_email.strip():
        collected.append(candidate_email)

    collected.extend(_extract_emails_from_text(user_message))
    return doc_svc.normalize_recipient_emails(collected)

def _coerce_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default

async def _send_mw_provisioning_email(
    *,
    company_id: UUID,
    personal_email: str,
    employee_name: str,
    work_email: str,
    google_result: dict | None,
    slack_result: dict | None,
) -> None:
    """Send a welcome email with provisioning credentials for Matcha Work onboarding."""
    temp_password: str | None = None
    if google_result:
        temp_password = google_result.get("initial_password")

    slack_invite_link: str | None = None
    slack_workspace_name: str | None = None
    if slack_result:
        for step in slack_result.get("steps") or []:
            resp = step.get("last_response") or {}
            if resp.get("invite_link"):
                slack_invite_link = resp["invite_link"]
                break

    google_succeeded = google_result and google_result.get("status") == "completed"
    slack_succeeded = slack_result and slack_result.get("status") == "completed"

    if not google_succeeded and not slack_succeeded:
        return

    async with get_connection() as conn:
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1", company_id,
        ) or "Your Company"
        if slack_succeeded:
            slack_config_row = await conn.fetchval(
                "SELECT config FROM integration_connections WHERE company_id = $1 AND provider = $2",
                company_id, PROVIDER_SLACK,
            )
            if slack_config_row:
                slack_cfg = json.loads(slack_config_row) if isinstance(slack_config_row, str) else slack_config_row
                slack_workspace_name = slack_cfg.get("slack_team_name")

    email_svc = get_email_service()
    await email_svc.send_provisioning_welcome_email(
        to_email=personal_email,
        to_name=employee_name,
        company_name=company_name,
        work_email=work_email if google_succeeded else None,
        temp_password=temp_password,
        slack_workspace_name=slack_workspace_name,
        slack_invite_link=slack_invite_link,
    )

async def _create_onboarding_employees(
    *,
    company_id: UUID,
    triggered_by: UUID,
    employees: list[dict],
) -> list[dict]:
    """Create employee records and trigger provisioning for each. Returns updated employee dicts."""
    results: list[dict] = []

    async with get_connection() as conn:
        # Pre-fetch integration config once for the company
        google_workspace_auto = False
        slack_auto = False
        try:
            integration_rows = await conn.fetch(
                """
                SELECT provider, config
                FROM integration_connections
                WHERE company_id = $1 AND status = 'connected'
                """,
                company_id,
            )
            for irow in integration_rows:
                cfg = _json_object(irow["config"])
                if irow["provider"] == PROVIDER_GOOGLE_WORKSPACE:
                    google_workspace_auto = _coerce_bool(cfg.get("auto_provision_on_employee_create"), True)
                elif irow["provider"] == PROVIDER_SLACK:
                    slack_auto = _coerce_bool(cfg.get("auto_invite_on_employee_create"), True)
        except Exception:
            logger.exception("Unable to query integration connections for company %s", company_id)

        for emp in employees:
            emp_status = (emp.get("status") or "").strip().lower()
            if emp_status in ("created", "done", "error"):
                results.append(emp)
                continue

            first_name = (emp.get("first_name") or "").strip()
            last_name = (emp.get("last_name") or "").strip()
            work_email = (emp.get("work_email") or "").strip().lower()

            if not first_name or not last_name or not work_email:
                emp["status"] = "error"
                emp["error"] = "Missing required fields: first_name, last_name, work_email"
                results.append(emp)
                continue

            try:
                existing = await conn.fetchval(
                    "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                    company_id, work_email,
                )
                if existing:
                    emp["status"] = "error"
                    emp["error"] = f"Employee with email {work_email} already exists"
                    results.append(emp)
                    continue

                start_date = None
                raw_start = (emp.get("start_date") or "").strip()
                if raw_start:
                    try:
                        start_date = datetime.strptime(raw_start, "%Y-%m-%d").date()
                    except ValueError:
                        pass  # leave as None

                personal_email = (emp.get("personal_email") or "").strip().lower() or None
                address = (emp.get("address") or "").strip() or None

                row = await conn.fetchrow(
                    """
                    INSERT INTO employees (org_id, email, personal_email, first_name, last_name,
                                           work_state, employment_type, start_date, address)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                    """,
                    company_id,
                    work_email,
                    personal_email,
                    first_name,
                    last_name,
                    (emp.get("work_state") or "").strip() or None,
                    (emp.get("employment_type") or "").strip() or None,
                    start_date,
                    address,
                )

                emp["status"] = "created"
                emp["employee_id"] = str(row["id"])
                emp["error"] = None

                # Trigger provisioning
                prov = {}
                google_result: dict | None = None
                slack_result: dict | None = None

                if google_workspace_auto:
                    try:
                        google_result = await start_google_workspace_onboarding(
                            company_id=company_id,
                            employee_id=row["id"],
                            triggered_by=triggered_by,
                            trigger_source="matcha_work_onboarding",
                        )
                        prov["google_workspace"] = "triggered"
                    except Exception as gex:
                        logger.exception("Google Workspace provisioning failed for %s", work_email)
                        prov["google_workspace"] = f"error: {gex}"

                if slack_auto:
                    try:
                        slack_result = await start_slack_onboarding(
                            company_id=company_id,
                            employee_id=row["id"],
                            triggered_by=triggered_by,
                            trigger_source="matcha_work_onboarding",
                        )
                        prov["slack"] = "triggered"
                    except Exception as sex:
                        logger.exception("Slack provisioning failed for %s", work_email)
                        prov["slack"] = f"error: {sex}"

                if prov:
                    emp["provisioning_results"] = prov

                # Send provisioning welcome email
                if personal_email and (google_result or slack_result):
                    try:
                        await _send_mw_provisioning_email(
                            company_id=company_id,
                            personal_email=personal_email,
                            employee_name=f"{first_name} {last_name}".strip(),
                            work_email=work_email,
                            google_result=google_result,
                            slack_result=slack_result,
                        )
                    except Exception:
                        logger.exception("Failed to send provisioning email for %s", work_email)

            except Exception as e:
                logger.exception("Failed to create employee %s %s: %s", first_name, last_name, e)
                emp["status"] = "error"
                emp["error"] = str(e)

            results.append(emp)

    return results

def _inject_slide_context(msg_dicts: list[dict], current_state: dict, slide_index: Optional[int]) -> None:
    """Prepend selected slide content to the last user message so the AI sees what it's editing.

    Modifies msg_dicts in-place. Only the AI-facing message list is changed — the saved
    database message remains the user's original text.
    """
    if slide_index is None or not msg_dicts:
        return

    # Find slides in top-level or under presentation (workbook)
    slides = current_state.get("slides") or []
    if not slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            slides = pres.get("slides") or []

    if not slides or not (0 <= slide_index < len(slides)):
        return

    slide = slides[slide_index]
    if not isinstance(slide, dict):
        return

    total = len(slides)
    title = slide.get("title", "Untitled")
    bullets = slide.get("bullets") or []
    speaker_notes = slide.get("speaker_notes", "")

    context_lines = [
        f"[EDITING Slide {slide_index + 1}/{total}: \"{title}\"]",
        "Below is the slide's CURRENT content. The user's request describes changes they want applied to THIS content.",
        "You MUST modify the slide to reflect their request — do NOT return the current content unchanged.",
        f"- Title: {title}",
        f"- Bullets: {json.dumps(bullets)}",
    ]
    if speaker_notes:
        context_lines.append(f"- Speaker Notes: {speaker_notes}")
    context_lines.append("")
    context_lines.append("Apply the following change:")

    context_block = "\n".join(context_lines)

    # Find last user message and prepend context
    for i in range(len(msg_dicts) - 1, -1, -1):
        if msg_dicts[i]["role"] == "user":
            original = msg_dicts[i]["content"]
            msg_dicts[i] = {
                "role": "user",
                "content": f"{context_block}\n{original}",
            }
            break

def _scope_slide_update(ai_resp, current_state: dict, slide_index: Optional[int]) -> None:
    """When a specific slide was targeted, restrict the AI's update to only that slide.

    The AI is instructed to return the full slides array, but it may inadvertently modify
    other slides or presentation-level fields. This function:
    1) Strips non-slide keys (title, subtitle, theme, etc.) from the update
    2) Merges only the targeted slide from the AI response into the existing slides array
    3) Handles workbook presentations where slides live under presentation.slides
    """
    if slide_index is None:
        return
    if not isinstance(ai_resp.structured_update, dict):
        return

    # Strip non-slide presentation fields — only slide content should change
    for key in ("presentation_title", "subtitle", "theme", "cover_image_url", "generated_at"):
        ai_resp.structured_update.pop(key, None)

    ai_slides = ai_resp.structured_update.get("slides")

    # Determine where current slides live
    current_slides = list(current_state.get("slides") or [])

    # Fallback: workbook presentations store slides under presentation.slides
    if not current_slides:
        pres = current_state.get("presentation")
        if isinstance(pres, dict):
            current_slides = list(pres.get("slides") or [])

    if not isinstance(ai_slides, list) or not current_slides:
        return
    if not (0 <= slide_index < len(ai_slides) and 0 <= slide_index < len(current_slides)):
        return

    merged = list(current_slides)
    merged[slide_index] = ai_slides[slide_index]
    ai_resp.structured_update["slides"] = merged

def _format_blog_mode_state(row) -> str:
    """Return a plain-text block describing the current blog draft (title,
    tone, audience, sections with ids, word counts, etc.). This is passed as
    `blog_mode_state` to the AI provider, which uses a dedicated blog-only
    system prompt — no generic multi-skill prompt and no risk of the AI
    invoking project/workbook/etc skills."""
    project_data = json.loads(row["project_data"]) if isinstance(row["project_data"], str) else (row["project_data"] or {})
    sections = json.loads(row["sections"]) if isinstance(row["sections"], str) else (row["sections"] or [])
    title = row["title"] or "(untitled)"
    slug = project_data.get("slug") or "(auto)"
    tone = project_data.get("tone") or "expert-casual"
    audience = project_data.get("audience") or "(not set — ask the user before drafting)"
    tags = project_data.get("tags") or []
    status = project_data.get("status") or "draft"
    excerpt = project_data.get("excerpt") or "(none)"
    stats = project_data.get("stats") or {}

    section_lines: list[str] = []
    for i, s in enumerate(sections, start=1):
        if not isinstance(s, dict):
            continue
        sid = s.get("id") or "?"
        st = (s.get("title") or "(untitled)").strip()
        content = s.get("content") or ""
        wc = len([w for w in re.split(r"\s+", content.strip()) if w])
        source = s.get("content_source") or ("user" if content else "empty")
        flags = []
        if content and source == "user":
            flags.append("USER-EDITED")
        if s.get("pending_revision"):
            flags.append("HAS-PENDING-AI-SUGGESTION")
        flag_str = f" [{' · '.join(flags)}]" if flags else ""
        section_lines.append(f'  {i}. id={sid} · "{st}" ({wc} words){flag_str}')
    sec_block = "\n".join(section_lines) if section_lines else "  (no sections yet — if the user wants to start, emit blog_outline to seed them)"

    return (
        f"Title: {title}\n"
        f"Slug: {slug}\n"
        f"Status: {status}\n"
        f"Audience: {audience}\n"
        f"Tone: {tone}\n"
        f"Tags: {', '.join(tags) if tags else '(none)'}\n"
        f"Word count: {stats.get('word_count', 0)} · Reading time: {stats.get('read_minutes', 0)} min\n"
        f"Excerpt: {excerpt}\n\n"
        f"Sections (in order — use these exact ids when emitting blog_section_draft/blog_section_revision):\n"
        f"{sec_block}"
    )

async def _fetch_project_meta(project_id: Optional[UUID]) -> Optional[dict]:
    """Fetch the project row needed by AI-turn helpers (skill routing + blog
    prompt). One query per turn — callers pass the result to both
    `_apply_ai_updates_and_operations` and `_blog_mode_state_from_meta`.
    """
    if not project_id:
        return None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT title, project_type, sections, project_data FROM mw_projects WHERE id = $1",
            project_id,
        )
    return dict(row) if row else None

def _blog_mode_state_from_meta(project_meta: Optional[dict]) -> Optional[str]:
    """If the project meta describes a blog, return the formatted state block
    for the dedicated blog system prompt. Otherwise None."""
    if not project_meta or project_meta.get("project_type") != "blog":
        return None
    return _format_blog_mode_state(project_meta)

async def _inject_recruiting_project_context(
    ctx: str, thread: dict, current_state: dict,
    project_meta: Optional[dict] = None,
) -> str:
    """If this thread belongs to a recruiting project, inject context so the AI
    generates posting sections instead of creating a new project.

    Pass `project_meta` (from `_fetch_project_meta`) to reuse an already-fetched
    row — the streaming handler previously ran this identical query twice per turn.
    """
    project_id = thread.get("project_id")
    if not project_id:
        return ctx

    from app.matcha.services import project_service as proj_svc
    row = project_meta
    if row is None:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT title, project_type, sections, project_data FROM mw_projects WHERE id = $1",
                project_id,
            )
    if not row:
        return ctx
    if row["project_type"] == "blog":
        # Blog projects use a dedicated system prompt (built separately via
        # _fetch_blog_mode_state) — skip the generic context injection.
        return ctx
    if row["project_type"] != "recruiting":
        return ctx

    sections = json.loads(row["sections"]) if isinstance(row["sections"], str) else (row["sections"] or [])
    project_data = json.loads(row["project_data"]) if isinstance(row["project_data"], str) else (row["project_data"] or {})
    posting = project_data.get("posting") or {}
    is_finalized = bool(posting.get("finalized"))
    candidates = project_data.get("candidates") or []
    candidates_count = len(candidates)
    section_count = len(sections)
    position_title = row["title"] or "the open role"

    # Build a compact candidate roster for the AI so it can auto-fill offer
    # letters without asking the user to re-enter details that are already in
    # the project. Include id so the AI can disambiguate by explicit id if
    # the user says "the first candidate" etc.
    shortlist_ids = set(project_data.get("shortlist_ids") or [])
    dismissed_ids = set(project_data.get("dismissed_ids") or [])
    roster_lines: list[str] = []
    for c in candidates[:50]:
        if c.get("id") in dismissed_ids:
            status_tag = "dismissed"
        elif c.get("id") in shortlist_ids:
            status_tag = "shortlisted"
        else:
            status_tag = c.get("status") or "pending"
        parts = [
            f"id={c.get('id', '?')}",
            f"name={c.get('name') or '(unknown)'}",
            f"email={c.get('email') or '(no email)'}",
        ]
        if c.get("current_title"):
            parts.append(f"current_title={c['current_title']}")
        if c.get("location"):
            parts.append(f"location={c['location']}")
        parts.append(f"status={status_tag}")
        roster_lines.append("- " + ", ".join(parts))
    roster_block = "\n".join(roster_lines) if roster_lines else "(no candidates uploaded yet)"

    ctx += f"""

=== RECRUITING PROJECT CONTEXT ===
This chat is part of a RECRUITING project. You are helping the user hire for a role.
- Position title (use this for offer letters): {position_title}
- Posting finalized: {is_finalized}
- Existing posting sections: {section_count}
- Candidates uploaded: {candidates_count}

CANDIDATE ROSTER (authoritative — use these exact values, do NOT ask the user to re-enter them):
{roster_block}

CRITICAL RULES FOR RECRUITING PROJECTS:
1. When the user describes a role or asks you to create a job posting, first determine whether you have enough information to draft.
   Required signals before drafting: location (city + remote/hybrid/on-site), employment type (FT/PT/contract + hours), ballpark compensation or explicit "open to discussion", and 2–3 role-specific responsibilities or must-haves.
   If any of those are missing, DO NOT emit project_sections yet and DO NOT claim a posting has been drafted.
   Instead respond conversationally (mode="general", operation="none", empty updates) with 2–4 concise clarifying questions covering the missing signals.
   Once you have the signals (either gathered across turns or supplied in one message), generate the full posting using the "project" skill with project_sections like "About the Role", "Responsibilities", "Requirements", "Compensation & Benefits". The sections will automatically appear in the project's Posting panel on the right.
   Never say "I've drafted the posting" in the same reply where project_sections is empty — only confirm a draft when you are actually emitting the sections.
2. Do NOT create a new project. The project already exists — when ready, just output project_sections with the posting content.
3. NEVER output raw JSON, code, SVG, or internal state in your responses. Always respond in clear, human-readable language.
4. To send interviews: tell the user to select candidates in the pipeline panel and click "Send Interviews".
5. To upload resumes: tell the user to click the paperclip icon or drag-and-drop PDF resumes into the chat.
6. To analyze candidates: tell the user to click "Analyze" in the Candidates tab of the pipeline panel.
7. Keep responses concise and actionable — guide the user through the recruiting workflow step by step.

OFFER LETTER AUTO-FILL (important):
8. When the user asks to generate/draft/create an offer letter for a specific candidate — whether they name them ("draft an offer for Mark"), point at them ("offer to the shortlisted one", "to the first candidate", "to this one"), or say they've decided to hire someone — you MUST pull candidate_name, candidate_email, and position_title directly from the CANDIDATE ROSTER above. Do NOT ask the user to re-type these fields.
9. If the user's reference is ambiguous (e.g. multiple shortlisted candidates), ask a single clarifying question naming the options from the roster — do not ask them to re-enter contact details.
10. Only prompt the user for fields that are NOT in the roster: salary, start_date, employment_type, benefits, etc.
11. When in doubt, prefer the shortlisted candidate. If there's exactly one candidate in the roster and the user says "generate the offer letter", use that candidate without asking who.
"""
    return ctx

async def _apply_ai_updates_and_operations(
    *,
    thread_id: UUID,
    company_id: UUID,
    ai_resp,
    current_state: dict,
    current_version: int,
    user_message: str,
    current_user_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    project_meta: Optional[dict] = None,
) -> tuple[dict, int, Optional[str], bool, str]:
    """Apply structured updates, execute supported operations, and return updated response state.

    `project_meta` (when supplied by the caller) contains at least
    `project_type` for the thread's project. We rely on it to drive the
    blog-skill routing below without a redundant DB fetch.
    """
    project_type_hint = (project_meta or {}).get("project_type") if project_id else None

    skill = ai_resp.skill or _infer_skill_from_state(current_state)
    # Blog projects always route to the blog skill — covers both legacy threads
    # whose state inference would otherwise return "project", and any future
    # prompt drift. With the dedicated blog system prompt in place, this is a
    # safety net rather than the primary defence.
    if project_type_hint == "blog":
        skill = "blog"
    # If skill is not a known document type (e.g. "none" or "chat"), fall back to
    # inferring from the update keys themselves so workbook/review/etc. updates
    # created on a fresh thread aren't silently dropped.
    elif skill not in ("offer_letter", "review", "workbook", "onboarding", "presentation", "handbook", "policy", "resume_batch", "inventory", "project", "blog") and isinstance(ai_resp.structured_update, dict) and ai_resp.structured_update:
        skill_from_updates = _infer_skill_from_state(ai_resp.structured_update)
        if skill_from_updates != "chat":
            skill = skill_from_updates
    initial_version = int(current_version)
    pdf_url: Optional[str] = None
    assistant_reply = ai_resp.assistant_reply
    changed = False

    should_execute_skill = bool(
        ai_resp.mode == "skill"
        and (ai_resp.confidence >= 0.65 or not ai_resp.missing_fields)
    )
    logger.info(
        "[MW] ai mode=%s skill=%s op=%s conf=%.2f missing=%s update_keys=%s should_exec=%s",
        ai_resp.mode, skill, ai_resp.operation, ai_resp.confidence,
        ai_resp.missing_fields,
        list(ai_resp.structured_update.keys()) if isinstance(ai_resp.structured_update, dict) else None,
        should_execute_skill,
    )
    force_send_draft = (
        skill == "offer_letter"
        and _looks_like_send_draft_command(user_message)
    )
    can_execute_operation = should_execute_skill or force_send_draft
    blog_directives: dict = {}

    if should_execute_skill and ai_resp.structured_update:
        safe_updates = _validate_updates_for_skill(skill, ai_resp.structured_update)
        if skill == "handbook" and current_state.get("handbook_source_type") == "upload":
            safe_updates = {}

        # Blog directives aren't part of the thread document schema — strip them
        # out of safe_updates and process them in the blog directive handler.
        # _validate_updates_for_skill("blog", ...) already whitelists BLOG_FIELDS
        # only, so nothing else survives for blog chats.
        if skill == "blog":
            from app.matcha.services.matcha_work_ai import BLOG_FIELDS as _BLOG_FIELDS
            for _bk in _BLOG_FIELDS:
                if _bk in safe_updates:
                    blog_directives[_bk] = safe_updates.pop(_bk)

        # No-project guard: don't persist project_title/project_sections on
        # threads with no linked project. Otherwise the state accumulates a
        # phantom project the user can't see and the AI keeps "updating" it.
        if not project_id:
            for _k in ("project_title", "project_sections", "project_status"):
                safe_updates.pop(_k, None)
        if safe_updates:
            result = await doc_svc.apply_update(thread_id, safe_updates)
            current_version = result["version"]
            current_state = result["current_state"]
            changed = changed or current_version != initial_version

            # Auto-sync AI-generated project_sections to the project's sections table.
            # Match by title (case-insensitive) so regenerations update existing
            # sections in place instead of appending duplicates. Sections added
            # manually by the user keep their own titles and are preserved.
            # Skip for blog projects: blog drafts use blog_outline / blog_section_draft /
            # blog_sections_replace directives; a stray project_sections emission would
            # silently append to the blog's sections (was a real bug, see commit history).
            _project_type = (project_meta or {}).get("project_type") if project_id else None
            _skip_project_sections_sync = _project_type == "blog"

            if project_id and not _skip_project_sections_sync and "project_sections" in safe_updates:
                from app.matcha.services import project_service as proj_svc
                new_sections = safe_updates.get("project_sections") or []
                if new_sections:
                    try:
                        existing = list(await proj_svc.get_sections(project_id))
                        existing_by_title: dict[str, int] = {}
                        for idx, s in enumerate(existing):
                            title_key = (s.get("title") or "").strip().lower()
                            if title_key and title_key not in existing_by_title:
                                existing_by_title[title_key] = idx
                        changed_sections = False
                        for section in new_sections:
                            if not isinstance(section, dict):
                                continue
                            content = (section.get("content") or "").strip()
                            if not content:
                                continue
                            title = (section.get("title") or "").strip()
                            title_key = title.lower()
                            existing_idx = existing_by_title.get(title_key) if title_key else None
                            if existing_idx is not None:
                                # Update existing section in place
                                merged = {**existing[existing_idx], "content": content}
                                if title:
                                    merged["title"] = title
                                existing[existing_idx] = merged
                                changed_sections = True
                            else:
                                # Append a new section with a fresh id
                                new_entry = {
                                    "id": os.urandom(8).hex(),
                                    "title": title or None,
                                    "content": content,
                                    "source_message_id": None,
                                }
                                existing.append(new_entry)
                                if title_key:
                                    existing_by_title[title_key] = len(existing) - 1
                                changed_sections = True
                        if changed_sections:
                            await proj_svc._update_sections(project_id, existing)
                            # Mirror the section content into project_data.posting.content
                            # so the Posting tab actually renders what the AI wrote.
                            # Without this, sections live on project.sections but the
                            # posting tab (which reads posting.content) stays empty —
                            # so the AI says "drafted it" but the user sees nothing.
                            try:
                                composed_parts: list[str] = []
                                for s in existing:
                                    if not isinstance(s, dict):
                                        continue
                                    content = (s.get("content") or "").strip()
                                    if not content:
                                        continue
                                    title = (s.get("title") or "").strip()
                                    if title:
                                        composed_parts.append(f"## {title}\n\n{content}")
                                    else:
                                        composed_parts.append(content)
                                composed = "\n\n".join(composed_parts)
                                if composed:
                                    async with get_connection() as _pconn:
                                        row = await _pconn.fetchrow(
                                            "SELECT project_data FROM mw_projects WHERE id = $1", project_id
                                        )
                                    if row:
                                        existing_data = row["project_data"]
                                        if isinstance(existing_data, str):
                                            existing_data = json.loads(existing_data or "{}")
                                        existing_data = existing_data or {}
                                        prior_posting = dict(existing_data.get("posting") or {})
                                        # Don't trample a finalized posting — operator may
                                        # have locked the content on purpose.
                                        if not prior_posting.get("finalized"):
                                            prior_posting["content"] = composed
                                            await proj_svc.update_project_data(
                                                project_id, {"posting": prior_posting}
                                            )
                            except Exception:
                                logger.warning(
                                    "Failed to mirror sections into posting for project %s",
                                    project_id, exc_info=True,
                                )
                    except Exception:
                        logger.warning("Failed to sync project_sections to project %s", project_id, exc_info=True)

            inferred = _infer_skill_from_state(current_state)
            if inferred == "offer_letter":
                pdf_url = await doc_svc.generate_pdf(
                    current_state,
                    thread_id,
                    current_version,
                    is_draft=True,
                    company_id=company_id,
                )
            elif inferred == "presentation" and not current_state.get("cover_image_url"):
                # Generate a cover image the first time slides are created
                cover_url = await doc_svc.generate_cover_image(
                    presentation_title=str(current_state.get("presentation_title") or "Presentation"),
                    subtitle=current_state.get("subtitle"),
                    company_id=company_id,
                    thread_id=thread_id,
                )
                if cover_url:
                    cover_result = await doc_svc.apply_update(thread_id, {"cover_image_url": cover_url})
                    current_version = cover_result["version"]
                    current_state = cover_result["current_state"]

    # Apply blog directives atomically under a row lock (prevents lost updates
    # from concurrent manual edits). blog_title_suggestions is informational —
    # AI describes options in reply text, no persistence.
    blog_changes_applied = False
    if blog_directives and project_id:
        from app.matcha.services import project_service as _blog_proj_svc
        try:
            _, blog_secs_changed = await _blog_proj_svc.apply_blog_directives(
                project_id,
                outline=blog_directives.get("blog_outline") if isinstance(blog_directives.get("blog_outline"), list) else None,
                draft=blog_directives.get("blog_section_draft") if isinstance(blog_directives.get("blog_section_draft"), dict) else None,
                revision=blog_directives.get("blog_section_revision") if isinstance(blog_directives.get("blog_section_revision"), dict) else None,
                replace=blog_directives.get("blog_sections_replace") if isinstance(blog_directives.get("blog_sections_replace"), list) else None,
            )
            if blog_secs_changed:
                changed = True
                blog_changes_applied = True
        except Exception:
            logger.warning("Failed to apply blog section directives for project %s", project_id, exc_info=True)

    # "Say it, do it" enforcement for blog chats. If the AI claimed to have
    # added/drafted/written/updated something but no directive actually
    # applied, strip the claim from the reply and replace it with an honest
    # propose-then-act line. Eliminates the pattern where the AI says
    # "I've put together an outline in the Write tab" while the sections
    # panel stays empty.
    if project_type_hint == "blog" and not blog_changes_applied and assistant_reply:
        claim_patterns = [
            r"\bI['’]ve\s+(?:put\s+together|added|drafted|written|written\s+up|updated|revised|structured|consolidated|created|outlined|put\s+down|laid\s+out|pulled\s+together|organized|compiled|assembled|set\s+up|composed)\b[^.!?]*[.!?]",
            r"\b(?:here['’]s|I['’]ve\s+got)\s+(?:an?|the|your)\s+(?:initial\s+)?outline[^.!?]*[.!?]",
            r"\bin\s+the\s+(?:Write|Preview|Publish)\s+tab[^.!?]*[.!?]",
            r"\bthe\s+outline\s+is\s+(?:now\s+)?in[^.!?]*[.!?]",
            r"\b(?:added|updated|populated|seeded|filled)\s+(?:the\s+)?(?:outline|sections?|draft)[^.!?]*[.!?]",
        ]
        import re as _re_claim
        stripped_reply = assistant_reply
        found_claim = False
        for pat in claim_patterns:
            if _re_claim.search(pat, stripped_reply, flags=_re_claim.IGNORECASE):
                found_claim = True
                stripped_reply = _re_claim.sub(pat, "", stripped_reply, flags=_re_claim.IGNORECASE)
        if found_claim:
            stripped_reply = _re_claim.sub(r"[ \t]+", " ", stripped_reply)
            stripped_reply = _re_claim.sub(r"\s+([.!?,;])", r"\1", stripped_reply)
            stripped_reply = _re_claim.sub(r"\n{3,}", "\n\n", stripped_reply).strip()
            honest_tail = (
                "\n\n(Note: I haven't actually written that to the Write tab yet — "
                "tell me to go ahead and I'll draft the outline now.)"
            )
            assistant_reply = (stripped_reply or "Ready when you are.") + honest_tail
            logger.warning(
                "[MW-blog] scrubbed phantom outline claim from reply for project %s thread %s",
                project_id, thread_id,
            )

    operation = str(ai_resp.operation or "none").strip().lower()
    if force_send_draft and operation in {"none", "create", "update", "track"}:
        operation = "send_draft"

    if can_execute_operation and operation not in {"none", "create", "update", "track"}:
        action_note: Optional[str] = None
        try:
            if operation == "save_draft":
                if skill != "offer_letter":
                    action_note = "Save draft is only available for offer letters."
                else:
                    saved = await doc_svc.save_offer_letter_draft(thread_id, company_id)
                    action_note = f"Saved draft successfully ({saved['offer_status']})."
            elif operation == "send_draft":
                if skill != "offer_letter":
                    action_note = "Draft sending is only available for offer letters."
                else:
                    recipients = _collect_offer_draft_recipients(
                        structured_update=ai_resp.structured_update
                        if isinstance(ai_resp.structured_update, dict)
                        else None,
                        current_state=current_state,
                        user_message=user_message,
                    )
                    send_result = await doc_svc.send_offer_letter_draft(
                        thread_id=thread_id,
                        company_id=company_id,
                        recipient_emails=recipients,
                    )
                    if send_result.get("pdf_url"):
                        pdf_url = send_result["pdf_url"]
                    action_note = (
                        f"Draft email send complete: {send_result['sent_count']} sent, "
                        f"{send_result['failed_count']} failed."
                    )
                    if send_result["failed_count"] > 0:
                        failed_recipients = [
                            str(row.get("email"))
                            for row in send_result.get("recipients", [])
                            if row.get("status") != "sent" and row.get("email")
                        ]
                        if failed_recipients:
                            action_note += f" Failed recipient(s): {', '.join(failed_recipients[:3])}."
            elif operation == "send_requests":
                if skill != "review":
                    action_note = "Sending review requests is only available in review threads."
                else:
                    recipient_emails: list[str] = []
                    if isinstance(ai_resp.structured_update, dict):
                        raw_emails = ai_resp.structured_update.get("recipient_emails")
                        if isinstance(raw_emails, list):
                            recipient_emails = [str(v) for v in raw_emails if str(v).strip()]

                    send_result = await doc_svc.send_review_requests(
                        thread_id=thread_id,
                        company_id=company_id,
                        recipient_emails=recipient_emails,
                    )
                    refreshed = await doc_svc.get_thread(thread_id, company_id)
                    if refreshed:
                        current_state = refreshed["current_state"]
                        current_version = refreshed["version"]
                        changed = changed or current_version != initial_version
                    action_note = (
                        f"Sent {send_result['sent_count']} request(s), "
                        f"{send_result['failed_count']} failed. "
                        f"Received {send_result['received_responses']}/{send_result['expected_responses']}."
                    )
            elif operation == "finalize":
                finalized = await doc_svc.finalize_thread(thread_id, company_id)
                refreshed = await doc_svc.get_thread(thread_id, company_id)
                if refreshed:
                    current_state = refreshed["current_state"]
                    current_version = refreshed["version"]
                if finalized.get("pdf_url"):
                    pdf_url = finalized["pdf_url"]
                action_note = "Thread finalized."
            elif operation == "create_employees":
                if skill != "onboarding":
                    action_note = "Employee creation is only available in onboarding threads."
                else:
                    raw_employees = current_state.get("employees")
                    if not isinstance(raw_employees, list) or not raw_employees:
                        action_note = "No employees found to create. Please add employee details first."
                    else:
                        results = await _create_onboarding_employees(
                            company_id=company_id,
                            triggered_by=current_user_id,
                            employees=[dict(e) for e in raw_employees],
                        )
                        current_state["employees"] = results
                        current_state["batch_status"] = "complete"
                        created = sum(1 for e in results if e.get("status") == "created")
                        errors = sum(1 for e in results if e.get("status") == "error")
                        result = await doc_svc.apply_update(
                            thread_id,
                            current_state,
                            diff_summary=f"Created {created} employee(s), {errors} error(s)",
                        )
                        current_version = result["version"]
                        current_state = result["current_state"]
                        changed = True
                        action_note = f"Created {created} employee(s)"
                        if errors:
                            error_names = [
                                f"{e.get('first_name', '?')} {e.get('last_name', '?')}: {e.get('error', 'unknown')}"
                                for e in results if e.get("status") == "error"
                            ]
                            action_note += f", {errors} failed: " + "; ".join(error_names[:5])
                        action_note += "."
            elif operation == "generate_presentation":
                if skill != "workbook":
                    pass  # AI already populated slides via structured_update; no error needed
                else:
                    generated = await doc_svc.generate_workbook_presentation(
                        thread_id=thread_id,
                        company_id=company_id,
                    )
                    current_state = generated["current_state"]
                    current_version = generated["version"]
                    changed = True
                    action_note = (
                        f"Generated a presentation with {generated['slide_count']} slides. "
                        "Open Preview to review and download."
                    )
            elif operation == "generate_handbook":
                if skill != "handbook":
                    action_note = "Handbook generation is only available in handbook threads."
                elif current_state.get("handbook_source_type") == "upload":
                    action_note = "Handbook generation is unavailable in upload review mode. Start a new template handbook thread instead."
                else:
                    title = current_state.get("handbook_title")
                    states = current_state.get("handbook_states") or []
                    legal_name = current_state.get("handbook_legal_name")
                    ceo = current_state.get("handbook_ceo")

                    if not title or not states or not legal_name or not ceo:
                        missing = []
                        if not title: missing.append("handbook_title")
                        if not states: missing.append("handbook_states")
                        if not legal_name: missing.append("handbook_legal_name")
                        if not ceo: missing.append("handbook_ceo")
                        action_note = f"Cannot generate — missing required fields: {', '.join(missing)}"
                    else:
                        await doc_svc.apply_update(thread_id, {"handbook_status": "generating"})

                        from app.core.models.handbook import (
                            HandbookCreateRequest, HandbookScopeInput,
                            CompanyHandbookProfileInput, HandbookSectionInput,
                        )
                        profile_data = current_state.get("handbook_profile") or {}
                        raw = profile_data if isinstance(profile_data, dict) else {}

                        scopes = [HandbookScopeInput(state=s.upper()) for s in states]
                        mode = "single_state" if len(scopes) == 1 else "multi_state"

                        profile = CompanyHandbookProfileInput(
                            legal_name=legal_name,
                            dba=current_state.get("handbook_dba"),
                            ceo_or_president=ceo,
                            headcount=current_state.get("handbook_headcount"),
                            remote_workers=raw.get("remote_workers", False),
                            minors=raw.get("minors", False),
                            tipped_employees=raw.get("tipped_employees", False),
                            tip_pooling=raw.get("tip_pooling", False),
                            union_employees=raw.get("union_employees", False),
                            federal_contracts=raw.get("federal_contracts", False),
                            group_health_insurance=raw.get("group_health_insurance", False),
                            background_checks=raw.get("background_checks", False),
                            hourly_employees=raw.get("hourly_employees", True),
                            salaried_employees=raw.get("salaried_employees", False),
                            commissioned_employees=raw.get("commissioned_employees", False),
                        )

                        custom_sections_raw = current_state.get("handbook_custom_sections") or []
                        custom_sections = [
                            HandbookSectionInput(
                                section_key=f"custom_{i}",
                                title=s.get("title", ""),
                                content=s.get("content", ""),
                                section_order=900 + i,
                                section_type="custom",
                            )
                            for i, s in enumerate(custom_sections_raw)
                            if isinstance(s, dict) and s.get("title")
                        ]

                        req = HandbookCreateRequest(
                            title=title,
                            mode=mode,
                            source_type="template",
                            industry=current_state.get("handbook_industry"),
                            scopes=scopes,
                            profile=profile,
                            custom_sections=custom_sections,
                            guided_answers=current_state.get("handbook_guided_answers") or {},
                            create_from_template=True,
                        )

                        handbook = await HandbookService.create_handbook(
                            company_id=str(company_id),
                            data=req,
                            created_by=str(current_user_id) if current_user_id else None,
                        )

                        section_previews = [
                            {"section_key": s.section_key, "title": s.title,
                             "content": (s.content or "")[:500], "section_type": s.section_type}
                            for s in (handbook.sections or [])
                        ]

                        coverage_updates = {}
                        try:
                            async with get_connection() as cov_conn:
                                industry_key = await cov_conn.fetchval(
                                    "SELECT industry FROM companies WHERE id = $1", str(company_id)
                                )
                            coverage = HandbookService.compute_coverage(handbook, industry_key or "")
                            coverage_updates = {
                                "handbook_strength_score": coverage.strength_score,
                                "handbook_strength_label": coverage.strength_label,
                            }
                        except Exception as cov_err:
                            logger.warning("Coverage computation failed: %s", cov_err)

                        result = await doc_svc.apply_update(thread_id, {
                            "handbook_status": "created",
                            "handbook_id": str(handbook.id),
                            "handbook_mode": mode,
                            "handbook_sections": section_previews,
                            **coverage_updates,
                        })
                        current_version = result["version"]
                        current_state = result["current_state"]
                        changed = True

                        section_count = len(handbook.sections or [])
                        score_note = ""
                        if coverage_updates.get("handbook_strength_score") is not None:
                            score_note = f" Coverage score: {coverage_updates['handbook_strength_score']}/100 ({coverage_updates['handbook_strength_label']})."
                        action_note = f"Handbook created with {section_count} sections.{score_note}"
            elif operation == "generate_policy":
                if skill != "policy":
                    action_note = "Policy generation is only available in policy threads."
                else:
                    policy_type = current_state.get("policy_type")
                    location_names = current_state.get("policy_location_names") or []

                    if not policy_type:
                        action_note = "Cannot generate — missing required field: policy_type"
                    elif not location_names:
                        action_note = "Cannot generate — please specify at least one location (city, state)."
                    else:
                        await doc_svc.apply_update(thread_id, {"policy_status": "generating"})

                        # Resolve location names to location IDs from business_locations
                        location_ids: list[str] = []
                        async with get_connection() as conn:
                            for loc_name in location_names:
                                parts = [p.strip() for p in loc_name.split(",")]
                                if len(parts) == 2:
                                    city, state = parts[0], parts[1]
                                    row = await conn.fetchrow(
                                        "SELECT id FROM business_locations WHERE company_id = $1 AND city ILIKE $2 AND state ILIKE $3",
                                        str(company_id), city, state,
                                    )
                                    if row:
                                        location_ids.append(str(row["id"]))

                        from app.core.services.policy_draft_service import generate_policy_draft_stream, PolicyDraftRequest

                        draft_request = PolicyDraftRequest(
                            policy_type=policy_type,
                            location_ids=location_ids if location_ids else None,
                            additional_context=current_state.get("policy_additional_context"),
                        )

                        # Collect the full generated content
                        policy_content = ""
                        async for event in generate_policy_draft_stream(str(company_id), draft_request):
                            if event.get("type") == "content":
                                policy_content += event.get("text", "")
                            elif event.get("type") == "error":
                                raise ValueError(event.get("message", "Policy generation failed"))

                        result = await doc_svc.apply_update(thread_id, {
                            "policy_status": "created",
                            "policy_content": policy_content,
                        })
                        current_version = result["version"]
                        current_state = result["current_state"]
                        changed = True
                        action_note = "Policy draft generated. Review in the Preview panel, then edit or save."
            else:
                action_note = f"The action '{operation}' is not supported yet."
        except ValueError as e:
            action_note = str(e)
        except Exception as e:
            logger.error(
                "Failed Matcha Work operation '%s' for thread %s: %s",
                operation,
                thread_id,
                e,
                exc_info=True,
            )
            action_note = "I understood the command, but couldn't complete it right now."

        assistant_reply = _append_action_note(assistant_reply, action_note)

    assistant_reply = _scrub_phantom_surface_claims(assistant_reply, project_id)

    return current_state, current_version, pdf_url, changed, assistant_reply
