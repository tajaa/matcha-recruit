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

# Google Search grounding tool — enables real-time web data in all MW responses
_GOOGLE_SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

from ...config import get_settings
from ...core.services.platform_settings import get_matcha_work_model_mode
from ..models.matcha_work import HandbookDocument, OfferLetterDocument, OnboardingDocument, PolicyDocument, PresentationDocument, ProjectDocument, ReviewDocument, WorkbookDocument

logger = logging.getLogger(__name__)

GEMINI_CALL_TIMEOUT = 120

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

SUPPORTED_AI_MODES = {"skill", "general", "clarify", "refuse"}
SUPPORTED_AI_SKILLS = {"chat", "offer_letter", "review", "workbook", "onboarding", "presentation", "handbook", "policy", "resume_batch", "inventory", "project", "none"}
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
MATCHA_WORK_STATIC_PROMPT_TEMPLATE = """You are Matcha Work, an HR copilot for US employers.

Today's date: {today}

Mission:
1) Provide high-quality general HR guidance for US teams.
2) Detect and execute supported Matcha Work skills from natural language.
3) Ask concise clarifying questions when required inputs are missing.
4) Never block normal Q&A just because no skill is invoked.
{company_context}

Supported skills:
- offer_letter: create/update offer letter content, save_draft, send_draft, finalize
- review: create/update anonymized review content, collect recipient_emails, send review requests, track responses
- workbook: create/update HR workbook documents and section content, generate_presentation
- project: create a project document for the user to build reports, plans, or briefs.
  Use this when the user says "create a project", "start a project", "make a plan", "leadership plan", "research report", etc.
  Fields: project_title (string), project_sections (array of objects with id, title, content), project_status ("drafting").
  The user will add content to the project from chat messages via the side panel. Just set the title and an empty sections array to initialize.
  Do NOT confuse with workbook — projects are user-edited documents, not AI-generated workbooks.
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

Mode selection:
- mode=skill when user clearly asks for a supported action.
- mode=general for informational/advisory HR questions.
- mode=clarify when action is requested but required details are missing.
- mode=refuse only for unsafe/disallowed or unsupported actions.

US HR policy:
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
  "skill": "offer_letter|review|workbook|onboarding|presentation|handbook|policy|none",
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
When your reply involves quantitative data, comparisons, trends, or breakdowns that would benefit
from a visual representation, include an inline SVG chart directly in the "reply" field.
Guidelines for charts:
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

async def _get_model(settings, model_override: str | None = None) -> str:
    if model_override and model_override in SUPPORTED_MODELS:
        return model_override
    mode = await get_matcha_work_model_mode()
    if mode == "heavy":
        return "gemini-3.1-pro-preview"
    return settings.analysis_model


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
                    tools=[_GOOGLE_SEARCH_TOOL],
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

            model = await _get_model(self.settings, model_override)
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
            context_summary=context_summary,
        )
        model = await _get_model(self.settings, model_override)

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
    ) -> AIResponse:
        # Try to cache the static prompt (instructions + company context)
        cache_name = self._get_or_create_cache(model, static_prompt, company_id)

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
                    tools=[_GOOGLE_SEARCH_TOOL],
                ),
            )
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
            return AIResponse(
                assistant_reply=raw_text or "I processed your request.",
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
    ) -> tuple[str, str, list, list[str], str]:
        """Returns (static_prompt, dynamic_prompt, contents, valid_fields, skill).

        static_prompt: instructions + company context (cacheable, changes slowly)
        dynamic_prompt: current_state + summary + slide lock (changes per message)
        """
        window_size = 15 if context_summary else 20
        windowed = messages[-window_size:]
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
        else:
            valid_fields = OFFER_LETTER_FIELDS + REVIEW_FIELDS + WORKBOOK_FIELDS + ONBOARDING_FIELDS + PRESENTATION_FIELDS + HANDBOOK_FIELDS + POLICY_FIELDS + PROJECT_FIELDS

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
        if current_skill == "project" and current_state.get("posting"):
            posting = current_state.get("posting", {})
            candidates_count = len(current_state.get("candidates", []))
            is_finalized = bool(posting.get("finalized"))
            dynamic_prompt += f"""
RECRUITING PROJECT CONTEXT:
You are helping with a recruiting/hiring project.
- Posting finalized: {is_finalized}
- Candidates: {candidates_count}

IMPORTANT RULES FOR RECRUITING PROJECTS:
1. NEVER output raw JSON, code, SVG, or internal state in your responses.
2. Always respond in clear, human-readable language.
3. To send interviews: tell the user to select candidates in the pipeline panel and click "Send Interviews". You cannot send interviews via chat.
4. To upload resumes: tell the user to click the paperclip icon or drag-and-drop PDF resumes into the chat.
5. To analyze candidates: tell the user to click "Analyze" in the Candidates tab of the pipeline panel.
6. Keep responses concise and actionable — guide the user through the recruiting workflow step by step.
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
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])],
                )
            )
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
