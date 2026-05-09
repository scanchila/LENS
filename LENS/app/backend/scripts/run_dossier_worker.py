"""CLI entrypoint for the dossier ingest worker (TICKET-046).

Run from the backend directory::

    cd LENS/app/backend
    python -m scripts.run_dossier_worker

The worker watches ``settings.LENS_CAR_TICKET_DIR`` for runtime evidence
tickets transitioning to ``done: true`` and ingests them into Postgres
+ AGE. Logs go to stdout for ``docker compose logs``.
"""

from __future__ import annotations

from app.workers.dossier_ingest_worker import run

if __name__ == "__main__":
    run()
