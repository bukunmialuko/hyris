from app.agent.nodes import adjust_scope, plan_quiz

CONCEPTS = [
    {"name": "self-attention", "salience": 0.95, "supporting_span": "..."},
    {"name": "multi-head attention", "salience": 0.8, "supporting_span": "..."},
    {"name": "positional encoding", "salience": 0.6, "supporting_span": "..."},
]
CTX = {
    "mastered_concepts": ["self-attention"],
    "weak_concepts": ["multi-head attention"],
    "recent_question_hashes": [],
}


def test_weak_first_and_unique_slots():
    plan = plan_quiz(CONCEPTS, CTX, final_count=6, difficulty="hard")
    assert plan[0]["concept"] == "multi-head attention"
    assert len(plan) == 6
    assert len({(s["concept"], s["bloom_level"]) for s in plan}) == 6


def test_mastered_bumped_harder():
    plan = plan_quiz(CONCEPTS, CTX, final_count=3, difficulty="hard")
    sa = next(s for s in plan if s["concept"] == "self-attention")
    assert sa["bloom_level"] == "evaluate"  # base analyse, bumped one up


def test_variants_marked():
    plan = plan_quiz(CONCEPTS, CTX, final_count=6, difficulty="hard")
    assert any(s["is_variant"] for s in plan[3:])


def test_adjust_scope_min_rule_and_note():
    out = adjust_scope(requested=20, max_supportable=4)
    assert out["final_count"] == 4 and out["note"]
    out = adjust_scope(requested=5, max_supportable=4)  # small gap: silent
    assert out["final_count"] == 4 and not out["note"]
    out = adjust_scope(requested=5, max_supportable=0)
    assert out["final_count"] == 0 and out["error"]


def test_hard_cap():
    out = adjust_scope(requested=20, max_supportable=50)
    assert out["final_count"] == 20
