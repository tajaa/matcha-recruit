"""
Contact Finder Service

Finds decision-maker contacts using multiple providers:
1. Hunter.io - Domain search for verified emails
2. Apollo.io - People search by company + title (optional)
3. AI suggestions - Educated guesses based on role

Priority: Hunter (verified emails) > Apollo > AI suggestions
"""

import re
from typing import Optional, List
from urllib.parse import quote_plus

import httpx
from pydantic import BaseModel

from ...config import get_settings
from ..models.leads_agent import HunterContact, ContactFinderResult


class CompanyEnrichment(BaseModel):
    """Company information from enrichment API."""
    domain: str
    name: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None


class SuggestedContact(BaseModel):
    """AI-suggested contact based on role analysis."""
    suggested_title: str
    reason: str
    linkedin_search_url: str
    priority: int  # 1 = highest


class ContactFinderService:
    """
    Find decision-maker contacts for executive positions.
    
    Uses Hunter.io as primary source, with fallback to Apollo and AI suggestions.
    """
    
    def __init__(self):
        self.settings = get_settings()
    
    async def find_contacts(
        self,
        company_name: str,
        company_domain: Optional[str],
        position_title: str,
        seniority: Optional[str] = None,
    ) -> ContactFinderResult:
        """
        Find likely hiring decision-makers for a position.
        
        Args:
            company_name: Name of the company
            company_domain: Company website domain (e.g., 'acme.com')
            position_title: Title of the position being filled
            seniority: Seniority level ('c_suite', 'vp', 'director', 'senior')
        
        Returns:
            ContactFinderResult with found contacts and their confidence scores
        """
        # If no domain, try to guess it from company name
        if not company_domain:
            company_domain = self._guess_domain(company_name)
        
        if not company_domain:
            return ContactFinderResult(
                domain="unknown",
                contacts_found=0,
                contacts=[],
                source="none",
                error="Could not determine company domain"
            )
        
        # Try Hunter.io first (best for verified emails)
        if self.settings.hunter_api_key:
            result = await self.search_hunter(
                domain=company_domain,
                seniority=seniority,
                position_title=position_title,
            )
            if result.contacts:
                return result
        
        # Fallback to Apollo if available
        if self.settings.apollo_api_key:
            decision_maker_titles = self._get_decision_maker_titles(position_title, seniority)
            result = await self.search_apollo(
                company_name=company_name,
                titles=decision_maker_titles,
            )
            if result.contacts:
                return result
        
        # Return empty result if no API keys configured
        return ContactFinderResult(
            domain=company_domain,
            contacts_found=0,
            contacts=[],
            source="none",
            error="No contact finder API keys configured"
        )
    
    async def search_hunter(
        self,
        domain: str,
        seniority: Optional[str] = None,
        position_title: Optional[str] = None,
    ) -> ContactFinderResult:
        """
        Search Hunter.io for contacts at a domain.
        
        Hunter API: GET https://api.hunter.io/v2/domain-search
        - Returns emails with confidence scores
        - Can filter by seniority (executive, senior, etc.)
        - Can filter by department (executive, human_resources, etc.)
        """
        if not self.settings.hunter_api_key:
            return ContactFinderResult(
                domain=domain,
                contacts_found=0,
                contacts=[],
                source="hunter",
                error="Hunter.io API key not configured"
            )
        
        # Map our seniority levels to Hunter's
        hunter_seniority = None
        if seniority:
            seniority_map = {
                "c_suite": "executive",
                "vp": "executive",
                "director": "senior",
                "senior": "senior",
            }
            hunter_seniority = seniority_map.get(seniority)
        
        # Determine which departments to search
        # For executive hires, look at executive and HR
        departments = ["executive"]
        if position_title and any(hr_word in position_title.lower() for hr_word in ["hr", "human", "people", "talent"]):
            departments = ["human_resources"]
        
        params = {
            "domain": domain,
            "api_key": self.settings.hunter_api_key,
            "limit": 10,
        }
        
        if hunter_seniority:
            params["seniority"] = hunter_seniority
        
        if departments:
            params["department"] = ",".join(departments)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.hunter.io/v2/domain-search",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            return ContactFinderResult(
                domain=domain,
                contacts_found=0,
                contacts=[],
                source="hunter",
                error=f"Hunter.io API error: {str(e)}"
            )
        
        contacts = []
        for email_data in data.get("data", {}).get("emails", []):
            contacts.append(HunterContact(
                email=email_data.get("value", ""),
                first_name=email_data.get("first_name"),
                last_name=email_data.get("last_name"),
                position=email_data.get("position"),
                seniority=email_data.get("seniority"),
                department=email_data.get("department"),
                linkedin=email_data.get("linkedin"),
                confidence=email_data.get("confidence", 0),
            ))
        
        # Sort by confidence score
        contacts.sort(key=lambda c: c.confidence, reverse=True)
        
        return ContactFinderResult(
            domain=domain,
            contacts_found=len(contacts),
            contacts=contacts,
            source="hunter",
        )
    
    async def search_apollo(
        self,
        company_name: str,
        titles: List[str],
    ) -> ContactFinderResult:
        """
        Search Apollo.io for people by company and title.
        
        Apollo API: POST https://api.apollo.io/v1/mixed_people/search
        """
        if not self.settings.apollo_api_key:
            return ContactFinderResult(
                domain=company_name,
                contacts_found=0,
                contacts=[],
                source="apollo",
                error="Apollo.io API key not configured"
            )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.apollo.io/v1/mixed_people/search",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                    },
                    json={
                        "api_key": self.settings.apollo_api_key,
                        "q_organization_name": company_name,
                        "person_titles": titles,
                        "per_page": 10,
                    }
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            return ContactFinderResult(
                domain=company_name,
                contacts_found=0,
                contacts=[],
                source="apollo",
                error=f"Apollo.io API error: {str(e)}"
            )
        
        contacts = []
        for person in data.get("people", []):
            email = person.get("email")
            if not email:
                continue
            
            contacts.append(HunterContact(
                email=email,
                first_name=person.get("first_name"),
                last_name=person.get("last_name"),
                position=person.get("title"),
                seniority=person.get("seniority"),
                department=None,
                linkedin=person.get("linkedin_url"),
                confidence=80 if person.get("email_status") == "verified" else 50,
            ))
        
        return ContactFinderResult(
            domain=company_name,
            contacts_found=len(contacts),
            contacts=contacts,
            source="apollo",
        )
    
    async def enrich_company(self, domain: str) -> Optional[CompanyEnrichment]:
        """
        Get company info from Clearbit.
        
        Clearbit API: GET https://company.clearbit.com/v2/companies/find
        """
        if not self.settings.clearbit_api_key:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://company.clearbit.com/v2/companies/find",
                    params={"domain": domain},
                    headers={
                        "Authorization": f"Bearer {self.settings.clearbit_api_key}",
                    }
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            return None
        
        return CompanyEnrichment(
            domain=domain,
            name=data.get("name"),
            industry=data.get("category", {}).get("industry"),
            employee_count=data.get("metrics", {}).get("employeesRange"),
            linkedin_url=data.get("linkedin", {}).get("handle"),
            twitter_handle=data.get("twitter", {}).get("handle"),
        )
    
    def suggest_decision_makers(
        self,
        position_title: str,
        seniority: Optional[str],
        company_name: str,
    ) -> List[SuggestedContact]:
        """
        AI-powered suggestions for who to contact based on role being hired.
        
        Logic:
        - C-suite hire (CEO, CFO, CTO) → Board, CEO, existing C-suite
        - VP hire → C-level of that function, CEO
        - Director hire → VP of that function
        - Always suggest: Head of Talent, VP People/HR
        
        Returns LinkedIn search URLs and title patterns.
        """
        suggestions = []
        title_lower = position_title.lower()
        company_encoded = quote_plus(company_name)
        
        # Determine function area
        function_area = self._detect_function_area(title_lower)
        
        # C-suite hires
        if seniority == "c_suite" or any(c in title_lower for c in ["ceo", "cfo", "cto", "cmo", "coo", "cro", "chief"]):
            suggestions.append(SuggestedContact(
                suggested_title="CEO / Founder",
                reason="CEO typically makes final decision on C-suite hires",
                linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords=CEO%20{company_encoded}",
                priority=1,
            ))
            suggestions.append(SuggestedContact(
                suggested_title="Board Member",
                reason="Board often involved in executive hiring",
                linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords=Board%20Director%20{company_encoded}",
                priority=2,
            ))
        
        # VP hires
        elif seniority == "vp" or "vp" in title_lower or "vice president" in title_lower:
            # Suggest the C-level of that function
            if function_area:
                c_title = self._get_c_level_for_function(function_area)
                suggestions.append(SuggestedContact(
                    suggested_title=c_title,
                    reason=f"{c_title} typically hires their VP reports",
                    linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(c_title)}%20{company_encoded}",
                    priority=1,
                ))
            suggestions.append(SuggestedContact(
                suggested_title="CEO",
                reason="CEO often involved in VP-level hires",
                linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords=CEO%20{company_encoded}",
                priority=2,
            ))
        
        # Director hires
        elif seniority == "director" or "director" in title_lower:
            if function_area:
                vp_title = f"VP {function_area}"
                suggestions.append(SuggestedContact(
                    suggested_title=vp_title,
                    reason=f"{vp_title} typically hires Director reports",
                    linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(vp_title)}%20{company_encoded}",
                    priority=1,
                ))
        
        # Always suggest HR/Talent
        suggestions.append(SuggestedContact(
            suggested_title="VP People / Head of HR",
            reason="HR leaders often coordinate executive recruiting",
            linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords=VP%20People%20OR%20Head%20HR%20{company_encoded}",
            priority=3,
        ))
        suggestions.append(SuggestedContact(
            suggested_title="Head of Talent Acquisition",
            reason="Talent leaders manage recruiting for senior roles",
            linkedin_search_url=f"https://www.linkedin.com/search/results/people/?keywords=Head%20Talent%20{company_encoded}",
            priority=4,
        ))
        
        # Sort by priority
        suggestions.sort(key=lambda s: s.priority)
        
        return suggestions
    
    def guess_email_patterns(
        self,
        domain: str,
        first_name: str,
        last_name: str,
    ) -> List[str]:
        """
        Generate likely email patterns for a person.
        
        Common patterns:
        - firstname.lastname@domain.com
        - firstname@domain.com
        - flastname@domain.com
        - firstnamel@domain.com
        """
        first = first_name.lower().strip()
        last = last_name.lower().strip()
        
        if not first or not last:
            return []
        
        patterns = [
            f"{first}.{last}@{domain}",
            f"{first}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}{last[0]}@{domain}",
            f"{first}_{last}@{domain}",
            f"{last}.{first}@{domain}",
            f"{first[0]}.{last}@{domain}",
        ]
        
        return patterns
    
    def _guess_domain(self, company_name: str) -> Optional[str]:
        """Guess company domain from name."""
        # Clean up company name
        name = company_name.lower().strip()
        # Remove common suffixes
        for suffix in [" inc", " inc.", " llc", " ltd", " corp", " corporation", " co"]:
            name = name.replace(suffix, "")
        # Remove special characters and spaces
        name = re.sub(r"[^a-z0-9]", "", name)
        
        if name:
            return f"{name}.com"
        return None
    
    def _get_decision_maker_titles(
        self,
        position_title: str,
        seniority: Optional[str],
    ) -> List[str]:
        """Get likely decision-maker titles based on position."""
        titles = []
        title_lower = position_title.lower()
        function_area = self._detect_function_area(title_lower)
        
        if seniority == "c_suite" or "chief" in title_lower:
            titles = ["CEO", "Chief Executive Officer", "Founder", "Board Director"]
        elif seniority == "vp" or "vp" in title_lower:
            if function_area:
                c_title = self._get_c_level_for_function(function_area)
                titles.append(c_title)
            titles.extend(["CEO", "Chief Executive Officer"])
        elif seniority == "director":
            if function_area:
                titles.append(f"VP {function_area}")
                titles.append(f"Vice President {function_area}")
        
        # Always include HR
        titles.extend(["VP People", "VP Human Resources", "Head of HR", "Head of Talent"])
        
        return titles
    
    def _detect_function_area(self, title_lower: str) -> Optional[str]:
        """Detect the functional area from a title."""
        function_keywords = {
            "Engineering": ["engineering", "software", "tech", "development", "developer"],
            "Sales": ["sales", "revenue", "account"],
            "Marketing": ["marketing", "growth", "brand"],
            "Finance": ["finance", "financial", "accounting", "controller"],
            "Operations": ["operations", "ops", "logistics"],
            "Product": ["product"],
            "People": ["people", "hr", "human resources", "talent"],
            "Legal": ["legal", "counsel", "compliance"],
            "Data": ["data", "analytics", "business intelligence"],
        }
        
        for function, keywords in function_keywords.items():
            if any(kw in title_lower for kw in keywords):
                return function
        
        return None
    
    def _get_c_level_for_function(self, function: str) -> str:
        """Get the C-level title for a function."""
        c_level_map = {
            "Engineering": "CTO",
            "Sales": "CRO",
            "Marketing": "CMO",
            "Finance": "CFO",
            "Operations": "COO",
            "Product": "CPO",
            "People": "CHRO",
            "Legal": "CLO",
            "Data": "CDO",
        }
        return c_level_map.get(function, "CEO")


# Singleton instance
_contact_finder: Optional[ContactFinderService] = None


def get_contact_finder() -> ContactFinderService:
    """Get the contact finder service instance."""
    global _contact_finder
    if _contact_finder is None:
        _contact_finder = ContactFinderService()
    return _contact_finder
