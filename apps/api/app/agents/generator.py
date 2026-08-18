"""Concept extraction + question generation (LLM calls via the provider layer)."""

from app.schemas.quiz import PageContent, QuestionProfile, QuizQuestion
from app.services.llm_provider import get_provider


async def extract_concepts(page: PageContent) -> list[str]:
    """Identify key concepts, claims and relationships worth testing."""
    provider = get_provider()
    # TODO: prompt for structured concept extraction
    raise NotImplementedError


async def generate_questions(
    page: PageContent,
    profile: QuestionProfile,
    concepts: list[str],
    feedback: str | None = None,
) -> list[QuizQuestion]:
    """Generate MCQs at the profile's Bloom level; structured JSON output only."""
    provider = get_provider()
    # TODO: prompt with profile → Bloom mapping; include critic feedback on retries
    raise NotImplementedError
