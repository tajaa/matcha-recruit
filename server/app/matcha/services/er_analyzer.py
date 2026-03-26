"""ER Analyzer Service for ER Copilot.

AI-powered analysis for Employee Relations investigations:
- Timeline Reconstruction
- Discrepancy Detection
- Policy Violation Check
- Summary Report Generation
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any, AsyncIterator, Callable

from google import genai

logger = logging.getLogger(__name__)

FALLBACK_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
)


# ===========================================
# Prompts
# ===========================================

TIMELINE_RECONSTRUCTION_PROMPT = """You are an Employee Relations investigation assistant. Analyze these witness statements and documents to construct a chronological timeline of events.

DOCUMENTS:
{documents}

Your task:
1. Extract every date, time, and temporal reference mentioned
2. Create a unified chronological timeline
3. Note which witness/document each event comes from
4. Flag any gaps or unclear periods

For each event in the timeline, provide:
- date: The date (YYYY-MM-DD format if known, or approximate description)
- time: The time if mentioned (HH:MM format), or null
- description: What happened
- participants: List of people involved
- source_document_id: The document ID this came from
- source_location: Where in the document (e.g., "Page 2" or "Lines 45-50")
- confidence: "high" if explicitly stated, "medium" if reasonably inferred, "low" if uncertain
- evidence_quote: Direct quote from the source supporting this event

Return ONLY a JSON object with this structure:
{{
    "events": [
        {{
            "date": "2024-11-15",
            "time": "14:30",
            "description": "Complainant observed respondent making inappropriate comments",
            "participants": ["Jane Smith", "John Doe"],
            "source_document_id": "doc-uuid-here",
            "source_location": "Page 2, Paragraph 3",
            "confidence": "high",
            "evidence_quote": "At approximately 2:30 PM, I witnessed John make the following statement..."
        }}
    ],
    "gaps_identified": ["No documentation for November 16-20", "No witnesses for evening shift"],
    "timeline_summary": "2-3 sentence summary of the overall timeline"
}}

Be thorough but objective. Only include events that are supported by the evidence."""


DISCREPANCY_DETECTION_PROMPT = """You are an Employee Relations investigation assistant. Analyze these witness statements for discrepancies and inconsistencies.

DOCUMENTS:
{documents}

