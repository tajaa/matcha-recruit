# Compliance Agent Architecture

This document describes the agentic patterns implemented in the compliance research pipeline.

---

## Overview

The compliance pipeline uses Gemini AI with Google Search grounding to research employment regulations for business locations. Rather than a simple request-response pattern, it implements several agentic behaviors: retry loops with feedback, adaptive verification, graceful degradation, and real-time progress streaming.

```
User Request (check location compliance)
        ↓
    Orchestrator (compliance_service.py)
        ↓
    ┌───────────────────────────────────────┐
    │  Jurisdiction Cache Check             │
    │  (skip Gemini if data is fresh)       │
    └───────────────────────────────────────┘
        ↓ (stale or missing)
    ┌───────────────────────────────────────┐
    │  Gemini Research                      │
    │  - Retry loop with feedback           │
    │  - JSON validation + schema checks    │
    │  - Fallback to stale cache on failure │
    └───────────────────────────────────────┘
        ↓
    ┌───────────────────────────────────────┐
    │  Change Detection                     │
    │  - Numeric extraction + comparison    │
    │  - Text normalization                 │
    │  - Material change filtering          │
    └───────────────────────────────────────┘
        ↓
    ┌───────────────────────────────────────┐
    │  Adaptive Verification                │
    │  - First pass verification            │
    │  - Retry with refined prompt if grey  │
    │  - Source confidence scoring          │
    └───────────────────────────────────────┘
        ↓
    ┌───────────────────────────────────────┐
    │  Legislation Scan                     │
    │  - Best-effort (no retries)           │
    │  - Deadline escalation                │
    └───────────────────────────────────────┘
        ↓
    Results → DB + Alerts + SSE Stream
```

---

## Core Files

| File | Purpose |
|------|---------|
| `server/app/core/services/gemini_compliance.py` | Gemini API wrapper with retry, validation, adaptive verification |
| `server/app/core/services/compliance_service.py` | Pipeline orchestration, change detection, caching, streaming |
| `server/app/core/routes/compliance.py` | Client SSE endpoint |
| `server/app/core/routes/admin.py` | Admin jurisdiction check endpoint |

---

## Agentic Patterns

### 1. Retry-with-Feedback Loop

**Location:** `gemini_compliance.py` → `_call_with_retry()`

When a Gemini call fails (JSON parse error, validation failure, timeout), the system retries with feedback appended to the prompt:

```python
async def _call_with_retry(self, build_prompt_fn, parse_fn, *, max_retries=1, on_retry=None):
    for attempt in range(1 + max_retries):
        prompt = build_prompt_fn(feedback=last_error if attempt > 0 else None)
        # ... call Gemini ...
        if parse_error:
            last_error = f"PREVIOUS ATTEMPT FAILED: {parse_error}"
            continue  # retry with feedback
```

This implements a minimal ReAct loop: **attempt → observe failure → retry with context**.

**Retry budgets:**
- `research_location_compliance()`: 1 retry (90s max with 45s timeout per call)
- `verify_compliance_change()`: 1 retry
- `scan_upcoming_legislation()`: 0 retries (best-effort)

### 2. Response Validation

**Location:** `gemini_compliance.py` → `_clean_json_text()`, `_validate_requirement()`, `_validate_verification()`

Gemini responses are validated before use:

1. **JSON cleaning** — Strip markdown fences, fix Python booleans (`True`→`true`), handle truncated responses
2. **Schema validation** — Check required fields, valid categories, confidence ranges
3. **Salvage logic** — On `GeminiExhaustedError`, attempt to extract valid items from partial responses

```python
def _validate_requirement(req: dict) -> Optional[str]:
    if req.get("category") not in VALID_CATEGORIES:
        return f"Invalid category: {req.get('category')}"
    if not req.get("title"):
        return "Missing title"
    # ...
```

### 3. Adaptive Verification

**Location:** `gemini_compliance.py` → `verify_compliance_change_adaptive()`

When verifying a compliance change, if the first attempt returns low confidence (0.3–0.6), the system retries with a refined prompt:

```python
async def verify_compliance_change_adaptive(...) -> VerificationResult:
    first = await self.verify_compliance_change(...)

    if first.confidence >= 0.6 or first.confidence < 0.3:
        return first  # confident enough or hopeless

    # Grey zone: retry with targeted .gov search instructions
    refined_prompt = f"""
    Previous verification returned LOW CONFIDENCE ({first.confidence:.2f}).
    Search SPECIFICALLY for official .gov sources for {jurisdiction_name}...
    """
    second = await self._verify_with_prompt(refined_prompt)
    return second if second.confidence > first.confidence else first
```

**Source confidence scoring** (`score_verification_confidence()`):
- Official `.gov` sources: highest weight
- News sources: medium weight
- Blogs/other: low weight

