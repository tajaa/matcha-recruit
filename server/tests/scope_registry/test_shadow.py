"""Shadow diff semantics + guardrails. Pure where possible; no live DB."""
import pytest

from app.core.services.scope_registry import shadow


def test_shadow_module_imports_and_is_guarded():
    # record_shadow must be an async function that never surfaces exceptions —
    # the finalize flow depends on it being fire-and-forget safe.
    import inspect
    assert inspect.iscoroutinefunction(shadow.record_shadow)


def test_diff_direction_semantics():
    """The set math the recorder uses — only_in_* are asymmetric differences."""
    resolve_keys = {"fmla", "osha_general_duty", "ab701_quota_notice"}
    expand_keys = {"fmla", "osha_general_duty", "some_category_grab_extra"}

    only_in_resolve = sorted(resolve_keys - expand_keys)
    only_in_expand = sorted(expand_keys - resolve_keys)

    # Precision the registry adds (classified applicable, grab missed it).
    assert only_in_resolve == ["ab701_quota_notice"]
    # Category-grab over-inclusion (e.g. a conditional whose trigger didn't fire).
    assert only_in_expand == ["some_category_grab_extra"]
    # Agreement is the intersection, implicitly.
    assert resolve_keys & expand_keys == {"fmla", "osha_general_duty"}


@pytest.mark.asyncio
async def test_record_shadow_swallows_a_broken_connection(monkeypatch):
    """A DB failure inside the shadow must not propagate — onboarding finalize
    already returned."""
    async def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(shadow, "get_connection", _boom)
    # Must return None without raising.
    result = await shadow.record_shadow(
        session_id="00000000-0000-0000-0000-000000000000",
        company_id=None,
        industry="warehousing",
        existing_items=[],
    )
    assert result is None
