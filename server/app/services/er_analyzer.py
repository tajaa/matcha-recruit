"""ER Analyzer Service for ER Copilot.

AI-powered analysis for Employee Relations investigations:
- Timeline Reconstruction
- Discrepancy Detection
- Policy Violation Check
- Summary Report Generation
"""

import json
from datetime import datetime, timezone
from typing import Optional, Any

from google import genai


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


class ERAnalyzer:
    """AI-powered analysis for ER investigations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-3-flash-preview",
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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        return response.text.strip()

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

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        return response.text.strip()

    # Synchronous versions for Celery tasks

    def reconstruct_timeline_sync(self, documents: list[dict]) -> dict[str, Any]:
        """Synchronous version of reconstruct_timeline."""
        documents_text = self._format_documents_for_prompt(documents)
        prompt = TIMELINE_RECONSTRUCTION_PROMPT.format(documents=documents_text)

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def detect_discrepancies_sync(self, documents: list[dict]) -> dict[str, Any]:
        """Synchronous version of detect_discrepancies."""
        documents_text = self._format_documents_for_prompt(documents)
        prompt = DISCREPANCY_DETECTION_PROMPT.format(documents=documents_text)

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
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

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result
