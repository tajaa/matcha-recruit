"""RAG Service for ER Copilot.

Retrieval-Augmented Generation using vector similarity search
over case evidence stored in PostgreSQL with pgvector.
"""

from typing import Optional
import asyncpg

from .embedding_service import EmbeddingService


class RAGService:
    """Semantic search over case evidence using vector embeddings."""

    def __init__(self, embedding_service: EmbeddingService):
        """
        Initialize RAG service.

        Args:
            embedding_service: EmbeddingService instance for generating query embeddings.
        """
        self.embedding_service = embedding_service

    async def search_evidence(
        self,
        case_id: str,
        query: str,
        conn: asyncpg.Connection,
        top_k: int = 5,
        min_similarity: float = 0.0,
        document_types: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Search case evidence using vector similarity.

        Args:
            case_id: The case ID to search within.
            query: The search query.
            conn: Database connection.
            top_k: Number of results to return.
            min_similarity: Minimum similarity threshold (0-1).
            document_types: Optional filter by document types.

        Returns:
            List of evidence chunks with similarity scores and source citations.
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        query_embedding = await self.embedding_service.embed_text(
            query,
            task_type=EmbeddingService.TASK_RETRIEVAL_QUERY,
        )

        # Build query with optional document type filter
        base_query = """
            SELECT
                ec.id,
                ec.content,
                ec.speaker,
                ec.page_number,
                ec.line_start,
                ec.line_end,
                ec.metadata,
                ec.chunk_index,
                ed.id as document_id,
                ed.filename,
                ed.document_type,
                1 - (ec.embedding <=> $1::vector) as similarity
            FROM er_evidence_chunks ec
            JOIN er_case_documents ed ON ec.document_id = ed.id
            WHERE ec.case_id = $2
        """

        params = [query_embedding, case_id]

        if document_types:
            base_query += f" AND ed.document_type = ANY($3)"
            params.append(document_types)

        if min_similarity > 0:
            base_query += f" AND 1 - (ec.embedding <=> $1::vector) >= ${len(params) + 1}"
            params.append(min_similarity)

        base_query += """
            ORDER BY ec.embedding <=> $1::vector
            LIMIT $""" + str(len(params) + 1)
        params.append(top_k)

        rows = await conn.fetch(base_query, *params)

        results = []
        for row in rows:
            line_range = None
            if row["line_start"] is not None:
                line_range = f"{row['line_start']}"
                if row["line_end"] is not None and row["line_end"] != row["line_start"]:
                    line_range += f"-{row['line_end']}"

            results.append({
                "chunk_id": str(row["id"]),
                "content": row["content"],
                "speaker": row["speaker"],
                "source_file": row["filename"],
                "document_id": str(row["document_id"]),
                "document_type": row["document_type"],
                "page_number": row["page_number"],
                "line_range": line_range,
                "chunk_index": row["chunk_index"],
                "similarity": float(row["similarity"]),
                "metadata": row["metadata"],
            })

        return results

    async def get_context_for_analysis(
        self,
        case_id: str,
        query: str,
        conn: asyncpg.Connection,
        max_tokens: int = 4000,
        top_k: int = 10,
    ) -> tuple[str, list[dict]]:
        """
        Get relevant context for LLM analysis.

        Args:
            case_id: The case ID.
            query: The query/question to find context for.
            conn: Database connection.
            max_tokens: Approximate max tokens for context (rough estimate: 4 chars = 1 token).
            top_k: Max number of chunks to consider.

        Returns:
            Tuple of (context_text, sources).
        """
        results = await self.search_evidence(
            case_id=case_id,
            query=query,
            conn=conn,
            top_k=top_k,
        )

        context_parts = []
        sources = []
        total_chars = 0
        max_chars = max_tokens * 4

        for result in results:
            content = result["content"]

            if total_chars + len(content) > max_chars:
                break

            # Format with source info
            source_info = f"[Source: {result['source_file']}"
            if result["page_number"]:
                source_info += f", Page {result['page_number']}"
            if result["line_range"]:
                source_info += f", Lines {result['line_range']}"
            source_info += "]"

            context_parts.append(f"{source_info}\n{content}")
            sources.append({
                "chunk_id": result["chunk_id"],
                "document_id": result["document_id"],
                "filename": result["source_file"],
                "page_number": result["page_number"],
                "line_range": result["line_range"],
                "similarity": result["similarity"],
            })

            total_chars += len(content)

        context_text = "\n\n---\n\n".join(context_parts)
        return context_text, sources

    async def find_similar_statements(
        self,
        case_id: str,
        statement: str,
        conn: asyncpg.Connection,
        top_k: int = 5,
        exclude_chunk_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Find statements similar to a given statement.

        Useful for finding corroborating or contradicting evidence.

        Args:
            case_id: The case ID.
            statement: The statement to find similar ones for.
            conn: Database connection.
            top_k: Number of results.
            exclude_chunk_id: Optional chunk ID to exclude (e.g., the source statement).

        Returns:
            List of similar statements with similarity scores.
        """
        results = await self.search_evidence(
            case_id=case_id,
            query=statement,
            conn=conn,
            top_k=top_k + 1,  # Get extra in case we need to exclude one
        )

        if exclude_chunk_id:
            results = [r for r in results if r["chunk_id"] != exclude_chunk_id]

        return results[:top_k]

    async def get_total_chunks(
        self,
        case_id: str,
        conn: asyncpg.Connection,
    ) -> int:
        """Get total number of evidence chunks for a case."""
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM er_evidence_chunks WHERE case_id = $1",
            case_id,
        )
        return count or 0

    async def get_document_chunks(
        self,
        document_id: str,
        conn: asyncpg.Connection,
    ) -> list[dict]:
        """Get all chunks for a specific document, ordered by chunk index."""
        rows = await conn.fetch(
            """
            SELECT id, chunk_index, content, speaker, page_number, line_start, line_end, metadata
            FROM er_evidence_chunks
            WHERE document_id = $1
            ORDER BY chunk_index
            """,
            document_id,
        )

        return [
            {
                "chunk_id": str(row["id"]),
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "speaker": row["speaker"],
                "page_number": row["page_number"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "metadata": row["metadata"],
            }
            for row in rows
        ]
