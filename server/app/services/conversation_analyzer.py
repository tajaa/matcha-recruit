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


SCREENING_INTERVIEW_ANALYSIS_PROMPT = """Analyze this screening interview transcript where an AI interviewer assessed a candidate's basic qualifications.

TRANSCRIPT:
{transcript}

Evaluate the candidate on these 4 attributes (score each 0-100):

1. COMMUNICATION & CLARITY (Weight: 30%)
   - How well do they articulate their thoughts?
   - Do they structure responses logically?
   - Are they concise yet thorough?
   - Do they use appropriate vocabulary?

2. ENGAGEMENT & ENERGY (Weight: 25%)
   - Are they enthusiastic and genuinely interested?
   - Do they actively participate in the conversation?
   - Do they ask thoughtful questions?
   - Is their energy appropriate for the context?

3. CRITICAL THINKING (Weight: 25%)
   - How do they approach problems?
   - Do they demonstrate analytical reasoning?
   - Can they think on their feet?
   - Do they consider multiple perspectives?

4. PROFESSIONALISM (Weight: 20%)
   - Is their tone appropriate?
   - Do they seem prepared?
   - Are they self-aware about strengths/weaknesses?
   - Do they handle questions gracefully?

For each attribute, provide:
- A score (0-100)
- 1-3 evidence quotes from the transcript
- Brief notes on what stood out

Calculate an overall score (weighted average using the weights above).

Provide a recommendation:
- "strong_pass": Score >= 80, no red flags
- "pass": Score 60-79, minor concerns
- "borderline": Score 40-59, significant concerns
- "fail": Score < 40 or major red flags

Return ONLY a JSON object with this structure:
{{
    "communication_clarity": {{
        "score": <0-100>,
        "evidence": ["quote1", "quote2"],
        "notes": "..."
    }},
    "engagement_energy": {{
        "score": <0-100>,
        "evidence": ["quote1", "quote2"],
        "notes": "..."
    }},
    "critical_thinking": {{
        "score": <0-100>,
        "evidence": ["quote1", "quote2"],
        "notes": "..."
    }},
    "professionalism": {{
        "score": <0-100>,
        "evidence": ["quote1", "quote2"],
        "notes": "..."
    }},
    "overall_score": <0-100>,
    "recommendation": "strong_pass/pass/borderline/fail",
    "summary": "2-3 sentence summary of the candidate's performance and fit potential"
}}

Return ONLY the JSON object, no other text."""


TUTOR_INTERVIEW_ANALYSIS_PROMPT = """Analyze this interview practice session transcript where a user practiced answering interview questions with an AI interviewer.

Provide feedback to help the user improve their interview skills.

TRANSCRIPT:
{transcript}

Evaluate the user's performance across three key areas:

1. RESPONSE QUALITY (How well-crafted are their answers?)
   - Specificity: Do they give concrete details or vague generalities?
   - Example Usage: Do they use the STAR method or similar structured examples?
   - Depth: Do they fully address the question or give surface-level answers?

2. COMMUNICATION SKILLS (How effectively do they communicate?)
   - Clarity: Are responses well-organized and easy to follow?
   - Confidence: Do they sound assured in their answers?
   - Professionalism: Is the tone appropriate for an interview?
   - Engagement: Do they show enthusiasm and interest?

3. CONTENT COVERAGE (What topics did they handle well or miss?)
   - Topics Covered: What interview topics were addressed?
   - Missed Opportunities: Where could they have elaborated more?
   - Follow-up Depth: Did they anticipate and address likely follow-ups?

For each response in the transcript, analyze:
- What question was asked
- Quality of the answer (specific, somewhat_specific, or vague)
- Whether they used concrete examples
- Specific feedback for improvement

Return ONLY a JSON object with this structure:
{{
    "response_quality": {{
        "overall_score": <0-100>,
        "specificity_score": <0-100>,
        "example_usage_score": <0-100>,
        "depth_score": <0-100>,
        "breakdown": [
            {{
                "question": "...",
                "quality": "specific/somewhat_specific/vague",
                "used_examples": true/false,
                "depth": "excellent/good/shallow",
                "feedback": "specific improvement suggestion"
            }}
        ]
    }},
    "communication_skills": {{
        "overall_score": <0-100>,
        "clarity_score": <0-100>,
        "confidence_score": <0-100>,
        "professionalism_score": <0-100>,
        "engagement_score": <0-100>,
        "notes": "overall communication feedback"
    }},
    "content_coverage": {{
        "topics_covered": ["list of topics discussed well"],
        "missed_opportunities": [
            {{
                "topic": "what could have been discussed",
                "suggestion": "how to address it"
            }}
        ],
        "follow_up_depth": "excellent/good/shallow"
    }},
    "improvement_suggestions": [
        {{
            "area": "which skill area",
            "suggestion": "specific actionable advice",
            "priority": "high/medium/low"
        }}
    ],
    "session_summary": "2-3 sentence summary of performance with key strengths and areas to improve"
}}

Return ONLY the JSON object, no other text."""


