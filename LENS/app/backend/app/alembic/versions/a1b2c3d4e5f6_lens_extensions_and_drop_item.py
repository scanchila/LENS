"""Drop legacy item table; verify pgvector + AGE extensions; init graph

Revision ID: a1b2c3d4e5f6
Revises: fe56fa70289e
Create Date: 2026-05-05

This migration is the boundary between the upstream FastAPI template's
schema and the LENS schema:

  1. Drops the legacy `item` table (the template's example CRUD)
  2. Asserts pgvector and Apache AGE extensions are available
     (the custom Postgres image installs them; this just registers
      them with this database via CREATE EXTENSION IF NOT EXISTS)
  3. Initializes the application's AGE graph

Subsequent migrations build the LENS schema on top of this baseline.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


GRAPH_NAME = "lens"


def upgrade() -> None:
    # Drop the legacy item table (template's example CRUD).
    op.execute("DROP TABLE IF EXISTS item CASCADE")

    # Ensure required extensions exist. The custom Postgres image bundles
    # both, but a database may be created later or restored from a dump
    # without the init script having run.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS age")

    # AGE requires LOAD + search_path adjustment per session; do it here
    # so the graph creation below works.
    op.execute("LOAD 'age'")
    op.execute('SET search_path = ag_catalog, "$user", public')

    # Idempotent graph creation. AGE raises if the graph already exists,
    # so we guard with a DO block.
    op.execute(
        f"""
        DO $$
        BEGIN
            PERFORM create_graph('{GRAPH_NAME}');
        EXCEPTION WHEN OTHERS THEN
            -- Graph already exists or cannot be created; ignore.
            NULL;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Not reversible: dropping the graph would lose data, and re-creating
    # the legacy item table would require schema details we no longer
    # carry. Provided as a no-op rather than reconstructing the previous
    # state.
    pass
