"""Add session_notes table for the persisted note tool

Revision ID: d4e5f7a8b9d0
Revises: d4e5f7a8b9c0
Create Date: 2026-05-09

Implements TICKET-041. Replaces the ephemeral in-memory note buffer with
a durable per-session ledger that other tools (and post-run analytics)
can read back.

Schema:
  session_notes(
    id          uuid pk,
    session_id  uuid,            -- agent-run session
    agent_name  text,            -- ToolContext.parent_agent_name
    kind        text,            -- 'scratch' | 'finding' | 'provenance'
                                 -- | 'hypothesis' | 'candidate'
    text        text,
    payload     jsonb,           -- structured side-channel
    created_at  timestamptz default now()
  )
  index ix_session_notes_session_kind_created on
        (session_id, kind, created_at)

The ``kind`` enum is enforced at the application layer (see
``app/agents/tools/note.py``) rather than via a Postgres CHECK so the
catalog can grow without a migration.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e5f7a8b9d0"
down_revision = "d4e5f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path TO public")

    op.create_table(
        "session_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )

    op.create_index(
        "ix_session_notes_session_kind_created",
        "session_notes",
        ["session_id", "kind", "created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.drop_index(
        "ix_session_notes_session_kind_created",
        table_name="session_notes",
        schema="public",
    )
    op.drop_table("session_notes", schema="public")