TUTOR_LANGUAGE_ANALYSIS_PROMPT = """Analyze this language practice session transcript where a user practiced speaking {language_name} with an AI conversation partner.

Provide feedback to help the user improve their {language_name} speaking skills.

TRANSCRIPT:
{transcript}

Evaluate the user's language proficiency across three key areas:

1. FLUENCY & PACE
   - Speaking Speed: Is it natural, too fast, or too slow?
   - Pause Frequency: Are there many hesitations or unnatural pauses?
   - Filler Words: How often do they use fillers (um, uh, like, etc.)?
   - Flow: Does the conversation flow naturally?

2. VOCABULARY
   - Word Variety: Do they use diverse vocabulary or repeat the same words?
   - Appropriateness: Are word choices suitable for the context?
   - Complexity: What level of vocabulary complexity (basic/intermediate/advanced)?
   - Notable Usage: Any particularly good or problematic word choices?

3. GRAMMAR
   - Sentence Structure: Are sentences well-formed?
   - Tense Usage: Are verb tenses used correctly and consistently?
   - Common Errors: What grammar mistakes appear? (List specific examples with corrections)
   - Complexity: Can they form complex sentences or only simple ones?

Determine overall proficiency level using CEFR scale:
- A1: Beginner - Basic phrases only
- A2: Elementary - Simple everyday expressions
- B1: Intermediate - Can handle most situations
- B2: Upper Intermediate - Can interact fluently
- C1: Advanced - Can express fluently and spontaneously
- C2: Mastery - Near-native command

Return ONLY a JSON object with this structure:
{{
    "fluency_pace": {{
        "overall_score": <0-100>,
        "speaking_speed": "natural/too_fast/too_slow/varies",
        "pause_frequency": "rare/occasional/frequent",
        "filler_word_count": <estimated number>,
        "filler_words_used": ["list of fillers noted"],
        "flow_rating": "excellent/good/choppy/poor",
        "notes": "feedback on fluency"
    }},
    "vocabulary": {{
        "overall_score": <0-100>,
        "variety_score": <0-100>,
        "appropriateness_score": <0-100>,
        "complexity_level": "basic/intermediate/advanced",
        "notable_good_usage": ["words/phrases used well"],
        "suggestions": ["vocabulary improvements to focus on"]
    }},
    "grammar": {{
        "overall_score": <0-100>,
        "sentence_structure_score": <0-100>,
        "tense_usage_score": <0-100>,
        "common_errors": [
            {{
                "error": "what the user said",
                "correction": "correct form",
                "type": "tense/agreement/word_order/article/preposition/other"
            }}
        ],
        "notes": "overall grammar feedback"
    }},
    "overall_proficiency": {{
        "level": "A1/A2/B1/B2/C1/C2",
        "level_description": "brief description of what this level means",
        "strengths": ["what they do well"],
        "areas_to_improve": ["what to focus on next"]
    }},
    "practice_suggestions": [
        {{
            "skill": "which aspect to practice",
            "exercise": "specific practice activity",
            "priority": "high/medium/low"
        }}
    ],
    "session_summary": "2-3 sentence summary of language performance with encouragement and clear next steps"
}}

Return ONLY the JSON object, no other text."""


