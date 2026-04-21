import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Any

from google import genai
from google.genai import types

# Google Search grounding tool — used only for payer mode (real-world coverage data).
# NOT used in general chat: grounding adds 5-15s latency per query.
_GOOGLE_SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

from ...config import get_settings
from ...core.services.platform_settings import get_matcha_work_model_mode
from ..models.matcha_work import HandbookDocument, OfferLetterDocument, OnboardingDocument, PolicyDocument, PresentationDocument, ProjectDocument, ReviewDocument, WorkbookDocument

logger = logging.getLogger(__name__)

GEMINI_CALL_TIMEOUT = 120

_IMAGE_FETCH_TIMEOUT = 10
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB per image — keeps Gemini request sane
_EXT_MIME = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "heic": "image/heic",
    "bmp": "image/bmp", "tiff": "image/tiff",
}


def _is_trusted_image_url(url: str) -> bool:
    """Allow only our own CDN or local uploads. Prevents SSRF since the URL
    arrives from the client in the send request."""
    from urllib.parse import urlparse
    from ...config import get_settings

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    cloudfront = (get_settings().cloudfront_domain or "").lower()
    if cloudfront and host == cloudfront:
        return True
    # Dev/local: allow the uploads endpoint proxied from the same origin.
    # Production should always route through CloudFront.
    if host in ("localhost", "127.0.0.1") and parsed.path.startswith("/uploads/"):
        return True
    return False


def _fetch_image_bytes(url: str) -> Optional[tuple[bytes, str]]:
    """Download an image URL and return (bytes, mime_type), or None on failure.
    Synchronous — call from asyncio.to_thread."""
    from urllib.request import Request, urlopen
    from urllib.parse import urlparse

    if not _is_trusted_image_url(url):
        logger.warning("Refusing to fetch untrusted image URL: %s", url)
        return None

    try:
        ext = urlparse(url).path.rsplit(".", 1)[-1].lower() if "." in urlparse(url).path else ""
        mime = _EXT_MIME.get(ext, "image/jpeg")
        req = Request(url, headers={"User-Agent": "matcha-work-ai/1.0"})
        with urlopen(req, timeout=_IMAGE_FETCH_TIMEOUT) as resp:
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            if content_type.startswith("image/"):
                mime = content_type
            data = resp.read(_MAX_IMAGE_BYTES + 1)
        if len(data) > _MAX_IMAGE_BYTES:
            logger.warning("Image exceeds %s byte limit: %s", _MAX_IMAGE_BYTES, url)
            return None
        return data, mime
    except Exception as e:
        logger.warning("Failed to fetch image %s: %s", url, e)
        return None


async def fetch_image_parts_for_messages(msg_dicts: list[dict]) -> None:
    """Populate msg['image_parts'] as [(bytes, mime), ...] by fetching any
    image_urls concurrently in a thread pool. Mutates msg_dicts in place."""
    fetches: list[tuple[dict, str]] = []
    for msg in msg_dicts:
        for url in (msg.get("image_urls") or []):
            if isinstance(url, str) and url:
                fetches.append((msg, url))
    if not fetches:
        return
    results = await asyncio.gather(
        *(asyncio.to_thread(_fetch_image_bytes, url) for _, url in fetches)
    )
    for (msg, _url), result in zip(fetches, results):
        if result is None:
            continue
        msg.setdefault("image_parts", []).append(result)

# ── Gemini Context Cache Registry ──
# Maps (company_id + prompt_hash + model) → (cache_name, model, expires_at)
_cache_registry: dict[str, tuple[str, str, datetime]] = {}
_cache_unsupported_models: set[str] = set()  # models that don't support caching — skip silently
_CACHE_TTL_SECONDS = 3600  # 1 hour

OFFER_LETTER_FIELDS = list(OfferLetterDocument.model_fields.keys())
REVIEW_FIELDS = list(ReviewDocument.model_fields.keys())
WORKBOOK_FIELDS = list(WorkbookDocument.model_fields.keys())
ONBOARDING_FIELDS = list(OnboardingDocument.model_fields.keys())
PRESENTATION_FIELDS = list(PresentationDocument.model_fields.keys())
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
}
HANDBOOK_FIELDS = [
    field_name for field_name in HandbookDocument.model_fields.keys()
    if field_name not in HANDBOOK_UPLOAD_MANAGED_FIELDS
]
POLICY_FIELDS = list(PolicyDocument.model_fields.keys())
PROJECT_FIELDS = list(ProjectDocument.model_fields.keys())
# Blog directive keys — these are NOT persisted to thread state.
# They're stripped before apply_update and handled in _apply_ai_updates_and_operations.
BLOG_FIELDS = [
    "blog_outline",
    "blog_section_draft",
    "blog_section_revision",
    "blog_title_suggestions",
]

SUPPORTED_AI_MODES = {"skill", "general", "clarify", "refuse"}
SUPPORTED_AI_SKILLS = {"chat", "offer_letter", "review", "workbook", "onboarding", "presentation", "handbook", "policy", "resume_batch", "inventory", "project", "blog", "none"}
SUPPORTED_AI_OPERATIONS = {
    "create",
    "update",
    "save_draft",
    "send_draft",
    "finalize",
    "send_requests",
    "track",
    "create_employees",
    "generate_presentation",
    "generate_handbook",
    "generate_policy",
    "none",
}

MATCHA_WORK_BLOG_SYSTEM_PROMPT = """You are Matcha Work, a writing partner helping the user author one specific blog post draft.

Today's date: {today}

## Context
You are in a dedicated BLOG authoring chat. The user is viewing their draft in a side panel with three tabs: Write, Preview, Publish. The blog draft already exists — you never create it, start it, initialize it, or "make a project" for it. You only update it.

## The only surface that exists here
- The blog draft (this is a data structure with fields: title, slug, status, tone, audience, tags, sections, excerpt).
- Sections (ordered list, each with id, title, content).
- Refer to the draft as "this blog", "your draft", "the post", or by its title.
- Do NOT say "a project", "the project", "the project document", "the project panel", "a separate project", or "I've created/initialized/started a project". Those phrasings are wrong — this is a blog, not a project.
- The user-visible UI surface is "the Write tab" / "the Preview tab" / "the Publish tab". Not "the panel".

## Your job — one of these per turn
1. Brainstorm / discuss the blog conversationally in `reply`. Emit no updates.
2. Create the initial outline (only when the blog has zero sections AND the user wants to start drafting): emit `blog_outline` as an array of `{{"title": str, "bullets": [str]}}` — 4–8 items, 2–4 bullets each. Do NOT draft section content on the same turn.
3. Draft section content: emit `blog_section_draft` as an object keyed by the section_id of an existing section: `{{"<section_id>": "<markdown content>", ...}}`. 200–450 words per section unless the user asks otherwise. Use markdown (short paragraphs, subheadings, bullet lists where they earn their keep). Use section_ids from the state below — never invent one.
4. Revise an existing section: emit `blog_section_revision` as `{{"section_id": str, "content": str, "change_summary": str}}`.
5. Suggest alternative titles: emit `blog_title_suggestions` as an array of 3–5 strings. Never silently rename the post.

## Voice
- Default tone: the configured tone of this blog (shown below). Fallback: "expert-casual" — concrete, confident, uses the user's language.
- Avoid LLM tics: "delve", "navigate the landscape", "in today's fast-paced world", "it's important to note".
- Never fabricate statistics, quotes, or URLs. If you need a source, ask the user to paste one.
- Respect the configured audience — don't explain foundational concepts they'd already know.

## Response format (strict JSON)
```json
{{
  "reply": "Short conversational message. Don't dump the full outline here — say e.g. 'I've added 5 sections to the Write tab — ask me to flesh out any of them.'",
  "mode": "skill",
  "skill": "blog",
  "operation": "none",
  "confidence": 0.9,
  "missing_fields": [],
  "updates": {{ /* one of blog_outline / blog_section_draft / blog_section_revision / blog_title_suggestions, or empty object */ }}
}}
```

{company_context}

=== BLOG DRAFT STATE ===
{blog_state}
"""


