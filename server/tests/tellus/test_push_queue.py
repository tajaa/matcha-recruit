"""Tests for services/push.py's per-request queue + post-commit flush (no DB,
no APNs — send/dispatch are monkeypatched out). Covers the two bugs from the
2026-08-14 push-notifications code review: a discarded asyncio.create_task
handle that let the loop GC an in-flight send, and schedule_push dispatching
before the caller's DB transaction committed.
"""
import asyncio
from uuid import uuid4

import pytest

from app.tellus.services import push


@pytest.mark.asyncio
async def test_enqueues_during_request_and_flushes_on_success(monkeypatch):
    dispatched = []
    monkeypatch.setattr(push, "_is_configured", lambda: True)
    monkeypatch.setattr(push, "_dispatch", lambda job: dispatched.append(job))

    gen = push.flush_pushes()
    await gen.__anext__()
    push.schedule_push([uuid4()], "board_post", "New post")
    assert dispatched == [], "must not dispatch before the request finishes"

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_exception_in_request_drops_the_queue(monkeypatch):
    dispatched = []
    monkeypatch.setattr(push, "_is_configured", lambda: True)
    monkeypatch.setattr(push, "_dispatch", lambda job: dispatched.append(job))

    gen = push.flush_pushes()
    await gen.__anext__()
    push.schedule_push([uuid4()], "board_post", "New post")

    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("handler blew up after queuing the push"))
    assert dispatched == [], "a rolled-back handler must never dispatch its queued pushes"


def test_dispatches_immediately_outside_a_request(monkeypatch):
    dispatched = []
    monkeypatch.setattr(push, "_is_configured", lambda: True)
    monkeypatch.setattr(push, "_dispatch", lambda job: dispatched.append(job))

    push.schedule_push([uuid4()], "board_post", "New post")
    assert len(dispatched) == 1


def test_kind_outside_push_kinds_never_dispatched(monkeypatch):
    dispatched = []
    monkeypatch.setattr(push, "_is_configured", lambda: True)
    monkeypatch.setattr(push, "_dispatch", lambda job: dispatched.append(job))

    push.schedule_push([uuid4()], "points_earned", "Points!")
    assert dispatched == []


def test_empty_account_ids_never_dispatched(monkeypatch):
    dispatched = []
    monkeypatch.setattr(push, "_is_configured", lambda: True)
    monkeypatch.setattr(push, "_dispatch", lambda job: dispatched.append(job))

    push.schedule_push([], "board_post", "New post")
    assert dispatched == []


@pytest.mark.asyncio
async def test_dispatch_tracks_task_in_inflight_set(monkeypatch):
    async def fake_safe_send(*_args, **_kwargs):
        return None

    monkeypatch.setattr(push, "_safe_send", fake_safe_send)
    created = {}
    real_create_task = asyncio.create_task

    def spy_create_task(coro):
        task = real_create_task(coro)
        created["task"] = task
        return task

    monkeypatch.setattr(asyncio, "create_task", spy_create_task)
    before = len(push._inflight)

    push._dispatch(([uuid4()], "title", None, {}))
    assert len(push._inflight) == before + 1, "task must be held strongly, not just fire-and-forget"

    await created["task"]  # drive it to completion so its done-callback discards it
    assert len(push._inflight) == before
