# Tier 1 Structured Data Safety Guardrails Plan

## Overview

The Tier 1 structured data system fetches compliance data from authoritative sources (DOL, EPI, NCSL) and uses it directly in compliance checks. Currently, this data bypasses the verification workflow that Tier 3 (Gemini) data goes through, creating risk of corrupted or malformed data being used automatically.

---

## Phase 1: Numeric Bounds & Input Validation (P1)

**Goal**: Prevent obviously invalid data from being accepted.

### 1.1 Add wage bounds validation

**File**: `server/app/core/services/structured_data/parsers/base.py`

```python
# Add to BaseParser class
WAGE_BOUNDS = {
    "minimum_wage": (2.00, 50.00),      # Federal min is $7.25, highest state ~$17
    "tipped_wage": (2.00, 20.00),       # Tipped minimum can be $2.13 federally
    "youth_wage": (2.00, 30.00),
}

def validate_wage_value(self, value: float, category: str) -> bool:
    """Check wage is within reasonable bounds."""
    bounds = self.WAGE_BOUNDS.get(category, (0.01, 100.00))
    return bounds[0] <= value <= bounds[1]
```

**File**: `server/app/core/services/structured_data/service.py`

Add validation in `_cache_requirement()` before inserting:
```python
if not self._validate_bounds(parsed.numeric_value, parsed.category):
    logger.warning(f"[Tier 1] Rejected out-of-bounds value: {parsed.numeric_value} for {parsed.category}")
    return None
```

### 1.2 Add effective date validation

Reject data with:
- `effective_date` more than 2 years in the past
- `effective_date` more than 1 year in the future

### 1.3 Validate HTTP response content-type

**File**: `server/app/core/services/structured_data/parsers/csv_parser.py`

```python
response = await client.get(url, timeout=60)
content_type = response.headers.get("content-type", "")
if "text/csv" not in content_type and "text/plain" not in content_type:
    raise ValueError(f"Expected CSV, got {content_type}")
```

---

## Phase 2: Audit Logging (P2)

**Goal**: Create database trail of all Tier 1 data decisions.

### 2.1 Create audit log table

```sql
CREATE TABLE structured_data_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- What happened
    event_type VARCHAR(50) NOT NULL,  -- 'fetch', 'parse', 'use', 'reject', 'fallback'

    -- Context
    source_id UUID REFERENCES structured_data_sources(id),
    jurisdiction_id UUID REFERENCES jurisdictions(id),
    cache_id UUID REFERENCES structured_data_cache(id),

    -- Details
    details JSONB,  -- category, value, reason, etc.

    -- Traceability
    triggered_by VARCHAR(100)  -- 'background_check', 'stream_check', 'manual_fetch'
);

CREATE INDEX idx_sda_created ON structured_data_audit_log(created_at);
CREATE INDEX idx_sda_source ON structured_data_audit_log(source_id);
CREATE INDEX idx_sda_event ON structured_data_audit_log(event_type);
```

### 2.2 Add logging helper

**File**: `server/app/core/services/structured_data/audit.py`

```python
async def log_tier1_event(
    conn: asyncpg.Connection,
    event_type: str,
    source_id: UUID = None,
    jurisdiction_id: UUID = None,
    cache_id: UUID = None,
    details: dict = None,
    triggered_by: str = None,
):
    await conn.execute("""
        INSERT INTO structured_data_audit_log
        (event_type, source_id, jurisdiction_id, cache_id, details, triggered_by)
        VALUES ($1, $2, $3, $4, $5, $6)
    """, event_type, source_id, jurisdiction_id, cache_id,
        json.dumps(details) if details else None, triggered_by)
```

### 2.3 Instrument key decision points

Log these events:
- `fetch_start` - Source fetch initiated
- `fetch_success` - Source fetched, N records parsed
- `fetch_error` - Source fetch failed (with error details)
- `parse_reject` - Individual record rejected (with reason)
- `tier1_use` - Tier 1 data used in compliance check
- `tier1_skip` - Tier 1 skipped, falling back to Tier 2/3
- `bounds_reject` - Value rejected for out-of-bounds

---

## Phase 3: Tier 1 Verification Parity (P3)

**Goal**: Subject Tier 1 data to same confidence/verification as Tier 3.

### 3.1 Add verification flag to cache table

```sql
ALTER TABLE structured_data_cache
ADD COLUMN verified_at TIMESTAMPTZ,
ADD COLUMN verification_status VARCHAR(20) DEFAULT 'pending',  -- pending, verified, rejected
ADD COLUMN confidence_score FLOAT;
```

### 3.2 Hold-for-review on first use

**File**: `server/app/core/services/structured_data/service.py`

```python
async def get_tier1_data(..., require_verified: bool = True):
    # For production: only return verified data
    if require_verified:
        query += " AND c.verification_status = 'verified'"

    # For new data: mark pending and trigger review
    for unverified in await self._get_unverified_cache(conn, jurisdiction_id):
        await self._queue_for_verification(conn, unverified)
```

### 3.3 Verification batch job

Add to existing verification workflow in `compliance_service.py`:

