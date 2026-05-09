import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from pydantic import EmailStr
from sqlalchemy import (
    ARRAY,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlmodel import Field, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Corpus schema (TICKET-010)
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 1024


class DocumentBase(SQLModel):
    source_type: str = Field(sa_column=Column(String(64), nullable=False))
    source_uri: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    raw_blob_key: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    parsed_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )


class Document(DocumentBase, table=True):
    __tablename__ = "documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, index=True, ondelete="CASCADE"
    )
    ingested_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


class ChunkBase(SQLModel):
    ord: int = Field(sa_column=Column(Integer, nullable=False))
    text: str = Field(sa_column=Column(Text, nullable=False))
    char_start: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    char_end: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    tokens: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


class Chunk(ChunkBase, table=True):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ord", name="uq_chunks_document_ord"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(
        foreign_key="documents.id", nullable=False, index=True, ondelete="CASCADE"
    )


class Embedding(SQLModel, table=True):
    __tablename__ = "embeddings"

    chunk_id: uuid.UUID = Field(
        foreign_key="chunks.id", primary_key=True, ondelete="CASCADE"
    )
    model: str = Field(sa_column=Column(String(128), nullable=False))
    vector: Any = Field(sa_column=Column(Vector(EMBEDDING_DIM), nullable=False))


# ---------------------------------------------------------------------------
# CAR dossier integration (TICKET-045, TICKET-046)
# ---------------------------------------------------------------------------


class DossierJob(SQLModel, table=True):
    """One row per CAR evidence_dossier ticket the orchestrator emits.

    ``ticket_id`` is the frontmatter ``tkt_<hex>`` id (the durable handle
    callers poll), not the filename's TICKET-NNNN number. ``status`` walks
    queued -> ingested | failed. ``payload_hash`` is the hash of the parsed
    dossier structure (sources URLs + claim texts + valences); the ingest
    worker uses it as an idempotency key for re-runs of the same file.
    """

    __tablename__ = "dossier_jobs"

    ticket_id: str = Field(sa_column=Column(Text, primary_key=True))
    candidate_id: uuid.UUID = Field(nullable=False, index=True)
    status: str = Field(
        default="queued",
        sa_column=Column(Text, nullable=False, server_default="queued"),
    )
    lens_attribution: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    ticket_path: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    dossier_path: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    payload_hash: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )
    ingested_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=True,
    )


# ---------------------------------------------------------------------------
# LLM cost log (TICKET-020)
# ---------------------------------------------------------------------------


class LlmCostLog(SQLModel, table=True):
    """Audit log for LLM provider spend.

    Append-only. Written by the ingestion pipeline (Voyage) and, in later
    PRs, by agent-loop adapters (Anthropic). Budget cap enforcement reads
    aggregates from this table.
    """

    __tablename__ = "llm_cost_log"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        index=True,
        ondelete="SET NULL",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="documents.id",
        nullable=True,
        index=True,
        ondelete="SET NULL",
    )
    model: str = Field(sa_column=Column(String(128), nullable=False))
    input_tokens: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    output_tokens: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    cost_usd: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(12, 6), nullable=False, server_default="0"),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Agent runtime: persisted session notes (TICKET-041)
# ---------------------------------------------------------------------------


class SessionNote(SQLModel, table=True):
    __tablename__ = "session_notes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(nullable=False, index=True)
    agent_name: str = Field(sa_column=Column(Text, nullable=False))
    # Validation against the supported enum lives in the note tool so the
    # catalog can be extended without a migration; see app/agents/tools/note.py.
    kind: str = Field(sa_column=Column(Text, nullable=False))
    text: str = Field(sa_column=Column(Text, nullable=False))
    payload: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Agent runtime: pending user questions (TICKET-042)
# ---------------------------------------------------------------------------


class PendingUserQuestion(SQLModel, table=True):
    __tablename__ = "pending_user_questions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(nullable=False, index=True)
    question: str = Field(sa_column=Column(Text, nullable=False))
    asked_by_agent: str = Field(sa_column=Column(Text, nullable=False))
    asked_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )
    answer: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    answered_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=True,
    )


class AnswerQuestionRequest(SQLModel):
    """Request body for POST /api/v1/sessions/{session_id}/answer-question."""

    question_id: uuid.UUID
    answer: str


# ---------------------------------------------------------------------------
# Candidates (TICKET-050) — the demo's load-bearing store
# ---------------------------------------------------------------------------


CANDIDATE_STATUSES = (
    "speculative",
    "supported",
    "challenged",
    "ready_to_validate",
    "killed",
    "merged_into",
)


CHALLENGER_VERDICTS = (
    "kept",
    "red_struck",
    "needs_evidence",
    "provenance_failed",
    "held",
)


