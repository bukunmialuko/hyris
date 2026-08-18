from fastapi import APIRouter

from app.agents.orchestrator import run_quiz_pipeline
from app.schemas.quiz import GenerateRequest, QuizResponse

router = APIRouter()


@router.post("/generate", response_model=QuizResponse)
async def generate(req: GenerateRequest) -> QuizResponse:
    """Full pipeline: content → concepts → questions → critic → validated quiz."""
    return await run_quiz_pipeline(req.page, req.profile)
