"""Quiz endpoints: start a run, stream its progress (SSE), poll its result."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.quiz import GenerateRequest, Quiz, RunCreated, RunStatus
from app.services.runs import registry

router = APIRouter()

_graph = None


def get_graph():
    """Lazy singleton so importing the app never needs an API key."""
    global _graph
    if _graph is None:
        from app.agent.graph import build_graph

        _graph = build_graph()
    return _graph


@router.post("/generate", response_model=RunCreated, status_code=202)
async def generate(req: GenerateRequest) -> RunCreated:
    run = await registry.start(
        get_graph(),
        {
            "page_url": req.page_url,
            "user_id": req.user_id,
            "requested": req.profile.question_count,
            "difficulty": req.profile.difficulty,
        },
    )
    return RunCreated(
        run_id=run.run_id,
        events_url=f"/quiz/runs/{run.run_id}/events",
        result_url=f"/quiz/runs/{run.run_id}",
    )


@router.get("/runs/{run_id}", response_model=RunStatus)
async def run_status(run_id: str) -> RunStatus:
    """Polling endpoint — Postman-friendly: call until status is done or failed."""
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run_id")
    return RunStatus(
        run_id=run.run_id,
        status=run.status,
        steps=run.steps,
        quiz=Quiz.model_validate(run.quiz) if run.quiz else None,
        error=run.error,
    )


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """SSE stream: step events as nodes complete, then the quiz (or error), then end."""
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run_id")

    async def stream():
        # replay steps already completed, then follow live
        for node in run.steps:
            yield f"data: {json.dumps({'event': 'step', 'node': node})}\n\n"
        if run.status == "done":
            yield f"data: {json.dumps({'event': 'quiz', 'quiz': run.quiz})}\n\n"
            yield f"data: {json.dumps({'event': 'end'})}\n\n"
            return
        if run.status == "failed":
            yield f"data: {json.dumps({'event': 'error', 'error': run.error})}\n\n"
            yield f"data: {json.dumps({'event': 'end'})}\n\n"
            return
        while True:
            msg = await run.queue.get()
            yield f"data: {json.dumps(msg)}\n\n"
            if msg.get("event") == "end":
                return

    return StreamingResponse(stream(), media_type="text/event-stream")
