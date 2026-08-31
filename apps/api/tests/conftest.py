"""Test doubles: a deterministic fake LLM, fake moderation, and a fake fetched page.

No test in this suite touches the network or a database, or needs an API key.
"""

import os
import re

import pytest

# Blank DATABASE_URL before any Settings() is built. An env var set to the empty string outranks a
# .env value in pydantic-settings, so a developer's local database cannot leak into the suite.
os.environ["DATABASE_URL"] = ""

ARTICLE = (
    "The transformer replaces recurrence with self-attention, letting every token attend to "
    "every other token in one step. Multi-head attention runs several attention functions in "
    "parallel so different heads can focus on different relationships. Positional encodings "
    "are added to the embeddings so word order still matters."
)


class FakeStructured:
    def __init__(self, schema, behavior):
        self.schema = schema
        self.behavior = behavior

    def invoke(self, messages):
        name = getattr(self.schema, "__name__", str(self.schema))
        user = messages[-1][1]
        if name == "PageAnalysis":
            return {
                "concepts": [
                    {"name": "self-attention", "salience": 0.9,
                     "supporting_span": "replaces recurrence with self-attention"},
                    {"name": "multi-head attention", "salience": 0.8,
                     "supporting_span": "runs several attention functions in parallel"},
                    {"name": "positional encodings", "salience": 0.6,
                     "supporting_span": "added to the embeddings so word order still matters"},
                    {"name": "hallucinated", "salience": 0.5,
                     "supporting_span": "quantum flux capacitors"},  # must be dropped
                ],
                "sufficiency_score": 0.9,
                "max_supportable_questions": 8,
            }
        if name == "QuestionBatch":
            slots = re.findall(r'slot_id (\d+): "([^"]+)" at (\w+)', user)
            qs = []
            for sid, concept, level in slots:
                sid = int(sid)
                if self.behavior.get("bad_slot") == sid and not self.behavior.get("repaired"):
                    qs.append({"slot_id": sid, "question": f"Broken {sid}?",
                               "options": ["a", "a", "c", "d"], "correct_answer": 9,
                               "explanation": ""})
                else:
                    qs.append({"slot_id": sid,
                               "question": f"What does {concept} do ({level}, slot {sid})?",
                               "options": [f"right-{sid}", f"w1-{sid}", f"w2-{sid}", f"w3-{sid}"],
                               "correct_answer": 0, "explanation": "Stated in the article."})
            if self.behavior.get("bad_slot") is not None and "Fix:" in user:
                self.behavior["repaired"] = True
            return {"questions": qs}
        if name == "VerdictBatch":
            sids = [int(m) for m in re.findall(r"slot_id (\d+):", user)]
            fail = self.behavior.get("critic_fails", set())
            return {"verdicts": [
                {"slot_id": sid, "passed": sid not in fail,
                 "reason": "ok" if sid not in fail else "wrong answer key"}
                for sid in sids]}
        raise AssertionError(f"unexpected schema {name}")


class FakeLLM:
    def __init__(self, behavior=None):
        self.behavior = behavior or {}

    def with_structured_output(self, schema):
        return FakeStructured(schema, self.behavior)


def fake_moderation(text: str) -> bool:
    return "FLAGME" in text


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_page(monkeypatch):
    """Make clean_page see a fixed article without any network."""
    from app.agent.tools import clean_page as cp

    class Meta:
        title = "Attention Is All You Need"

    monkeypatch.setattr(cp, "ssrf_guard", lambda url: "")
    monkeypatch.setattr(cp.trafilatura, "fetch_url", lambda url: "<html>x</html>")
    monkeypatch.setattr(cp.trafilatura, "extract", lambda *a, **k: ARTICLE)
    monkeypatch.setattr(cp.trafilatura, "extract_metadata", lambda html: Meta())
    return ARTICLE