### 4. Graceful Degradation (Stale-Data Fallback)

**Location:** `compliance_service.py` → `run_compliance_check_stream()`, `run_compliance_check_background()`

When Gemini fails or returns empty results, the system falls back to cached jurisdiction data:

```python
if not requirements and not used_repository:
    j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
    if j_reqs:
        requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
        used_repository = True  # skip upserts/alerts/verification
        yield {"type": "fallback", "message": "Using cached data (live research unavailable)"}
```

**Important:** Fallback data sets `used_repository = True` to prevent:
- Upserting stale data back to the repository (would corrupt `last_verified_at`)
- Creating alerts for cached data (false positives)
- Running verification on cached data (wasted API calls)

### 5. Real-Time Progress Streaming (Heartbeats)

**Location:** `compliance_service.py` → `_heartbeat_while()`

Long-running Gemini calls (45-90s) could cause SSE connection timeouts. The heartbeat pattern keeps connections alive:

```python
async def _heartbeat_while(task, *, queue=None, interval=8):
    """Yield progress events and heartbeats while a task runs."""
    while not task.done():
        # Drain any queued events (e.g., retry notifications)
        while queue and not queue.empty():
            yield queue.get_nowait()

        done, _ = await asyncio.wait({task}, timeout=interval)
        if done:
            break
        yield {"type": "heartbeat"}  # converted to SSE comment ": heartbeat\n\n"
```

**Key details:**
- Heartbeat interval: 8s (under Nginx's 10s `send_timeout`)
- Retry events stream in real-time via queue (not buffered until completion)
- `X-Accel-Buffering: no` header disables Nginx proxy buffering for SSE

### 6. Change Detection & False Positive Prevention

**Location:** `compliance_service.py` → `_sync_requirements_to_location()`, `_normalize_value_text()`, `_is_material_numeric_change()`

The system detects material changes while filtering out false positives from Gemini rephrasing:

**Value normalization:**
```python
def _normalize_value_text(value, category):
    # Normalize units: "per hour" → "/hr", "yearly" → "/yr"
    # Normalize synonyms: "compensated" → "paid"
    # Strip parenthetical annotations: "(unpaid)" → ""
    # Normalize hyphens: "30-min" → "30 min"
```

**Material change logic:**
```python
if _is_material_numeric_change(old_num, new_num, category):
    material_change = True
elif old_num is None or new_num is None:
    # Fall back to text comparison only when numerics unavailable
    material_change = _is_material_text_change(old_value, new_value, category)
# When numerics match, DON'T flag as material (trust numeric comparison)
```

**Hallucination guards:**
- Minimum wage decreases are rejected (virtually never happen in reality)
- Key drift detection prevents duplicate requirements with different titles

---

## Jurisdiction Repository

The jurisdiction repository (`jurisdictions`, `jurisdiction_requirements`, `jurisdiction_legislation` tables) acts as a shared cache:

1. **Freshness check** — If jurisdiction was verified within `auto_check_interval_days`, skip Gemini entirely
2. **Shared across locations** — Multiple business locations in the same jurisdiction share cached data
3. **Admin sync** — Admin jurisdiction checks update all linked business locations automatically

---

## SSE Event Types

| Event | Purpose |
|-------|---------|
| `started` | Check initiated |
| `repository` | Loading from fresh cache (skipping Gemini) |
| `researching` | Calling Gemini for research |
| `retrying` | Retry attempt after failure |
| `fallback` | Using stale cached data (Gemini unavailable) |
| `processing` | Processing requirements |
| `result` | Individual requirement status (new/existing) |
| `verifying` | Starting verification phase |
| `verifying_item` | Per-verification progress (current/total) |
| `verified` | Verification complete |
| `scanning` | Legislation scan started |
| `legislation` | Legislation items found |
| `completed` | Check finished with counts |
| `error` | Error occurred |
| `: heartbeat` | SSE comment to keep connection alive |

---

## Timing Budget

| Operation | Timeout | Retries | Max Duration |
|-----------|---------|---------|--------------|
| Research | 45s | 1 | 90s |
| Verification (per change) | 45s | 1 + adaptive | 135s |
| Legislation scan | 45s | 0 | 45s |
| Heartbeat interval | 8s | — | — |
| Nginx SSE timeout | 120s | — | — |

---

## Configuration

| Setting | Location | Default |
|---------|----------|---------|
| `GEMINI_CALL_TIMEOUT` | `gemini_compliance.py` | 45s |
| `HEARTBEAT_INTERVAL` | `compliance_service.py` | 8s |
| `MAX_VERIFICATIONS_PER_CHECK` | `compliance_service.py` | 3 |
| `MATERIAL_CHANGE_THRESHOLDS` | `compliance_service.py` | wage: $0.25, default: $0.10 |
