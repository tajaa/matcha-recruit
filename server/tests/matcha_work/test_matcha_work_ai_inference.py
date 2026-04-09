import sys
from types import ModuleType


google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
google_module.genai = genai_module

sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

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
