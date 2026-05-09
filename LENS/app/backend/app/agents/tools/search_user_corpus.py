"""``search_user_corpus`` tool (TICKET-040).

Hybrid pgvector + Postgres FTS over the calling user's chunks.

Score formula::

    score = 0.7 * (1 - cosine_distance) + 0.3 * ts_rank_cd(...)

The 0.7/0.3 weights are a starting point. Tuning lives in TICKET-050+
once we have proposer evaluation telemetry.

Owner derivation
----------------
The session model in ``app.agents.types.ToolContext`` does not yet carry an
``owner_id`` (sessions/runs/users will land in a later PR alongside the
orchestrator). Until then we accept the owner from one of two sources, in
priority order:

  1. An ``owner_resolver`` callable injected at construction time:
     ``async (session_id) -> uuid.UUID | None``. The orchestrator wires this
     once it knows how sessions map to users.
  2. A direct ``owner_id_override`` constructor argument — used by tests
     and CLI smoke runs where the session model is irrelevant.

If neither yields an owner we return a ``ToolResult`` error rather than
running an unfiltered query: leaking another user's documents into a
proposer prompt is the kind of failure AGENTS.md flags as load-bearing.
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text

from app.core.db import engine
from app.ingestion.embeddings import VoyageEmbedder, get_embedder

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec

OwnerResolver = Callable[[uuid.UUID], Awaitable[uuid.UUID | None]]

logger = logging.getLogger("app.agents.tools.search_user_corpus")

DEFAULT_TOP_K = 10
MAX_TOP_K = 50
SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3
QUERY_CACHE_SIZE = 64


def _format_vector(vec: list[float]) -> str:
    """Render a list[float] as a pgvector literal (no client-side binding)."""
    return "[" + ",".join(f"{v:.7f}" for v in vec) + "]"


class _LRUCache(OrderedDict[Any, list[float]]):
    """Small, dependency-free LRU keyed by ``(session_id, query)``.

    Bounded to ``QUERY_CACHE_SIZE`` entries to avoid unbounded growth in
    long-running orchestrator processes.
    """

    def __init__(self, capacity: int) -> None:
        super().__init__()
        self._capacity = capacity

    def get_or_none(self, key: Any) -> list[float] | None:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return None

    def put(self, key: Any, value: list[float]) -> None:
        if key in self:
            self.move_to_end(key)
            self[key] = value
            return
        self[key] = value
        if len(self) > self._capacity:
            self.popitem(last=False)


class SearchUserCorpusTool(Tool):
    spec = ToolSpec(
        name="search_user_corpus",
        description=(
            "Semantic + keyword search over the user's uploaded documents. "
            "Returns ranked chunks with provenance (document, char range, source URI)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language query.",
                    "minLength": 1,
                },
                "top_k": {
                    "type": "integer",
                    "description": (
                        "Maximum number of chunks to return. "
                        f"Default {DEFAULT_TOP_K}, max {MAX_TOP_K}."
                    ),
                    "default": DEFAULT_TOP_K,
                    "minimum": 1,
                    "maximum": MAX_TOP_K,
                },
            },
            "required": ["query"],
        },
        output_schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "format": "uuid"},
                    "document_id": {"type": "string", "format": "uuid"},
                    "text": {"type": "string"},
                    "score": {"type": "number"},
                    "provenance": {
                        "type": "object",
                        "properties": {
                            "source_uri": {"type": ["string", "null"]},
                            "char_start": {"type": ["integer", "null"]},
                            "char_end": {"type": ["integer", "null"]},
                        },
                        "required": ["source_uri", "char_start", "char_end"],
                    },
                },
                "required": ["chunk_id", "document_id", "text", "score", "provenance"],
            },
        },
    )

    def __init__(
        self,
        embedder: VoyageEmbedder | None = None,
        owner_resolver: OwnerResolver | None = None,
        owner_id_override: uuid.UUID | None = None,
    ) -> None:
        """
        Args:
            embedder: dependency-injection seam for tests; defaults to the
                process-wide Voyage embedder.
            owner_resolver: optional ``async (session_id) -> uuid.UUID | None``;
                wired by the orchestrator once sessions know about users.
            owner_id_override: used by tests / smoke runs where there is no
                session model. If set, takes precedence over the resolver.
        """
        self._embedder = embedder or get_embedder()
        self._owner_resolver = owner_resolver
        self._owner_id_override = owner_id_override
        self._cache: _LRUCache = _LRUCache(capacity=QUERY_CACHE_SIZE)

    async def _embed_query_cached(
        self, session_id: uuid.UUID, query: str
    ) -> list[float]:
        key = (session_id, query)
        cached = self._cache.get_or_none(key)
        if cached is not None:
            return cached
        run = await self._embedder.embed_query(query)
        if not run.vectors:
            raise RuntimeError("Voyage returned no query embedding")
        vec = run.vectors[0]
        self._cache.put(key, vec)
        return vec

    async def _resolve_owner(self, ctx: ToolContext) -> uuid.UUID | None:
        if self._owner_id_override is not None:
            return self._owner_id_override
        if self._owner_resolver is not None:
            try:
                return await self._owner_resolver(ctx.session_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("owner_resolver failed: %s", exc)
                return None
        return None

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult(content="Empty query; nothing searched.", is_error=True)

        top_k_raw = args.get("top_k", DEFAULT_TOP_K)
        try:
            top_k = int(top_k_raw)
        except (TypeError, ValueError):
            return ToolResult(
                content=f"Invalid top_k {top_k_raw!r}; expected integer.",
                is_error=True,
            )
        top_k = max(1, min(top_k, MAX_TOP_K))

        owner_id = await self._resolve_owner(ctx)
        if owner_id is None:
            return ToolResult(
                content=(
                    "search_user_corpus requires an owner: configure either "
                    "owner_id_override or owner_resolver. Refusing to search "
                    "without an owner filter."
                ),
                is_error=True,
            )

        try:
            query_vec = await self._embed_query_cached(ctx.session_id, query)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                content=f"Voyage query embedding failed: {exc!r}", is_error=True
            )

        rows = self._run_hybrid_query(query_vec, query, owner_id, top_k)

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "chunk_id": str(row["chunk_id"]),
                    "document_id": str(row["document_id"]),
                    "text": row["text"],
                    "score": float(row["score"]),
                    "provenance": {
                        "source_uri": row.get("source_uri"),
                        "char_start": row.get("char_start"),
                        "char_end": row.get("char_end"),
                    },
                }
            )

        return ToolResult(
            content=results,
            is_error=False,
            metadata={
                "query": query,
                "top_k": top_k,
                "n_results": len(results),
            },
        )

    def _run_hybrid_query(
        self,
        query_vec: list[float],
        query_text: str,
        owner_id: uuid.UUID,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Run the hybrid pgvector+FTS query and return raw rows.

        The ``$query_vector`` literal is interpolated rather than bound
        because pgvector's ``::vector`` cast is strict about parameter
        formats across psycopg drivers; we render the literal locally
        from a controlled list[float] to keep that behavior consistent.
        ``query_text`` and ``owner_id`` use proper SQL parameters.
        """
        vec_literal = _format_vector(query_vec)

        sql = f"""
            WITH scored AS (
                SELECT
                    c.id            AS chunk_id,
                    c.document_id   AS document_id,
                    c.text          AS text,
                    c.char_start    AS char_start,
                    c.char_end      AS char_end,
                    d.source_uri    AS source_uri,
                    1.0 - (e.vector <=> '{vec_literal}'::vector) AS sem_sim,
                    ts_rank_cd(
                        to_tsvector('english', c.text),
                        plainto_tsquery('english', :query_text)
                    ) AS kw_rank
                FROM public.chunks c
                JOIN public.embeddings e ON e.chunk_id = c.id
                JOIN public.documents  d ON d.id = c.document_id
                WHERE d.owner_id = :owner_id
            )
            SELECT
                chunk_id,
                document_id,
                text,
                char_start,
                char_end,
                source_uri,
                ({SEMANTIC_WEIGHT} * sem_sim) + ({KEYWORD_WEIGHT} * kw_rank) AS score
            FROM scored
            ORDER BY score DESC
            LIMIT :top_k
        """

        with engine.connect() as conn:
            result = conn.execute(
                text(sql),
                {
                    "query_text": query_text,
                    "owner_id": str(owner_id),
                    "top_k": int(top_k),
                },
            )
            return [dict(row._mapping) for row in result]
