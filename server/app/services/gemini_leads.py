"""
Gemini Leads Service

AI-powered analysis for the Leads Agent workflow:
1. Position analysis - Filter jobs against search criteria
2. Contact ranking - Pick best decision-maker from found contacts
3. Email generation - Write personalized outreach emails
"""

import json
import os
import re
from typing import Optional, List

from google import genai
from google.genai import types

from ..config import get_settings
from ..models.leads_agent import (
    GeminiAnalysis,
    Lead,
    Contact,
    SearchRequest,
)


class GeminiLeadsService:
    """
    Gemini AI integration for the Leads Agent workflow.
    
    Uses Gemini for:
    - Analyzing positions against search criteria
    - Ranking contacts to find best decision-maker
    - Generating personalized outreach emails
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[genai.Client] = None
    
    @property
    def client(self) -> genai.Client:
        """Get or create Gemini client."""
        if self._client is None:
            # Check for specific API key for this service first
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
    
    def _clean_json_text(self, text: str) -> str:
        """Clean JSON text by removing markdown and finding the JSON object."""
        text = text.strip()
        
        # Remove markdown code blocks if present
        if "```" in text:
            # Try to find the content between first ``` and last ```
            parts = text.split("```")
            for part in parts:
                if "{" in part and "}" in part:
                    # found a candidate
                    text = part
                    if text.startswith("json"):
                        text = text[4:]
                    break
        
        # Find the first '{' and last '}'
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1:
            text = text[start:end+1]
            
        # Fix common LLM JSON errors (Python booleans/None)
        # Use regex to avoid replacing inside strings (mostly)
        text = re.sub(r':\s*True\b', ': true', text)
        text = re.sub(r':\s*False\b', ': false', text)
        text = re.sub(r':\s*None\b', ': null', text)
            
        return text

    async def analyze_position(
        self,
        title: str,
        company_name: str,
        location: Optional[str],
        description: Optional[str],
        salary_text: Optional[str],
        criteria: SearchRequest,
    ) -> GeminiAnalysis:
        """
        Analyze if a position matches the search criteria.
        
        Returns a score 1-10 and reasoning explaining the assessment.
        Also extracts structured data like seniority level and salary range.
        """
        # Build criteria description
        criteria_parts = []
        if criteria.role_types:
            criteria_parts.append(f"Role types: {', '.join(criteria.role_types)}")
        if criteria.locations:
            criteria_parts.append(f"Target locations: {', '.join(criteria.locations)}")
        if criteria.industries:
            criteria_parts.append(f"Industries: {', '.join(criteria.industries)}")
        if criteria.salary_min:
            criteria_parts.append(f"Minimum salary: ${criteria.salary_min:,}")
        if criteria.salary_max:
            criteria_parts.append(f"Maximum salary: ${criteria.salary_max:,}")
        
        criteria_text = "\n".join(criteria_parts) if criteria_parts else "No specific criteria set"
        
        prompt = f"""You are an executive recruiting AI assistant. Analyze this job posting to determine if it matches our search criteria.

## Search Criteria
{criteria_text}

## Job Posting
Title: {title}
Company: {company_name}
Location: {location or 'Not specified'}
Salary: {salary_text or 'Not specified'}

Description:
{(description or 'No description available')[:2000]}

## Instructions
Analyze this position and respond with a JSON object containing:

1. "relevance_score": Integer 1-10 where:
   - 1-3: Poor match (wrong level, wrong location, etc.)
   - 4-6: Partial match (meets some criteria, e.g., role matches but salary/industry is ambiguous)
   - 7-10: Strong match (meets most/all criteria)

2. "is_qualified": Boolean - true if score >= 5. Note: If salary is not mentioned in the posting, do NOT penalize the score for it. Focus on Role and Location first.

3. "reasoning": Brief explanation of your scoring (2-3 sentences)

4. "extracted_seniority": One of: "c_suite", "vp", "director", "senior", or null
   - "c_suite" for CEO, CFO, CTO, CMO, COO, CRO, Chief anything
   - "vp" for VP, Vice President
   - "director" for Director level
   - "senior" for Senior Manager, Head of (non-VP)

