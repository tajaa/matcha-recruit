"""
Conversation Analyzer Service

Analyzes interview transcripts to evaluate:
1. Coverage completeness - Did questions cover all key dimensions?
2. Response depth - Were responses specific and actionable?
3. Missed opportunities - What follow-ups should have been asked?
4. Prompt improvements - How can the AI interviewer be improved?
"""

import json
from datetime import datetime, timezone
from typing import Optional, Any

from google import genai


CULTURE_INTERVIEW_ANALYSIS_PROMPT = """Analyze this culture interview transcript where an AI interviewer asked an HR representative about their company culture.

Evaluate the AI interviewer's effectiveness at eliciting useful information for assessing culture fit.

TRANSCRIPT:
{transcript}

KEY CULTURE DIMENSIONS TO ASSESS COVERAGE:
1. Work Environment & Collaboration - How teams work together, collaboration style
2. Company Values & Recognition - Core values, how success is celebrated
3. Communication Style - Async vs sync, meeting culture, transparency
4. Growth & Development - Career paths, learning opportunities, mentorship
5. Work-Life Balance - Flexibility, expectations, boundaries
6. Team Dynamics - Team size, hierarchy, decision-making process

For each dimension, evaluate:
- covered: Was this topic discussed? (true/false)
- depth: How thoroughly? ("deep" = specific examples given, "shallow" = mentioned briefly, "none" = not discussed)
- evidence: Brief quote or paraphrase from transcript showing coverage

Also evaluate each interviewee response:
- question_summary: What was being asked
- response_quality: "specific" (concrete examples/details), "somewhat_specific" (some details), "vague" (generic/abstract)
- actionability: "high" (useful for culture matching), "medium" (somewhat useful), "low" (not very useful)
- notes: What made the response good or lacking

Identify missed opportunities where the interviewer should have probed deeper.

Suggest improvements to the AI interviewer's questioning strategy.

Return ONLY a JSON object with this structure:
{{
    "coverage_completeness": {{
        "overall_score": <0-100>,
        "dimensions_covered": ["list of covered dimension names"],
        "dimensions_missed": ["list of missed dimension names"],
        "coverage_details": {{
            "work_environment": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "values": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "communication": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "growth": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "work_life_balance": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "team_dynamics": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}}
        }}
    }},
    "response_depth": {{
        "overall_score": <0-100>,
        "specific_examples_count": <number>,
        "vague_responses_count": <number>,
        "response_analysis": [
            {{
                "question_summary": "...",
                "response_quality": "specific/somewhat_specific/vague",
                "actionability": "high/medium/low",
                "notes": "..."
            }}
        ]
    }},
    "missed_opportunities": [
        {{
            "topic": "what topic was missed",
            "suggested_followup": "what question should have been asked",
            "reason": "why this would have been valuable"
        }}
    ],
    "prompt_improvement_suggestions": [
        {{
            "category": "follow_up_depth/topic_coverage/question_phrasing/conversation_flow",
            "current_behavior": "what the AI currently does",
            "suggested_improvement": "what it should do instead",
            "priority": "high/medium/low"
        }}
    ],
    "interview_summary": "2-3 sentence summary of how well this interview captured the company culture"
}}

Return ONLY the JSON object, no other text."""


