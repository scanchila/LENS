"""Session-scoped API routes.

Currently exposes the ``answer-question`` endpoint that unblocks an
``ask_user`` tool call (TICKET-042). Future session lifecycle
operations (start, finish, attach corpus, etc.) live alongside.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import select

from app.api.deps import SessionDep
from app.models import AnswerQuestionRequest, PendingUserQuestion

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post(
    "/{session_id}/answer-question",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def answer_question(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    body: AnswerQuestionRequest,
) -> Response:
    """Record the user's answer to a pending question.

    Returns 204 on success, 404 if the question is not found (or belongs
    to a different session), 409 if the question already has an answer.
    """
    statement = select(PendingUserQuestion).where(
        PendingUserQuestion.id == body.question_id,
        PendingUserQuestion.session_id == session_id,
    )
    question = session.exec(statement).first()
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    if question.answer is not None:
        raise HTTPException(status_code=409, detail="question already answered")

    question.answer = body.answer
    question.answered_at = datetime.now(timezone.utc)
    session.add(question)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
