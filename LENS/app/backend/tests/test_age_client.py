"""AGE client + seed verification tests (TICKET-011)."""

import asyncio
from typing import Any

from app.graph import age_client, cypher, with_graph


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_seed_principles_loaded() -> None:
    rows = _run(with_graph("MATCH (p:Principle) RETURN count(p)"))
    assert len(rows) == 1
    raw = str(rows[0][0])
    count = int(raw.split("::")[0])
    assert count >= 5, f"expected >= 5 seeded principles, got {count}"


def test_round_trip_create_and_query() -> None:
    _run(
        cypher(
            "CREATE (a:Principle {name: $a}) "
            "CREATE (b:Principle {name: $b}) "
            "CREATE (a)-[:analog_of]->(b) "
            "RETURN a",
            a="__test_a__",
            b="__test_b__",
        )
    )
    try:
        rows = _run(
            cypher(
                "MATCH (a:Principle {name: $a})-[r:analog_of]->(b:Principle {name: $b}) "
                "RETURN r",
                a="__test_a__",
                b="__test_b__",
            )
        )
        assert len(rows) == 1
    finally:
        _run(
            cypher(
                "MATCH (a:Principle {name: $a})-[r:analog_of]->(b:Principle {name: $b}) "
                "DELETE r, a, b RETURN 1",
                a="__test_a__",
                b="__test_b__",
            )
        )


def test_age_client_singleton_default_graph() -> None:
    assert age_client._graph_name == "lens"