TUTOR_SPANISH_ANALYSIS_PROMPT = """Analyze this Spanish language practice session transcript where a user practiced speaking Spanish with an AI conversation partner.

Provide detailed feedback to help the user improve their Spanish speaking skills, with special attention to Spanish-specific challenges.

TRANSCRIPT:
{transcript}

Evaluate the user's Spanish proficiency across these key areas:

1. FLUENCY & PACE
   - Speaking Speed: Natural, too fast, or too slow?
   - Pause Frequency: Hesitations or unnatural pauses?
   - Filler Words: Spanish fillers (este, pues, o sea, eh) vs English fillers?
   - Flow: Does the conversation flow naturally?

2. VOCABULARY
   - Word Variety: Diverse vocabulary or repetitive?
   - Appropriateness: Suitable word choices for context?
   - Complexity: Basic/intermediate/advanced vocabulary?
   - False Cognates: Any confusion with false friends (e.g., embarazada/embarrassed)?

3. GRAMMAR - General
   - Sentence Structure: Well-formed sentences?
   - Tense Usage: Correct and consistent verb tenses?
   - Common Errors: List specific examples with corrections

4. SPANISH-SPECIFIC GRAMMAR
   - VERB CONJUGATION: Check regular and irregular verb conjugations
     * Present tense accuracy
     * Past tenses (preterite vs imperfect usage)
     * Future and conditional forms
     * Subjunctive mood (when appropriate)
   - GENDER & NUMBER AGREEMENT
     * Noun-adjective agreement (el libro rojo, la casa blanca)
     * Article usage (el/la/los/las, un/una/unos/unas)
     * Demonstratives and possessives
   - SER VS ESTAR: Correct usage for:
     * Identity/characteristics (ser) vs states/locations (estar)
     * Common mistakes like "estoy feliz" vs "soy feliz"
   - POR VS PARA: Correct usage for:
     * Duration, exchange, cause (por)
     * Purpose, destination, deadline (para)

Determine overall proficiency level using CEFR scale:
- A1: Beginner - Basic phrases only
- A2: Elementary - Simple everyday expressions
- B1: Intermediate - Can handle most situations
- B2: Upper Intermediate - Can interact fluently
- C1: Advanced - Can express fluently and spontaneously
- C2: Mastery - Near-native command

Return ONLY a JSON object with this structure:
{{
    "fluency_pace": {{
        "overall_score": <0-100>,
        "speaking_speed": "natural/too_fast/too_slow/varies",
        "pause_frequency": "rare/occasional/frequent",
        "filler_word_count": <estimated number>,
        "filler_words_used": ["list of fillers noted"],
        "flow_rating": "excellent/good/choppy/poor",
        "notes": "feedback on fluency"
    }},
    "vocabulary": {{
        "overall_score": <0-100>,
        "variety_score": <0-100>,
        "appropriateness_score": <0-100>,
        "complexity_level": "basic/intermediate/advanced",
        "notable_good_usage": ["words/phrases used well"],
        "suggestions": ["vocabulary improvements to focus on"],
        "false_cognates_noted": ["any false friend mistakes"]
    }},
    "grammar": {{
        "overall_score": <0-100>,
        "sentence_structure_score": <0-100>,
        "tense_usage_score": <0-100>,
        "common_errors": [
            {{
                "error": "what the user said",
                "correction": "correct form",
                "type": "conjugation/gender/ser_estar/por_para/tense/agreement/word_order/article/preposition/other",
                "explanation": "brief explanation of the rule"
            }}
        ],
        "notes": "overall grammar feedback"
    }},
    "spanish_specific": {{
        "conjugation": {{
            "score": <0-100>,
            "regular_verb_accuracy": <0-100>,
            "irregular_verb_accuracy": <0-100>,
            "tense_appropriateness": <0-100>,
            "subjunctive_attempts": <number of attempts>,
            "subjunctive_accuracy": <0-100 or null if no attempts>,
            "notable_errors": [
                {{
                    "verb": "infinitive form",
                    "user_said": "incorrect conjugation",
                    "correct": "correct conjugation",
                    "tense": "present/preterite/imperfect/future/conditional/subjunctive",
                    "person": "yo/tú/él/nosotros/etc"
                }}
            ],
            "notes": "feedback on verb conjugation"
        }},
        "gender_agreement": {{
            "score": <0-100>,
            "errors": [
                {{
                    "phrase": "incorrect phrase",
                    "correction": "correct phrase",
                    "rule": "brief explanation (e.g., 'problema is masculine despite -a ending')"
                }}
            ],
            "notes": "feedback on gender/number agreement"
        }},
        "ser_estar": {{
            "score": <0-100>,
            "errors": [
                {{
                    "user_said": "incorrect usage",
                    "correction": "correct form",
                    "explanation": "why ser or estar is correct here"
                }}
            ],
            "notes": "feedback on ser/estar usage"
        }},
        "por_para": {{
            "score": <0-100>,
            "errors": [
                {{
                    "user_said": "incorrect usage",
                    "correction": "correct form",
                    "explanation": "why por or para is correct here"
                }}
            ],
            "notes": "feedback on por/para usage"
        }}
    }},
    "overall_proficiency": {{
        "level": "A1/A2/B1/B2/C1/C2",
        "level_description": "brief description of what this level means",
        "strengths": ["what they do well"],
        "areas_to_improve": ["what to focus on next"]
    }},
    "practice_suggestions": [
        {{
            "skill": "which aspect to practice",
            "exercise": "specific practice activity",
            "priority": "high/medium/low"
        }}
    ],
    "session_summary": "2-3 sentence summary of Spanish performance with encouragement and clear next steps",
    "vocabulary_used": [
        {{
            "word": "the Spanish word/phrase",
            "category": "verb/noun/adjective/adverb/phrase/expression",
            "used_correctly": true/false,
            "context": "brief context of how it was used",
            "correction": "if incorrect, the correct form or usage",
            "difficulty": "basic/intermediate/advanced"
        }}
    ],
    "vocabulary_suggestions": [
        {{
            "word": "suggested Spanish word/phrase to learn",
            "meaning": "English meaning",
            "example": "example sentence in Spanish",
            "difficulty": "basic/intermediate/advanced"
        }}
    ]
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

    async def analyze_screening_interview(
        self,
        transcript: str,
    ) -> dict[str, Any]:
        """Analyze a screening interview transcript for candidate quality."""
        prompt = SCREENING_INTERVIEW_ANALYSIS_PROMPT.format(transcript=transcript)

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
            print(f"[ConversationAnalyzer] Failed to parse screening JSON: {e}")
            print(f"[ConversationAnalyzer] Raw response: {text}")
            # Return a minimal fallback structure for screening
            return {
                "communication_clarity": {
                    "score": 0,
                    "evidence": [],
                    "notes": "Analysis failed",
                },
                "engagement_energy": {
                    "score": 0,
                    "evidence": [],
                    "notes": "Analysis failed",
                },
                "critical_thinking": {
                    "score": 0,
                    "evidence": [],
                    "notes": "Analysis failed",
                },
                "professionalism": {
                    "score": 0,
                    "evidence": [],
                    "notes": "Analysis failed",
                },
                "overall_score": 0,
                "recommendation": "fail",
                "summary": f"Failed to analyze transcript: {str(e)}",
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }

    async def analyze_tutor_interview(
        self,
        transcript: str,
    ) -> dict[str, Any]:
        """Analyze an interview practice session for user improvement feedback."""
        prompt = TUTOR_INTERVIEW_ANALYSIS_PROMPT.format(transcript=transcript)

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
            analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            return analysis
        except json.JSONDecodeError as e:
            print(f"[ConversationAnalyzer] Failed to parse tutor interview JSON: {e}")
            print(f"[ConversationAnalyzer] Raw response: {text}")
            return {
                "response_quality": {
                    "overall_score": 0,
                    "specificity_score": 0,
                    "example_usage_score": 0,
                    "depth_score": 0,
                    "breakdown": [],
                },
                "communication_skills": {
                    "overall_score": 0,
                    "clarity_score": 0,
                    "confidence_score": 0,
                    "professionalism_score": 0,
                    "engagement_score": 0,
                    "notes": "Analysis failed",
                },
                "content_coverage": {
                    "topics_covered": [],
                    "missed_opportunities": [],
                    "follow_up_depth": "shallow",
                },
                "improvement_suggestions": [],
                "session_summary": f"Failed to analyze transcript: {str(e)}",
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }

    async def analyze_tutor_language(
        self,
        transcript: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """Analyze a language practice session for proficiency feedback."""
        # Use Spanish-specific prompt for Spanish sessions
        if language == "es":
            prompt = TUTOR_SPANISH_ANALYSIS_PROMPT.format(transcript=transcript)
        else:
            language_name = "English"
            prompt = TUTOR_LANGUAGE_ANALYSIS_PROMPT.format(
                transcript=transcript,
                language_name=language_name,
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
            analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            analysis["language"] = language
            return analysis
        except json.JSONDecodeError as e:
            print(f"[ConversationAnalyzer] Failed to parse tutor language JSON: {e}")
            print(f"[ConversationAnalyzer] Raw response: {text}")
            return {
                "fluency_pace": {
                    "overall_score": 0,
                    "speaking_speed": "varies",
                    "pause_frequency": "occasional",
                    "filler_word_count": 0,
                    "filler_words_used": [],
                    "flow_rating": "poor",
                    "notes": "Analysis failed",
                },
                "vocabulary": {
                    "overall_score": 0,
                    "variety_score": 0,
                    "appropriateness_score": 0,
                    "complexity_level": "basic",
                    "notable_good_usage": [],
                    "suggestions": [],
                },
                "grammar": {
                    "overall_score": 0,
                    "sentence_structure_score": 0,
                    "tense_usage_score": 0,
                    "common_errors": [],
                    "notes": "Analysis failed",
                },
                "overall_proficiency": {
                    "level": "A1",
                    "level_description": "Unable to assess",
                    "strengths": [],
                    "areas_to_improve": [],
                },
                "practice_suggestions": [],
                "session_summary": f"Failed to analyze transcript: {str(e)}",
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "language": language,
            }
