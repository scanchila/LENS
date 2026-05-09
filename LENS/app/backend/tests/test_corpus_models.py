"""Round-trip tests for the corpus tables (TICKET-010)."""

import uuid

import numpy as np
from sqlalchemy import text
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models import EMBEDDING_DIM, Chunk, Document, Embedding, User


def _ensure_user(session: Session) -> User:
    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    assert user is not None, "FIRST_SUPERUSER fixture user not found"
    return user


def test_round_trip_chunk_with_embedding() -> None:
    with Session(engine) as session:
        user = _ensure_user(session)

        doc = Document(
            owner_id=user.id,
            source_type="test",
            source_uri="memory://test",
            raw_blob_key=None,
            parsed_metadata={"origin": "test_round_trip"},
        )
        session.add(doc)
        session.flush()

        chunk = Chunk(
            document_id=doc.id,
            ord=0,
            text="hello world",
            char_start=0,
            char_end=11,
            tokens=2,
        )
        session.add(chunk)
        session.flush()

        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32).tolist()
        emb = Embedding(chunk_id=chunk.id, model="voyage-3-large", vector=vec)
        session.add(emb)
        session.commit()

        # ANN distance via pgvector returns a numeric distance.
        probe = "[" + ",".join("0" for _ in range(EMBEDDING_DIM)) + "]"
        distance_row = session.execute(
            text(
                f"SELECT vector <-> '{probe}'::vector AS d "
                "FROM embeddings WHERE chunk_id = :cid"
            ),
            {"cid": str(chunk.id)},
        ).first()
        assert distance_row is not None
        assert isinstance(distance_row[0], (int, float))

        # FTS index exercised via to_tsquery on the same row.
        fts_row = session.execute(
            text(
                "SELECT id FROM chunks "
                "WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :q) "
                "AND id = :cid"
            ),
            {"q": "hello", "cid": str(chunk.id)},
        ).first()
        assert fts_row is not None

        session.execute(
            text("DELETE FROM documents WHERE id = :id"), {"id": str(doc.id)}
        )
        session.commit()


def test_document_chunk_cascade() -> None:
    with Session(engine) as session:
        user = _ensure_user(session)

        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            owner_id=user.id,
            source_type="test",
            source_uri="memory://cascade",
            parsed_metadata={},
        )
        session.add(doc)
        session.flush()

        chunk = Chunk(
            document_id=doc.id, ord=0, text="x", char_start=0, char_end=1, tokens=1
        )
        session.add(chunk)
        session.flush()

        emb = Embedding(
            chunk_id=chunk.id,
            model="voyage-3-large",
            vector=[0.0] * EMBEDDING_DIM,
        )
        session.add(emb)
        session.commit()

        session.execute(
            text("DELETE FROM documents WHERE id = :id"),
            {"id": str(doc_id)},
        )
        session.commit()

        leftover = session.execute(
            text("SELECT count(*) FROM chunks WHERE document_id = :id"),
            {"id": str(doc_id)},
        ).scalar()
        assert leftover == 0