Your task:
1. Identify direct contradictions between witnesses
2. Find timeline conflicts (events described at same time but conflicting)
3. Detect internal inconsistencies within a single witness's account
4. Flag implausible claims
5. Note significant omissions (information one witness mentions that others don't)

For each discrepancy, assess the severity:
- "high": Major contradiction that affects core facts
- "medium": Notable inconsistency that needs clarification
- "low": Minor discrepancy that may be explained by perspective

Return ONLY a JSON object with this structure:
{{
    "discrepancies": [
        {{
            "subject": "Whether the door was open or closed during the conversation",
            "severity": "high",
            "statement_a": "The door was open the entire time",
            "statement_b": "I knocked because the door was closed",
            "source_a": "Jane Smith — Page 3, Line 15",
            "source_b": "Bob Johnson — Page 2, Line 8",
            "notes": "This discrepancy is significant because it affects whether the conversation could have been overheard"
        }}
    ],
    "credibility_notes": [
        {{
            "witness": "Jane Smith",
            "note": "Generally consistent account",
            "factors": ["Timeline aligns with other evidence", "No internal contradictions"]
        }}
    ],
    "summary": "Overview of key discrepancies and their implications for the investigation"
}}

STRICT TEMPORAL ANCHORING:
- Do not automatically assume cause-and-effect just because two events happen in sequence.
- Map digital evidence (e.g., a chat message, email, log entry) to its specific referenced timestamp or event.
- Do not allow one actor's subjective interpretation of a message to override the objective timestamp of when the referenced event actually occurred.
- Correlation in timeline position does not imply causation.

Be neutral and objective. Do not assume which account is correct."""


POLICY_VIOLATION_PROMPT = """You are an Employee Relations investigation assistant. Analyze the evidence against the company policy to identify potential violations.

POLICY DOCUMENT:
{policy}

EVIDENCE DOCUMENTS:
{evidence}

Your task:
1. Identify specific policy sections that may have been violated
2. For each potential violation, cite the exact policy text
3. Link to specific evidence supporting the violation
4. Assess severity and relevance

CRITICAL MATCHING RULES:
- Only flag a violation when the evidence DIRECTLY AND SPECIFICALLY relates to the policy section's subject matter.
- Do NOT match evidence to a policy section simply because they share a broad theme. For example, do NOT match safety violations (e.g., equipment hazards, lockout/tagout) to a dress code or appearance policy just because both loosely relate to "professionalism" or "workplace standards."
- Each violation must pass this test: would a reasonable HR professional, reading the specific policy text and the specific evidence, agree that this evidence describes conduct the policy was written to address?

SEVERITY CRITERIA:
- "major": Clear, direct violation with strong supporting evidence. The policy language specifically covers the conduct described.
- "minor": Possible violation with circumstantial evidence, or the policy applies but the conduct is borderline.

RELEVANCE CRITERIA:
- "high": The evidence directly describes conduct that the policy section was specifically written to address.
- "medium": The evidence relates to the policy section's subject matter but the connection requires some interpretation.
- "low": The connection between evidence and policy is tenuous, thematic, or requires a stretch to justify. These should generally NOT be included.

Return ONLY a JSON object with this structure:
{{
    "violations": [
        {{
            "policy_section": "Section 3.2: Workplace Harassment",
            "policy_text": "Employees shall not engage in conduct that creates an intimidating, hostile, or offensive work environment",
            "severity": "major",
            "relevance": "high",
            "evidence": [
                {{
                    "source_document_id": "doc-uuid",
                    "quote": "He said 'you people don't belong here'",
                    "location": "Page 2, Lines 12-14",
                    "how_it_violates": "This statement could constitute harassment based on protected class"
                }}
            ],
            "analysis": "Multiple witnesses confirm the statement was made, and it appears to target a protected class"
        }}
    ],
    "policies_potentially_applicable": [
        "Section 4.1: Professional Conduct - May also be relevant",
        "Section 5.3: Discrimination - Consider if pattern exists"
    ],
    "summary": "Overview of findings and their severity"
}}

Be thorough but fair. Note both supporting and potentially mitigating evidence. Prioritize precision over volume — it is better to return fewer, well-matched violations than many tenuous ones."""


SUMMARY_REPORT_PROMPT = """You are an Employee Relations investigation assistant. Generate a professional investigation summary report.

CASE INFORMATION:
{case_info}

TIMELINE:
{timeline}

DISCREPANCIES:
{discrepancies}

POLICY ANALYSIS:
{policy_analysis}

Generate a comprehensive, neutral investigation summary report suitable for HR leadership and legal review. The report should:

1. Be written in third person, passive voice
2. Present facts objectively without editorial commentary
3. Distinguish between established facts, witness statements, and investigator observations
4. Note areas where evidence is inconclusive
5. Be suitable for potential legal proceedings

Structure the report with these sections:
1. Investigation Overview (dates, parties, allegation summary)
2. Investigation Process (documents reviewed, interviews conducted)
3. Factual Findings (chronological account based on evidence)
4. Analysis of Evidence (credibility assessment, discrepancies)
5. Policy Analysis (potential violations identified)
6. Conclusion (findings and any unresolved questions)

Return the report as plain text, professionally formatted."""


DETERMINATION_LETTER_PROMPT = """You are an Employee Relations investigation assistant. Generate a professional determination letter.

CASE INFORMATION:
{case_info}

DETERMINATION: {determination}

SUMMARY OF FINDINGS:
{findings}

Generate a formal determination letter that:
1. Is addressed to the appropriate party
2. Summarizes the investigation without rehashing every detail
3. Clearly states the determination: {determination}
4. Notes any corrective actions (if substantiated)
5. Explains next steps and resources
6. Is written in a professional, neutral tone

CRITICAL — EVIDENCE ATTRIBUTION:
- When citing facts, distinguish between findings from directly reviewed documents (uploaded evidence) and claims made in witness testimony.
- Do NOT state that "records confirm" or "HR records show" something unless the actual records (Teams messages, emails, system logs) were uploaded and reviewed. If a fact comes from a witness's account of a record, attribute it to the witness: "Per [witness name]'s account..." or "According to testimony from [name]..."
- This distinction is essential for the legal defensibility of the determination.

The letter should be suitable for delivery to the employee and potential inclusion in personnel file.

Return the letter as plain text, professionally formatted."""

DETERMINATION_CONFIDENCE_PROMPT = """You are evaluating the strength of evidence in an internal company policy investigation.
Your job is to assess how confident we can be that a policy infraction occurred, based on the
available evidence. Score from 0.10 (case just opened, no evidence yet) to 0.95 (overwhelming evidence).

Evaluate these four signals:

1. DUAL CONFIRMATION — Is the reported issue supported by both evidence AND at least one
   witness who corroborates it? Look for multiple people describing the same behavior/incident.

2. ADMISSION — Has the subject acknowledged, admitted, or taken responsibility for the
   act or policy violation in any interview or statement? Look for direct or indirect admissions.

3. DIMINISHING RETURNS — Have multiple people been interviewed with consistent accounts
   and no significant new information emerging? This suggests further investigation
   is unlikely to change the picture.

4. HARD EVIDENCE — Is there documented proof (data, records, policy text matched to actions)
   that directly demonstrates a policy violation?

CRITICAL EVIDENCE DISTINCTION:
- Only count documents listed in EVIDENCE DOCUMENTS as "hard evidence." If a witness DESCRIBES a Teams message, email, or log entry but that record is not in the uploaded documents, it is TESTIMONY about evidence, not the evidence itself.
- A witness saying "the Teams message was sent Friday" is NOT the same as having the Teams message. The witness's claim must be corroborated by the actual record to count as hard evidence.
- When scoring confidence, clearly note if key claims rest on testimony alone vs. direct documentary proof.

CASE INFORMATION:
{case_info}

EVIDENCE DOCUMENTS:
{evidence_overview}

TRANSCRIPT EXCERPTS:
{transcript_excerpts}

ANALYSIS RESULTS:
Timeline: {timeline_summary}
Discrepancies: {discrepancies_summary}
Policy findings: {policy_summary}

Return ONLY a JSON object:
{{
  "confidence": 0.XX,
  "signals": [
    {{
      "name": "hard_evidence" | "admission" | "dual_confirmation" | "diminishing_returns",
      "present": true/false,
      "strength": "strong" | "moderate" | "weak",
      "reasoning": "1 sentence explaining why this signal is/isn't present"
    }}
  ],
  "summary": "1-2 sentence overall assessment of evidence strength"
}}

Rules:
- confidence must be between 0.10 and 0.95
- Always evaluate all 4 signals even if not present (set present: false)
- Be calibrated: 0.10-0.30 = early/weak, 0.30-0.50 = building, 0.50-0.70 = substantial, 0.70-0.95 = strong/overwhelming
- A single strong signal (clear admission, hard proof) can justify 0.50+
- Multiple moderate signals compound to higher confidence
- Do NOT inflate confidence — be honest about gaps"""


OUTCOME_ANALYSIS_PROMPT = """You are an Employee Relations investigation assistant. Based on the evidence, analysis, and company policy, evaluate this case and recommend 2-4 possible outcome paths.

CASE INFORMATION:
{case_info}

ANALYSIS SUMMARY:
{analysis_summary}

POLICY FINDINGS:
{policy_findings}

PAST CASE PRECEDENT (this company):
{precedent_stats}

ABSOLUTE RULES — READ BEFORE GENERATING ANY OUTPUT:

1. NO IMMUNITY FOR ANY PARTY: Filing a complaint does NOT shield the complainant from accountability.
   - If the complainant committed policy violations (discriminatory remarks, skipped safety/medication protocols, harassment, etc.), they MUST receive disciplinary action in party_actions — NEVER "No Action."
   - If the respondent lied during the investigation, retaliated, or destroyed evidence, these are AGGRAVATING factors. Escalate to termination, not just a warning.
   - Dishonesty during an HR investigation is itself a terminable offense. State this explicitly.
   - "No Action" for ANY party is ONLY permitted if the investigation found zero evidence of wrongdoing by that party.

2. MULTI-ACTOR: Each outcome MUST be a COMBINED recommendation covering ALL non-witness parties.
   - Include a "party_actions" array with an entry for EVERY non-witness party.
   - EVERY party_action must have a substantive action. Do not default to "No Action" for complainants.
   - The action_label must summarize actions for all parties (e.g., "Written Warning for [complainant] + Termination for [respondent]").

3. CLOSED SYSTEM: Only reference names, events, policies, and evidence from the provided data. Do not fabricate.

For each outcome path, provide:
- determination: "substantiated", "unsubstantiated", or "inconclusive"
- recommended_action: one of "termination", "disciplinary_action", "retraining", "no_action", "resignation", "other"
- action_label: Human-readable label summarizing actions for ALL parties
- reasoning: 2-3 sentences citing specific evidence from the provided data only
- policy_basis: Which company policies from POLICY FINDINGS support this outcome
- hr_considerations: Best practice notes, risks, or mitigating factors
- precedent_note: How this aligns with the PAST CASE PRECEDENT stats provided
- confidence: "high", "medium", or "low" based on evidence strength
- party_actions: Array of per-party action recommendations. REQUIRED when multiple non-witness parties exist. Each: {{"name": "...", "role": "complainant"|"respondent", "action": "short action label", "detail": "1-2 sentence explanation citing evidence"}}

Order outcomes from most to least supported by evidence, highest confidence first.

Return ONLY a JSON object with this structure:
{{
  "outcomes": [
    {{
      "determination": "substantiated",
      "recommended_action": "disciplinary_action",
      "action_label": "Written Warning for [complainant] + Termination for [respondent]",
      "reasoning": "Cite specific facts from CASE INFORMATION and ANALYSIS SUMMARY only.",
      "policy_basis": "Cite policies from POLICY FINDINGS only.",
      "hr_considerations": "Note legal exposure, precedent alignment, and mitigation steps.",
      "precedent_note": "Reference the precedent stats above.",
      "confidence": "high",
      "party_actions": [
        {{"name": "ACTUAL NAME", "role": "complainant", "action": "Written Warning", "detail": "Complainant's own violations (cite specific evidence) require corrective action despite being the victim of the original complaint."}},
        {{"name": "ACTUAL NAME", "role": "respondent", "action": "Termination", "detail": "Respondent's retaliation and dishonesty during investigation constitute gross misconduct."}}
      ]
    }}
  ],
  "case_summary": "2-3 sentence executive summary"
}}

SYSTEM DATA PRIORITY:
- When evaluating the validity of a performance action, objective system data (audit logs, system records, documented metrics) must be weighted significantly higher than interpersonal chat sentiment or subjective interpretation.
- Do NOT recommend overturning a data-backed performance action solely because concurrent interpersonal conflict exists.
- If system records confirm the performance issue, the performance action stands as valid regardless of unrelated interpersonal disputes.

STRICT TEMPORAL ANCHORING:
- Do not automatically assume cause-and-effect just because two events happen in sequence.
- Strictly map digital evidence (chat messages, emails, log entries) to their specific referenced timestamps or events.
- Do not allow one actor's subjective interpretation of a message to override the objective timestamp of when the referenced event actually occurred.
- Correlation in timeline position does not imply causation — require explicit evidence of causal linkage.

CRITICAL — CLOSED-SYSTEM CONSTRAINT (MANDATORY):
- You are operating as a CLOSED SYSTEM. You may ONLY reference information present in the CASE INFORMATION, ANALYSIS SUMMARY, and POLICY FINDINGS provided above.
- NAMES: You may ONLY use names that appear in case_info.involved_parties or in the case description/analysis text. Do NOT invent, substitute, or fabricate any person's name. If a party's name is not in the data, refer to them by role ("the complainant", "the respondent").
- EVENTS: You may ONLY describe events that are explicitly mentioned in the case description, analysis summary, or uploaded documents. Do NOT fabricate incidents, conversations, forensic findings, or specific dates that are not in the provided data.
- EVIDENCE: Distinguish between documents actually uploaded to the system and records merely REFERENCED in testimony. If a witness describes a Teams message, email, or log but that record was not uploaded, say "according to [name]'s account" — NOT "records confirm" or "forensic logs show."
- POLICY: Only cite policies that appear in the POLICY FINDINGS section. Do not invent policy names, section numbers, or framework titles.
- If the provided data is insufficient to support a specific claim, say so honestly rather than filling gaps with fabricated details.

Rules:
- Provide 2 to 4 outcome paths, sorted by evidence strength
- Always include at least one path with a different determination when evidence allows
- Be objective — present options, don't advocate for one
- confidence must be "high", "medium", or "low"
- Keep reasoning concise but cite specific evidence
- If precedent data is sparse, say so honestly in precedent_note"""

HEALTHCARE_OUTCOME_RULES = """
HEALTHCARE JUST CULTURE FRAMEWORK — MANDATORY FOR THIS COMPANY
This company operates in healthcare ({specialties_context}). Apply the following overrides:

RANKING HIERARCHY (overrides default "sort by evidence strength"):
1. Severity of potential patient harm (highest weight)
2. Evidence strength
3. Historical precedent (lowest weight — see precedent override below)

SAFETY PROTOCOL RULES:
- High-alert medications include: chemotherapy agents, opioids, insulin, anticoagulants, concentrated electrolytes, neuromuscular blocking agents, and parenteral nutrition.
- Bypassing a safety protocol for ANY high-alert medication carries PRESUMPTIVE LETHAL RISK.
- Evaluate by what COULD have happened (potential harm), not what DID happen (actual outcome). A near-miss is NOT a mitigating factor — it is luck, not competence.

JUST CULTURE DISTINCTIONS (must be reflected in reasoning):
- Human error (slip/lapse — e.g., miscounted dose under fatigue): system-level fix + retraining. Recommended action: retraining.
- At-risk behavior (conscious choice to bypass a known safety step — e.g., skipping double-check because "it takes too long"): disciplinary action scaling to termination based on severity of potential harm. For high-alert medications, recommended action: termination.
- Reckless behavior (conscious disregard of substantial and unjustifiable risk — e.g., overriding safety alert without clinical justification): termination is the FIRST-ranked outcome, not an alternative.

PRECEDENT OVERRIDE:
- Past lenient outcomes for similar violations do NOT lower the ranking of severe-harm outcomes.
- If historical data shows warnings/retraining for safety protocol bypasses, note in precedent_note that prior outcomes may reflect institutional under-response and should not set the standard for patient safety cases.

Apply these rules to the outcome ranking. The most severe clinically-appropriate action must be ranked FIRST when the violation involves potential patient harm, regardless of what past cases show.
"""


SUGGESTED_GUIDANCE_PROMPT = """You are an Employee Relations investigation assistant generating interactive next-step guidance for an active case.

CASE INFORMATION:
{case_info}

INTAKE CONTEXT:
{intake_context}

EVIDENCE OVERVIEW:
{evidence_overview}

ANALYSIS RESULTS:
{analysis_results}

DOCUMENT EXCERPTS (from uploaded evidence):
{document_excerpts}

ANALYSES ALREADY COMPLETED: {analyses_completed}

IMPORTANT: The system automatically handles timeline reconstruction, policy checking,
and discrepancy detection. Do NOT suggest cards that trigger these system features.
Instead, tell the HUMAN INVESTIGATOR what to do outside this system:
- Conduct witness interviews (who specifically, what to ask)
- Gather physical/electronic evidence (timecards, emails, safety logs, CCTV)
- Request records from other departments (payroll, facilities, IT, legal)
- Contact regulatory agencies (OSHA, EEOC, etc.) when warranted
- Review/search specific evidence already uploaded for missing context

Use "run_analysis" ONLY if a specific analysis failed and should be retried, never as a primary recommendation.
Prefer action types: "upload_document", "search_evidence", "open_tab".

Generate practical, concrete recommendations for the human investigator. Recommendations must be realistic for the current evidence.

CRITICAL — DISTINGUISH ACTUAL EVIDENCE FROM REFERENCED EVIDENCE:
- ACTUAL EVIDENCE = only the documents listed in EVIDENCE OVERVIEW (completed_non_policy_doc_names). These have been uploaded and analyzed by the system.
- REFERENCED EVIDENCE = records, messages, logs, or documents MENTIONED in witness testimony or uploaded documents but NOT themselves uploaded. These are CLAIMS, not verified facts.
- When a witness describes a Teams message, email, log entry, or record — that is the WITNESS'S ACCOUNT of that record, not the record itself. Do NOT state that the record "confirms" or "shows" anything unless the actual record appears in the uploaded documents list.
- In your summary and cards, clearly flag when a fact comes from witness testimony vs. direct documentary evidence.
- If critical records (Teams messages, system logs, emails) are referenced in testimony but not uploaded, recommend obtaining them as a high-priority next step.

CRITICAL — Use specific names and details:
- Reference people BY NAME as they appear in the documents or involved_employees list. Never say "reporting party", "the employee", "the complainant", or "the subject" when you know the actual name.
- Reference specific facts, dates, and events from the document excerpts. Your guidance should demonstrate that you have read and understood the evidence.
- If the case has involved_employees, incorporate their names and roles into recommendations (e.g., "Interview Sarah Chen about the March 3rd incident" not "Interview the reporting party about the incident").

Return ONLY a JSON object with this structure:
{{
  "summary": "2-3 sentence executive guidance summary referencing specific people and facts from the evidence",
  "cards": [
    {{
      "id": "witness-interview-1",
      "title": "Interview [specific person] about [specific event]",
      "recommendation": "Schedule interview with [name] to clarify [specific detail from evidence].",
      "rationale": "Direct witness accounts are needed to corroborate or refute the reported sequence of events.",
      "priority": "high",
      "blockers": ["Witness availability must be confirmed"],
      "action": {{
        "type": "upload_document",
        "label": "Upload Interview Notes",
        "tab": null,
        "analysis_type": null,
        "search_query": null
      }}
    }}
  ]
}}

HEALTHCARE / CLINICAL ENVIRONMENT RULES:
- If the case involves a clinical, hospital, or healthcare setting, you MUST distinguish between EMPLOYEES and NON-EMPLOYEES (patients, patient family members, visitors).
- NEVER recommend that HR conduct formal interviews with patients or patient family members. HR has no authority over non-employees and doing so violates the organization's duty of care.
- For patient/family witness accounts, recommend that HR obtain statements through the Patient Advocate, Risk Management, or existing formal grievance/complaint channels — NOT through direct HR interrogation.
- When evidence references a patient or family member as a witness, recommend "Request the Patient Advocate's formal grievance report" or "Obtain the documented complaint through Risk Management" — not "Interview [family member name]."
- Clinical staff (nurses, doctors, aides) ARE employees and can be interviewed by HR, but be sensitive to clinical scheduling and patient care responsibilities.

Constraints:
1. Provide 3 to 4 cards, sorted by urgency.
2. Allowed action.type values: "run_analysis", "open_tab", "search_evidence", "upload_document".
3. Allowed action.tab values: "timeline", "discrepancies", "policy", "search".
4. If action.type is "run_analysis", action.analysis_type must be "timeline", "discrepancies", or "policy". Only use this to retry a failed analysis.
5. If action.type is "search_evidence", include a concise action.search_query.
6. Keep recommendation and rationale concise (1-2 sentences each).
7. Keep tone neutral and investigation-focused.
8. Never include legal conclusions; focus on next investigative steps.
9. Focus on what the HUMAN must do: interview people, collect records, request documents. Do NOT recommend running system analyses that are already completed.
10. Always use real names from the documents — never use generic placeholders like "the employee" or "reporting party" when names are available.
11. In healthcare settings, never recommend HR interview patients, patient family members, or other non-employees. Use Patient Advocate or Risk Management channels instead.
"""


class ERAnalyzer:
    """AI-powered analysis for ER investigations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash",
    ):
        """
        Initialize the ER analyzer.

        Args:
            api_key: Gemini API key.
            vertex_project: GCP project ID for Vertex AI.
            vertex_location: Vertex AI location.
            model: Model to use for analysis (default: gemini-2.5-flash).
        """
        self.model = model

        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Either api_key or vertex_project must be provided")

    @staticmethod
    def _is_model_unavailable_error(error: Exception) -> bool:
        """Return True when the configured model is unavailable for the current account/project."""
        message = str(error).lower()
        if "model" not in message:
            return False
        return (
            "not found" in message
            or "does not have access" in message
            or "unsupported model" in message
            or "404" in message
        )

    def _model_candidates(self) -> list[str]:
        """Try configured model first, then stable fallbacks."""
        candidates = [self.model, *FALLBACK_MODELS]
        deduped: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in deduped:
                deduped.append(candidate)
        return deduped

    async def _generate_content_async(self, prompt: str) -> str:
        """Generate content with automatic fallback when the configured model is unavailable."""
        last_model_error: Exception | None = None
        for candidate in self._model_candidates():
            try:
                response = await self.client.aio.models.generate_content(
                    model=candidate,
                    contents=prompt,
                )
                if candidate != self.model:
                    logger.warning(
                        "ERAnalyzer model '%s' unavailable; fell back to '%s'",
                        self.model,
                        candidate,
                    )
                return (response.text or "").strip()
            except Exception as exc:
                if self._is_model_unavailable_error(exc):
                    last_model_error = exc
                    logger.warning(
                        "ERAnalyzer model candidate '%s' unavailable: %s",
                        candidate,
                        exc,
                    )
                    continue
                raise

        if last_model_error:
            raise last_model_error
        raise RuntimeError("No Gemini model candidates were available for ER analysis")

    async def _generate_content_streaming(self, prompt: str) -> AsyncIterator[str]:
        """Stream content from Gemini, yielding text chunks. Falls back through model candidates."""
        last_model_error: Exception | None = None
        for candidate in self._model_candidates():
            try:
                response = await self.client.aio.models.generate_content_stream(
                    model=candidate,
                    contents=prompt,
                )
                if candidate != self.model:
                    logger.warning(
                        "ERAnalyzer model '%s' unavailable; fell back to '%s'",
                        self.model,
                        candidate,
                    )
                async for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as exc:
                if self._is_model_unavailable_error(exc):
                    last_model_error = exc
                    logger.warning(
                        "ERAnalyzer model candidate '%s' unavailable: %s",
                        candidate,
                        exc,
                    )
                    continue
                raise

        if last_model_error:
            raise last_model_error
        raise RuntimeError("No Gemini model candidates were available for ER analysis")

    def _generate_content_sync(self, prompt: str) -> str:
        """Synchronous generate_content with the same model fallback behavior."""
        last_model_error: Exception | None = None
        for candidate in self._model_candidates():
            try:
                response = self.client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                )
                if candidate != self.model:
                    logger.warning(
                        "ERAnalyzer model '%s' unavailable; fell back to '%s'",
                        self.model,
                        candidate,
                    )
                return (response.text or "").strip()
            except Exception as exc:
                if self._is_model_unavailable_error(exc):
                    last_model_error = exc
                    logger.warning(
                        "ERAnalyzer model candidate '%s' unavailable: %s",
                        candidate,
                        exc,
                    )
                    continue
                raise

        if last_model_error:
            raise last_model_error
        raise RuntimeError("No Gemini model candidates were available for ER analysis")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks and preamble text."""
        text = text.strip()

        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: locate the outermost {...} JSON object in case of
            # preamble text or trailing content surrounding the JSON.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _format_documents_for_prompt(self, documents: list[dict]) -> str:
        """Format document list for inclusion in prompt."""
        parts = []
        for doc in documents:
            parts.append(f"--- Document: {doc['filename']} (ID: {doc['id']}) ---")
            parts.append(f"Type: {doc['document_type']}")
            parts.append(f"Content:\n{doc['text']}")
            parts.append("")
        return "\n".join(parts)

    async def reconstruct_timeline(
        self,
        documents: list[dict],
    ) -> dict[str, Any]:
        """
        Reconstruct chronological timeline from documents.

        Args:
            documents: List of documents with 'id', 'filename', 'document_type', 'text'.

        Returns:
            Timeline analysis with events, gaps, and summary.
        """
        documents_text = self._format_documents_for_prompt(documents)
        prompt = TIMELINE_RECONSTRUCTION_PROMPT.format(documents=documents_text)

        text = await self._generate_content_async(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def detect_discrepancies(
        self,
        documents: list[dict],
    ) -> dict[str, Any]:
        """
        Detect discrepancies between witness statements.

        Args:
            documents: List of transcript documents.

        Returns:
            Discrepancy analysis with identified conflicts and credibility notes.
        """
        documents_text = self._format_documents_for_prompt(documents)
        prompt = DISCREPANCY_DETECTION_PROMPT.format(documents=documents_text)

        text = await self._generate_content_async(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def check_policy_violations(
        self,
        policy_doc: dict,
        evidence_docs: list[dict],
    ) -> dict[str, Any]:
        """
        Check evidence against policy for violations.

        Args:
            policy_doc: Policy document with 'id', 'filename', 'text'.
            evidence_docs: List of evidence documents.

        Returns:
            Policy violation analysis with identified violations and citations.
        """
        policy_text = f"--- Policy: {policy_doc['filename']} (ID: {policy_doc['id']}) ---\n{policy_doc['text']}"
        evidence_text = self._format_documents_for_prompt(evidence_docs)

        prompt = POLICY_VIOLATION_PROMPT.format(
            policy=policy_text,
            evidence=evidence_text,
        )

        text = await self._generate_content_async(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def generate_summary_report(
        self,
        case_info: dict,
        timeline: Optional[dict] = None,
        discrepancies: Optional[dict] = None,
        policy_analysis: Optional[dict] = None,
    ) -> str:
        """
        Generate investigation summary report.

        Args:
            case_info: Case metadata (number, title, description).
            timeline: Timeline analysis result.
            discrepancies: Discrepancy analysis result.
            policy_analysis: Policy violation analysis result.

        Returns:
            Formatted investigation summary report.
        """
        prompt = SUMMARY_REPORT_PROMPT.format(
            case_info=json.dumps(case_info, indent=2),
            timeline=json.dumps(timeline, indent=2) if timeline else "Not yet analyzed",
            discrepancies=json.dumps(discrepancies, indent=2) if discrepancies else "Not yet analyzed",
            policy_analysis=json.dumps(policy_analysis, indent=2) if policy_analysis else "Not yet analyzed",
        )

        return await self._generate_content_async(prompt)

    async def generate_determination_letter(
        self,
        case_info: dict,
        determination: str,
        findings: str,
    ) -> str:
        """
        Generate determination letter.

        Args:
            case_info: Case metadata.
            determination: The determination (substantiated, unsubstantiated, inconclusive).
            findings: Summary of key findings.

        Returns:
            Formatted determination letter.
        """
        prompt = DETERMINATION_LETTER_PROMPT.format(
            case_info=json.dumps(case_info, indent=2),
            determination=determination,
            findings=findings,
        )

        return await self._generate_content_async(prompt)

    async def evaluate_determination_confidence(
        self,
        case_info: dict[str, Any],
        evidence_overview: dict[str, Any],
        transcript_excerpts: str,
        timeline_summary: str,
        discrepancies_summary: str,
        policy_summary: str,
    ) -> dict[str, Any]:
        """Evaluate evidence confidence for determination readiness.

        Returns a dict with confidence score (0.10-0.95), signal assessments,
        and summary. Falls back to a minimal result on any failure.
        """
        prompt = DETERMINATION_CONFIDENCE_PROMPT.format(
            case_info=json.dumps(case_info, indent=2),
            evidence_overview=json.dumps(evidence_overview, indent=2),
            transcript_excerpts=transcript_excerpts or "No transcripts available.",
            timeline_summary=timeline_summary or "Not yet analyzed",
            discrepancies_summary=discrepancies_summary or "Not yet analyzed",
            policy_summary=policy_summary or "Not yet analyzed",
        )
        try:
            text = await self._generate_content_async(prompt)
            result = self._parse_json_response(text)
            # Clamp confidence to valid range
            conf = result.get("confidence", 0.10)
            if not isinstance(conf, (int, float)):
                conf = 0.10
            result["confidence"] = max(0.10, min(0.95, float(conf)))
            return result
        except Exception as exc:
            logger.warning("Determination confidence evaluation failed: %s", exc)
            return {"confidence": 0.10, "signals": [], "summary": "Insufficient data"}

    async def generate_suggested_guidance(
        self,
        case_info: dict[str, Any],
        intake_context: Optional[dict[str, Any]],
        evidence_overview: dict[str, Any],
        analysis_results: dict[str, Any],
        document_excerpts: str = "",
    ) -> dict[str, Any]:
        """
        Generate structured interactive suggested guidance cards.

        Args:
            case_info: Case metadata (number, title, description, status).
            intake_context: Intake answers and assistance metadata.
            evidence_overview: Evidence/doc readiness summary.
            analysis_results: Timeline/discrepancy/policy outputs.
            document_excerpts: Truncated text from uploaded documents.

        Returns:
            Dict with summary + cards payload.
        """
        analyses_completed = evidence_overview.pop("analyses_completed", {})
        prompt = SUGGESTED_GUIDANCE_PROMPT.format(
            case_info=json.dumps(case_info, indent=2),
            intake_context=json.dumps(intake_context or {}, indent=2),
            evidence_overview=json.dumps(evidence_overview, indent=2),
            analysis_results=json.dumps(analysis_results, indent=2),
            document_excerpts=document_excerpts or "(No document text available yet)",
            analyses_completed=json.dumps(analyses_completed, indent=2),
        )

        text = await self._generate_content_async(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def generate_outcome_analysis(
        self,
        case_info: dict,
        analysis_summary: str,
        policy_findings: str,
        precedent_stats: dict,
        healthcare_context: dict | None = None,
        determination_confidence: float | None = None,
    ) -> dict[str, Any]:
        """Generate AI-analyzed outcome recommendations for case determination.

        Args:
            case_info: Case metadata (number, title, description, status).
            analysis_summary: Combined timeline/discrepancy analysis summary.
            policy_findings: Policy violation analysis summary.
            precedent_stats: Past case outcome counts for this company.
            healthcare_context: If set, applies Just Culture framework for clinical safety.

        Returns:
            Dict with outcomes list and case_summary.
        """
        try:
            prompt = OUTCOME_ANALYSIS_PROMPT.format(
                case_info=json.dumps(case_info, indent=2, default=str),
                analysis_summary=analysis_summary or "No analysis summary available.",
                policy_findings=policy_findings or "No policy findings available.",
                precedent_stats=json.dumps(precedent_stats, indent=2, default=str) if precedent_stats else "No prior case data available.",
            )
            if healthcare_context:
                specialties = healthcare_context.get("specialties")
                specialties_str = ", ".join(specialties) if specialties else "general healthcare"
                prompt += "\n\n" + HEALTHCARE_OUTCOME_RULES.format(specialties_context=specialties_str)
            if determination_confidence is not None:
                prompt += (
                    f"\n\nEVIDENCE READINESS SCORE: {determination_confidence:.0%}\n"
                    "This reflects investigation maturity — how complete and consistent the evidence record is.\n"
                )
                if determination_confidence >= 0.80:
                    prompt += (
                        "MANDATORY CALIBRATION (EVIDENCE READINESS >= 80%):\n"
                        "- The investigation has been certified as sufficiently complete.\n"
                        "- You MUST NOT recommend 'case closure due to insufficient evidence' or any outcome "
                        "whose action_label or reasoning says evidence is insufficient, lacking, or needs gathering.\n"
                        "- At least one outcome MUST have confidence 'high'.\n"
                        "- If the evidence genuinely doesn't support a specific allegation, use determination "
                        "'unsubstantiated' with 'no_action' — NOT 'inconclusive' with 'insufficient evidence'.\n"
                    )
                else:
                    prompt += (
                        "NOTE: Evidence readiness is below 80%, so outcomes reflecting incomplete "
                        "investigation (e.g., 'gather more evidence') are acceptable.\n"
                    )
            text = await self._generate_content_async(prompt)
            result = self._parse_json_response(text)
            result["generated_at"] = datetime.now(timezone.utc).isoformat()
            result["model"] = self.model
            return result
        except Exception as exc:
            logger.warning("Outcome analysis generation failed: %s", exc, exc_info=True)
            return {
                "outcomes": [],
                "case_summary": "Unable to generate outcome analysis. Please review the case manually.",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
            }

    # Phase markers for streaming outcome analysis status detection
    _OUTCOME_PHASE_MARKERS = [
        ("case_summary", "Summarizing case findings..."),
        ("policy_basis", "Reviewing applicable policies..."),
        ("reasoning", "Analyzing supporting evidence..."),
        ("hr_considerations", "Assessing HR best practices..."),
        ("precedent_note", "Comparing with past case outcomes..."),
    ]

    async def generate_outcome_analysis_streaming(
        self,
        case_info: dict,
        analysis_summary: str,
        policy_findings: str,
        precedent_stats: dict,
        on_status: Callable[[str], Any] | None = None,
        healthcare_context: dict | None = None,
        determination_confidence: float | None = None,
    ) -> dict[str, Any]:
        """Generate outcome analysis with streaming status callbacks.

        Same as generate_outcome_analysis but streams Gemini output and calls
        on_status(msg) when it detects the AI entering a new JSON section.
        """
        try:
            prompt = OUTCOME_ANALYSIS_PROMPT.format(
                case_info=json.dumps(case_info, indent=2, default=str),
                analysis_summary=analysis_summary or "No analysis summary available.",
                policy_findings=policy_findings or "No policy findings available.",
                precedent_stats=json.dumps(precedent_stats, indent=2, default=str) if precedent_stats else "No prior case data available.",
            )
            if healthcare_context:
                specialties = healthcare_context.get("specialties")
                specialties_str = ", ".join(specialties) if specialties else "general healthcare"
                prompt += "\n\n" + HEALTHCARE_OUTCOME_RULES.format(specialties_context=specialties_str)
            if determination_confidence is not None:
                prompt += (
                    f"\n\nEVIDENCE READINESS SCORE: {determination_confidence:.0%}\n"
                    "This reflects investigation maturity — how complete and consistent the evidence record is.\n"
                )
                if determination_confidence >= 0.80:
                    prompt += (
                        "MANDATORY CALIBRATION (EVIDENCE READINESS >= 80%):\n"
                        "- The investigation has been certified as sufficiently complete.\n"
                        "- You MUST NOT recommend 'case closure due to insufficient evidence' or any outcome "
                        "whose action_label or reasoning says evidence is insufficient, lacking, or needs gathering.\n"
                        "- At least one outcome MUST have confidence 'high'.\n"
                        "- If the evidence genuinely doesn't support a specific allegation, use determination "
                        "'unsubstantiated' with 'no_action' — NOT 'inconclusive' with 'insufficient evidence'.\n"
                    )
                else:
                    prompt += (
                        "NOTE: Evidence readiness is below 80%, so outcomes reflecting incomplete "
                        "investigation (e.g., 'gather more evidence') are acceptable.\n"
                    )

            accumulated = ""
            fired_phases: set[str] = set()
            determination_count = 0

            async for chunk in self._generate_content_streaming(prompt):
                accumulated += chunk

                # Detect determination entries (can appear multiple times for each outcome)
                new_det_count = accumulated.count('"determination"')
                if new_det_count > determination_count:
                    determination_count = new_det_count
                    if on_status:
                        if determination_count == 1:
                            await on_status("Evaluating primary outcome path...")
                        else:
                            await on_status(f"Evaluating alternative outcome {determination_count - 1}...")

                # Detect other phase markers
                for marker, message in self._OUTCOME_PHASE_MARKERS:
                    if marker not in fired_phases and f'"{marker}"' in accumulated:
                        fired_phases.add(marker)
                        if on_status:
                            await on_status(message)

            result = self._parse_json_response(accumulated)
            result["generated_at"] = datetime.now(timezone.utc).isoformat()
            result["model"] = self.model
            return result
        except Exception as exc:
            logger.warning("Outcome analysis streaming failed: %s", exc, exc_info=True)
            return {
                "outcomes": [],
                "case_summary": "Unable to generate outcome analysis. Please review the case manually.",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
            }

    # Synchronous versions for Celery tasks

    def reconstruct_timeline_sync(self, documents: list[dict]) -> dict[str, Any]:
        """Synchronous version of reconstruct_timeline."""
        documents_text = self._format_documents_for_prompt(documents)
        prompt = TIMELINE_RECONSTRUCTION_PROMPT.format(documents=documents_text)

        text = self._generate_content_sync(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def detect_discrepancies_sync(self, documents: list[dict]) -> dict[str, Any]:
        """Synchronous version of detect_discrepancies."""
        documents_text = self._format_documents_for_prompt(documents)
        prompt = DISCREPANCY_DETECTION_PROMPT.format(documents=documents_text)

        text = self._generate_content_sync(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def check_policy_violations_sync(
        self,
        policy_doc: dict,
        evidence_docs: list[dict],
    ) -> dict[str, Any]:
        """Synchronous version of check_policy_violations."""
        policy_text = f"--- Policy: {policy_doc['filename']} (ID: {policy_doc['id']}) ---\n{policy_doc['text']}"
        evidence_text = self._format_documents_for_prompt(evidence_docs)

        prompt = POLICY_VIOLATION_PROMPT.format(
            policy=policy_text,
            evidence=evidence_text,
        )

        text = self._generate_content_sync(prompt)
        result = self._parse_json_response(text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result
