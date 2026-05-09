"""Background workers.

Each worker runs as its own long-lived process (typically a docker compose
service). Workers do not import FastAPI or run as part of the HTTP app.
"""
