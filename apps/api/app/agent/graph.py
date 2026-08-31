"""Graph wiring — the reference implementation of the design's agent graph.

build_graph() takes its backends as arguments (dependency injection): tests pass
MemorySaver/InMemoryStore and a fake LLM; the API passes the PostgresStore its lifespan opened
(app/services/persistence.py). build_graph() opens nothing and never reads DATABASE_URL, so an
unconfigured caller always gets an isolated in-memory store.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from app.agent import guards, nodes
from app.agent.state import QuizState
from app.agent.tools import memory as memory_tools
from app.agent.tools.clean_page import clean_page as clean_page_tool
from app.config import get_settings


def build_graph(checkpointer=None, store=None, llm=None, moderation=None):
    """Compile the quiz agent graph. Defaults are in-memory backends and the
    configured OpenAI model, created lazily so imports stay side-effect free."""
    s = get_settings()
    checkpointer = checkpointer or MemorySaver()
    store = store or InMemoryStore()
    if llm is None:
        from app.services.llm import get_llm

        llm = get_llm()
    if moderation is None:
        moderation = guards.default_moderation()

    # ---------------- nodes (closures over the injected dependencies)

    def load_memory(state: QuizState) -> QuizState:
        return {
            "learner_context": memory_tools.load_learner_context(
                store, state["user_id"], state["page_url"]
            )
        }

    def clean_page(state: QuizState) -> QuizState:
        r = clean_page_tool(state["page_url"])
        if not r.ok:
            return {"error": r.error}
        return {"clean_text": r.clean_text, "title": r.title, "truncated": r.truncated}

    def guard_input(state: QuizState) -> QuizState:
        ok, err = guards.moderate_text(state["clean_text"], moderation)
        return {} if ok else {"error": err}

    def analyze_page(state: QuizState) -> QuizState:
        return nodes.analyze_page(llm, state["clean_text"], state["title"], state["requested"])

    def adjust_scope(state: QuizState) -> QuizState:
        return nodes.adjust_scope(state["requested"], state["max_supportable"])

    def plan_quiz(state: QuizState) -> QuizState:
        blueprint = nodes.plan_quiz(
            state["concepts"], state["learner_context"], state["final_count"], state["difficulty"]
        )
        return {
            "blueprint": blueprint,
            "pending_slots": blueprint,
            "questions": [],
            "gen_retries": 0,
            "round": 0,
            "feedback": "",
        }

    def generate_questions(state: QuizState) -> QuizState:
        new = nodes.generate_questions(
            llm, state["clean_text"], state["pending_slots"], state.get("feedback", "")
        )
        return {"questions": state["questions"] + new}

    def schema_gate(state: QuizState) -> QuizState:
        valid, missing, feedback = nodes.schema_gate(
            state["questions"], state["blueprint"], state["learner_context"]["recent_question_hashes"]
        )
        return {
            "questions": valid,
            "pending_slots": missing,
            "gen_retries": state["gen_retries"] + (1 if missing else 0),
            "feedback": feedback,
        }

    def critique_questions(state: QuizState) -> QuizState:
        res = nodes.critique_questions(llm, state["clean_text"], state["questions"])
        failed = res["failed_slot_ids"]
        return {
            "questions": [q for q in state["questions"] if q["slot_id"] not in failed],
            "pending_slots": [b for b in state["blueprint"] if b["slot_id"] in failed],
            "round": state["round"] + 1,
            "gen_retries": 0,
            "feedback": res["feedback"],
        }

    def finalize_quiz(state: QuizState) -> QuizState:
        return {
            "quiz": nodes.finalize_quiz(
                state["title"], state.get("note", ""), state.get("truncated", False), state["questions"]
            )
        }

    def guard_output(state: QuizState) -> QuizState:
        kept, err = guards.moderate_quiz(state["quiz"]["questions"], moderation)
        if err:
            return {"error": err}
        return {"quiz": {**state["quiz"], "questions": kept}}

    def write_memory(state: QuizState) -> QuizState:
        memory_tools.record_quiz(store, state["user_id"], state["page_url"], state["quiz"])
        return {}

    def end_gracefully(state: QuizState) -> QuizState:
        return {"quiz": {}}

    # ---------------- routing

    def ok_or_fail(state: QuizState) -> str:
        return "fail" if state.get("error") else "ok"

    def after_gate(state: QuizState) -> str:
        if state["pending_slots"] and state["gen_retries"] <= s.max_gen_retries:
            return "retry"
        return "critique"

    def after_critique(state: QuizState) -> str:
        if state["pending_slots"] and state["round"] < s.max_repair_rounds:
            return "repair"
        return "done"

    # ---------------- wiring

    b = StateGraph(QuizState)
    for name, fn in [
        ("load_memory", load_memory),
        ("clean_page", clean_page),
        ("guard_input", guard_input),
        ("analyze_page", analyze_page),
        ("adjust_scope", adjust_scope),
        ("plan_quiz", plan_quiz),
        ("generate_questions", generate_questions),
        ("schema_gate", schema_gate),
        ("critique_questions", critique_questions),
        ("finalize_quiz", finalize_quiz),
        ("guard_output", guard_output),
        ("write_memory", write_memory),
        ("end_gracefully", end_gracefully),
    ]:
        b.add_node(name, fn)

    b.add_edge(START, "load_memory")  # parallel fan-out
    b.add_edge(START, "clean_page")
    b.add_conditional_edges("clean_page", ok_or_fail, {"ok": "guard_input", "fail": "end_gracefully"})
    b.add_conditional_edges("guard_input", ok_or_fail, {"ok": "analyze_page", "fail": "end_gracefully"})
    b.add_conditional_edges("analyze_page", ok_or_fail, {"ok": "adjust_scope", "fail": "end_gracefully"})
    b.add_conditional_edges("adjust_scope", ok_or_fail, {"ok": "plan_quiz", "fail": "end_gracefully"})
    b.add_edge(["load_memory", "adjust_scope"], "plan_quiz")  # fan-in: wait for BOTH branches
    b.add_edge("plan_quiz", "generate_questions")
    b.add_edge("generate_questions", "schema_gate")
    b.add_conditional_edges(
        "schema_gate", after_gate, {"retry": "generate_questions", "critique": "critique_questions"}
    )
    b.add_conditional_edges(
        "critique_questions", after_critique, {"repair": "generate_questions", "done": "finalize_quiz"}
    )
    b.add_edge("finalize_quiz", "guard_output")
    b.add_conditional_edges("guard_output", ok_or_fail, {"ok": "write_memory", "fail": "end_gracefully"})
    b.add_edge("write_memory", END)
    b.add_edge("end_gracefully", END)

    return b.compile(checkpointer=checkpointer, store=store)
