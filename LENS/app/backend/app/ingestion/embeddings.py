"""Voyage embedding service (TICKET-020).

Wraps the official ``voyageai`` Python client.

Design choices:
  - ``voyage-3-large`` (1024-dim) is the default; matches the embeddings
    table dimension. The model is a setting so we can swap to a smaller /
    cheaper variant per-call if needed.
  - Batching: 64 chunks per call (Voyage's recommended max for v3-large).
  - Retry: simple exponential backoff on ``RateLimitError`` / 429s with
    jittered sleeps. Tenacity is overkill here.
  - Token + cost accounting: per call, return ``EmbeddingBatch`` carrying
    the vectors plus a Voyage-reported token count. Cost is computed from
    settings.VOYAGE_COST_PER_M_INPUT_TOKENS_USD.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.ingestion.embeddings")

DEFAULT_BATCH_SIZE = 64
MAX_RETRIES = 5
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0


@dataclass
class EmbeddingBatch:
    """Result of one embed call (one batch)."""

    vectors: list[list[float]]
    input_tokens: int
    model: str


@dataclass
class EmbeddingRun:
    """Aggregate result across all batches for one document."""

    vectors: list[list[float]]
    input_tokens: int
    cost_usd: float
    model: str


class VoyageError(RuntimeError):
    """Voyage embedding failed (after retries / non-retriable error)."""


def _voyage_cost(input_tokens: int) -> float:
    """Cost in USD for ``input_tokens`` against the configured Voyage model.

    Output tokens for embeddings are zero by definition.
    """
    rate = settings.VOYAGE_COST_PER_M_INPUT_TOKENS_USD
    return (input_tokens / 1_000_000.0) * rate


def _is_rate_limited(exc: BaseException) -> bool:
    """Best-effort detection across voyageai versions / proxy errors."""
    msg = str(exc).lower()
    if "rate limit" in msg or "rate_limit" in msg or "429" in msg:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    name = type(exc).__name__.lower()
    return "ratelimit" in name


class VoyageEmbedder:
    """Async-friendly wrapper around the Voyage SDK.

    The Voyage Python client is synchronous; we offload calls onto a
    thread to keep the FastAPI event loop responsive during ingestion.

    The ``input_type`` parameter is set per-call: ``"document"`` while
    ingesting and ``"query"`` for search queries (Voyage tunes embeddings
    differently for asymmetric retrieval).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._api_key = (
            api_key or settings.VOYAGE_API_KEY or os.environ.get("VOYAGE_API_KEY")
        )
        self._model = model or settings.VOYAGE_EMBED_MODEL
        self._batch_size = batch_size
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise VoyageError("VOYAGE_API_KEY is not set; cannot call the Voyage API.")
        try:
            import voyageai
        except Exception as exc:
            raise VoyageError(f"voyageai SDK not installed: {exc}") from exc
        self._client = voyageai.Client(api_key=self._api_key)  # type: ignore[attr-defined]
        return self._client

    def _embed_batch_sync(self, texts: list[str], input_type: str) -> EmbeddingBatch:
        client = self._ensure_client()
        result = client.embed(
            texts=texts,
            model=self._model,
            input_type=input_type,
            truncation=True,
        )
        # Voyage SDK returns object with ``.embeddings`` and ``.total_tokens``.
        vectors = list(result.embeddings)
        input_tokens = int(getattr(result, "total_tokens", 0) or 0)
        return EmbeddingBatch(
            vectors=vectors, input_tokens=input_tokens, model=self._model
        )

    async def _embed_batch(self, texts: list[str], input_type: str) -> EmbeddingBatch:
        attempt = 0
        while True:
            try:
                return await asyncio.to_thread(
                    self._embed_batch_sync, texts, input_type
                )
            except VoyageError:
                raise
            except Exception as exc:
                attempt += 1
                if attempt > MAX_RETRIES or not _is_rate_limited(exc):
                    raise VoyageError(f"Voyage embed failed: {exc!r}") from exc
                backoff = min(MAX_BACKOFF_S, BASE_BACKOFF_S * (2 ** (attempt - 1)))
                jitter = random.uniform(0, backoff * 0.25)
                sleep_for = backoff + jitter
                logger.warning(
                    "Voyage rate-limited (attempt %d); sleeping %.2fs",
                    attempt,
                    sleep_for,
                )
                await asyncio.sleep(sleep_for)

    async def embed_documents(self, texts: list[str]) -> EmbeddingRun:
        """Embed a list of document chunks. Batches at ``self.batch_size``."""
        return await self._embed_many(texts, input_type="document")

    async def embed_query(self, query: str) -> EmbeddingRun:
        """Embed a single user query. Returns a 1-vector EmbeddingRun."""
        return await self._embed_many([query], input_type="query")

    async def _embed_many(self, texts: list[str], input_type: str) -> EmbeddingRun:
        if not texts:
            return EmbeddingRun(
                vectors=[], input_tokens=0, cost_usd=0.0, model=self._model
            )
        all_vectors: list[list[float]] = []
        total_tokens = 0
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            result = await self._embed_batch(batch, input_type=input_type)
            all_vectors.extend(result.vectors)
            total_tokens += result.input_tokens
        cost = _voyage_cost(total_tokens)
        return EmbeddingRun(
            vectors=all_vectors,
            input_tokens=total_tokens,
            cost_usd=cost,
            model=self._model,
        )


_default_embedder: VoyageEmbedder | None = None


def get_embedder() -> VoyageEmbedder:
    """Return a process-wide default embedder; constructed lazily."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = VoyageEmbedder()
    return _default_embedder
