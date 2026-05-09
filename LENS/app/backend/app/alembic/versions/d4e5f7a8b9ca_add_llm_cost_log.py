"""Add llm_cost_log table for tracking LLM provider spend

Revision ID: d4e5f7a8b9ca
Revises: c3d4e5f7a8b9
Create Date: 2026-05-09

Implements TICKET-020 cost tracking. Each ingestion logs Voyage embedding
spend per document so the orchestrator can later enforce budget caps and
report cost in the upload response.

Schema:
  - id: primary key
  - owner_id: FK to user (nullable for system-level work)
  - document_id: FK to documents (nullable; non-ingestion calls won't have one)
  - model: provider model identifier (e.g. "voyage-3-large")
  - input_tokens / output_tokens
  - cost_usd: numeric for accurate accounting
  - created_at: timestamptz
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e5f7a8b9ca"
down_revision = "c3d4e5f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AGE migration leaves search_path on ag_catalog; force public.
    op.execute("SET search_path TO public")

    op.create_table(
        "llm_cost_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.documents.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.drop_table("llm_cost_log", schema="public")