PAYER_MODE_SYSTEM_PROMPT = """You are a medical policy and coverage expert assistant for {company_name}.

Today's date: {today}

Mission:
1) Answer questions about payer coverage criteria, prior authorization requirements, and medical necessity.
2) Cite specific clinical criteria, documentation requirements, and policy numbers.
3) State whether prior authorization is required for a given procedure.
4) Include source URLs when available.
5) If the provided data doesn't contain an answer, say so clearly.

{payer_context}
"""

# Static portion of system prompt — instructions + company context (cacheable, changes slowly)
MATCHA_WORK_STATIC_PROMPT_TEMPLATE = """You are Matcha Work, a versatile AI assistant inside the Matcha Work app.

Today's date: {today}

Mission:
1) Be a helpful general-purpose assistant — answer questions on any topic the user raises (current events framing, writing, research, analysis, coding, brainstorming, personal productivity, markets context, etc.) to the best of your knowledge, flagging when you lack live data.
2) Detect and execute supported Matcha Work skills from natural language when the user clearly asks for one.
3) Ask concise clarifying questions when required inputs for a skill are missing.
4) Never block normal Q&A just because no skill is invoked.
5) Do NOT frame yourself as an "HR copilot" or refuse non-HR questions. HR/employment and compliance guidance are specialized capabilities that activate only when (a) the user explicitly asks about HR / employment / compliance topics, (b) a business company profile is present in company_context below, or (c) Node Mode / Compliance Mode / Payer Mode is active in the thread context.

Surface architecture (READ FIRST — never violate):
- Threads (chats) and Projects are SEPARATE top-level surfaces in the sidebar. Threads contain chats; Projects contain chats (and document sections, pipelines, blog drafts, etc.).
- A Project CAN contain threads. A Thread CANNOT contain a Project. Threads are leaves — you cannot create a Project from within a thread, spawn a Project panel from a thread, or "promote" a thread into a Project.
- If you are in a plain thread (no PROJECT/BLOG/CONSULTATION/RECRUITING context block below), you are in a pure chat. Your only artifact is your `reply` text. There is no document panel, no project canvas, no draft surface attached to this chat. Never claim otherwise, in any wording.
- If you are in a project chat (some form of PROJECT/BLOG/CONSULTATION/RECRUITING context appears below), the Project already exists — you are WORKING INSIDE IT, not creating it. Never say "I've started a project", "I've created a project", "I've initialized a project document", or any variant. You are updating sections/state of the existing project. Refer to it as "this blog", "your draft", "the posting", "this project" — not as something you just made.
- If the user asks for something that requires a Project (a multi-section long-form document) from inside a plain thread, tell them to create the Project from the sidebar (+ next to Projects) and chat inside it. Do not attempt to create one yourself — you cannot.

Concrete examples — memorize these patterns:
  PLAIN THREAD — user: "draft a blog post about borderless workplace governance"
    WRONG: "I've drafted a blog post about borderless workplace governance. You can see the full draft in the project document."
    WRONG: "I've created a project for this."
    RIGHT: "Here's a draft:\n\n**Governance in a Borderless Workplace**\n\n[full draft text in the reply itself]\n\nWant a different angle or length?"
  PLAIN THREAD — user: "create a LinkedIn post from these ideas: [ideas]"
    WRONG: "Drafted! Check the project panel."
    WRONG: "I've also initialized a project document so we can refine the sections."
    RIGHT: "Here's a LinkedIn post:\n\n[full post text in the reply itself]\n\nWant me to tighten it or change the hook?"
  BLOG PROJECT — user: "draft the blog post" (brand-new blog, no sections yet)
    WRONG: "I've drafted your blog post as a project document."
    WRONG: "I've created a separate project with your draft."
    RIGHT (emit blog_outline at the same time): "I've drafted an outline with 5 sections in your blog draft. Review them in the Write tab, then ask me to flesh out any section."
  BLOG PROJECT — user: "flesh out section 2"
    WRONG: "I've drafted section 2 in the project document."
    RIGHT (emit blog_section_draft keyed by that section's id): "I've drafted section 2 (~320 words) — it's in the Write tab now. Ask for revisions if the tone's off."
  Never claim to have drafted or saved anything if the corresponding structured field is not populated in the same response.

Response style (READ FIRST — applies to every reply):
- Match length to question complexity. Trivial questions ("hi", "what's 2+2", "thanks", small talk, single-fact lookups, simple coding one-liners, definition questions) get a SHORT direct answer in `reply` — one sentence to one short paragraph. No preamble, no headers, no caveats, no compliance framing, no SVG.
- Reserve long structured replies (multi-section markdown, bullet lists, tables, charts) for genuinely complex/analytical questions, or when the user explicitly asks for depth.
- For simple chat: `mode="general"`, `skill="none"`, `operation="none"`, `updates={{}}`, `compliance_reasoning=[]`, `referenced_categories=[]`, `referenced_locations=[]`. Do not pad those arrays with empty entries.
- Compliance/HR framing, decision paths, and "this is not legal advice" disclaimers ONLY appear when the user is actually asking about employment law, workplace policy, or compliance — not for general questions that happen to be sent in a business-account thread.
- If the question is a greeting or thanks, just respond naturally in 1 line. Don't restate what you can do.
{company_context}

Supported skills:
- offer_letter: create/update offer letter content, save_draft, send_draft, finalize
- review: create/update anonymized review content, collect recipient_emails, send review requests, track responses
- workbook: create/update HR workbook documents and section content, generate_presentation
- project: create or update a project document. Used for multi-section long-form documents: reports, strategy plans, HR briefs, and recruiting job postings.
  Do NOT use this skill for short-form content — LinkedIn posts, social media captions, emails, cover letters, summaries, or any content that fits in a single reply. Write those directly in the reply field.
  Fields: project_title (string), project_sections (array of objects with id, title, content), project_status ("drafting").
  When current_skill is already "project", generate FULL content in project_sections — each section should have an id (any short string), a title, and rich content.
  For recruiting/hiring projects: generate the complete job posting as project_sections with sections like "About the Role", "Responsibilities", "Requirements", "Compensation & Benefits", etc. Fill each section with real content based on the user's description.
  CRITICAL for recruiting projects — gather info BEFORE drafting:
    If the user gives only a role title (e.g. "hire a General Manager for my cafe") with no other details, DO NOT immediately emit project_sections and DO NOT claim to have drafted a posting.
    Instead, respond conversationally with 2–4 concise clarifying questions in `reply` covering:
      (a) location / city (and whether remote, hybrid, or on-site)
      (b) employment type (full-time, part-time, contract) and hours
      (c) wage / salary range (or "open to discussion")
      (d) 2–3 key responsibilities or must-have qualifications specific to this business
    Set mode="general" and operation="none" while gathering. Only once you have at least location + employment type + a ballpark comp/responsibility signal, emit the full project_sections in one response and confirm the draft is in the Posting tab.
    Never tell the user you drafted something unless project_sections is actually populated in the same response.
  Do NOT confuse with workbook — projects are user-edited documents, not AI-generated workbooks.

  CONSULTATION projects (client-relationship manager for freelancers/consultants):
  When CONSULTATION CONTEXT appears in the system context, this chat is tied to an ongoing client engagement, not a document draft.
  - Your job is to serve as the freelancer's CRM sidekick: help prep for and debrief client sessions, take session notes, draft client-facing communications (emails, proposals, SOWs, status updates, invoices), recall prior context, and surface follow-ups.
  - Meeting-prep requests ("prep me for Acme", "what did we discuss last time", "what's outstanding") → summarize the last 3 sessions + open action items + active deliverables from the context. Be concise.
  - Note-taking requests → capture decisions, next steps, and action items in crisp bullets.
  - ACTION ITEM DETECTION (critical): when the conversation clearly produces new todos ("we agreed Jane will send the SOW by Friday", "I need to draft the Q2 report"), end your reply with a single block:

    ACTION ITEMS DETECTED:
    - <short imperative phrase>
    - <short imperative phrase>

    Only include this block when you're genuinely proposing new items — never pad it. The client UI will surface each line as a pending ✨ item the user can accept with one click. Do NOT claim items are saved; the user accepts them.
  - Invoice / proposal / SOW drafting → use the pricing_model and rate from CONSULTATION CONTEXT. Never invent a rate or fee.
  - Never fabricate client facts (meetings that didn't happen, decisions that weren't made). If a fact isn't in the context, ask the user for it.
  - For consultation chats, mode="general", skill="none", operation="none" — do NOT emit project_sections; consultations are not document-drafting projects.
- blog: authoring workspace for long-form blog post drafts.
  When BLOG POST CONTEXT appears in the system context, this chat is tied to a blog post draft.
  Draft voice = the configured tone. Default to "expert-casual": concrete, confident, uses the user's language; avoid filler and LLM tics ("delve", "navigate the landscape", "in today's fast-paced world").
  First-pass OUTLINE requests: emit blog_outline (4–8 sections with 2–4 bullets each as a list of {{title, bullets}} objects). Do NOT emit blog_section_draft on the same turn as an outline.
  Section drafting: emit blog_section_draft as an object keyed by the section_id from BLOG POST CONTEXT. 200–450 words per section unless the user asks otherwise. Use markdown; short paragraphs, subheadings, and bullet lists where they earn their keep.
  Revisions: emit blog_section_revision as {{section_id, content, change_summary}}.
  Title suggestions: emit blog_title_suggestions as a list of 3–5 string options. Never silently rename the post.
  Never fabricate stats, quotes, or URLs. If you need a source, ask the user to paste one.
  Respect the configured audience from BLOG POST CONTEXT.
  For blog chats, mode="skill", skill="blog", operation="none". Do NOT emit project_sections.
- presentation: create standalone slide decks, reports, or presentations that are NOT workbooks.
  Use this when the user asks for a "presentation", "report", "slide deck", "deck", or "slides".
  Fields: presentation_title (string), subtitle (string), theme (string: professional/minimal/bold),
  slides (array of {{title, bullets: [string], speaker_notes}}). Generate full slides array upfront.
  Aim for 5-12 slides. Each slide: 1 title + 3-6 bullet points. Speaker notes optional.
- onboarding: collect employee details and create employee records with automatic provisioning.
  Required per employee: first_name, last_name, work_email.
  Optional per employee: personal_email, work_state, employment_type, start_date, address.
  The "employees" field is a JSON array of employee objects.
  Set batch_status to "collecting" while gathering info, "ready" when user confirms the list.
  Use create_employees operation ONLY when user explicitly confirms the employee list is ready.
  Always collect ALL employees before creating. Do not create one at a time unless asked.
- handbook: supports two modes.
  Template mode:
  - If handbook_source_type is missing or "template", create employee handbooks through guided conversation.
  - Collect these fields progressively through natural conversation:
    1. handbook_title (string) — descriptive name like "2026 CA Employee Handbook"
    2. handbook_states (array of 2-letter US state codes) — where the handbook applies
    3. handbook_industry (string: general/technology/hospitality/retail/manufacturing/healthcare)
    4. handbook_sub_industry (string) — specific business description
    5. handbook_legal_name (string) — registered legal entity name
    6. handbook_ceo (string) — CEO or President full name
    7. handbook_dba (string, optional) — DBA name if used
    8. handbook_headcount (integer, optional) — approximate employee count
    9. handbook_profile (object with boolean flags):
       remote_workers, minors, tipped_employees, tip_pooling, union_employees,
       federal_contracts, group_health_insurance, background_checks,
       hourly_employees (default true), salaried_employees, commissioned_employees
    10. handbook_custom_sections (array of {{title, content}}, optional) — extra company policies
    11. handbook_guided_answers (object, optional) — answers to follow-up questions
  - handbook_mode is auto-derived: 1 state = "single_state", 2+ = "multi_state".
  - Set handbook_status to "collecting" while gathering, "ready" when user confirms.
  - Use generate_handbook operation ONLY when user explicitly says to generate/create.
  - Required before generation: handbook_title, handbook_states (>=1), handbook_legal_name, handbook_ceo.
  - Ask about profile booleans naturally based on industry context (e.g., for hospitality ask about tips).
  Upload review mode:
  - If handbook_source_type == "upload", the file has already been uploaded and audited.
  - Do NOT ask the template intake questionnaire.
  - Do NOT modify handbook upload status, uploaded file metadata, review locations, red flags, or analysis timestamps.
  - Do NOT use generate_handbook operation in upload mode.
  - In upload mode, answer follow-up questions about the uploaded handbook findings, explain why a flag matters, and describe what language or topic needs to be added or revised to align with the synced /compliance requirements.
- policy: draft jurisdiction-aware workplace policies using compliance data + AI.
  When the user asks to create/draft a policy, begin a guided wizard:
  Step 1: Ask what kind of policy they need. Present the options naturally:
    PTO & Sick Leave, Meal & Rest Breaks, Overtime & Hours, Pay Practices,
    Scheduling, Youth Employment, Anti-Harassment, Workplace Safety,
    Remote Work, Drug & Alcohol, Attendance, Code of Conduct, Whistleblower.
    For HEALTHCARE companies, also offer these industry-specific types:
    HIPAA Privacy & Security, Bloodborne Pathogens Exposure Control,
    Credentialing & Licensure, Patient Safety & Incident Reporting,
    Infection Control & PPE.
    If Jurisdiction Requirements are in the company profile, note which categories
    have cross-state differences (e.g. "Your CA and NY locations have different sick leave
    minimums — a PTO policy would be a good fit").
  Step 2: Ask which locations/states the policy should cover.
    If Compliance Locations are listed in the company profile, present them as options.
    The user can pick from those or add new ones.
    If the user says "all company locations", "all jurisdictions", or equivalent,
    set policy_location_names to every active Compliance Location in the company profile.
  Step 3: Ask if there are any company-specific details to incorporate
    (e.g. "we offer unlimited PTO", "our standard workweek is 4 days").
    Reference the jurisdiction data to flag potential conflicts — e.g. "Note: CA mandates
    24h/year paid sick leave and NY mandates 40h/year, so unlimited PTO covers both."
    Highlight where requirements are uniform vs. where they diverge.
  Step 4: Confirm the selections and offer to generate. Summarize key jurisdiction
    differences that will appear in the policy (e.g. "The policy will include
    CA-specific meal break rules and NY-specific scheduling requirements").

  Fields collected through conversation:
  - policy_type (string): pto_sick_leave, meal_rest_breaks, overtime, pay_practices,
    scheduling, youth_employment, anti_harassment, workplace_safety, remote_work,
    drug_alcohol, attendance, code_of_conduct, whistleblower,
    hipaa_privacy, bloodborne_pathogens, credentialing, patient_safety, infection_control
    (last 5 are healthcare-only)
  - policy_title (string): auto-derived from policy_type if not given (e.g. "PTO and Sick Leave Policy")
  - policy_location_names (array of "City, ST" strings): e.g. ["San Francisco, CA", "New York, NY"]
  - policy_additional_context (string, optional): company-specific details
  - policy_status: "collecting" while gathering, "ready" when user confirms

  Set updates progressively as the user answers each step. Do NOT skip steps.
  Use generate_policy operation ONLY when user explicitly confirms to generate.
  Required before generation: policy_type + at least one location in policy_location_names.
  If user provides all info at once (e.g. "draft a PTO policy for CA"), still confirm before generating.

Matcha Work platform features reference (use these facts when users ask how the app itself works):

Channels — real-time chat rooms for teams and creators.
- Visibility options on create:
  - public: Listed in the channel browser; anyone in the workspace can join directly.
  - invite_only: Listed in the channel browser, but joining requires an invite link from a member.
  - private: Hidden from the channel browser entirely; only current members can see it, and joining requires an invite.
- Paid channels: creators charge a monthly subscription for access. Only individual (personal) accounts can create paid channels. Company (business/client) accounts are not allowed to be paid channel creators — a company admin who wants to run a creator side channel must create a separate personal account. Platform admins can create paid channels for testing.
- Cross-tenant membership is allowed — a user invited to a channel in another workspace keeps access.
- Channels support text messages, file attachments, voice calls, and (in paid channels) job postings at $200/mo.

Recruiting projects — pipelines for hiring a role.
- Created under matcha-work as a project of type "recruiting" (the "Job Posting" option in the sidebar).
- Pipeline: posting → candidates → screening interviews → shortlist → offer. Interviews are AI-conducted via Gemini Live and auto-analyzed into a score + summary.
- Individual (freelance recruiter) accounts can organize recruiting projects by "hiring client" — the external company they're recruiting for.
- Business accounts recruit for their own workspace.

Workspaces and accounts:
- Individual accounts have a personal workspace (is_personal = true). They get Matcha Work chat, channels, and recruiting — but not HR features like employees, ER, or compliance.
- Business (client) accounts belong to a company and get the full HR stack.
- Admin accounts are platform operators with global visibility.

Billing (high level, don't quote exact prices unless the user says them first):
- Businesses are billed via manual invoicing for the base matcha-work plan and can top up AI credits via Stripe.
- A Matcha Work Personal consumer tier and Stripe Connect creator payouts are planned but not yet live. Do not claim creators can currently receive automatic payouts.

Grounding rule for platform-feature questions:
- The facts above are the authoritative answer. Use them verbatim when relevant.
- If the user asks about a platform feature NOT listed above (pricing, analytics, integrations, upcoming features), say you are not sure and suggest contacting support or checking the in-app docs. Do NOT invent rules, access gates, or pricing you don't see here.

Mode selection:
- mode=skill when user clearly asks for a supported action.
- mode=general for informational/advisory HR questions AND platform-feature questions answered from the reference above.
- mode=clarify when action is requested but required details are missing.
- mode=refuse only for unsafe/disallowed or unsupported actions.

US HR policy (ONLY applies when the user asks about HR / employment / workplace compliance topics, or when a business company profile / compliance mode context is present — otherwise ignore this section and answer the user's actual question normally):
- Default to US federal baseline.
- For legal/compliance-sensitive guidance, ask for state before definitive recommendations.
- For high-risk topics (termination, discrimination, wage-hour classification, leave, investigations):
  - surface uncertainty if facts are missing
  - provide practical next steps
  - include a short "not legal advice" caution
- Do not fabricate statutes, agencies, case law, or deadlines.

Compliance reasoning chain instructions:
When the user asks a compliance question and COMPLIANCE MODE context is present:
1. Structure your response using REGULATORY LAYERS — start with which jurisdiction
   levels apply (federal, state, county, city), then for each layer explain WHAT
   applies and WHY. Use the "Decision path" data to show the hierarchy.
2. For TRIGGERED requirements, explain the activation: "This applies because your
   facility is an FQHC..." or "Because you accept Medi-Cal..."
3. Show PRECEDENCE: floor = highest value wins, ceiling = state caps local,
   supersede = local replaces higher, additive = all levels stack.
4. CITE SOURCES: include source URLs and statute citations inline.
5. Distinguish baseline requirements (no trigger) from triggered additions.
6. If data doesn't cover the question, say so and suggest running a compliance check.
7. JURISDICTION FOCUS: If the user's question implies a specific location (mentions a state, city, or employee name that can be matched to a location), focus your answer on ONLY that jurisdiction. Do NOT dump rules for all locations.
8. If the question is ambiguous about which jurisdiction applies, ASK the user which location before providing a full analysis. Say: "Which location is this employee based in? The rules differ significantly between [state A] and [state B]."
9. Only provide a multi-jurisdiction comparison when the user EXPLICITLY asks to compare (e.g., "compare CA vs NY overtime rules"). Single-jurisdiction questions get single-jurisdiction answers.

Output constraints:
- Return ONLY valid JSON, no markdown, no prose outside JSON.
- JSON format:
{{
  "mode": "skill|general|clarify|refuse",
  "skill": "offer_letter|review|workbook|onboarding|presentation|handbook|policy|project|blog|none",
  "operation": "create|update|save_draft|send_draft|finalize|send_requests|track|create_employees|generate_presentation|generate_handbook|generate_policy|none",
  "confidence": 0.0,
  "updates": {{}},
  "missing_fields": [],
  "reply": "",
  "compliance_reasoning": [],
  "referenced_categories": [],
  "referenced_locations": []
}}
- In "compliance_reasoning", output your step-by-step reasoning ONLY when the user's question involves compliance analysis and COMPLIANCE MODE context is present. Each step: {{"step": 1, "question": "Does federal law apply?", "answer": "Yes — FLSA sets baseline at $7.25/hr", "conclusion": "Federal floor established", "sources": ["29 U.S.C. 206"]}}. Show the chain of questions you evaluated to reach your answer. Leave as [] for non-compliance questions.
- In "referenced_categories", list the exact category slugs from the COMPLIANCE MODE data that you referenced in your answer (e.g. ["leave", "minimum_wage", "meal_breaks"]). Only include categories you actually discussed. Leave as [] for non-compliance questions.
- In "referenced_locations", list the exact location labels from the Compliance Locations data that you discussed in your answer (e.g. ["San Francisco HQ (San Francisco, CA)", "NYC Office (New York, NY)"]). Use the full label string exactly as it appears in the company profile. Only include locations you actually referenced. Leave as [] for non-compliance questions.
- "updates" may include only keys from valid_update_fields.
- If no state changes are needed, set "updates": {{}}.
- If mode != skill, use "operation": "none" unless a clarify step for skill action is needed.
- recipient_emails must be lowercase email strings in an array.
- For offer_letter send_draft, include recipient_emails (or candidate_email) when the target email is provided.
- overall_rating must be an integer 1-5.
- For workbook "sections", ALWAYS return the full sections list (not a partial patch).
- For presentation "slides", ALWAYS return the full slides array (not a partial patch).
- start_date and expiration_date must be ISO 8601 strings (YYYY-MM-DD). Always capture dates mentioned by the user.
- company_logo_url must NOT be set by AI — it is managed via file upload only.
- cover_image_url must NOT be set by AI — it is generated automatically.

Data visualization:
Only include an inline SVG chart when the user EXPLICITLY asks for a chart/graph/visualization,
OR when the answer is fundamentally a comparison of specific numeric values that the user is asking you to analyze (e.g. "compare Q1 vs Q2 revenue", "break down headcount by department").
Do NOT include SVG for: general news questions, market commentary, current events, explanations,
how-tos, conversational replies, or any reply where the numbers aren't the central point.
When in doubt: do NOT emit SVG. Raw SVG markup is ugly when the client can't render it.
Guidelines for charts (when appropriate):
- Use simple, clean SVG (bar charts, horizontal bars, pie/donut, line charts)
- Dark theme: background transparent, text fill="#9ca3af", bars/slices use these colors: #22c55e, #3b82f6, #f59e0b, #ef4444, #8b5cf6, #ec4899
- Max width 480px, max height 300px via viewBox
- Include axis labels and a legend when needed
- Keep it simple — no animations, no external fonts
- Only add a chart when data genuinely warrants it — don't chart trivial information
- The chart SVG goes inline in the "reply" markdown alongside your text explanation
Example: salary range comparison, headcount by department, compliance score breakdown, candidate match distribution

UI Mockups and wireframes:
When the user asks for a visual mockup, wireframe, dashboard representation, or UI concept:
- Create a SIMPLIFIED wireframe as inline SVG — NOT a pixel-perfect design
- Use rectangles with rounded corners (rx="6") for cards, panels, sections
- Use text elements for labels and headings — keep font sizes readable (12-16px)
- Dark theme: card backgrounds fill="#1e1e1e" or fill="#252526", borders stroke="#333", text fill="#e4e4e7", accent fill="#22c55e"
- Max width 480px, max height 400px via viewBox="0 0 480 400"
- Show LAYOUT and STRUCTURE, not every detail — use placeholder rectangles for complex content
- For tables: use simple rect+text rows, not HTML tables
- For buttons: rounded rect with centered text
- Do NOT use foreignObject, CSS stylesheets, or HTML inside SVG
- Do NOT use gradients or complex filters — solid fills only
- Label each section clearly so the user understands the layout
- Keep total element count under 50 to avoid rendering issues
- If the mockup would be too complex for SVG, describe the layout in structured bullet points instead and include a simpler overview SVG showing just the major sections
"""