CANDIDATE_INTERVIEW_ANALYSIS_PROMPT = """Analyze this candidate interview transcript where an AI interviewer assessed a job candidate's work preferences and culture fit.

Evaluate the AI interviewer's effectiveness at eliciting useful information for assessing culture fit with the company.

TRANSCRIPT:
{transcript}

{culture_context}

KEY CANDIDATE ASSESSMENT DIMENSIONS:
1. Work Style Preferences - How they prefer to work, environment needs
2. Communication Style - How they prefer to communicate and receive feedback
3. Career Goals & Motivation - What drives them, where they want to go
4. Problem-Solving Approach - How they handle challenges and decisions
5. Values & Culture Fit - What matters to them in a workplace
6. Work-Life Balance - Their expectations and boundaries

For each dimension, evaluate:
- covered: Was this topic discussed? (true/false)
- depth: How thoroughly? ("deep" = specific examples given, "shallow" = mentioned briefly, "none" = not discussed)
- evidence: Brief quote or paraphrase from transcript showing coverage

Also evaluate each candidate response:
- question_summary: What was being asked
- response_quality: "specific" (concrete examples/details), "somewhat_specific" (some details), "vague" (generic/abstract)
- actionability: "high" (useful for culture matching), "medium" (somewhat useful), "low" (not very useful)
- notes: What made the response good or lacking

Identify missed opportunities where the interviewer should have probed deeper.

Suggest improvements to the AI interviewer's questioning strategy.

Return ONLY a JSON object with this structure:
{{
    "coverage_completeness": {{
        "overall_score": <0-100>,
        "dimensions_covered": ["list of covered dimension names"],
        "dimensions_missed": ["list of missed dimension names"],
        "coverage_details": {{
            "work_style": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "communication": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "career_goals": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "problem_solving": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "values": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}},
            "work_life_balance": {{"covered": true/false, "depth": "deep/shallow/none", "evidence": "..."}}
        }}
    }},
    "response_depth": {{
        "overall_score": <0-100>,
        "specific_examples_count": <number>,
        "vague_responses_count": <number>,
        "response_analysis": [
            {{
                "question_summary": "...",
                "response_quality": "specific/somewhat_specific/vague",
                "actionability": "high/medium/low",
                "notes": "..."
            }}
        ]
    }},
    "missed_opportunities": [
        {{
            "topic": "what topic was missed",
            "suggested_followup": "what question should have been asked",
            "reason": "why this would have been valuable"
        }}
    ],
    "prompt_improvement_suggestions": [
        {{
            "category": "follow_up_depth/topic_coverage/question_phrasing/conversation_flow",
            "current_behavior": "what the AI currently does",
            "suggested_improvement": "what it should do instead",
            "priority": "high/medium/low"
        }}
    ],
    "interview_summary": "2-3 sentence summary of how well this interview assessed the candidate's culture fit potential"
}}

Return ONLY the JSON object, no other text."""


class ConversationAnalyzer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash-lite",
    ):
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

    async def analyze_interview(
        self,
        transcript: str,
        interview_type: str,
        culture_profile: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Analyze an interview transcript for quality and effectiveness."""

        if interview_type == "culture":
            prompt = CULTURE_INTERVIEW_ANALYSIS_PROMPT.format(transcript=transcript)
        else:
            # Candidate interview - include culture context if available
            culture_context = ""
            if culture_profile:
                culture_context = f"""COMPANY CULTURE CONTEXT (use to evaluate if questions aligned with company needs):
- Collaboration Style: {culture_profile.get('collaboration_style', 'unknown')}
- Communication: {culture_profile.get('communication', 'unknown')}
- Pace: {culture_profile.get('pace', 'unknown')}
- Hierarchy: {culture_profile.get('hierarchy', 'unknown')}
- Work-Life Balance: {culture_profile.get('work_life_balance', 'unknown')}
- Values: {', '.join(culture_profile.get('values', []))}
- Key Traits: {', '.join(culture_profile.get('key_traits', []))}
"""
            prompt = CANDIDATE_INTERVIEW_ANALYSIS_PROMPT.format(
                transcript=transcript,
                culture_context=culture_context,
            )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        # Parse JSON from response
        text = response.text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            analysis = json.loads(text)
            # Add timestamp
            analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            return analysis
        except json.JSONDecodeError as e:
            print(f"[ConversationAnalyzer] Failed to parse JSON: {e}")
            print(f"[ConversationAnalyzer] Raw response: {text}")
            # Return a minimal fallback structure
            return {
                "coverage_completeness": {
                    "overall_score": 0,
                    "dimensions_covered": [],
                    "dimensions_missed": [],
                    "coverage_details": {},
                },
                "response_depth": {
                    "overall_score": 0,
                    "specific_examples_count": 0,
                    "vague_responses_count": 0,
                    "response_analysis": [],
                },
                "missed_opportunities": [],
                "prompt_improvement_suggestions": [],
                "interview_summary": f"Failed to analyze transcript: {str(e)}",
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "raw_response": text[:500] if text else None,
            }
