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


@pytest.mark.parametrize("default_queue", [True, False])
def test_worker_startup_recovers_auto_schedule_dispatch_only_on_default_queue(monkeypatch, default_queue):
    from unittest.mock import Mock
    from app.workers.tasks import schedule_auto_generation as automatic

    module = importlib.import_module("app.workers.celery_app")
    monkeypatch.setattr(module, "_serves_default_queue", lambda _sender: default_queue)
    monkeypatch.setattr(module, "_scheduler_flags", lambda _keys: {})
    # No startup test should publish to a real broker. Patch the defining
    # task objects for every unconditional recovery hook.
    recoveries = [
        ("er_document_processing", "reset_stale_er_documents"),
        ("huume_code", "reconcile_stale_runs"),
        ("project_agent", "reconcile_stale_runs"),
        ("schedule_break_refresh", "recover_stale_employee_schedule_breaks"),
        ("auth_device_sessions", "prune_device_sessions"),
    ]
    for task_module, name in recoveries:
        task = getattr(importlib.import_module(f"app.workers.tasks.{task_module}"), name)
        monkeypatch.setattr(task, "delay", Mock())
    dispatch = Mock()
    monkeypatch.setattr(automatic.dispatch_schedule_automation, "delay", dispatch)
    module.on_worker_ready(sender=object())
    assert dispatch.call_count == int(default_queue)


def test_admin_can_trigger_auto_schedule_dispatch(monkeypatch):
    import asyncio
    from unittest.mock import Mock
    from app.core.routes.admin import platform_settings
    from app.workers.tasks import schedule_auto_generation as automatic

    class Conn:
        async def fetchrow(self, _query, key):
            assert key == automatic.DISPATCH_TASK_KEY
            return {"task_key": key}

    class Context:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(platform_settings, "get_connection", Context)
    publish = Mock()
    monkeypatch.setattr(automatic.dispatch_schedule_automation, "delay", publish)
    result = asyncio.run(platform_settings.trigger_scheduler(automatic.DISPATCH_TASK_KEY))
    assert result["status"] == "triggered" and result["task_key"] == automatic.DISPATCH_TASK_KEY
    publish.assert_called_once()
