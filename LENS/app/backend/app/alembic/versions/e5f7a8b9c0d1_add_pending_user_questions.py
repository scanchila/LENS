"""Add pending_user_questions table for the ask_user tool

Revision ID: e5f7a8b9c0d1
Revises: d4e5f7a8b9c0
Create Date: 2026-05-09

Implements TICKET-042. The web-mediated ask_user tool persists each
question into this table, then polls for a non-null ``answer``. The
SSE endpoint added by TICKET-080 will LISTEN on the
``pending_user_questions`` channel; the tool itself uses ``pg_notify``
to wake that listener.

Schema:
  pending_user_questions(
    id              uuid pk,
    session_id      uuid,
    question        text,
    asked_by_agent  text,
    asked_at        timestamptz default now(),
    answer          text null,
    answered_at     timestamptz null
  )
  index ix_pending_user_questions_session_asked on
        (session_id, asked_at)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5f7a8b9c0d1"
down_revision = "d4e5f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path TO public")

    op.create_table(
        "pending_user_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("asked_by_agent", sa.Text(), nullable=False),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="public",
    )

    op.create_index(
        "ix_pending_user_questions_session_asked",
        "pending_user_questions",
        ["session_id", "asked_at"],
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.drop_index(
        "ix_pending_user_questions_session_asked",
        table_name="pending_user_questions",
        schema="public",
    )
    op.drop_table("pending_user_questions", schema="public")
