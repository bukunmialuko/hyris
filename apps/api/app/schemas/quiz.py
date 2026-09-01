"""Pydantic models for the API boundary, mirroring packages/contracts/quiz.schema.json."""

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
