import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Mock the Google GenAI SDK before importing service modules
# google.genai comes from tests/conftest.py (real SDK when installed, one
# permissive stub otherwise). Never override sys.modules for it here — the
# override leaks process-wide and breaks whichever test imports next.

from app.config import load_settings
from app.matcha.services.matcha_work_ai import GeminiProvider, AIResponse

@pytest.fixture(scope="module", autouse=True)
def setup_settings():
    load_settings()

# Mock helper classes for response candidates
class MockPart:
    def __init__(self, text=None, inline_data=None):
        self.text = text
        self.inline_data = inline_data

class MockInlineData:
    def __init__(self, data, mime_type="image/png"):
        self.data = data
        self.mime_type = mime_type

class MockContent:
    def __init__(self, parts):
        self.parts = parts

class MockCandidate:
    def __init__(self, content):
        self.content = content

class MockResponse:
    def __init__(self, candidates, usage_metadata=None):
        self.candidates = candidates
        self.usage_metadata = usage_metadata

class MockUsageMetadata:
    def __init__(self, prompt_token_count=10, candidates_token_count=1024, total_token_count=1034):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.total_token_count = total_token_count

class MockModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({
            "model": model,
            "contents": contents,
            "config": config
        })
        parts = [
            MockPart(text="Here is your beautiful matcha cup!"),
            MockPart(inline_data=MockInlineData(data=b"mock_image_bytes"))
        ]
        return MockResponse(
            candidates=[MockCandidate(content=MockContent(parts=parts))],
            usage_metadata=MockUsageMetadata()
        )

class MockClient:
    def __init__(self):
        self.models = MockModels()


@pytest.mark.asyncio
@patch("app.core.services.storage.get_storage")
async def test_image_generation_routing_and_upload(mock_get_storage):
    # Setup mock storage upload_file to return a mock CDN URL (async)
    mock_storage = MagicMock()
    mock_storage.upload_file = AsyncMock(return_value="https://cdn.example.com/mock_image.png")
    mock_get_storage.return_value = mock_storage

    # Initialize provider and assign our MockClient
    provider = GeminiProvider()
    mock_client = MockClient()
    provider._client = mock_client

    # Test prompt that triggers image generation
    messages = [
        {"role": "user", "content": "Can you generate a beautiful image of matcha green tea on a table?"}
    ]

    response = await provider.generate(
        messages=messages,
        current_state={},
        company_id="11111111-1111-1111-1111-111111111111",
        thread_id="22222222-2222-2222-2222-222222222222"
    )

    # Verify that the image preview model was called
    assert len(mock_client.models.calls) == 1
    assert mock_client.models.calls[0]["model"] == "gemini-3.1-flash-image-preview"

    # Verify storage upload was called with expected arguments
    mock_storage.upload_file.assert_called_once()
    args, kwargs = mock_storage.upload_file.call_args
    assert args[0] == b"mock_image_bytes"
    assert kwargs["content_type"] == "image/png"
    assert "companies/11111111-1111-1111-1111-111111111111/threads/22222222-2222-2222-2222-222222222222/images" in kwargs["prefix"]

    # Verify that the response includes the correct properties and attachments metadata
    assert isinstance(response, AIResponse)
    assert response.assistant_reply == "Here is your beautiful matcha cup!"
    assert response.attachments is not None
    assert len(response.attachments) == 1
    assert response.attachments[0]["url"] == "https://cdn.example.com/mock_image.png"
    assert response.attachments[0]["kind"] == "image"


@pytest.mark.asyncio
@patch("app.matcha.services.matcha_work_ai._get_model")
@patch("app.core.services.storage.get_storage")
async def test_non_image_requests_normal_flow(mock_get_storage, mock_get_model):
    mock_get_model.return_value = "gemini-3.5-flash"
    
    # Setup provider and mock it to bypass real API calls for normal flow
    provider = GeminiProvider()
    
    # We mock _call_gemini to see if it routes normal messages to standard generation
    with patch.object(provider, "_call_gemini", return_value=AIResponse(assistant_reply="Standard reply")) as mock_call:
        messages = [
            {"role": "user", "content": "How do I draft an offer letter?"}
        ]
        
        response = await provider.generate(
            messages=messages,
            current_state={},
        )
        
        # Verify it went to _call_gemini (the standard text model flow)
        mock_call.assert_called_once()
        assert response.assistant_reply == "Standard reply"
        assert response.attachments is None
