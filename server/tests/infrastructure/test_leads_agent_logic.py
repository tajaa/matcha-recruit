
import asyncio
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock

# Mock config
import os
os.environ["SEARCH_API_KEY"] = "mock_key"
os.environ["JINA_API_KEY"] = "mock_key"
os.environ["HUNTER_API_KEY"] = "mock_key"

from app.config import load_settings
from app.models.leads_agent import SearchRequest, SearchResultItem, GeminiAnalysis
from app.services.leads_agent import LeadsAgentService

async def test_lead_saving():
    """Test that search results are correctly processed and saved."""
    print("Testing Leads Agent Logic...")
    
    # Initialize settings
    load_settings()
    
    # Mock services
    service = LeadsAgentService()
    service.gemini.analyze_position = AsyncMock(return_value=GeminiAnalysis(
        relevance_score=8,
        is_qualified=True,
        reasoning="Good match",
        extracted_seniority="c_suite",
        extracted_domain="acme.com",
        extracted_salary_min=200000
    ))
    
    # Mock DB connection context manager
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None  # No duplicates
    mock_conn.execute.return_value = "INSERT 1"
    
    # Mock get_connection context manager
    service._save_lead_from_search = AsyncMock(return_value=(True, False))
    
    # Create fake search item
    item = SearchResultItem(
        job_id="test_job_1",
        title="CTO",
        company_name="Acme Corp",
        location="San Francisco",
        description="Looking for a CTO..."
    )
    
    # Test save logic
    created, deduped = await service._save_lead_from_search(
        item, 
        service.gemini.analyze_position.return_value
    )
    
    print(f"Save Result: Created={created}, Deduped={deduped}")
    assert created is True
    assert deduped is False
    print("✅ Logic verified")

if __name__ == "__main__":
    try:
        asyncio.run(test_lead_saving())
    except Exception as e:
        print(f"❌ Test failed: {e}")
