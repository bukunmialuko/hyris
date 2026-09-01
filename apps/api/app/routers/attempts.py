"""Submitting an attempt: score it, save it, and move the learner's mastery.

This is the half of the loop that makes the next quiz different from this one.
"""

from fastapi import APIRouter, HTTPException

from app.deps import CurrentUserId, Sessions, Store
from app.schemas.quiz import AttemptRequest, AttemptResult, QuestionResult
from app.services.attempts import apply_mastery, load_owned_quiz, record_attempt, score

router = APIRouter()


@router.post("", response_model=AttemptResult, status_code=201)
def submit_attempt(
    req: AttemptRequest,
    user_id: CurrentUserId,
    sessions: Sessions,
    store: Store,
) -> AttemptResult:
    """Score the caller's answers against their stored quiz.

    Deliberately `def`: FastAPI runs a sync endpoint in a threadpool, so the database round-trips
    and the store write do not park the event loop.
    """
    quiz = load_owned_quiz(sessions, req.quiz_id, user_id)
    if quiz is None:
        # 404 whether the quiz does not exist, belongs to someone else, or there is no database at
        # all: a caller must not be able to tell those apart by probing ids.
        raise HTTPException(404, "Unknown quiz.")

    results = score(quiz.payload, req.answers)
    attempt_id, is_new = record_attempt(sessions, req.quiz_id, req.answers, results, req.attempt_id)
    if is_new:
        # Only on a first submission: re-counting one answer would move mastery for a thing the
        # learner did once.
        apply_mastery(store, user_id, results)

    return AttemptResult(
        attempt_id=attempt_id,
        quiz_id=req.quiz_id,
        score=sum(1 for r in results if r["correct"]),
        total=len(results),
        results=[QuestionResult(**r) for r in results],
    )
