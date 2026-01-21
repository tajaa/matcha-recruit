"""Embedding Service for ER Copilot.

Generates vector embeddings using Gemini Embeddings API (text-embedding-004).
Embeddings are 768-dimensional vectors used for semantic similarity search.
"""

from typing import Optional

from google import genai


class EmbeddingService:
    """Generate embeddings using Gemini Embeddings API."""

    # Gemini text-embedding-004 produces 768-dimensional vectors
    EMBEDDING_DIMENSION = 768
    MODEL = "text-embedding-004"

    # Task types for embeddings
    TASK_RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
    TASK_RETRIEVAL_QUERY = "RETRIEVAL_QUERY"
    TASK_SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
    TASK_CLASSIFICATION = "CLASSIFICATION"
    TASK_CLUSTERING = "CLUSTERING"

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
    ):
        """
        Initialize the embedding service.

        Args:
            api_key: Gemini API key (use if not using Vertex AI).
            vertex_project: GCP project ID for Vertex AI.
            vertex_location: Vertex AI location (default: us-central1).
        """
        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Either api_key or vertex_project must be provided")

    async def embed_text(
        self,
        text: str,
        task_type: str = TASK_RETRIEVAL_DOCUMENT,
    ) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: The text to embed.
            task_type: The type of task (affects embedding optimization).
                       Use TASK_RETRIEVAL_DOCUMENT for documents being indexed.
                       Use TASK_RETRIEVAL_QUERY for search queries.

        Returns:
            768-dimensional embedding vector.
        """
        response = await self.client.aio.models.embed_content(
            model=self.MODEL,
            contents=text,
            config={"task_type": task_type},
        )
        return list(response.embeddings[0].values)

    async def embed_batch(
        self,
        texts: list[str],
        task_type: str = TASK_RETRIEVAL_DOCUMENT,
        batch_size: int = 100,
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.
            task_type: The type of task.
            batch_size: Number of texts to embed per API call.

        Returns:
            List of 768-dimensional embedding vectors.
        """
        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = await self.client.aio.models.embed_content(
                model=self.MODEL,
                contents=batch,
                config={"task_type": task_type},
            )
            batch_embeddings = [list(e.values) for e in response.embeddings]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_text_sync(
        self,
        text: str,
        task_type: str = TASK_RETRIEVAL_DOCUMENT,
    ) -> list[float]:
        """
        Synchronous version of embed_text.

        Args:
            text: The text to embed.
            task_type: The type of task.

        Returns:
            768-dimensional embedding vector.
        """
        response = self.client.models.embed_content(
            model=self.MODEL,
            contents=text,
            config={"task_type": task_type},
        )
        return list(response.embeddings[0].values)

    def embed_batch_sync(
        self,
        texts: list[str],
        task_type: str = TASK_RETRIEVAL_DOCUMENT,
        batch_size: int = 100,
    ) -> list[list[float]]:
        """
        Synchronous version of embed_batch.

        Args:
            texts: List of texts to embed.
            task_type: The type of task.
            batch_size: Number of texts to embed per API call.

        Returns:
            List of 768-dimensional embedding vectors.
        """
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.models.embed_content(
                model=self.MODEL,
                contents=batch,
                config={"task_type": task_type},
            )
            batch_embeddings = [list(e.values) for e in response.embeddings]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[str]:
        """
        Split text into overlapping chunks suitable for embedding.

        Args:
            text: The text to chunk.
            chunk_size: Target size of each chunk in characters.
            overlap: Number of overlapping characters between chunks.

        Returns:
            List of text chunks.
        """
        chunks = []
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())

                # Start new chunk with overlap
                if overlap > 0 and len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks
