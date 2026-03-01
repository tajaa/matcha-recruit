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
from typing import Optional, Any

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
            "type": "contradiction",
            "severity": "high",
            "description": "Witnesses disagree on whether the door was open or closed",
            "statement_1": {{
                "source_document_id": "doc-uuid-1",
                "speaker": "Jane Smith",
                "quote": "The door was open the entire time",
                "location": "Page 3, Line 15"
            }},
            "statement_2": {{
                "source_document_id": "doc-uuid-2",
                "speaker": "Bob Johnson",
                "quote": "I knocked because the door was closed",
                "location": "Page 2, Line 8"
            }},
            "analysis": "This discrepancy is significant because it affects whether the conversation could have been overheard"
        }}
    ],
    "credibility_notes": [
        {{
            "witness": "Jane Smith",
            "assessment": "Generally consistent account",
            "reasoning": "Timeline aligns with other evidence, no internal contradictions"
        }}
    ],
    "summary": "Overview of key discrepancies and their implications for the investigation"
}}

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
4. Assess severity (major vs minor violation)

Return ONLY a JSON object with this structure:
{{
    "violations": [
        {{
            "policy_section": "Section 3.2: Workplace Harassment",
            "policy_text": "Employees shall not engage in conduct that creates an intimidating, hostile, or offensive work environment",
            "severity": "major",
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

Be thorough but fair. Note both supporting and potentially mitigating evidence."""


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

For each outcome path, provide:
- determination: "substantiated", "unsubstantiated", or "inconclusive"
- recommended_action: one of "termination", "disciplinary_action", "retraining", "no_action", "resignation", "other"
- action_label: Human-readable label for the action (e.g. "Termination for Cause", "Written Warning + Retraining")
- reasoning: 2-3 sentences citing specific evidence that supports this path
- policy_basis: Which company policies or legal standards support this outcome
- hr_considerations: Best practice notes, risks, or mitigating factors to consider
- precedent_note: How this aligns with the company's past case outcomes (use the precedent stats provided)
- confidence: "high", "medium", or "low" based on evidence strength for this path

Order outcomes from most to least supported by evidence.

Return ONLY a JSON object with this structure:
{{
  "outcomes": [
    {{
      "determination": "substantiated",
      "recommended_action": "disciplinary_action",
      "action_label": "Written Warning with Mandatory Training",
      "reasoning": "Two witnesses corroborate the reported behavior. The respondent's own statement partially acknowledges the conduct.",
      "policy_basis": "Section 3.2 Workplace Conduct prohibits intimidating behavior. Progressive discipline policy calls for written warning on first offense.",
      "hr_considerations": "Consider respondent's tenure and clean prior record as mitigating factors. Document the warning thoroughly for potential future escalation.",
      "precedent_note": "3 of 5 similar past cases resulted in disciplinary action rather than termination.",
      "confidence": "high"
    }}
  ],
  "case_summary": "2-3 sentence executive summary of the case and key evidence"
}}

Rules:
- Provide 2 to 4 outcome paths, sorted by evidence strength
- Always include at least one path with a different determination when evidence allows
- Be objective — present options, don't advocate for one
- confidence must be "high", "medium", or "low"
- Keep reasoning concise but cite specific evidence
- If precedent data is sparse, say so honestly in precedent_note"""


SUGGESTED_GUIDANCE_PROMPT = """You are an Employee Relations investigation assistant generating interactive next-step guidance for an active case.

CASE INFORMATION:
{case_info}

INTAKE CONTEXT:
{intake_context}

EVIDENCE OVERVIEW:
{evidence_overview}

ANALYSIS RESULTS:
{analysis_results}

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

Return ONLY a JSON object with this structure:
{{
  "summary": "2-3 sentence executive guidance summary",
  "cards": [
    {{
      "id": "witness-interview-1",
      "title": "Interview named witnesses about gap period",
      "recommendation": "Schedule interviews with witnesses mentioned in existing statements to clarify events during the unresolved window.",
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
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = text.strip()

        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

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
    ) -> dict[str, Any]:
        """
        Generate structured interactive suggested guidance cards.

        Args:
            case_info: Case metadata (number, title, description, status).
            intake_context: Intake answers and assistance metadata.
            evidence_overview: Evidence/doc readiness summary.
            analysis_results: Timeline/discrepancy/policy outputs.

        Returns:
            Dict with summary + cards payload.
        """
        analyses_completed = evidence_overview.pop("analyses_completed", {})
        prompt = SUGGESTED_GUIDANCE_PROMPT.format(
            case_info=json.dumps(case_info, indent=2),
            intake_context=json.dumps(intake_context or {}, indent=2),
            evidence_overview=json.dumps(evidence_overview, indent=2),
            analysis_results=json.dumps(analysis_results, indent=2),
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
    ) -> dict[str, Any]:
        """Generate AI-analyzed outcome recommendations for case determination.

        Args:
            case_info: Case metadata (number, title, description, status).
            analysis_summary: Combined timeline/discrepancy analysis summary.
            policy_findings: Policy violation analysis summary.
            precedent_stats: Past case outcome counts for this company.

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
