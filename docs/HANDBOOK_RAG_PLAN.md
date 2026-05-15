# Handbook RAG (forward-only)

## Context

Today policy mapping reads ALL active handbook sections, truncated to 300 chars, and dumps them into the Gemini prompt (`ir_incidents.py:_get_handbook_policy_entries`). For small handbooks this is fine; for handbooks with 40+ sections it's noisy + cuts policy text mid-sentence, hurting match accuracy. We have pgvector + `EmbeddingService` (Gemini `text-embedding-004`, 768-dim) already running for `er_evidence_chunks` and `compliance_embeddings`. Plug handbooks into the same pipeline so policy mapping retrieves the top-K relevant sections semantically. **Forward-only**: existing handbooks stay on the truncation path; only handbooks published or updated after this lands get chunked + embedded.

**Outcome.** When IR Copilot runs `policy_mapping`, the orchestrator embeds the incident description, retrieves the top 6 most-relevant chunks from the active handbook version (if it has been indexed), and passes only those into the policy-mapping prompt. Older un-indexed handbooks fall back to current truncation. Future features (compliance Q&A on handbook, handbook freshness checks, etc.) reuse the same chunks.

## Approach

One new table (`handbook_chunks`) keyed by `(handbook_section_id, chunk_index)` with `embedding vector(768)`. One new Celery task (`handbook_indexer`) that chunks + embeds every section of a handbook version. Hook fires on `publish_handbook` (`server/app/core/services/handbook_service.py:3211`) — only newly-published versions trigger. New chunks get a `version` column tagged with the indexer version (`v1`) so re-indexing later (different chunk size, different embedding model) is a clean migration.

Query path: `_get_handbook_policy_entries` checks if the active version has chunks. If yes, embed incident description + run cosine-similarity query against `handbook_chunks`, return top 6 with full chunk text. If no chunks (old handbook), fall back to existing truncation path. No backfill — explicitly forward-only.

## Files to modify / create

### Backend
- `server/alembic/versions/<new>_add_handbook_chunks.py` — schema migration
- `server/app/matcha/services/handbook_indexer.py` — new (chunker + embed batch + insert)
- `server/app/workers/tasks/handbook_indexer.py` — new (Celery task wrapping the service)
- `server/app/workers/celery_app.py` — register task
- `server/app/core/services/handbook_service.py:3211` — `publish_handbook` enqueues indexer after the publish UPDATE commits
- `server/app/matcha/routes/ir_incidents.py:_get_handbook_policy_entries` — branch on chunks-available, run cosine-similarity retrieval when available

### No frontend changes
The user-visible policy_mapping output is unchanged in structure. Quality improves silently.

## Schema migration (concrete SQL)

```sql
-- Forward-only handbook RAG. No backfill.
CREATE TABLE IF NOT EXISTS handbook_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handbook_section_id UUID NOT NULL REFERENCES handbook_sections(id) ON DELETE CASCADE,
    handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding vector(768) NOT NULL,
    indexer_version VARCHAR(20) NOT NULL DEFAULT 'v1',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_handbook_chunks_version ON handbook_chunks(handbook_version_id);
CREATE INDEX idx_handbook_chunks_section ON handbook_chunks(handbook_section_id);
CREATE INDEX idx_handbook_chunks_company ON handbook_chunks(company_id);
-- IVFFlat for cosine similarity. Sized for ~10k handbooks × 50 sections × 4 chunks ≈ 2M rows.
CREATE INDEX idx_handbook_chunks_embedding
    ON handbook_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

## Indexer service

`server/app/matcha/services/handbook_indexer.py`:

```python
async def index_handbook_version(handbook_version_id: UUID) -> dict:
    """Chunk + embed every section of the version. Idempotent: deletes
    prior chunks for this version before re-indexing."""
    # 1. Load version + all sections (id, content)
    # 2. For each section: chunk content (~500-800 tokens, 50-token overlap)
    # 3. Batch-embed via EmbeddingService.embed_text_batch (text-embedding-004)
    # 4. INSERT INTO handbook_chunks (delete existing for version first)
    # 5. Return {"sections": N, "chunks": M, "model": "text-embedding-004"}
