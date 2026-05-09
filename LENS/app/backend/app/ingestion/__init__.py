"""Document ingestion pipeline (TICKET-020).

Submodules:
- :mod:`parsers`     — extension/MIME dispatch into raw text + metadata
- :mod:`chunker`     — semantic-paragraph + sliding-window fallback chunker
- :mod:`embeddings`  — Voyage embedding service with batching + retry
- :mod:`pipeline`    — top-level ``ingest_document`` entry point
"""

from .pipeline import IngestionResult, ingest_document

__all__ = ["IngestionResult", "ingest_document"]
