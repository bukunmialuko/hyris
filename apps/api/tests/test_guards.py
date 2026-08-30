from app.agent.guards import BLOCK_MESSAGE, UNAVAILABLE_MESSAGE, moderate_quiz, moderate_text
from app.agent.tools.clean_page import ssrf_guard
from tests.conftest import fake_moderation


def test_ssrf_blocks_non_public():
    for bad in [
        "http://localhost:8000/admin",
        "http://127.0.0.1/x",
        "http://169.254.169.254/meta",
        "http://192.168.1.1/router",
        "ftp://example.com",
        "not a url",
    ]:
        assert ssrf_guard(bad), bad


def test_moderation_flags_and_passes():
    ok, _ = moderate_text("perfectly fine article", fake_moderation)
    assert ok
    ok, err = moderate_text("bad content FLAGME here", fake_moderation)
    assert not ok and err == BLOCK_MESSAGE


def test_moderation_fails_closed():
    def broken(_text):
        raise RuntimeError("api down")

    ok, err = moderate_text("anything", broken)
    assert not ok and err == UNAVAILABLE_MESSAGE


def test_quiz_moderation_drops_flagged():
    qs = [
        {"question": "fine?", "options": ["a", "b", "c", "d"], "explanation": ""},
        {"question": "FLAGME?", "options": ["a", "b", "c", "d"], "explanation": ""},
    ]
    kept, err = moderate_quiz(qs, fake_moderation)
    assert len(kept) == 1 and not err
    kept, err = moderate_quiz([qs[1]], fake_moderation)
    assert not kept and err == BLOCK_MESSAGE
