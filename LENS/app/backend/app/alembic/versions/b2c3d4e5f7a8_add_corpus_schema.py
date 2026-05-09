"""Add corpus schema (documents, chunks, embeddings) + HNSW + FTS GIN

Revision ID: b2c3d4e5f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09

Implements TICKET-010. The pgvector extension was already enabled by the
parent migration; this migration creates the LENS ingestion pipeline tables:

  - documents: per-source-file metadata
  - chunks:    text segments derived from documents
  - embeddings: 1024-dim vectors (Voyage voyage-3-large) keyed by chunk

Indexes:
  - HNSW on embeddings.vector with vector_cosine_ops (ANN)
  - GIN on chunks.text (FTS / hybrid retrieval)
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f7a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


EMBEDDING_DIM = 1024


def upgrade() -> None:
    # AGE's CREATE EXTENSION in the parent migration set search_path to
    # ag_catalog. Force this migration's tables into the public schema
    # explicitly so they don't leak into the AGE namespace.
    op.execute("SET search_path TO public")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("raw_blob_key", sa.Text(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "parsed_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema="public",
    )

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.UniqueConstraint("document_id", "ord", name="uq_chunks_document_ord"),
        schema="public",
    )

    op.create_table(
        "embeddings",
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.chunks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("vector", Vector(EMBEDDING_DIM), nullable=False),
        schema="public",
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_embeddings_vector_hnsw
            ON public.embeddings
            USING hnsw (vector vector_cosine_ops)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_text_fts
            ON public.chunks
            USING gin (to_tsvector('english', text))
        """
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.execute("DROP INDEX IF EXISTS public.ix_chunks_text_fts")
    op.execute("DROP INDEX IF EXISTS public.ix_embeddings_vector_hnsw")
    op.drop_table("embeddings", schema="public")
    op.drop_table("chunks", schema="public")
    op.drop_table("documents", schema="public")
