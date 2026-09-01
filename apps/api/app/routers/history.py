"""Quiz history: what this caller has generated before."""

from fastapi import APIRouter, Query

from app.deps import CurrentUserId, Sessions
from app.schemas.quiz import QuizHistory, QuizSummary
from app.services.quizzes import DEFAULT_LIMIT, MAX_LIMIT, list_quizzes

router = APIRouter()


@router.get("", response_model=QuizHistory)
def quiz_history(
    user_id: CurrentUserId,
    sessions: Sessions,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> QuizHistory:
    """This caller's quizzes, newest first.

    Deliberately `def`: FastAPI runs a sync endpoint in a threadpool, so the query does not park the
    event loop. With no DATABASE_URL there is genuinely no history, so the answer is an empty list
    rather than an error.
    """
    rows = list_quizzes(sessions, user_id, limit)
    return QuizHistory(
        quizzes=[
            QuizSummary(
                id=r.id,
                title=r.payload.get("title", ""),
                source_url=r.source_url,
                question_count=len(r.payload.get("questions", [])),
                created_at=r.created_at,
            )
            for r in rows
        ]
    )