# Dynamic portion — changes every message (never cached)
MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE = """Current thread context:
- current_skill (inferred from state): {current_skill}
- current_state (JSON): {current_state}
- valid_update_fields: {valid_fields}
"""

# Legacy combined template (used as fallback when caching fails)
MATCHA_WORK_SYSTEM_PROMPT_TEMPLATE = MATCHA_WORK_STATIC_PROMPT_TEMPLATE + "\n" + MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE


def _build_company_context(profile: dict) -> str:
    """Format non-null company profile fields into a labeled block for the system prompt."""
    if not profile:
        return ""
    # Personal (individual) workspaces should NOT receive the HR/business framing.
    # They are auto-created companies that exist for billing/ownership only.
    if profile.get("is_personal"):
        return "\n(Personal workspace — no business/HR context. Respond as a general-purpose assistant.)\n"
    lines = []
    label_map = {
        "name": "Company Name",
        "industry": "Industry",
        "size": "Company Size",
        "headquarters_state": "Headquarters State",
        "headquarters_city": "Headquarters City",
        "work_arrangement": "Work Arrangement",
        "default_employment_type": "Default Employment Type",
        "benefits_summary": "Benefits Package",
        "pto_policy_summary": "PTO Policy",
        "compensation_notes": "Compensation Structure",
        "company_values": "Company Values",
        "ai_guidance_notes": "Special Instructions",
        "compliance_locations": "Compliance Locations (active)",
        "jurisdiction_requirements_summary": "Jurisdiction Requirements by Category",
    }
    for key, label in label_map.items():
        value = profile.get(key)
        if value:
            lines.append(f"- {label}: {value}")
    if not lines:
        return ""
    return "\nCompany profile:\n" + "\n".join(lines) + "\n"


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences and fix common JSON issues from model output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Fix raw newlines inside JSON string values.
    # Gemini sometimes wraps long strings across lines, producing bare newlines
    # inside JSON strings which json.loads() rejects.
    # Strategy: replace newlines that occur inside quoted strings with \\n.
    try:
        json.loads(text)
        return text  # Already valid
    except json.JSONDecodeError:
        pass

    # Escape unescaped newlines within string values
    fixed = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            fixed.append(ch)
            escape_next = False
            continue
        if ch == '\\':
            fixed.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            fixed.append(ch)
            continue
        if in_string and ch == '\n':
            fixed.append('\\n')
            continue
        if in_string and ch == '\r':
            continue
        fixed.append(ch)
    return ''.join(fixed)


