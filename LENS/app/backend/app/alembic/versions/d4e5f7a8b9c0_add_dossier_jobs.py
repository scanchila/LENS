"""Add dossier_jobs table for CAR evidence_dossier ticket tracking

Revision ID: d4e5f7a8b9c0
Revises: c3d4e5f7a8b9
Create Date: 2026-05-09

Implements TICKET-045 (queue_evidence_dossier) and TICKET-046
(dossier_ingest_worker) persistence:

  - One row per CAR evidence_dossier ticket the orchestrator emits.
  - ticket_id is the frontmatter ``tkt_<hex>`` id, not the filename
    number; the filename number is for humans, the ticket_id is the
    durable handle callers poll.
  - status transitions: queued -> ingested | failed.
  - payload_hash is the parsed-structure hash recorded at ingest time
    so re-running the worker on the same dossier becomes a no-op.

Index on (status, created_at) so the worker (and operators) can scan
``WHERE status = 'queued' ORDER BY created_at`` cheaply.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e5f7a8b9c0"
down_revision = "c3d4e5f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The parent AGE migration leaves search_path on ag_catalog. Force
    # public so the new table lands where every other LENS table lives.
    op.execute("SET search_path TO public")

    op.create_table(
        "dossier_jobs",
        sa.Column("ticket_id", sa.Text(), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("lens_attribution", sa.Text(), nullable=True),
        sa.Column("ticket_path", sa.Text(), nullable=True),
        sa.Column("dossier_path", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'ingested', 'failed')",
            name="ck_dossier_jobs_status",
        ),
        schema="public",
    )

    op.create_index(
        "ix_dossier_jobs_status_created_at",
        "dossier_jobs",
        ["status", "created_at"],
        schema="public",
    )

    op.create_index(
        "ix_dossier_jobs_candidate_id",
        "dossier_jobs",
        ["candidate_id"],
        schema="public",
    )


def downgrade() -> None:
    op.execute("SET search_path TO public")
    op.drop_index(
        "ix_dossier_jobs_candidate_id",
        table_name="dossier_jobs",
        schema="public",
    )
    op.drop_index(
        "ix_dossier_jobs_status_created_at",
        table_name="dossier_jobs",
        schema="public",
    )
    op.drop_table("dossier_jobs", schema="public")
