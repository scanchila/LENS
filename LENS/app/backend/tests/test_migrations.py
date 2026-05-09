"""Migration sanity tests for TICKET-010.

Verify that ``alembic upgrade head`` (run by tests-start.sh prestart)
landed the pgvector extension and the hybrid retrieval indexes (HNSW
+ FTS GIN) on the corpus tables.
"""

from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine


def test_pgvector_present() -> None:
    with Session(engine) as session:
        row = session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).first()
    assert row is not None, "vector extension is not installed"


def test_age_present() -> None:
    with Session(engine) as session:
        row = session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'age'")
        ).first()
    assert row is not None, "age extension is not installed"


def test_hybrid_indexes_created() -> None:
    with Session(engine) as session:
        hnsw = session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'embeddings' "
                "AND indexname = 'ix_embeddings_vector_hnsw'"
            )
        ).first()
        fts = session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'chunks' "
                "AND indexname = 'ix_chunks_text_fts'"
            )
        ).first()
    assert hnsw is not None, "HNSW index missing on embeddings.vector"
    assert fts is not None, "GIN tsvector index missing on chunks.text"