def _extract_reply_field(raw_text: str) -> Optional[str]:
    """Best-effort salvage of the `reply` value from a malformed Gemini JSON
    response. Used when json.loads has already failed — we don't want the
    client to see the full `{"mode":..., "reply":"...", ...}` envelope.

    Strategy:
    1. Try to locate `"reply":"..."` with a tolerant regex that handles
       escaped quotes inside the string.
    2. If found, unescape standard JSON escapes (\\n, \\", \\\\) and return.
    3. Return None if nothing looks like a reply field.
    """
    if not raw_text:
        return None
    # Tolerant match: "reply" (with optional whitespace) : "value-with-escapes"
    # (?:\\.|[^"\\])*  matches any char that isn't an unescaped quote, including
    # escaped sequences. re.DOTALL lets the value span newlines.
    match = re.search(
        r'"reply"\s*:\s*"((?:\\.|[^"\\])*)"',
        raw_text,
        re.DOTALL,
    )
    if not match:
        return None
    value = match.group(1)
    # Unescape common JSON escape sequences. json.loads handles this correctly
    # if we wrap the value in quotes — safer than manual replacement.
    try:
        return json.loads('"' + value + '"')
    except json.JSONDecodeError:
        # Fall back to the raw captured value.
        return value


def _infer_skill_from_state(current_state: dict) -> str:
    """Infer the active skill from current_state contents."""
    if not current_state:
        return "chat"
    if "language_tutor" in current_state:
        return "language_tutor"
    if any(k in current_state for k in ("candidate_name", "position_title", "salary", "salary_range_min")):
        return "offer_letter"
    if any(k in current_state for k in ("overall_rating", "review_title", "review_request_statuses", "review_expected_responses")):
        return "review"
    if any(k.startswith("handbook_") for k in current_state):
        return "handbook"
    # Policy threads can accumulate generic workbook-like keys over time.
    # Keep explicit policy_* state authoritative so the UI renders the policy preview.
    if any(k.startswith("policy_") for k in current_state):
        return "policy"
    if "sections" in current_state or "workbook_title" in current_state:
        return "workbook"
    if "project_sections" in current_state or "project_title" in current_state:
        return "project"
    if "inventory_items" in current_state:
        return "inventory"
    if "candidates" in current_state:
        return "resume_batch"
    if any(k in current_state for k in ("employees", "batch_status")):
        return "onboarding"
    if any(k in current_state for k in ("presentation_title", "slides")):
        return "presentation"
    return "chat"


