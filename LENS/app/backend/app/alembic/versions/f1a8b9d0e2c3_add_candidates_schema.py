"""Add candidates + candidate_scores tables.

Revision ID: f1a8b9d0e2c3
Revises: e5f7a8b9c0d1
Create Date: 2026-05-09

Implements TICKET-050 §migration. The ``candidates`` table is the
demo's load-bearing store: every lens proposer writes here, every
adversarial agent reads + updates, every UI render reads from here.

Schema:
  candidates(
    id                   uuid pk,
    session_id           uuid index,
    owner_id             uuid fk -> user.id,
    lens                 text,                -- 'cross_domain_transfer' etc
    statement            text,
    evidence_chunk_ids   uuid[] default '{}',
    v_hat                float,
    c_hat                float,
    pipeline_steps       jsonb default '[]',
    status               text default 'speculative',
                            (speculative | supported | challenged
                             | ready_to_validate | killed | merged_into)
    challenger_verdict   text null,
                            (kept | red_struck | needs_evidence
                             | provenance_failed | held)
    dossier_grounded     bool default false,
    provenance_audited   bool default false,
    source_count         int default 0,
    reinforces           text[] default '{}',
    merged_from          uuid[] default '{}',
    ahead_of_yc          bool default false,
    pain_owner           text null,
    why_now              text null,
    contradictions       jsonb default '[]',
    open_assumptions     jsonb default '[]',
    validation_path      jsonb default '[]',
    evidence_sources     jsonb default '[]',
    created_at           timestamptz default now(),
    updated_at           timestamptz default now()
  )

  candidate_scores(
    candidate_id   uuid pk fk -> candidates.id,
    non_obvious    float,
    grounded       float,
    actionable     float,
    v_hat          float,
    c_hat          float,
    composite      float,
    scored_at      timestamptz default now()
  )
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1a8b9d0e2c3"
down_revision = "d4e5f7a8b9ca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path TO public")

    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("lens", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "evidence_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("v_hat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("c_hat", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "pipeline_steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'speculative'"),
        ),
        sa.Column("challenger_verdict", sa.Text(), nullable=True),
        sa.Column(
            "dossier_grounded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "provenance_audited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "source_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "reinforces",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "merged_from",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column(
            "ahead_of_yc",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("pain_owner", sa.Text(), nullable=True),
        sa.Column("why_now", sa.Text(), nullable=True),
        sa.Column(
            "contradictions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "open_assumptions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "validation_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "status IN ('speculative','supported','challenged',"
            "'ready_to_validate','killed','merged_into')",
            name="ck_candidates_status",
        ),
        sa.CheckConstraint(
            "challenger_verdict IS NULL OR challenger_verdict IN "
            "('kept','red_struck','needs_evidence','provenance_failed','held')",
            name="ck_candidates_challenger_verdict",
        ),
        schema="public",
    )

    op.create_index(
        "ix_candidates_session_status",
        "candidates",
        ["session_id", "status"],
        schema="public",
    )

    op.create_table(
        "candidate_scores",
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.candidates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("non_obvious", sa.Float(), nullable=False, server_default="0"),
        sa.Column("grounded", sa.Float(), nullable=False, server_default="0"),
        sa.Column("actionable", sa.Float(), nullable=False, server_default="0"),
        sa.Column("v_hat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("c_hat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("composite", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.drop_table("candidate_scores", schema="public")
    op.drop_index(
        "ix_candidates_session_status",
        table_name="candidates",
        schema="public",
    )
    op.drop_table("candidates", schema="public")
