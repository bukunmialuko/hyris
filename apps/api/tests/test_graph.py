"""End-to-end graph tests with fake LLM, fake moderation, and a fake page."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.agent.graph import build_graph
from tests.conftest import FakeLLM, fake_moderation

INPUTS = {
    "page_url": "https://example.org/attention",
    "user_id": "test_user",
    "requested": 3,
    "difficulty": "medium",
}


def run(graph, inputs=INPUTS, thread="t1"):
    final = {}
    for update in graph.stream(inputs, {"configurable": {"thread_id": thread}},
                               stream_mode="updates"):
        for node, out in update.items():
            final.setdefault("_steps", []).append(node)
            final.update(out or {})
    return final


def test_happy_path(fake_llm, fake_page):
    store = InMemoryStore()
    graph = build_graph(MemorySaver(), store, llm=fake_llm, moderation=fake_moderation)
    final = run(graph)
    quiz = final["quiz"]
    assert len(quiz["questions"]) == 3
    assert quiz["title"] == "Attention Is All You Need"
    # hallucinated concept was dropped before planning
    assert all("hallucinated" not in q["question"] for q in quiz["questions"])
    # parallel fan-out ran both branches, guards ran on both sides
    for node in ["load_memory", "clean_page", "guard_input", "guard_output", "write_memory"]:
        assert node in final["_steps"]
    # memory loop closed
    assert len(store.search(("users", "test_user", "quiz_history"))) == 1


def test_schema_retry_then_success(fake_page):
    llm = FakeLLM({"bad_slot": 1})  # first attempt for slot 1 is malformed
    graph = build_graph(llm=llm, moderation=fake_moderation)
    final = run(graph)
    assert len(final["quiz"]["questions"]) == 3
    assert final["_steps"].count("generate_questions") >= 2  # retried


def test_critic_repair_loop(fake_page):
    llm = FakeLLM({"critic_fails": {0}})  # critic always fails slot 0
    graph = build_graph(llm=llm, moderation=fake_moderation)
    final = run(graph)
    # after max rounds the failing slot is dropped, the rest ship
    assert final["quiz"]["questions"]
    assert all(q["slot_id"] != 0 for q in final["quiz"]["questions"])
    assert final["_steps"].count("critique_questions") == 2  # bounded loop


def test_fetch_failure_ends_gracefully(fake_llm, monkeypatch):
    from app.agent.tools import clean_page as cp

    monkeypatch.setattr(cp, "ssrf_guard", lambda url: "")
    monkeypatch.setattr(cp.trafilatura, "fetch_url", lambda url: None)
    graph = build_graph(llm=fake_llm, moderation=fake_moderation)
    final = run(graph)
    assert final["quiz"] == {} and "Could not fetch" in final["error"]
    assert "end_gracefully" in final["_steps"]
    assert "analyze_page" not in final["_steps"]  # no LLM call after failure


def test_ssrf_blocked(fake_llm):
    graph = build_graph(llm=fake_llm, moderation=fake_moderation)
    final = run(graph, {**INPUTS, "page_url": "http://127.0.0.1/secret"})
    assert final["quiz"] == {} and "cannot be quizzed" in final["error"]


def test_unsafe_page_refused(fake_llm, fake_page, monkeypatch):
    from app.agent.tools import clean_page as cp

    monkeypatch.setattr(cp.trafilatura, "extract", lambda *a, **k: "awful FLAGME content")
    graph = build_graph(llm=fake_llm, moderation=fake_moderation)
    final = run(graph)
    assert final["quiz"] == {}
    assert "guard_input" in final["_steps"] and "analyze_page" not in final["_steps"]


def test_moderation_outage_fails_closed(fake_llm, fake_page):
    def broken(_text):
        raise RuntimeError("moderation down")

    graph = build_graph(llm=fake_llm, moderation=broken)
    final = run(graph)
    assert final["quiz"] == {} and "Safety check unavailable" in final["error"]