5. "extracted_salary_min": Integer or null - Minimum salary in USD if mentioned

6. "extracted_salary_max": Integer or null - Maximum salary in USD if mentioned

7. "extracted_domain": String or null - Company website domain if you can infer it (e.g., "acme.com")

Respond ONLY with the JSON object, no other text."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.settings.analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                ),
            )
            
            # Parse JSON response
            text = self._clean_json_text(response.text)
            if not text:
                return GeminiAnalysis(
                    relevance_score=5,
                    is_qualified=False,
                    reasoning="Model returned empty response (likely filtered or safety block).",
                )
            
            data = json.loads(text)
            
            # Enforce qualification threshold in code (safeguard against model inconsistency)
            score = data.get("relevance_score", 5)
            is_qualified = score >= 5
            
            return GeminiAnalysis(
                relevance_score=score,
                is_qualified=is_qualified,
                reasoning=data.get("reasoning", "Analysis completed"),
                extracted_seniority=data.get("extracted_seniority"),
                extracted_salary_min=data.get("extracted_salary_min"),
                extracted_salary_max=data.get("extracted_salary_max"),
                extracted_domain=data.get("extracted_domain"),
            )
        except Exception as e:
            # Fallback: Save the lead anyway so the user can see it, rather than blocking on AI errors
            raw_text = response.text[:200] if 'response' in locals() and hasattr(response, 'text') else 'N/A'
            return GeminiAnalysis(
                relevance_score=5,
                is_qualified=True,  # Default to True on error so we don't lose the lead
                reasoning=f"Auto-saved. AI Analysis failed: {str(e)}. Raw: {raw_text}...",
                extracted_seniority=None,
                extracted_salary_min=None,
                extracted_salary_max=None,
                extracted_domain=None,
            )
    
    async def rank_contacts(
        self,
        lead: Lead,
        contacts: List[Contact],
    ) -> tuple[Optional[Contact], str]:
        """
        Pick the best contact for outreach from a list of found contacts.
        
        Returns the best contact and the reasoning for the selection.
        """
        if not contacts:
            return None, "No contacts available"
        
        if len(contacts) == 1:
            return contacts[0], "Only one contact available"
        
        # Build contact list for prompt
        contact_list = []
        for i, contact in enumerate(contacts):
            contact_list.append(
                f"{i+1}. {contact.name}"
                f"\n   Title: {contact.title or 'Unknown'}"
                f"\n   Email: {contact.email or 'Unknown'}"
                f"\n   Confidence: {contact.email_confidence or 'Unknown'}%"
                f"\n   Source: {contact.source or 'Unknown'}"
            )
        contacts_text = "\n\n".join(contact_list)
        
        prompt = f"""You are an executive recruiting AI. We need to reach out about an open position. Pick the best contact to email.

## Open Position
Title: {lead.title}
Company: {lead.company_name}
Seniority: {lead.seniority_level or 'Unknown'}

## Available Contacts
{contacts_text}

## Instructions
Choose the best contact to reach out to. Consider:
1. Who is most likely the hiring decision-maker for this role?
2. Higher email confidence scores are better
3. C-level executives usually hire for VP roles
4. VPs usually hire for Director roles
5. HR/Talent leaders coordinate but may not be decision-makers

Respond with a JSON object:
{{
    "selected_index": <1-based index of best contact>,
    "reasoning": "<1-2 sentences explaining why this person>"
}}

Respond ONLY with the JSON object."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.settings.analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=200,
                ),
            )
            
            text = self._clean_json_text(response.text)
            
            data = json.loads(text)
            selected_index = data.get("selected_index", 1) - 1  # Convert to 0-based
            reasoning = data.get("reasoning", "Selected as best match")
            selected_index = data.get("selected_index", 1) - 1  # Convert to 0-based
            reasoning = data.get("reasoning", "Selected as best match")
            
            if 0 <= selected_index < len(contacts):
                return contacts[selected_index], reasoning
            else:
                return contacts[0], "Default selection (index out of range)"
                
        except Exception as e:
            # Default to first contact on error
            return contacts[0], f"Default selection (error: {str(e)})"
    
    async def generate_outreach_email(
        self,
        lead: Lead,
        contact: Contact,
        sender_name: str = "Aaron",
        sender_company: str = "Matcha Recruit",
    ) -> tuple[str, str]:
        """
        Generate a personalized cold outreach email.
        
        Returns (subject, body) tuple.
        """
        prompt = f"""You are an executive recruiter writing a cold outreach email. Write a professional, personalized email.

