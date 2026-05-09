import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from pydantic import EmailStr
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
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
