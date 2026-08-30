from app.agent.nodes import schema_gate
from app.agent.tools.memory import qhash

SLOTS = [
    {"slot_id": 0, "concept": "a", "bloom_level": "apply", "is_variant": False},
    {"slot_id": 1, "concept": "b", "bloom_level": "apply", "is_variant": False},
]


def q(sid, question="Q?", options=None, correct=0):
    return {
        "slot_id": sid,
        "question": question,
        "options": options or [f"o{i}{sid}" for i in range(4)],
        "correct_answer": correct,
        "explanation": "",
    }


def test_valid_pass():
    valid, missing, _ = schema_gate([q(0, "One?"), q(1, "Two?")], SLOTS, [])
    assert len(valid) == 2 and not missing


def test_bad_index_and_dup_options_rejected():
    bad = [q(0, "One?", correct=7), q(1, "Two?", options=["x", "x", "y", "z"])]
    valid, missing, feedback = schema_gate(bad, SLOTS, [])
    assert not valid and len(missing) == 2 and "invalid" in feedback


def test_recent_repeat_blocked():
    question = "What is attention?"
    valid, missing, _ = schema_gate([q(0, question)], SLOTS[:1], [qhash(question)])
    assert not valid and missing


def test_missing_slot_reported():
    valid, missing, _ = schema_gate([q(0, "One?")], SLOTS, [])
    assert len(valid) == 1 and missing[0]["slot_id"] == 1
