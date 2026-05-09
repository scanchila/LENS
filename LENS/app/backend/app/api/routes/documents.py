"""Document ingestion endpoints (TICKET-020).

POST /api/v1/documents/upload — multipart upload entry point.

Validation at the edge:
  * payload size  -> 413 if above settings.LENS_UPLOAD_MAX_BYTES
  * mime / extension -> 415 if unsupported
  * empty file -> 400

The ingest itself is delegated to :func:`app.ingestion.pipeline.ingest_document`.
On success we return ``{document_id, n_chunks, cost_usd, model}`` so the
caller can display the cost from a single response without a follow-up
query.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.config import settings
from app.ingestion.parsers import (
    ParserError,
    UnsupportedDocumentError,
)
from app.ingestion.pipeline import ingest_document

logger = logging.getLogger("app.api.documents")

router = APIRouter(prefix="/documents", tags=["documents"])


class UploadResponse(BaseModel):
    document_id: uuid.UUID
    n_chunks: int
    cost_usd: float
    model: str


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    current_user: CurrentUser,
    file: UploadFile = File(..., description="The document to ingest"),
) -> UploadResponse:
    """Ingest a single document for the authenticated user.

    The user is the document's owner; later access (search, dossier) is
    filtered to the owner's documents only.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename"
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload"
        )
    if len(data) > settings.LENS_UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Upload exceeds {settings.LENS_UPLOAD_MAX_BYTES} bytes "
                f"(got {len(data)})."
            ),
        )

    try:
        result = await ingest_document(
            file_bytes=data,
            filename=file.filename,
            owner_id=current_user.id,
            mime_type=file.content_type,
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        )
    except ParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("ingest_document failed for %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc!r}",
        )

    return UploadResponse(
        document_id=result.document_id,
        n_chunks=result.n_chunks,
        cost_usd=result.cost_usd,
        model=result.model,
    )