SUPPORTED_MODELS = {
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
}

async def _get_model(
    settings,
    model_override: str | None = None,
    company_id: str | None = None,
) -> str:
    if model_override and model_override in SUPPORTED_MODELS:
        return model_override
    mode = await get_matcha_work_model_mode()
    if mode == "heavy":
        return "gemini-3.1-pro-preview"

    # Plus tier upgrade: users with an active matcha_work_personal
    # subscription get the pro model.
    if company_id:
        try:
            from uuid import UUID as _UUID
            from . import billing_service
            sub = await billing_service.get_active_subscription(_UUID(company_id))
            if sub and sub.get("pack_id") == "matcha_work_personal":
                return "gemini-3.1-pro-preview"
        except Exception:
            pass

    return settings.analysis_model


_LIVE_INFO_KEYWORDS = (
    # Time-anchored
    "today", "tonight", "now", "current", "currently", "latest", "recent",
    "recently", "this week", "this month", "this year", "this morning",
    "yesterday", "last week", "last month", "right now", "as of",
    # Markets / finance
    "market", "markets", "stock", "stocks", "ticker", "price of",
    "share price", "exchange rate", "crypto", "bitcoin", "ethereum",
    "s&p", "nasdaq", "dow", "fed", "interest rate", "yield", "earnings",
    "inflation", "cpi", "ppi", "jobs report", "unemployment rate",
    # News / events
    "news", "headline", "headlines", "breaking", "press release",
    "announced", "announcement", "launch", "launched", "release date",
    "released", "ship date", "shipped", "ipo", "acquisition",
    "happening", "going on", "update on", "what's up with",
    # Sports / weather
    "score", "scores", "game", "weather", "forecast", "temperature",
    # Politics
    "election", "polls", "primary", "vote", "voted", "supreme court",
    # Lookup-shaped wh- queries that usually need fresh web data
    "who is the", "who's the", "who won", "who founded", "who created",
    "when did", "when was", "when is", "when will",
    "where is", "where's the headquarters",
    "how much does", "how many users", "how big is",
    "ceo of", "founder of", "valuation of", "revenue of", "owner of",
)


def needs_live_web_context(user_message: str) -> bool:
    """Quick heuristic: does this question need real-time web grounding?

    Conservative — false positives cost 5–15s of latency, so we only return True
    on clear time-sensitive or fresh-fact patterns. Trivial chit-chat, math,
    coding, and timeless explainers should return False.
    """
    if not user_message:
        return False
    lowered = user_message.lower()
    if len(lowered) < 8:
        return False  # "hi", "thanks", etc.
    return any(kw in lowered for kw in _LIVE_INFO_KEYWORDS)


# ── Auto-thinking heuristic ──
# Trivial chat → no thinking (fastest). Most general questions → low. Compliance,
# payer, multi-step skills, analytical asks → high.
_HIGH_THINK_KEYWORDS = (
    "compare", "trade-off", "tradeoff", "analyze", "analysis",
    "evaluate", "design", "architect", "architecture", "strategy",
    "strategize", "diagnose", "debug", "root cause", "why does",
    "why is", "explain why", "step by step", "step-by-step", "plan",
    "outline a", "implement", "refactor", "optimi", "calculate",
    "derive", "prove", "what if", "tradeoffs", "pros and cons",
)
_TRIVIAL_PATTERNS = (
    "hi", "hey", "hello", "yo", "sup", "thanks", "thank you", "ty",
    "ok", "okay", "cool", "nice", "got it", "great",
)