class Candidate(SQLModel, table=True):
    """One opportunity candidate produced by a lens.

    Persisted under one ``session_id``. Rolled forward by Challenger,
    Synthesizer, and Critic. Read by the SSE-fed prediction board.
    """

    __tablename__ = "candidates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(nullable=False, index=True)
    owner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        index=True,
        ondelete="CASCADE",
    )
    lens: str = Field(sa_column=Column(Text, nullable=False))
    statement: str = Field(sa_column=Column(Text, nullable=False))
    evidence_chunk_ids: list[uuid.UUID] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(PostgresUUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
    )
    v_hat: float = Field(default=0.0, nullable=False)
    c_hat: float = Field(default=0.0, nullable=False)
    pipeline_steps: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    status: str = Field(
        default="speculative",
        sa_column=Column(Text, nullable=False, server_default="speculative"),
    )
    challenger_verdict: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    dossier_grounded: bool = Field(default=False, nullable=False)
    provenance_audited: bool = Field(default=False, nullable=False)
    source_count: int = Field(default=0, nullable=False)
    reinforces: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Text), nullable=False, server_default="{}"),
    )
    merged_from: list[uuid.UUID] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(PostgresUUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
    )
    ahead_of_yc: bool = Field(default=False, nullable=False)
    pain_owner: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    why_now: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    contradictions: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    open_assumptions: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    validation_path: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    evidence_sources: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


class CandidateScore(SQLModel, table=True):
    """Per-candidate scoring history (TICKET-062 Critic output)."""

    __tablename__ = "candidate_scores"

    candidate_id: uuid.UUID = Field(
        foreign_key="candidates.id", primary_key=True, ondelete="CASCADE"
    )
    non_obvious: float = Field(default=0.0, nullable=False)
    grounded: float = Field(default=0.0, nullable=False)
    actionable: float = Field(default=0.0, nullable=False)
    v_hat: float = Field(default=0.0, nullable=False)
    c_hat: float = Field(default=0.0, nullable=False)
    composite: float = Field(default=0.0, nullable=False)
    scored_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


class CandidatePublic(SQLModel):
    """Read model returned by GET /api/v1/sessions/{sid}/candidates."""

    id: uuid.UUID
    session_id: uuid.UUID
    lens: str
    statement: str
    evidence_chunk_ids: list[uuid.UUID]
    v_hat: float
    c_hat: float
    pipeline_steps: list[Any]
    status: str
    challenger_verdict: str | None
    dossier_grounded: bool
    provenance_audited: bool
    source_count: int
    reinforces: list[str]
    merged_from: list[uuid.UUID]
    ahead_of_yc: bool
    pain_owner: str | None
    why_now: str | None
    contradictions: list[Any]
    open_assumptions: list[Any]
    validation_path: list[Any]
    evidence_sources: list[Any]
    created_at: datetime
    updated_at: datetime


class CandidatesPublic(SQLModel):
    data: list[CandidatePublic]
    count: int


# ---------------------------------------------------------------------------
# LensSession / Run / CandidateChange — operator-driven flow
# ---------------------------------------------------------------------------


class LensSession(SQLModel, table=True):
    """An operator-created investigation session.

    Distinct from the legacy ``Candidate.session_id`` UUID, which the
    11-stage demo uses as a free-form identifier with no backing row.
    The new run-based flow persists a real LensSession row and uses its
    id as the session_id on candidates it creates.
    """

    __tablename__ = "lens_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        index=True,
        ondelete="CASCADE",
    )
    title: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    goal_query: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


class Run(SQLModel, table=True):
    """One operator-triggered action against a LensSession.

    A run is the unit of "what just happened" the UI shows in the
    timeline. Each run that mutates candidates produces one or more
    ``CandidateChange`` rows.
    """

    __tablename__ = "runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(
        foreign_key="lens_sessions.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    kind: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(
        default="pending",
        sa_column=Column(Text, nullable=False, server_default="pending"),
    )
    mode: str = Field(
        default="scripted",
        sa_column=Column(Text, nullable=False, server_default="scripted"),
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=True,
    )


class CandidateChange(SQLModel, table=True):
    """Per-candidate diff produced by a run.

    field_diffs is a mapping ``{field: {"from": old, "to": new}}``. Used
    to render the per-idea history drawer.
    """

    __tablename__ = "candidate_changes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(
        foreign_key="runs.id", nullable=False, index=True, ondelete="CASCADE"
    )
    candidate_id: uuid.UUID = Field(
        foreign_key="candidates.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    change_kind: str = Field(sa_column=Column(Text, nullable=False))
    field_diffs: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


# Read models


class LensSessionPublic(SQLModel):
    id: uuid.UUID
    title: str
    description: str | None
    goal_query: str | None
    created_at: datetime
    updated_at: datetime


class LensSessionsPublic(SQLModel):
    data: list[LensSessionPublic]
    count: int


class RunPublic(SQLModel):
    id: uuid.UUID
    session_id: uuid.UUID
    kind: str
    status: str
    mode: str
    input: dict[str, Any]
    summary: dict[str, Any]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class RunsPublic(SQLModel):
    data: list[RunPublic]
    count: int


class CandidateChangePublic(SQLModel):
    id: uuid.UUID
    run_id: uuid.UUID
    candidate_id: uuid.UUID
    change_kind: str
    field_diffs: dict[str, Any]
    reason: str | None
    created_at: datetime


class CandidateHistoryPublic(SQLModel):
    candidate_id: uuid.UUID
    changes: list[CandidateChangePublic]
    runs: dict[str, RunPublic]  # run_id -> RunPublic for join-free render


class RunDetailPublic(SQLModel):
    run: RunPublic
    changes: list[CandidateChangePublic]
