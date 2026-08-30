"""API tests: start a run, poll to completion. Uses the fake graph stack."""

import asyncio

import httpx
import pytest

from app.main import app
from app.routers import quiz as quiz_router
from tests.conftest import FakeLLM, fake_moderation


@pytest.fixture
def fake_graph(fake_page, monkeypatch):
    from app.agent.graph import build_graph

    graph = build_graph(llm=FakeLLM(), moderation=fake_moderation)
    monkeypatch.setattr(quiz_router, "get_graph", lambda: graph)
    return graph


async def test_generate_and_poll(fake_graph):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/quiz/generate",
            json={"page_url": "https://example.org/attention",
                  "profile": {"question_count": 3, "difficulty": "medium"}},
        )
        assert r.status_code == 202
        run_id = r.json()["run_id"]

        for _ in range(100):
            status = (await client.get(f"/quiz/runs/{run_id}")).json()
            if status["status"] != "running":
                break
            await asyncio.sleep(0.05)
        assert status["status"] == "done"
        assert len(status["quiz"]["questions"]) == 3
        assert "plan_quiz" in status["steps"]


async def test_unknown_run_404(fake_graph):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/quiz/runs/nope")).status_code == 404


async def test_question_count_validated(fake_graph):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/quiz/generate",
            json={"page_url": "https://x.org", "profile": {"question_count": 40}},
        )
        assert r.status_code == 422  # hard cap enforced at the boundary
