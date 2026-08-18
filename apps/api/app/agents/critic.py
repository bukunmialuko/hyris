"""Question critic: factual correctness, ambiguity, distractor quality, coverage."""

from pydantic import BaseModel

from app.schemas.quiz import PageContent, QuizQuestion


class CritiqueReport(BaseModel):
    score: float  # 0..1
    feedback: str


async def critique_questions(page: PageContent, questions: list[QuizQuestion]) -> CritiqueReport:
    # TODO: reasoning-model pass; check each question against source text
    raise NotImplementedError