```python
async def verify_tier1_batch(conn, limit=50):
    """Verify pending Tier 1 cache entries using Gemini cross-check."""
    pending = await conn.fetch("""
        SELECT * FROM structured_data_cache
        WHERE verification_status = 'pending'
        ORDER BY fetched_at DESC LIMIT $1
    """, limit)

    for entry in pending:
        # Cross-check with quick Gemini lookup
        confidence = await gemini_service.verify_wage_value(
            entry['jurisdiction_key'],
            entry['category'],
            entry['numeric_value']
        )

        await conn.execute("""
            UPDATE structured_data_cache
            SET verification_status = $1, confidence_score = $2, verified_at = NOW()
            WHERE id = $3
        """, 'verified' if confidence >= 0.6 else 'rejected', confidence, entry['id'])
```

### 3.4 Auto-verify trusted sources

Sources with historical accuracy >95% can be auto-verified:

```sql
ALTER TABLE structured_data_sources
ADD COLUMN auto_verify BOOLEAN DEFAULT false,
ADD COLUMN historical_accuracy FLOAT;
```

---

## Phase 4: Retry & Circuit Breaker (P4)

**Goal**: Handle transient failures gracefully.

### 4.1 Add retry with exponential backoff

**File**: `server/app/core/services/structured_data/service.py`

```python
async def _fetch_with_retry(self, url: str, max_retries: int = 3) -> httpx.Response:
    for attempt in range(max_retries):
        try:
            response = await client.get(url, timeout=60)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                await asyncio.sleep(retry_after)
                continue
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
```

### 4.2 Add circuit breaker

**File**: `server/app/core/services/structured_data/circuit_breaker.py`

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=300):
        self.failures = {}  # source_id -> failure_count
        self.open_until = {}  # source_id -> timestamp

    def is_open(self, source_id: UUID) -> bool:
        if source_id in self.open_until:
            if datetime.now() > self.open_until[source_id]:
                del self.open_until[source_id]
                self.failures[source_id] = 0
                return False
            return True
        return False

    def record_failure(self, source_id: UUID):
        self.failures[source_id] = self.failures.get(source_id, 0) + 1
        if self.failures[source_id] >= self.failure_threshold:
            self.open_until[source_id] = datetime.now() + timedelta(seconds=self.recovery_timeout)
```

### 4.3 Track source health

```sql
ALTER TABLE structured_data_sources
ADD COLUMN consecutive_failures INT DEFAULT 0,
ADD COLUMN circuit_open_until TIMESTAMPTZ;
```

---

## Phase 5: First-Time Data Review (P5)

**Goal**: Require human review for new sources/jurisdictions.

### 5.1 Flag new sources

```sql
ALTER TABLE structured_data_sources
ADD COLUMN requires_initial_review BOOLEAN DEFAULT true,
ADD COLUMN initial_review_completed_at TIMESTAMPTZ,
ADD COLUMN initial_review_by VARCHAR(100);
```

### 5.2 Admin review queue

Create API endpoint for admin to review pending sources:

```python
@router.get("/admin/tier1/pending-review")
async def get_pending_review():
    return await conn.fetch("""
        SELECT s.*, COUNT(c.id) as cached_records
        FROM structured_data_sources s
        LEFT JOIN structured_data_cache c ON c.source_id = s.id
        WHERE s.requires_initial_review = true
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """)

@router.post("/admin/tier1/approve/{source_id}")
async def approve_source(source_id: UUID, reviewer: str):
    await conn.execute("""
        UPDATE structured_data_sources
        SET requires_initial_review = false,
            initial_review_completed_at = NOW(),
            initial_review_by = $2
        WHERE id = $1
    """, source_id, reviewer)
```

### 5.3 Block unapproved sources from production use

```python
async def get_tier1_data(...):
    # Only use data from approved sources in production
    query += " AND s.requires_initial_review = false"
```

---

## Implementation Order

| Phase | Priority | Effort | Risk Reduction |
|-------|----------|--------|----------------|
| Phase 1: Bounds validation | P1 | Low | High - prevents obvious bad data |
| Phase 2: Audit logging | P2 | Medium | Medium - enables debugging/forensics |
| Phase 3: Verification parity | P3 | High | High - catches subtle errors |
| Phase 4: Retry/circuit breaker | P4 | Medium | Medium - improves reliability |
| Phase 5: First-time review | P5 | Medium | Medium - human oversight for new sources |

---

## Verification Checklist

After implementation:

1. **Bounds test**: Insert CSV with wage=$999.99, verify rejected
2. **Audit test**: Run compliance check, verify audit log populated
3. **Verification test**: Add unverified cache entry, verify not returned until approved
4. **Circuit breaker test**: Fail source 5x, verify circuit opens
5. **First-time test**: Add new source, verify requires_initial_review blocks usage

---

## Files to Modify

- `server/app/core/services/structured_data/service.py` - Main service
- `server/app/core/services/structured_data/parsers/base.py` - Validation
- `server/app/core/services/structured_data/audit.py` - New file
- `server/app/core/services/structured_data/circuit_breaker.py` - New file
- `server/app/core/services/compliance_service.py` - Integration
- `server/migrations/` - New migration for schema changes