```

Chunking strategy: split each section's content on paragraph boundaries first, then split paragraphs >800 tokens at sentence boundaries with 50-token overlap. Reuse `EmbeddingService.embed_text` (already in `server/app/core/services/embedding_service.py`).

## Hook into publish

`server/app/core/services/handbook_service.py:publish_handbook` (line 3211) — after the UPDATE that flips `is_published`, enqueue the indexer task:

```python
from app.workers.tasks.handbook_indexer import run_handbook_indexer
run_handbook_indexer.delay(str(version_id))
```

Fire-and-forget — UI doesn't wait. If the indexer fails, the handbook still publishes; policy_mapping just falls back to the old path.

## Query path

`server/app/matcha/routes/ir_incidents.py:_get_handbook_policy_entries`:

```python
async def _get_handbook_policy_entries(conn, company_id, incident_description: str = None):
    # Find active handbook version (existing logic)
    version_id = ...

    # Check if this version has been indexed
    chunk_count = await conn.fetchval(
        "SELECT COUNT(*) FROM handbook_chunks WHERE handbook_version_id = $1",
        version_id,
    )

    if chunk_count and incident_description:
        # RAG path
        from app.core.services.embedding_service import get_embedding_service
        emb = await get_embedding_service().embed_text(incident_description)
        rows = await conn.fetch(
            """
            SELECT hc.id, hs.title, hc.content,
                   1 - (hc.embedding <=> $1::vector) AS similarity
            FROM handbook_chunks hc
            JOIN handbook_sections hs ON hs.id = hc.handbook_section_id
            WHERE hc.handbook_version_id = $2
            ORDER BY hc.embedding <=> $1::vector
            LIMIT 6
            """,
            emb, version_id,
        )
        return [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "description": r["content"][:300],
                "content": r["content"],
                "similarity": r["similarity"],
            }
            for r in rows
        ]

    # Fallback: existing truncation path (unchanged)
    ...
```

`_auto_map_policy_violations` already has incident description-equivalent context. Update the call to thread `incident_description` into `_get_handbook_policy_entries`.

## Forward-only policy

No backfill migration. Existing handbooks stay un-chunked → policy_mapping uses truncation. Only published-after-this-lands handbooks get chunked. If admin wants to backfill an old handbook, they can re-publish (UPDATE forces a new version) or we add an admin "Index handbook" button later.

## Reuse references

- **Embedding service** — `server/app/core/services/embedding_service.py` (`text-embedding-004`, 768-dim, already exists)
- **RAG query pattern** — `server/app/core/services/rag_service.py` and `payer_policy_rag.py` for the cosine-similarity query shape
- **Existing chunk table pattern** — `er_evidence_chunks` (`server/app/database.py:1850`) and `compliance_embeddings` (`server/app/database.py:2933`) for column conventions
- **pgvector** — `CREATE EXTENSION vector` already runs in `init_db`

## Verification plan

### Migration
- `alembic upgrade head`. Verify `\d handbook_chunks` shows the columns + indexes.

### Tests
- `server/tests/test_handbook_indexer.py`:
  - Chunk-and-embed a small fixture handbook (3 sections, mix of short + long).
  - Assert N chunks per section based on length.
  - Re-run indexer → asserts old chunks deleted, new ones inserted (idempotent).
- `server/tests/test_policy_mapping_rag.py`:
  - With chunks present, retrieval returns top-K by similarity.
  - With no chunks (old handbook), falls back to truncation path.

### Manual end-to-end (staging)
1. Create new handbook with 30+ sections via the existing UI.
2. Publish.
3. Watch Celery logs — `run_handbook_indexer` fires, processes ~N chunks.
4. Open an IR incident on the same company.
5. In Copilot, accept "Run Policy Mapping Analysis".
6. Inspect `ir_incident_analysis.analysis_data` for the policy mapping result — chunks referenced should be from the most-relevant sections (not the full handbook).
7. Compare quality: same incident on a non-RAG'd handbook (manually un-index by deleting chunks) should match more loosely.

### Performance
- Embedding 50 sections × ~3 chunks each = 150 calls. Gemini `text-embedding-004` batches 100 at a time. ~1.5s total.
- Query: cosine search over 2M-row index returns in <50ms with IVFFlat.
- Net effect: policy_mapping prompt drops from ~24k chars → ~4k chars. Faster Gemini round-trip, better focus.

## Out of scope

- Backfilling existing handbooks (user explicit).
- Frontend changes (policy_mapping output shape unchanged).
- Other features that could use the chunks (compliance Q&A, freshness drift) — they'll consume `handbook_chunks` later as they're built.
- Re-indexing on individual section edits — only fires on publish. Section-level updates without a republish stay un-indexed (acceptable: re-publish is the canonical "go live" action).
