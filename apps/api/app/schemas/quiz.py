"""Pydantic models for the API boundary, mirroring packages/contracts/quiz.schema.json."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# The only three states a run can be in — shared with app.services.runs.
RunState = Literal["running", "done", "failed"]

EducationLevel = Literal["high_school", "undergraduate", "masters", "research"]
Difficulty = Literal["easy", "medium", "hard", "expert"]
BloomLevel = Literal["remember", "understand", "apply", "analyse", "evaluate", "create"]


class QuestionProfile(BaseModel):
    education_level: EducationLevel = "masters"
    difficulty: Difficulty = "hard"
    question_count: int = Field(default=5, ge=1, le=20)
    allow_trick_questions: bool = False
    require_explanations: bool = True


class GenerateRequest(BaseModel):
    page_url: str = Field(min_length=1)
    profile: QuestionProfile = QuestionProfile()
    # Identity is the X-User-Id header, not a body field: GET endpoints need it too, and real auth
    # will replace the dependency rather than every schema. See app/deps.py.


class RunCreated(BaseModel):
    run_id: str
    events_url: str
    result_url: str


class QuizQuestion(BaseModel):
    slot_id: int
    # Carried from the blueprint so an attempt can say which concept was tested (Step 4).
    concept: str | None = None
    bloom_level: BloomLevel | None = None
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_answer: int = Field(ge=0, le=3)
    explanation: str | None = None


class Quiz(BaseModel):
    id: str
    title: str
    note: str = ""
    truncated: bool = False
    questions: list[QuizQuestion]


class RunStatus(BaseModel):
    run_id: str
    status: RunState
    steps: list[str] = []
    quiz: Quiz | None = None
    error: str | None = None


class QuizSummary(BaseModel):
    """A history row. Deliberately not the full payload: a list of twenty quizzes should not ship
    twenty question sets, and the client already holds the one it is showing."""

    id: str
    title: str
    source_url: str
    question_count: int
    created_at: datetime


class QuizHistory(BaseModel):
    quizzes: list[QuizSummary]


class AttemptRequest(BaseModel):
    quiz_id: str = Field(min_length=1)
    # {question_id: chosen option index}. A question left out is marked wrong.
    answers: dict[str, int] = Field(default_factory=dict)
    # Optional idempotency key: resubmitting the same one records nothing and moves no mastery.
    attempt_id: str | None = None


class QuestionResult(BaseModel):
    question_id: str
    concept: str | None = None
    picked: int | None = None
    correct_answer: int
    correct: bool


class AttemptResult(BaseModel):
    attempt_id: str
    quiz_id: str
    score: int
    total: int
    results: list[QuestionResult]
