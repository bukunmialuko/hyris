"""Pydantic models for the API boundary, mirroring packages/contracts/quiz.schema.json."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

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
    user_id: str = "anonymous"  # replaced by real auth in a later milestone


class RunCreated(BaseModel):
    run_id: str
    events_url: str
    result_url: str


class QuizQuestion(BaseModel):
    slot_id: int
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_answer: int = Field(ge=0, le=3)
    explanation: Optional[str] = None


class Quiz(BaseModel):
    id: str
    title: str
    note: str = ""
    truncated: bool = False
    questions: list[QuizQuestion]


class RunStatus(BaseModel):
    run_id: str
    status: Literal["running", "done", "failed"]
    steps: list[str] = []
    quiz: Optional[Quiz] = None
    error: Optional[str] = None