def classify_thinking_level(
    user_message: str,
    current_skill: str,
    compliance_mode: bool,
    payer_mode: bool,
    node_mode: bool,
) -> str:
    """Return Gemini thinking level: "none", "low", or "high".

    Used to keep latency low on trivial chat while letting complex / compliance /
    multi-step skill calls actually reason. Falls back to "low" when uncertain.
    """
    if compliance_mode or payer_mode:
        return "high"
    msg = (user_message or "").strip().lower()
    if not msg:
        return "low"
    # Trivial single-token replies
    if len(msg) < 12:
        stripped = msg.rstrip("!.?")
        if stripped in _TRIVIAL_PATTERNS:
            return "none"
    # Skill threads doing real document work benefit from thinking
    if current_skill in {"offer_letter", "review", "workbook", "handbook",
                         "policy", "presentation", "project", "onboarding"}:
        return "high"
    if node_mode:
        return "high"
    if any(kw in msg for kw in _HIGH_THINK_KEYWORDS):
        return "high"
    # Long, structured questions → likely worth thinking
    if len(msg) > 280 or msg.count("\n") > 2:
        return "high"
    return "low"


async def fetch_live_web_context(user_message: str, settings) -> Optional[str]:
    """Run a grounded Gemini call to fetch current web info about the user's question.

    Returns a text block to inject into company_context, or None on failure.
    Grounded calls take 5-15s so this is gated by needs_live_web_context().
    """
    try:
        from google import genai as _genai
        api_key = settings.gemini_api_key
        if not api_key:
            return None
        client = _genai.Client(api_key=api_key)
        model = getattr(settings, "analysis_model", None) or "gemini-3-flash-preview"
        today = date.today().isoformat()
        logger.info("[grounding] Fetching live web context (model=%s) for: %r", model, user_message[:120])
        prompt = (
            f"Today is {today}. The user asked: {user_message!r}\n\n"
            "Use Google Search to find the most relevant, current, factual information "
            "needed to answer this. Return a concise factual briefing (no preamble, no "
            "caveats about being an AI) with the key facts, numbers, quotes, and source "
            "names. If the question isn't actually time-sensitive, return an empty string."
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        tools=[_GOOGLE_SEARCH_TOOL],
                    ),
                )
            ),
            timeout=20,
        )
        text = (response.text or "").strip()
        logger.info("[grounding] Got %d chars of live web context", len(text))
        if not text:
            return None
        return (
            "\n\n=== LIVE WEB CONTEXT (fetched via Google Search grounding just now) ===\n"
            f"{text}\n"
            "=== END LIVE WEB CONTEXT ===\n"
            "CRITICAL INSTRUCTIONS for using the block above:\n"
            "1. The block above IS your real-time data for this question. It was just fetched from Google Search.\n"
            "2. DO NOT say 'I don't have access to live data', 'I can't access real-time information', or any similar disclaimer. That would be a lie — you have the data right here.\n"
            "3. Answer the user's question directly using the specific facts, numbers, and quotes above.\n"
            "4. You may cite the source names mentioned in the block.\n"
            "5. Do NOT output an SVG chart for this reply — it is a news/current-events answer.\n"
        )
    except Exception as e:
        logger.warning("fetch_live_web_context failed: %s", e)
        return None


@dataclass
class AIResponse:
    assistant_reply: str
    structured_update: dict | None = field(default=None)
    mode: str = "general"
    skill: str = "none"
    operation: str = "none"
    confidence: float = 0.0
    missing_fields: list[str] = field(default_factory=list)
    token_usage: dict | None = field(default=None)
    compliance_reasoning: list[dict] | None = field(default=None)
    referenced_categories: list[str] | None = field(default=None)
    referenced_locations: list[str] | None = field(default=None)


class MatchaWorkAIProvider:
    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
        model_override: Optional[str] = None,
        company_id: str = "",
    ) -> AIResponse:
        raise NotImplementedError