## About the Open Position
Title: {lead.title}
Company: {lead.company_name}
Location: {lead.location or 'Not specified'}
Description: {(lead.job_description or 'Executive leadership role')[:500]}

## Recipient
Name: {contact.name}
Title: {contact.title or 'Executive'}

## Sender
Name: {sender_name}
Company: {sender_company}

## Instructions
Write a cold outreach email:
1. Keep it SHORT (3-4 paragraphs, under 150 words total)
2. Personalize based on their title and company
3. Mention the specific role we can help fill
4. Value proposition: We specialize in executive search with AI-powered culture matching
5. Clear call-to-action: Request a brief call
6. Professional but warm tone
7. No fluff or generic statements

Respond with a JSON object:
{{
    "subject": "<email subject line - make it compelling but professional>",
    "body": "<email body - use \\n for line breaks>"
}}

Respond ONLY with the JSON object."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.settings.analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=500,
                ),
            )
            
            text = self._clean_json_text(response.text)
            
            data = json.loads(text)
            selected_index = data.get("selected_index", 1) - 1  # Convert to 0-based
            reasoning = data.get("reasoning", "Selected as best match")
            subject = data.get("subject", f"Executive Search Partnership - {lead.title}")
            body = data.get("body", "").replace("\\n", "\n")
            
            return subject, body
            
        except Exception as e:
            # Return a basic template on error
            subject = f"Executive Search Partnership - {lead.title} at {lead.company_name}"
            body = f"""Hi {contact.first_name or contact.name.split()[0]},

I noticed your team is hiring a {lead.title}. At {sender_company}, we specialize in executive search with AI-powered culture matching that helps find leaders who truly fit.

Would you be open to a brief call this week to discuss how we might help?

Best regards,
{sender_name}
{sender_company}"""
            return subject, body


    async def find_decision_maker_from_search(
        self,
        company_name: str,
        role_title: str,
        search_results: str,
    ) -> Optional[dict]:
        """
        Identify the likely decision maker from search results.
        
        Returns dict with {name, title, reason} or None.
        """
        prompt = f"""You are an executive recruiter researcher. We are trying to find the hiring manager for a specific role.

## Target Company
Company: {company_name}
Open Role: {role_title}

## Web Search Results (Leadership Team)
{search_results[:3000]}

## Instructions
Identify the most likely person to be the hiring manager or key decision-maker for this role.
- For C-level roles (e.g. CTO), look for the CEO or Founder.
- For VP roles (e.g. VP Sales), look for the C-level equivalent (e.g. CRO or CEO).
- For Director roles, look for the VP.

Respond with a JSON object:
{{
    "name": "<Name of the person>",
    "title": "<Their Title>",
    "reasoning": "<Why you picked them based on the search results>"
}}

If you cannot find a specific person's name in the results, return null.

Respond ONLY with the JSON object."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.settings.analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=200,
                ),
            )
            
            text = self._clean_json_text(response.text)
            if not text or text == "null":
                return None
            
            return json.loads(text)
            
        except Exception as e:
            print(f"[Gemini] Error finding decision maker: {e}")
            return None


# Singleton instance
_gemini_leads: Optional[GeminiLeadsService] = None


def get_gemini_leads_service() -> GeminiLeadsService:
    """Get the Gemini leads service instance."""
    global _gemini_leads
    if _gemini_leads is None:
        _gemini_leads = GeminiLeadsService()
    return _gemini_leads
