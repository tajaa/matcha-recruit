"""Add HNSW vector indexes for RAG semantic search.

compliance_embeddings and payer_policy_embeddings had NO vector index — every
`ORDER BY embedding <=> $1` in the matcha-work compliance/payer chat computed
cosine distance against every row (sequential scan), so retrieval latency grew
linearly with the corpus. HNSW (vs ivfflat) needs no training step, handles
incremental inserts well, and is the right default for these append-heavy
tables. Requires pgvector >= 0.5.0.

Built CONCURRENTLY so the apply doesn't lock reads/writes — which means it
runs in an autocommit block and this migration is NOT transactional. If a
CONCURRENTLY build fails partway it can leave an INVALID index behind: check
`\d+ compliance_embeddings` and drop/rebuild if so.

Apply via ./scripts/migrate-dev.sh then ./scripts/migrate-prod.sh — never
directly against prod (see root CLAUDE.md production-safety list).

Revision ID: hnswvec01
Revises: analysispilot01
Create Date: 2026-07-09
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "hnswvec01"
down_revision = "analysispilot01"
branch_labels = None
depends_on = None

_INDEXES = (
    (
        "ix_compliance_embeddings_embedding_hnsw",
        "compliance_embeddings",
    ),
    (
        "ix_payer_policy_embeddings_embedding_hnsw",
        "payer_policy_embeddings",
    ),
)


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        for index_name, table in _INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} "
                f"ON {table} USING hnsw (embedding vector_cosine_ops)"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for index_name, _table in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
