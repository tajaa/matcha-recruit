"""Research tasks — AI-driven browse-and-summarize inputs on a project.

Split out of `tasks.py` (2026-07-19). The persistence layer moved to
`app/matcha/services/research_task_service.py`; what stays here is the HTTP
shape — auth/access checks, error translation, and the three SSE streams.

The SSE generators stay in the route on purpose: they are HTTP framing, not
business logic. The service owns the "claim" step each stream begins with (flip
inputs to `running` inside a FOR UPDATE txn), which is the part that must not
race.

Storage note: research tasks are lists inside `mw_projects.project_data` JSONB,
not their own table — see the service module docstring.
"""
import asyncio
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.matcha_work._shared import _sse_data, _verify_project_access

router = APIRouter()


@router.post("/projects/{project_id}/research-tasks")
async def create_research_task(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new research task in a project."""
    from app.matcha.services import research_task_service as rt_svc

    await _verify_project_access(project_id, current_user)
    return await rt_svc.create_task(
        project_id,
        name=body.get("name", "Untitled Research"),
        instructions=body.get("instructions", ""),
    )

@router.put("/projects/{project_id}/research-tasks/{task_id}")
async def update_research_task(
    project_id: UUID,
    task_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a research task definition."""
    from app.matcha.services import research_task_service as rt_svc

    await _verify_project_access(project_id, current_user)
    try:
        return await rt_svc.update_task(project_id, task_id, body)
    except rt_svc.ResearchTaskError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.delete("/projects/{project_id}/research-tasks/{task_id}")
async def delete_research_task(
    project_id: UUID,
    task_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Delete a research task and all its results."""
    from app.matcha.services import research_task_service as rt_svc

    await _verify_project_access(project_id, current_user)
    return await rt_svc.delete_task(project_id, task_id)

@router.post("/projects/{project_id}/research-tasks/{task_id}/inputs")
async def add_research_inputs(
    project_id: UUID,
    task_id: str,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add URLs to a research task."""
    from app.matcha.services import research_task_service as rt_svc

    await _verify_project_access(project_id, current_user)
    try:
        return await rt_svc.add_inputs(project_id, task_id, body.get("urls", []))
    except rt_svc.ResearchTaskError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

@router.delete("/projects/{project_id}/research-tasks/{task_id}/inputs/{input_id}")
async def delete_research_input(
    project_id: UUID,
    task_id: str,
    input_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a URL from a research task."""
    from app.matcha.services import research_task_service as rt_svc

    await _verify_project_access(project_id, current_user)
    try:
        return await rt_svc.delete_input(project_id, task_id, input_id)
    except rt_svc.ResearchTaskError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

async def _stream_one_input(
    *, project_id, task_id, input_id, url, instructions, capture_screenshot=None,
    company_id=None, emit_start: str = None,
):
    """Run one browse pass, relaying its status callbacks as SSE frames.

    `run_research_for_input` reports progress through an `on_status` callback,
    which can't be yielded from directly — so the pass runs as a background task
    and its messages come back over a queue that this generator drains on a 1s
    tick until the task completes, then once more for anything still buffered.
    """
    from app.matcha.services.research_browse_service import run_research_for_input

    if emit_start:
        yield _sse_data({"type": "status", "input_id": input_id, "url": url,
                         "message": emit_start})

    status_queue: asyncio.Queue = asyncio.Queue()

    async def stream_status(msg: str):
        await status_queue.put(msg)

    # `retry` deliberately calls through without capture_screenshot/company_id
    # (it never passed them); keep that by only forwarding when supplied.
    extra = {}
    if capture_screenshot is not None:
        extra["capture_screenshot"] = capture_screenshot
    if company_id is not None:
        extra["company_id"] = company_id

    browse_task = asyncio.create_task(
        run_research_for_input(
            project_id, task_id, input_id, url, instructions,
            on_status=stream_status, **extra,
        )
    )

    while not browse_task.done():
        try:
            msg = await asyncio.wait_for(status_queue.get(), timeout=1.0)
            yield _sse_data({"type": "status", "input_id": input_id, "message": msg})
        except asyncio.TimeoutError:
            pass

    while not status_queue.empty():
        msg = status_queue.get_nowait()
        yield _sse_data({"type": "status", "input_id": input_id, "message": msg})

    result = browse_task.result()
    yield _sse_data({
        "type": "complete" if not result.get("error") else "error",
        "input_id": input_id,
        "url": url,
        "findings": result.get("findings", {}),
        "summary": result.get("summary", ""),
        "error": result.get("error"),
    })

@router.post("/projects/{project_id}/research-tasks/{task_id}/run")
async def run_research_task(
    project_id: UUID,
    task_id: str,
    capture_screenshot: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Run all pending research inputs sequentially with SSE status streaming."""
    from app.matcha.services import research_task_service as rt_svc
    from starlette.responses import StreamingResponse

    project, _role = await _verify_project_access(project_id, current_user)
    company_id = str(project.get("company_id") or await get_client_company_id(current_user))

    try:
        pending_inputs, instructions = await rt_svc.claim_pending_inputs(project_id, task_id)
    except rt_svc.ResearchTaskError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    if not pending_inputs:
        return {"queued": 0}

    async def event_stream():
        for i, inp in enumerate(pending_inputs):
            async for frame in _stream_one_input(
                project_id=project_id, task_id=task_id, input_id=inp["id"],
                url=inp["url"], instructions=instructions,
                capture_screenshot=capture_screenshot, company_id=company_id,
                emit_start=f"Starting research ({i + 1}/{len(pending_inputs)}): {inp['url']}",
            ):
                yield frame

        yield _sse_data({"type": "done",
                         "message": f"Finished researching {len(pending_inputs)} URL(s)"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/{project_id}/research-tasks/{task_id}/inputs/{input_id}/follow-up")
async def follow_up_research_input(
    project_id: UUID,
    task_id: str,
    input_id: str,
    body: dict = Body(...),
    capture_screenshot: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Re-research a URL with additional instructions, building on previous findings."""
    from app.matcha.services import research_task_service as rt_svc
    from starlette.responses import StreamingResponse

    project, _role = await _verify_project_access(project_id, current_user)
    company_id = str(project.get("company_id") or await get_client_company_id(current_user))

    follow_up = body.get("follow_up", "").strip()
    if not follow_up:
        raise HTTPException(status_code=400, detail="follow_up is required")

    follow_url, combined_instructions = await rt_svc.claim_follow_up(
        project_id, task_id, input_id, follow_up,
    )
    if not follow_url:
        raise HTTPException(status_code=404, detail="Input not found")

    async def event_stream():
        async for frame in _stream_one_input(
            project_id=project_id, task_id=task_id, input_id=input_id,
            url=follow_url, instructions=combined_instructions,
            capture_screenshot=capture_screenshot, company_id=company_id,
        ):
            yield frame
        yield _sse_data({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/{project_id}/research-tasks/{task_id}/inputs/{input_id}/retry")
async def retry_research_input(
    project_id: UUID,
    task_id: str,
    input_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Retry a failed research input with SSE streaming."""
    from app.matcha.services import research_task_service as rt_svc
    from starlette.responses import StreamingResponse

    await _verify_project_access(project_id, current_user)

    retry_url, retry_instructions = await rt_svc.claim_retry(project_id, task_id, input_id)
    if not retry_url:
        raise HTTPException(status_code=404, detail="Input not found")

    async def event_stream():
        async for frame in _stream_one_input(
            project_id=project_id, task_id=task_id, input_id=input_id,
            url=retry_url, instructions=retry_instructions,
        ):
            yield frame
        yield _sse_data({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/projects/{project_id}/research-tasks/{task_id}/stop")
async def stop_research_task(
    project_id: UUID,
    task_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reset all running inputs back to pending (cancel in-flight research)."""
    from app.matcha.services import research_task_service as rt_svc

    await _verify_project_access(project_id, current_user)
    return await rt_svc.stop_task(project_id, task_id)
