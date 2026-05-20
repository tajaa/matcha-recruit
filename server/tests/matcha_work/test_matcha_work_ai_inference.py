import sys
from types import ModuleType


google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")

class MockTool:
    def __init__(self, *args, **kwargs):
        pass

class MockGoogleSearch:
    def __init__(self, *args, **kwargs):
        pass

class MockPartClass:
    def __init__(self, text=None, *args, **kwargs):
        self.text = text
    
    @classmethod
    def from_bytes(cls, data, mime_type):
        return cls()

    @classmethod
    def from_text(cls, text):
        return cls(text=text)

class MockContentClass:
    def __init__(self, role=None, parts=None, *args, **kwargs):
        self.role = role
        self.parts = parts

types_module.Tool = MockTool
types_module.GoogleSearch = MockGoogleSearch
types_module.Part = MockPartClass
types_module.Content = MockContentClass

genai_module.Client = object
genai_module.types = types_module
class MockGenerateContentConfig:
    def __init__(self, *args, **kwargs):
        pass

class MockImageConfig:
    def __init__(self, *args, **kwargs):
        pass

class MockThinkingConfig:
    def __init__(self, *args, **kwargs):
        pass

types_module.ThinkingConfig = MockThinkingConfig
types_module.GenerateContentConfig = MockGenerateContentConfig
types_module.ImageConfig = MockImageConfig

google_module.genai = genai_module

sys.modules["google"] = google_module
sys.modules["google.genai"] = genai_module
sys.modules["google.genai.types"] = types_module

from app.matcha.services.matcha_work_ai import HANDBOOK_FIELDS, _infer_skill_from_state


def test_infer_policy_before_workbook_for_mixed_state():
    state = {
        "sections": [{"title": "Overview", "content": "Existing workbook content"}],
        "policy_title": "Code of Conduct Policy",
        "policy_status": "created",
    }

    assert _infer_skill_from_state(state) == "policy"


def test_infer_workbook_without_policy_fields():
    state = {
        "workbook_title": "Manager Playbook",
        "sections": [{"title": "Overview", "content": "Workbook content"}],
    }

    assert _infer_skill_from_state(state) == "workbook"


def test_infer_handbook_for_upload_state():
    state = {
        "handbook_source_type": "upload",
        "handbook_upload_status": "reviewed",
        "handbook_uploaded_filename": "handbook.pdf",
    }

    assert _infer_skill_from_state(state) == "handbook"


def test_handbook_ai_fields_exclude_upload_managed_state():
    assert "handbook_red_flags" not in HANDBOOK_FIELDS
    assert "handbook_upload_status" not in HANDBOOK_FIELDS
