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

from app.matcha.services.matcha_work_ai import _infer_skill_from_state


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
