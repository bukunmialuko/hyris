"""Pydantic models mirroring packages/contracts/quiz.schema.json."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

EducationLevel = Literal["high_school", "undergraduate", "masters", "research"]
Difficulty = Literal["easy", "medium", "hard", "expert"]
BloomLevel = Literal["remember", "understand", "apply", "analyse", "evaluate", "create"]


class PageContent(BaseModel):
    url: str
    title: str
    text: str
    word_count: int = Field(alias="wordCount", default=0)


class QuestionProfile(BaseModel):
    education_level: EducationLevel = "masters"
    difficulty: Difficulty = "hard"
    cognitive_level: str = "analysis"
    question_style: str = "conceptual"
    question_count: int = Field(default=5, ge=1, le=30)
    allow_trick_questions: bool = False
    require_explanations: bool = True


class GenerateRequest(BaseModel):
    page: PageContent
    profile: QuestionProfile


class QuizQuestion(BaseModel):
    id: str
    bloom_level: Optional[BloomLevel] = None
    concept: Optional[str] = None
    question: str
    options: list[str] = Field(min_length=2, max_length=6)
    correct_answer: int = Field(ge=0)
    explanation: Optional[str] = None


class QuizSource(BaseModel):
    url: Optional[str] = None
    page_title: Optional[str] = None
    extracted_at: Optional[str] = None


class Quiz(BaseModel):
    id: str
    title: str
    source: Optional[QuizSource] = None
    profile: Optional[QuestionProfile] = None
    concepts: list[str] = []
    questions: list[QuizQuestion]


class QuizResponse(BaseModel):
    quiz: Quiz
