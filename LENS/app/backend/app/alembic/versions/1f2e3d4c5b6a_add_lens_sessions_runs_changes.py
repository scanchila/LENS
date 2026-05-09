"""Add lens_sessions, runs, and candidate_changes tables.

Revision ID: 1f2e3d4c5b6a
Revises: f1a8b9d0e2c3
Create Date: 2026-05-09

The new flow models the demo as a series of operator-triggered runs
against a user-created session, with per-candidate change history so
operators can see what each run did to each idea.

Schema:
  lens_sessions(
    id            uuid pk,
    owner_id      uuid fk -> user.id (nullable),
    title         text,
    description   text null,
    goal_query    text null,
    created_at    timestamptz default now(),
    updated_at    timestamptz default now()
  )

  runs(
    id            uuid pk,
    session_id    uuid fk -> lens_sessions.id,
    kind          text  -- seed_ideas|document_upload|hn_search|contradiction_lens|cross_domain_lens
    status        text default 'pending'
                     (pending|running|complete|failed)
    mode          text default 'scripted'  (scripted|real)
    input         jsonb default '{}',
    summary       jsonb default '{}',
    error         text null,
    started_at    timestamptz default now(),
    finished_at   timestamptz null
  )

  candidate_changes(
    id            uuid pk,
    run_id        uuid fk -> runs.id,
    candidate_id  uuid fk -> candidates.id,
    change_kind   text  (created|updated|killed|merged|restored|reinforced|red_struck)
    field_diffs   jsonb default '{}',
    reason        text null,
    created_at    timestamptz default now()
  )

The Candidate.session_id column is intentionally NOT promoted to a FK
into lens_sessions: the existing 11-stage demo at /board/{sid} uses a
free-form UUID and continues to work unmodified.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1f2e3d4c5b6a"
down_revision = "f1a8b9d0e2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path TO public")

    op.create_table(
        "lens_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("goal_query", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.lens_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'scripted'"),
        ),
        sa.Column(
            "input",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('seed_ideas','document_upload','hn_search',"
            "'contradiction_lens','cross_domain_lens')",
            name="ck_runs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','complete','failed')",
            name="ck_runs_status",
        ),
        sa.CheckConstraint(
            "mode IN ('scripted','real')",
            name="ck_runs_mode",
        ),
        schema="public",
    )

    op.create_index(
        "ix_runs_session_started",
        "runs",
        ["session_id", "started_at"],
        schema="public",
    )

    op.create_table(
        "candidate_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.candidates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("change_kind", sa.Text(), nullable=False),
        sa.Column(
            "field_diffs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "change_kind IN ('created','updated','killed','merged',"
            "'restored','reinforced','red_struck')",
            name="ck_candidate_changes_kind",
        ),
        schema="public",
    )

    op.create_index(
        "ix_candidate_changes_candidate_created",
        "candidate_changes",
        ["candidate_id", "created_at"],
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.drop_index(
        "ix_candidate_changes_candidate_created",
        table_name="candidate_changes",
        schema="public",
    )
    op.drop_table("candidate_changes", schema="public")
    op.drop_index(
        "ix_runs_session_started", table_name="runs", schema="public"
    )
    op.drop_table("runs", schema="public")
    op.drop_table("lens_sessions", schema="public")
