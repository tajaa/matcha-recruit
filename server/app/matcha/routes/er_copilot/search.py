"""Evidence search (RAG over case documents)."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ....config import get_settings
from ...models.er_case import (
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    EvidenceSearchResult,
)

from ._shared import (
    logger,
    _verify_case_company,
    _normalize_search_metadata,
    _normalize_document_type,
)

router = APIRouter()


@router.post("/{case_id}/search", response_model=EvidenceSearchResponse)
async def search_evidence(
    case_id: UUID,
    search: EvidenceSearchRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search case evidence using semantic similarity."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # Verify case belongs to company before searching
    async with get_connection() as verify_conn:
        await _verify_case_company(verify_conn, case_id, company_id, current_user.role == "admin")

    async with get_connection() as conn:
        try:
            total_chunks = await conn.fetchval(
                "SELECT COUNT(*) FROM er_evidence_chunks WHERE case_id = $1",
                case_id,
            )
        except Exception as chunk_count_error:
            logger.warning(
                "Failed to count evidence chunks for case %s: %s",
                case_id,
                chunk_count_error,
            )
            total_chunks = 0
        results: list[dict] = []
        semantic_error: Exception | None = None

        try:
            settings = get_settings()
            from ....core.services.embedding_service import EmbeddingService
            from ....core.services.rag_service import RAGService

            embedding_service = EmbeddingService(api_key=settings.gemini_api_key)
            rag_service = RAGService(embedding_service)
            results = await rag_service.search_evidence(
                case_id=str(case_id),
                query=search.query,
                conn=conn,
                top_k=search.top_k,
            )
        except Exception as exc:
            semantic_error = exc

        # Fallback to keyword matching when semantic search is unavailable or returns no matches.
        if semantic_error is not None or not results:
            if semantic_error is not None:
                logger.warning(
                    "Semantic evidence search failed for case %s; using keyword fallback: %s",
                    case_id,
                    semantic_error,
                )
            else:
                logger.info(
                    "Semantic evidence search returned no matches for case %s; using keyword fallback",
                    case_id,
                )
            like_query = f"%{search.query.strip()}%"
            chunk_rows = []
            try:
                chunk_rows = await conn.fetch(
                    """
                    SELECT
                        ec.id,
                        ec.content,
                        ec.speaker,
                        ec.page_number,
                        ec.line_start,
                        ec.line_end,
                        ec.metadata,
                        ed.filename,
                        ed.document_type
                    FROM er_evidence_chunks ec
                    JOIN er_case_documents ed ON ec.document_id = ed.id
                    WHERE ec.case_id = $1
                      AND ec.content ILIKE $2
                    ORDER BY ec.created_at DESC
                    LIMIT $3
                    """,
                    case_id,
                    like_query,
                    search.top_k,
                )
            except Exception as chunk_query_error:
                logger.warning(
                    "Chunk-level keyword search failed for case %s: %s",
                    case_id,
                    chunk_query_error,
                )

            results = []
            for row in chunk_rows:
                line_range = None
                if row["line_start"] is not None:
                    line_range = f"{row['line_start']}"
                    if row["line_end"] is not None and row["line_end"] != row["line_start"]:
                        line_range += f"-{row['line_end']}"

                results.append(
                    {
                        "chunk_id": str(row["id"]),
                        "content": row["content"],
                        "speaker": row["speaker"],
                        "source_file": row["filename"],
                        "document_type": row["document_type"],
                        "page_number": row["page_number"],
                        "line_range": line_range,
                        "similarity": 0.35,
                        "metadata": row["metadata"] or {"search_mode": "keyword_chunk"},
                    }
                )

            if not results:
                doc_rows = []
                try:
                    doc_rows = await conn.fetch(
                        """
                        SELECT id, filename, document_type, scrubbed_text
                        FROM er_case_documents
                        WHERE case_id = $1
                          AND processing_status = 'completed'
                          AND scrubbed_text ILIKE $2
                        ORDER BY created_at DESC
                        LIMIT $3
                        """,
                        case_id,
                        like_query,
                        search.top_k,
                    )
                except Exception as doc_query_error:
                    logger.warning(
                        "Document-level keyword search failed for case %s: %s",
                        case_id,
                        doc_query_error,
                    )

                query_lower = search.query.strip().lower()
                for row in doc_rows:
                    text = (row["scrubbed_text"] or "").strip()
                    if not text:
                        continue
                    match_idx = text.lower().find(query_lower)
                    if match_idx < 0:
                        continue
                    start = max(0, match_idx - 140)
                    end = min(len(text), match_idx + len(query_lower) + 180)
                    snippet = text[start:end].strip()
                    if start > 0:
                        snippet = f"...{snippet}"
                    if end < len(text):
                        snippet = f"{snippet}..."

                    results.append(
                        {
                            "chunk_id": f"doc-{row['id']}",
                            "content": snippet,
                            "speaker": None,
                            "source_file": row["filename"],
                            "document_type": row["document_type"],
                            "page_number": None,
                            "line_range": None,
                            "similarity": 0.2,
                            "metadata": {"search_mode": "keyword_document_excerpt"},
                        }
                    )

        normalized_results: list[EvidenceSearchResult] = []
        for r in results:
            similarity_raw = r.get("similarity") if isinstance(r, dict) else None
            try:
                similarity = float(similarity_raw) if similarity_raw is not None else 0.0
            except Exception:
                similarity = 0.0

            normalized_results.append(
                EvidenceSearchResult(
                    chunk_id=str(r.get("chunk_id") or ""),
                    content=str(r.get("content") or ""),
                    speaker=r.get("speaker") if isinstance(r.get("speaker"), str) else None,
                    source_file=str(r.get("source_file") or "Unknown source"),
                    document_type=_normalize_document_type(r.get("document_type")),
                    page_number=r.get("page_number") if isinstance(r.get("page_number"), int) else None,
                    line_range=r.get("line_range") if isinstance(r.get("line_range"), str) else None,
                    similarity=similarity,
                    metadata=_normalize_search_metadata(r.get("metadata")),
                )
            )

        return EvidenceSearchResponse(
            results=normalized_results,
            query=search.query,
            total_chunks=total_chunks or 0,
        )


# ===========================================
# Reports
# ===========================================

