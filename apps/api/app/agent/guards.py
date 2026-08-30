"""Safety middleware: input and output moderation. All checks FAIL CLOSED."""

from typing import Callable

BLOCK_MESSAGE = "This page isn't suitable for quiz generation."
UNAVAILABLE_MESSAGE = "Safety check unavailable, please try again."
_CHUNK = 30000  # chars per moderation request

# Moderation callable signature: (text) -> flagged: bool. May raise; we contain it here.
ModerationFn = Callable[[str], bool]


def default_moderation() -> ModerationFn:
    """OpenAI omni-moderation, created lazily so tests never need a key."""
    from openai import OpenAI

    from app.config import get_settings

    client = OpenAI(api_key=get_settings().openai_api_key or None)

    def moderate(text: str) -> bool:
        res = client.moderations.create(model="omni-moderation-latest", input=text)
        return any(r.flagged for r in res.results)

    return moderate


def moderate_text(text: str, moderation: ModerationFn) -> tuple[bool, str]:
    """(ok, error). Fail-closed: an API failure blocks."""
    try:
        for i in range(0, max(len(text), 1), _CHUNK):
            if moderation(text[i : i + _CHUNK]):
                return False, BLOCK_MESSAGE
        return True, ""
    except Exception:  # noqa: BLE001 — fail closed
        return False, UNAVAILABLE_MESSAGE


def moderate_quiz(questions: list[dict], moderation: ModerationFn) -> tuple[list[dict], str]:
    """(kept_questions, error). Drops flagged questions; error set when the check
    failed (fail closed) or when nothing survives."""
    kept = []
    for q in questions:
        blob = " ".join([q.get("question", ""), *q.get("options", []), q.get("explanation", "")])
        ok, err = moderate_text(blob, moderation)
        if err == UNAVAILABLE_MESSAGE:
            return [], err
        if ok:
            kept.append(q)
    if not kept:
        return [], BLOCK_MESSAGE
    return kept, ""
