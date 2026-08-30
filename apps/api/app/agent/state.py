"""Typed graph state — the single shared structure every node reads and writes.

The parallel branches write different keys, so the fan-in needs no reducers.
"""

from typing import Literal, TypedDict

BloomLevel = Literal["remember", "understand", "apply", "analyse", "evaluate", "create"]
BLOOM_LADDER: list[str] = ["remember", "understand", "apply", "analyse", "evaluate", "create"]

BASE_BLOOM: dict[str, str] = {
    "easy": "understand",
    "medium": "apply",
    "hard": "analyse",
    "expert": "evaluate",
}


class Concept(TypedDict):
    name: str
    salience: float        # 0..1, how central to the article
    supporting_span: str   # verbatim quote grounding the concept


class LearnerContext(TypedDict):
    mastered_concepts: list[str]
    weak_concepts: list[str]
    recent_question_hashes: list[str]


class Slot(TypedDict):
    slot_id: int
    concept: str
    bloom_level: str
    is_variant: bool


class QuizQuestion(TypedDict):
    slot_id: int
    question: str
    options: list[str]     # exactly 4
    correct_answer: int    # index into options
    explanation: str


class QuizState(TypedDict, total=False):
    # input
    page_url: str
    user_id: str
    requested: int
    difficulty: str
    # branch A — memory
    learner_context: LearnerContext
    # branch B — page
    clean_text: str
    title: str
    truncated: bool
    concepts: list[Concept]
    sufficiency: float
    max_supportable: int
    final_count: int
    note: str
    # planning + generation
    blueprint: list[Slot]
    pending_slots: list[Slot]
    feedback: str
    questions: list[QuizQuestion]
    gen_retries: int
    round: int
    # output
    quiz: dict
    error: str
