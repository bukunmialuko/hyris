"""The agentic workflow: understand → generate → critique → (regenerate) → return.

Plain Python orchestration per the architecture decision — no LangGraph until needed.
"""

import uuid

from app.agents.critic import critique_questions
from app.agents.generator import extract_concepts, generate_questions
from app.schemas.quiz import PageContent, QuestionProfile, Quiz, QuizResponse, QuizSource

MAX_REGENERATION_ROUNDS = 2
QUALITY_THRESHOLD = 0.7


async def run_quiz_pipeline(page: PageContent, profile: QuestionProfile) -> QuizResponse:
    concepts = await extract_concepts(page)

    questions = await generate_questions(page, profile, concepts)

    for _ in range(MAX_REGENERATION_ROUNDS):
        report = await critique_questions(page, questions)
        if report.score >= QUALITY_THRESHOLD:
            break
        questions = await generate_questions(page, profile, concepts, feedback=report.feedback)

    quiz = Quiz(
        id=f"quiz_{uuid.uuid4().hex[:12]}",
        title=page.title,
        source=QuizSource(url=page.url, page_title=page.title),
        profile=profile,
        concepts=concepts,
        questions=questions,
    )
    return QuizResponse(quiz=quiz)
