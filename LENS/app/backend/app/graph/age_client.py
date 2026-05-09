"""Async Apache AGE Cypher helper.

Wraps ``psycopg`` so callers can issue Cypher against the ``lens`` graph
without repeating the ``LOAD 'age'`` / ``SET search_path`` boilerplate
that AGE requires per connection.

Usage::

    rows = await with_graph(
        "MATCH (p:Principle) RETURN p.name LIMIT $k",
        {"k": 10},
    )

    rows = await cypher("MATCH (n) RETURN count(n)")

Cypher parameters are interpolated client-side (Cypher inside
``cypher(...)`` does not bind SQL placeholders). All values are JSON-encoded
before substitution; pass only primitives, lists, and dicts.

Single-column RETURN only. The Postgres ``cypher()`` SRF requires the
caller to declare each return column's type; this helper hard-codes a
single ``agtype`` column. Multi-column queries should be split.
"""

from __future__ import annotations

import json
import re
from typing import Any

from psycopg import AsyncConnection

from app.core.config import settings

GRAPH_NAME = "lens"

_PARAM_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _render_param(value: Any) -> str:
    """Render a Python value as a Cypher literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_render_param(v) for v in value) + "]"
    if isinstance(value, dict):
        items = [f"{k}: {_render_param(v)}" for k, v in value.items()]
        return "{" + ", ".join(items) + "}"
    raise TypeError(f"Unsupported Cypher param type: {type(value).__name__}")


def _interpolate(query: str, params: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in params:
            raise KeyError(f"Cypher param ${key} not provided")
        return _render_param(params[key])

    return _PARAM_RE.sub(repl, query)


class AGEClient:
    def __init__(self, dsn: str | None = None, graph_name: str = GRAPH_NAME) -> None:
        self._dsn = dsn or str(settings.SQLALCHEMY_DATABASE_URI).replace(
            "postgresql+psycopg://", "postgresql://"
        )
        self._graph_name = graph_name

    async def with_graph(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[tuple[Any, ...]]:
        params = params or {}
        rendered = _interpolate(query, params)
        sql = f"SELECT * FROM cypher('{self._graph_name}', $cypher${rendered}$cypher$) AS (result agtype)"

        async with await AsyncConnection.connect(self._dsn) as conn:
            async with conn.cursor() as cur:
                await cur.execute("LOAD 'age'")
                await cur.execute('SET search_path = ag_catalog, "$user", public')
                await cur.execute(sql)
                return list(await cur.fetchall())

    async def cypher(self, query: str, **params: Any) -> list[tuple[Any, ...]]:
        return await self.with_graph(query, params)


age_client = AGEClient()


async def with_graph(
    query: str, params: dict[str, Any] | None = None
) -> list[tuple[Any, ...]]:
    return await age_client.with_graph(query, params)


async def cypher(query: str, **params: Any) -> list[tuple[Any, ...]]:
    return await age_client.cypher(query, **params)
