"""on_worker_ready's dispatch table — every (task_key, module, callable) entry
must resolve to a real Celery task, and task_keys must be unique (they're the
scheduler_settings primary key AND the dict key `_scheduler_flags` returns
lookups by). A typo here silently drops a scheduled task with no error until
someone notices it never runs — exactly the failure mode the old copy-pasted
if/else block was prone to.
"""

import importlib
import sys
from types import ModuleType

import pytest

# Stub google.genai before any app imports (matches other app.main tests).
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

from app.workers.celery_app import _SCHEDULED_TASKS, celery_app


def test_schedule_eligibility_is_registered_during_worker_startup():
    module_path = "app.workers.tasks.schedule_eligibility"

    assert module_path in celery_app.conf.include
    celery_app.loader.import_default_modules()
    assert "schedule_eligibility.run" in celery_app.tasks


def test_task_keys_are_unique():
    keys = [key for key, _, _ in _SCHEDULED_TASKS]
    assert len(keys) == len(set(keys)), "duplicate task_key would collide in _scheduler_flags()"


@pytest.mark.parametrize("task_key,module_path,callable_name", _SCHEDULED_TASKS)
def test_entry_resolves_to_a_celery_task(task_key, module_path, callable_name):
    module = importlib.import_module(module_path)
    task = getattr(module, callable_name, None)
    assert task is not None, f"{module_path}.{callable_name} does not exist ({task_key})"
    assert hasattr(task, "delay"), f"{module_path}.{callable_name} is not a Celery task ({task_key})"