class GeminiProvider(MatchaWorkAIProvider):
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self._client = genai.Client(api_key=api_key)
            elif self.settings.use_vertex:
                self._client = genai.Client(
                    vertexai=True,
                    project=self.settings.vertex_project,
                    location=self.settings.vertex_location,
                )
            else:
                self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _get_or_create_cache(self, model: str, static_prompt: str, company_id: str = "") -> Optional[str]:
        """Get or create a Gemini cached content for the static system prompt.

        Returns cache name if successful, None if caching isn't supported or fails.
        Works with any model — silently skips models that don't support caching.
        """
        # Skip models we've already learned don't support caching
        if model in _cache_unsupported_models:
            return None

        prompt_hash = hashlib.md5(static_prompt.encode()).hexdigest()[:12]
        key = f"{company_id}:{prompt_hash}:{model}"

        # Check existing cache
        if key in _cache_registry:
            name, cached_model, expires = _cache_registry[key]
            if datetime.now(timezone.utc) < expires and cached_model == model:
                return name
            # Expired — remove
            del _cache_registry[key]

        try:
            cached = self.client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    system_instruction=static_prompt,
                    ttl=f"{_CACHE_TTL_SECONDS}s",
                ),
            )
            expires = datetime.now(timezone.utc) + timedelta(seconds=_CACHE_TTL_SECONDS)
            _cache_registry[key] = (cached.name, model, expires)
            logger.info("[cache] Created Gemini cache %s for company=%s model=%s", cached.name, company_id, model)
            return cached.name
        except Exception as e:
            err_str = str(e).lower()
            if "not supported" in err_str or "not available" in err_str or "minimum" in err_str or "caching" in err_str:
                _cache_unsupported_models.add(model)
                logger.info("[cache] Model %s does not support caching, skipping future attempts", model)
            else:
                logger.warning("[cache] Failed to create Gemini cache: %s", e)
            return None

    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
        context_summary: Optional[str] = None,
        payer_mode_prompt: Optional[str] = None,
        model_override: Optional[str] = None,
        company_id: str = "",
        compliance_mode: bool = False,
        payer_mode: bool = False,
        node_mode: bool = False,
        blog_mode_state: Optional[str] = None,
    ) -> AIResponse:
        if payer_mode_prompt:
            # Payer mode: dedicated medical policy prompt, plain text response (no JSON)
            window_size = 15 if context_summary else 20
            windowed = messages[-window_size:]
            payer_contents = [
                types.Content(
                    role="model" if m["role"] == "assistant" else "user",
                    parts=[types.Part.from_text(text=m["content"])],
                )
                for m in windowed
                if m.get("content")
            ]
            full_prompt = payer_mode_prompt
            if context_summary:
                full_prompt += f"\n\nPrior conversation summary:\n{context_summary}"

            model = await _get_model(self.settings, model_override, company_id=company_id)
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.client.models.generate_content(
                            model=model,
                            contents=payer_contents,
                            config=types.GenerateContentConfig(
                                system_instruction=full_prompt,
                                temperature=0.2,
                                tools=[_GOOGLE_SEARCH_TOOL],
                            ),
                        )
                    ),
                    timeout=GEMINI_CALL_TIMEOUT,
                )
                reply = response.text or "I couldn't generate a response."
                return AIResponse(assistant_reply=reply, structured_update=None)
            except Exception as e:
                logger.error("Payer mode Gemini call failed: %s", e, exc_info=True)
                return AIResponse(
                    assistant_reply="I encountered an error looking up payer policy data. Please try again.",
                    structured_update=None,
                )

        static_prompt, dynamic_prompt, contents, valid_fields, inferred_skill = self._build_prompt_and_contents(
            messages, current_state, company_context=company_context, slide_index=slide_index,
            context_summary=context_summary, blog_mode_state=blog_mode_state,
        )
        model = await _get_model(self.settings, model_override, company_id=company_id)

        # Auto-pick thinking level based on the latest user message + thread mode.
        latest_user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        thinking_level = classify_thinking_level(
            latest_user_msg,
            inferred_skill,
            compliance_mode=compliance_mode,
            payer_mode=payer_mode,
            node_mode=node_mode,
        )

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_gemini,
                    static_prompt,
                    dynamic_prompt,
                    contents,
                    valid_fields,
                    model,
                    inferred_skill,
                    company_id,
                    thinking_level,
                ),
                timeout=GEMINI_CALL_TIMEOUT,
            )
            return response
        except asyncio.TimeoutError:
            logger.error("Gemini call timed out after %s seconds", GEMINI_CALL_TIMEOUT)
            return AIResponse(
                assistant_reply="I'm taking too long to respond. Please try again.",
                structured_update=None,
            )
        except Exception as e:
            logger.error("Gemini call failed: %s", e, exc_info=True)
            return AIResponse(
                assistant_reply="I encountered an error processing your request. Please try again.",
                structured_update=None,
            )

    def _call_gemini(
        self,
        static_prompt: str,
        dynamic_prompt: str,
        contents: list,
        valid_fields: list[str],
        model: str,
        inferred_skill: str,
        company_id: str = "",
        thinking_level: str = "low",
    ) -> AIResponse:
        import time as _time
        # Try to cache the static prompt (instructions + company context)
        _tc0 = _time.monotonic()
        cache_name = self._get_or_create_cache(model, static_prompt, company_id)
        logger.info("[TIMING] cache lookup/create %.2fs (cache_name=%s)", _time.monotonic() - _tc0, cache_name)

        # Build thinking_config — "none" → budget=0 (disabled, fastest path);
        # "low"/"high" → use named level so the model picks an appropriate budget.
        if thinking_level == "none":
            thinking_cfg = types.ThinkingConfig(thinking_budget=0)
        else:
            thinking_cfg = types.ThinkingConfig(thinking_level=thinking_level)
        logger.info("[TIMING] thinking_level=%s skill=%s", thinking_level, inferred_skill)

        _tg0 = _time.monotonic()
        if cache_name:
            # Cached: static prompt is in the cache. Dynamic context goes as a
            # content prefix because Gemini doesn't allow system_instruction + cached_content together.
            cached_contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=f"[SYSTEM CONTEXT]\n{dynamic_prompt}")]),
                types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]),
                *contents,
            ]
            response = self.client.models.generate_content(
                model=model,
                contents=cached_contents,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=0.2,
                    response_mime_type="application/json",
                    thinking_config=thinking_cfg,
                ),
            )
        else:
            # Fallback: send everything uncached via system_instruction
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=static_prompt + "\n\n" + dynamic_prompt,
                    temperature=0.2,
                    response_mime_type="application/json",
                    thinking_config=thinking_cfg,
                ),
            )
        logger.info("[TIMING] generate_content %.2fs", _time.monotonic() - _tg0)
        raw_text = response.text or ""
        raw_text = _clean_json_text(raw_text)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse Gemini JSON response: %s | Raw: %s",
                e,
                raw_text[:300],
            )
            # Salvage: try to extract the `reply` field via regex so the user
            # at least sees the AI's text instead of the raw JSON envelope.
            salvaged_reply = _extract_reply_field(raw_text) or "I processed your request."
            return AIResponse(
                assistant_reply=salvaged_reply,
                structured_update=None,
                mode="general",
                skill="none",
                operation="none",
            )

        # Gemini sometimes returns a list-wrapped response (e.g. [{...}]) even
        # though the prompt asks for an object. Try to unwrap or salvage.
        if isinstance(parsed, list):
            # Case 1: single-item list containing the expected response object
            if len(parsed) == 1 and isinstance(parsed[0], dict) and (
                "mode" in parsed[0] or "skill" in parsed[0] or "reply" in parsed[0]
            ):
                parsed = parsed[0]
            # Case 2: bare list of section-shaped dicts — treat as project_sections
            elif (
                inferred_skill == "project"
                and all(isinstance(item, dict) and ("title" in item or "content" in item) for item in parsed)
            ):
                logger.info("Salvaging bare section list as project_sections update")
                parsed = {
                    "mode": "skill",
                    "skill": "project",
                    "operation": "update",
                    "confidence": 0.8,
                    "updates": {"project_sections": parsed},
                    "reply": "I've drafted the posting sections. Review them in the panel on the right.",
                }
            else:
                logger.warning(
                    "Gemini returned list response, cannot unwrap: %s",
                    raw_text[:300],
                )
                return AIResponse(
                    assistant_reply="I processed your request.",
                    structured_update=None,
                    mode="general",
                    skill="none",
                    operation="none",
                )

        if not isinstance(parsed, dict):
            logger.warning(
                "Gemini returned non-dict response (%s): %s",
                type(parsed).__name__,
                raw_text[:300],
            )
            return AIResponse(
                assistant_reply="I processed your request.",
                structured_update=None,
                mode="general",
                skill="none",
                operation="none",
            )

        reply = parsed.get("reply", "Done.")
        raw_updates = parsed.get("updates", {})
        if isinstance(raw_updates, dict):
            allowed = set(valid_fields)
            updates = {k: v for k, v in raw_updates.items() if k in allowed}
        else:
            updates = {}

        raw_mode = str(parsed.get("mode") or "").strip().lower()
        mode = raw_mode if raw_mode in SUPPORTED_AI_MODES else ""

        # Backward compatibility with older reply/updates-only JSON.
        if not mode:
            mode = "skill" if updates else "general"

        raw_skill = str(parsed.get("skill") or "").strip().lower()
        skill = raw_skill if raw_skill in SUPPORTED_AI_SKILLS else ""
        if not skill:
            skill = inferred_skill if mode == "skill" else "none"

        raw_operation = str(parsed.get("operation") or "").strip().lower()
        operation = raw_operation if raw_operation in SUPPORTED_AI_OPERATIONS else ""
        if not operation:
            if mode == "skill":
                operation = "update" if updates else "track"
            else:
                operation = "none"

        raw_confidence = parsed.get("confidence")
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.8 if mode == "skill" else 0.5
        confidence = max(0.0, min(1.0, confidence))

        raw_missing_fields = parsed.get("missing_fields", [])
        if isinstance(raw_missing_fields, list):
            missing_fields = [str(item).strip() for item in raw_missing_fields if str(item).strip()]
        else:
            missing_fields = []

        raw_compliance_reasoning = parsed.get("compliance_reasoning")
        compliance_reasoning = None
        if isinstance(raw_compliance_reasoning, list) and raw_compliance_reasoning:
            compliance_reasoning = raw_compliance_reasoning

        raw_referenced_categories = parsed.get("referenced_categories")
        referenced_categories = None
        if isinstance(raw_referenced_categories, list) and raw_referenced_categories:
            referenced_categories = [str(c).strip() for c in raw_referenced_categories if str(c).strip()]
            if not referenced_categories:
                referenced_categories = None

        raw_referenced_locations = parsed.get("referenced_locations")
        referenced_locations = None
        if isinstance(raw_referenced_locations, list) and raw_referenced_locations:
            referenced_locations = [str(loc).strip() for loc in raw_referenced_locations if str(loc).strip()]
            if not referenced_locations:
                referenced_locations = None

        return AIResponse(
            assistant_reply=reply,
            structured_update=updates if updates else None,
            mode=mode,
            skill=skill,
            operation=operation,
            confidence=confidence,
            missing_fields=missing_fields,
            token_usage=self._extract_usage_metadata(response, model),
            compliance_reasoning=compliance_reasoning,
            referenced_categories=referenced_categories,
            referenced_locations=referenced_locations,
        )

    async def estimate_usage(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
    ) -> dict:
        static_prompt, dynamic_prompt, _, _, _ = self._build_prompt_and_contents(
            messages, current_state, company_context=company_context, slide_index=slide_index
        )
        model = await _get_model(self.settings)
        windowed = messages[-20:]
        char_count = len(static_prompt) + len(dynamic_prompt) + sum(len(str(msg.get("content", ""))) for msg in windowed)
        prompt_tokens = max(1, char_count // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": None,
            "total_tokens": prompt_tokens,
            "estimated": True,
            "model": model,
        }

    def _build_prompt_and_contents(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
        context_summary: Optional[str] = None,
        blog_mode_state: Optional[str] = None,
    ) -> tuple[str, str, list, list[str], str]:
        """Returns (static_prompt, dynamic_prompt, contents, valid_fields, skill).

        static_prompt: instructions + company context (cacheable, changes slowly)
        dynamic_prompt: current_state + summary + slide lock (changes per message)

        When blog_mode_state is provided (set by the route for project_type='blog'),
        a dedicated blog-only system prompt is used instead of the generic
        multi-skill prompt. This removes every non-blog skill from the AI's
        vocabulary so it cannot hallucinate creating a project document.
        """
        window_size = 15 if context_summary else 20
        windowed = messages[-window_size:]

        # Dedicated blog mode — swap the entire system prompt. Bypasses the
        # generic multi-skill prompt so the AI can't hallucinate using project /
        # workbook / other skills on a blog chat.
        if blog_mode_state is not None:
            static_prompt = MATCHA_WORK_BLOG_SYSTEM_PROMPT.format(
                today=date.today().isoformat(),
                company_context=company_context,
                blog_state=blog_mode_state,
            )
            if context_summary:
                static_prompt += (
                    f"\n\n## Conversation Context Summary\n"
                    f"(Earlier messages were summarized to preserve context)\n"
                    f"{context_summary}\n"
                )
            blog_contents: list = []
            for msg in windowed:
                role = "user" if msg["role"] == "user" else "model"
                parts: list = []
                if role == "user":
                    for image_bytes, mime in (msg.get("image_parts") or []):
                        if image_bytes:
                            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
                text_content = msg.get("content") or ""
                if text_content or not parts:
                    parts.append(types.Part(text=text_content))
                blog_contents.append(types.Content(role=role, parts=parts))
            return static_prompt, "", blog_contents, list(BLOG_FIELDS), "blog"

        current_skill = _infer_skill_from_state(current_state)
        if current_skill == "offer_letter":
            valid_fields = OFFER_LETTER_FIELDS
        elif current_skill == "review":
            valid_fields = REVIEW_FIELDS
        elif current_skill == "workbook":
            valid_fields = WORKBOOK_FIELDS
        elif current_skill == "onboarding":
            valid_fields = ONBOARDING_FIELDS
        elif current_skill == "presentation":
            valid_fields = PRESENTATION_FIELDS
        elif current_skill == "handbook":
            valid_fields = HANDBOOK_FIELDS
        elif current_skill == "policy":
            valid_fields = POLICY_FIELDS
        elif current_skill == "project":
            valid_fields = PROJECT_FIELDS
        elif current_skill == "blog":
            valid_fields = BLOG_FIELDS
        else:
            valid_fields = OFFER_LETTER_FIELDS + REVIEW_FIELDS + WORKBOOK_FIELDS + ONBOARDING_FIELDS + PRESENTATION_FIELDS + HANDBOOK_FIELDS + POLICY_FIELDS + PROJECT_FIELDS + BLOG_FIELDS

        # Static part — instructions + company context (cached at Gemini API level)
        static_prompt = MATCHA_WORK_STATIC_PROMPT_TEMPLATE.format(
            today=date.today().isoformat(),
            company_context=company_context,
        )

        # Dynamic part — per-message state (never cached)
        dynamic_prompt = MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE.format(
            current_skill=current_skill,
            current_state=json.dumps(current_state, default=str, separators=(",", ":")),
            valid_fields=", ".join(valid_fields),
        )

        # Recruiting project context — add specific instructions
        # (The route-level _inject_recruiting_project_context provides the primary
        #  context via company_context; this adds post-finalization details from thread state)
        if current_skill == "project" and current_state.get("posting"):
            posting = current_state.get("posting", {})
            candidates_count = len(current_state.get("candidates", []))
            is_finalized = bool(posting.get("finalized"))
            dynamic_prompt += f"""
RECRUITING PROJECT UPDATE:
- Posting finalized: {is_finalized}
- Candidates: {candidates_count}
"""

        if context_summary:
            dynamic_prompt += (
                f"\n\n## Conversation Context Summary\n"
                f"(Earlier messages were summarized to preserve context)\n"
                f"{context_summary}\n"
            )

        if slide_index is not None and current_skill in ("presentation", "workbook"):
            slides = current_state.get("slides") or []
            if not slides:
                pres = current_state.get("presentation")
                if isinstance(pres, dict):
                    slides = pres.get("slides") or []
            slide_title = ""
            if 0 <= slide_index < len(slides):
                slide_title = slides[slide_index].get("title", "") if isinstance(slides[slide_index], dict) else ""
            label = f' "{slide_title}"' if slide_title else ""
            total = len(slides)
            dynamic_prompt += (
                f"\n\n--- SLIDE LOCK ACTIVE ---\n"
                f"The user has selected Slide {slide_index + 1}/{total}{label} (0-based index {slide_index}). "
                f"You MUST only modify this slide. In your updates JSON:\n"
                f"- The 'slides' array must be identical to current_state except at index {slide_index}\n"
                f"- Do NOT change any other slide's title, bullets, or speaker_notes\n"
                f"- Do NOT include presentation_title, subtitle, theme, or cover_image_url in updates\n"
                f"- Only include 'slides' in your updates object\n"
                f"- CRITICAL: The user is requesting a CHANGE to the current slide. You must produce "
                f"updated content that differs from current_state. If the user asks to add, remove, or "
                f"modify something, the slide in your response MUST reflect that change. Never return "
                f"the slide unchanged when the user has requested a modification.\n"
                f"--- END SLIDE LOCK ---"
            )

        contents = []
        for msg in windowed:
            role = "user" if msg["role"] == "user" else "model"
            parts: list = []
            # Multimodal: attach any pre-fetched image bytes. The route layer
            # populates image_parts via fetch_image_parts_for_messages() so
            # this pure builder never does blocking I/O.
            if role == "user":
                for image_bytes, mime in (msg.get("image_parts") or []):
                    if image_bytes:
                        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
            text_content = msg.get("content") or ""
            if text_content or not parts:
                parts.append(types.Part(text=text_content))
            contents.append(types.Content(role=role, parts=parts))
        return static_prompt, dynamic_prompt, contents, valid_fields, current_skill

    def _extract_usage_metadata(self, response: Any, model: str) -> Optional[dict]:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None

        def _get(*keys: str) -> Optional[Any]:
            for key in keys:
                value = getattr(usage, key, None)
                if value is None and isinstance(usage, dict):
                    value = usage.get(key)
                if value is not None:
                    return value
            return None

        def _to_int(value: Any) -> Optional[int]:
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        prompt_tokens = _to_int(_get("prompt_token_count", "input_token_count", "promptTokenCount"))
        completion_tokens = _to_int(
            _get("candidates_token_count", "output_token_count", "candidatesTokenCount")
        )
        cached_tokens = _to_int(_get("cached_content_token_count")) or 0
        total_tokens = _to_int(_get("total_token_count", "totalTokenCount"))

        # Gemini's prompt_token_count includes cached tokens. Subtract them
        # so users aren't charged for cached content.
        if cached_tokens > 0 and prompt_tokens is not None:
            prompt_tokens = max(0, prompt_tokens - cached_tokens)

        # Recompute total from the adjusted prompt + completion
        if prompt_tokens is not None or completion_tokens is not None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "estimated": False,
            "model": model,
        }


COMPACTION_PROMPT = (
    "Summarize this conversation history into a concise context block (max 200 words). "
    "Include: key decisions made, document type, specific values/names/dates mentioned, "
    "user preferences expressed, and current state of the work. "
    "Do NOT include greetings or filler. Return ONLY the summary text, no JSON."
)

COMPACTION_MODEL = "gemini-2.0-flash"
COMPACTION_THRESHOLD = 30


async def compact_conversation(
    messages: list[dict],
    client: genai.Client,
) -> Optional[str]:
    """Summarize older messages into a short context block using a fast model."""
    if len(messages) < COMPACTION_THRESHOLD:
        return None

    # Summarize all but the most recent 15 messages
    older = messages[:-15]
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in older
    )

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=COMPACTION_MODEL,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=conversation_text)],
                )],
                config=types.GenerateContentConfig(
                    system_instruction=COMPACTION_PROMPT,
                    temperature=0.1,
                ),
            ),
            timeout=30,
        )
        summary = (response.text or "").strip()
        if summary:
            return summary
    except Exception:
        logger.warning("Conversation compaction failed", exc_info=True)

    return None


_provider: Optional[GeminiProvider] = None


def get_ai_provider() -> GeminiProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider
