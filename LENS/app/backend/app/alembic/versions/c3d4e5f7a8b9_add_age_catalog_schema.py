"""Add Apache AGE catalog labels, edge types, and seed principles

Revision ID: c3d4e5f7a8b9
Revises: b2c3d4e5f7a8
Create Date: 2026-05-09

Implements TICKET-011. The AGE extension and the `lens` graph were
created by the parent migration ``a1b2c3d4e5f6``. Here we:

  - Declare the catalog labels:   Principle, Source, Candidate, Claim
  - Declare the catalog edges:    analog_of, prerequisite_for,
                                  application_of, composes_with,
                                  supports, refutes, cited_by
  - Seed 8 hand-curated principles plus a handful of `analog_of` and
    `prerequisite_for` edges where the relationship is genuine.

AGE's ``create_vlabel`` / ``create_elabel`` raise on duplicate, so each
declaration is wrapped in a DO block that swallows exceptions to make
the migration idempotent.
"""

import json

from alembic import op

revision = "c3d4e5f7a8b9"
down_revision = "b2c3d4e5f7a8"
branch_labels = None
depends_on = None


GRAPH_NAME = "lens"

VERTEX_LABELS = ("Principle", "Source", "Candidate", "Claim")
EDGE_LABELS = (
    "analog_of",
    "prerequisite_for",
    "application_of",
    "composes_with",
    "supports",
    "refutes",
    "cited_by",
)


SEED_PRINCIPLES = [
    {
        "name": "memoization",
        "description": (
            "Cache the result of a deterministic computation keyed by its "
            "inputs; identical inputs return instantly without recomputing."
        ),
        "structural_signature": (
            "A pure function with bounded input space whose evaluation is "
            "expensive relative to lookup; same inputs always produce the "
            "same output; cache invalidation is unnecessary."
        ),
        "canonical_examples": [
            "Recursive Fibonacci with a memo table",
            "HTTP response caching keyed by URL + headers",
            "React useMemo / useCallback",
            "Database materialized views",
        ],
    },
    {
        "name": "lazy_evaluation",
        "description": (
            "Defer computing a value until its result is actually needed; "
            "large or infinite intermediate structures can be expressed "
            "without materializing."
        ),
        "structural_signature": (
            "Composable description of computation decoupled from execution; "
            "consumers pull only what they need; producers describe arbitrarily "
            "large structures cheaply."
        ),
        "canonical_examples": [
            "Haskell pervasive lazy evaluation",
            "Python generators and itertools",
            "Database query planners",
            "Promise chains (deferred execution)",
        ],
    },
    {
        "name": "layered_abstraction",
        "description": (
            "Express a complex system as a stack of layers, each providing a "
            "clean interface to the layer above and depending only on the "
            "layer below."
        ),
        "structural_signature": (
            "Concerns at different levels of abstraction can be separated; "
            "each layer's complexity is hidden behind a narrower interface; "
            "layers depend downward only."
        ),
        "canonical_examples": [
            "OSI / TCP/IP stack",
            "OS kernel <-> syscalls <-> libc <-> application",
            "Database storage engines beneath SQL beneath ORM",
        ],
    },
    {
        "name": "pipelines_with_backpressure",
        "description": (
            "Connect processing stages so each signals upstream when it "
            "cannot keep up; producers slow down rather than overwhelming "
            "consumers."
        ),
        "structural_signature": (
            "Producer-consumer chain where upstream throughput sometimes "
            "exceeds downstream; data loss unacceptable; queues bounded; "
            "system must remain stable under load."
        ),
        "canonical_examples": [
            "Reactive Streams (Akka, RxJava)",
            "Unix pipes with blocking writes",
            "Kafka consumer groups with controlled fetch rates",
            "TCP flow control via window size",
        ],
    },
    {
        "name": "idempotence",
        "description": (
            "Design operations so applying them N times has the same effect "
            "as applying them once; safe under retries, duplicates, and "
            "reordering."
        ),
        "structural_signature": (
            "An operation invoked across an unreliable channel; retries are "
            "cheaper than tracking exactly-once delivery; semantic effect "
            "expressible as a state transition that repeats safely."
        ),
        "canonical_examples": [
            "HTTP PUT / DELETE",
            "Database UPSERT / ON CONFLICT DO UPDATE",
            "Stripe Idempotency-Key header",
            "Kafka transactional producer with deduplication",
        ],
    },
    {
        "name": "eventual_consistency",
        "description": (
            "Relax the requirement that all replicas agree at every moment; "
            "guarantee instead that replicas converge absent new updates."
        ),
        "structural_signature": (
            "Availability and partition tolerance matter more than instant "
            "global agreement; users tolerate stale reads in exchange for "
            "uptime; convergence (not immediacy) is the contract."
        ),
        "canonical_examples": [
            "DNS propagation",
            "Amazon Dynamo / DynamoDB",
            "Git's distributed commit model",
            "SMTP relay delivery",
        ],
    },
    {
        "name": "content_addressable_storage",
        "description": (
            "Address data by a hash of its contents; identical content has "
            "identical address; deduplication is automatic; integrity is "
            "verifiable; references are immutable."
        ),
        "structural_signature": (
            "Data identity defined by content rather than location; "
            "integrity verification is needed; references should not break "
            "when storage layout changes."
        ),
        "canonical_examples": [
            "Git object database",
            "IPFS / IPLD",
            "Docker image layers",
            "Bitcoin transaction IDs",
        ],
    },
    {
        "name": "novelty_search",
        "description": (
            "Optimize for novelty (distance from previously-seen behaviors) "
            "rather than for an objective; counterintuitively beats "
            "objective-based search on deceptive landscapes."
        ),
        "structural_signature": (
            "Direct progress toward the objective is deceptive; behavior "
            "space large but bounded; novelty measurable via behavioral "
            "distance."
        ),
        "canonical_examples": [
            "Lehman & Stanley biped-walking experiments",
            "POET (paired open-ended trailblazer)",
            "Quality-Diversity / MAP-Elites",
        ],
    },
]


# (source_name, target_name, edge_label)
SEED_EDGES: list[tuple[str, str, str]] = [
    # Memoization is structurally analogous to content-addressable storage
    # (both substitute a lookup for a recomputation, keyed by content/inputs).
    ("memoization", "content_addressable_storage", "analog_of"),
    # Lazy evaluation is the structural complement of memoization in the
    # space of evaluation-strategy primitives.
    ("lazy_evaluation", "memoization", "analog_of"),
    # Idempotence is a prerequisite for safe eventual consistency: replicas
    # that converge must apply replayed updates without divergence.
    ("idempotence", "eventual_consistency", "prerequisite_for"),
    # Backpressure pipelines presuppose layered abstraction (each stage is
    # a layer with a clean upstream/downstream contract).
    ("layered_abstraction", "pipelines_with_backpressure", "prerequisite_for"),
]


def _ag_load_session() -> None:
    op.execute("LOAD 'age'")
    op.execute('SET search_path = ag_catalog, "$user", public')


def _create_label_idempotent(label: str, kind: str) -> None:
    """kind is 'vlabel' or 'elabel'."""
    op.execute(
        f"""
        DO $$
        BEGIN
            PERFORM create_{kind}('{GRAPH_NAME}', '{label}');
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END
        $$;
        """
    )


def _to_cypher_props(d: dict) -> str:
    """Render a dict as a Cypher property map literal.

    Keys are emitted unquoted; string values use single-quoted Cypher syntax
    with single quotes escaped. Lists of strings render as Cypher list
    literals. JSON encoding is used for value escaping for safety.
    """
    parts = []
    for k, v in d.items():
        parts.append(f"{k}: {json.dumps(v)}")
    return "{" + ", ".join(parts) + "}"


def upgrade() -> None:
    _ag_load_session()

    for label in VERTEX_LABELS:
        _create_label_idempotent(label, "vlabel")
    for label in EDGE_LABELS:
        _create_label_idempotent(label, "elabel")

    for principle in SEED_PRINCIPLES:
        name_lit = json.dumps(principle["name"])
        op.execute(
            f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                MERGE (p:Principle {{name: {name_lit}}})
                SET p = {_to_cypher_props(principle)}
                RETURN p
            $$) AS (p agtype);
            """
        )

    for src, dst, edge in SEED_EDGES:
        src_lit = json.dumps(src)
        dst_lit = json.dumps(dst)
        op.execute(
            f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                MATCH (a:Principle {{name: {src_lit}}}),
                      (b:Principle {{name: {dst_lit}}})
                MERGE (a)-[r:{edge}]->(b)
                RETURN r
            $$) AS (r agtype);
            """
        )


def downgrade() -> None:
    _ag_load_session()

    for src, dst, edge in SEED_EDGES:
        src_lit = json.dumps(src)
        dst_lit = json.dumps(dst)
        op.execute(
            f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                MATCH (a:Principle {{name: {src_lit}}})-[r:{edge}]->(b:Principle {{name: {dst_lit}}})
                DELETE r
            $$) AS (r agtype);
            """
        )
    for principle in SEED_PRINCIPLES:
        name_lit = json.dumps(principle["name"])
        op.execute(
            f"""
            SELECT * FROM cypher('{GRAPH_NAME}', $$
                MATCH (p:Principle {{name: {name_lit}}})
                DETACH DELETE p
            $$) AS (p agtype);
            """
        )
    # Labels intentionally kept; PR-2/3 will reuse them.
