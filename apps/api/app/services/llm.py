"""LLM provider factory — the model is replaceable (OpenAI now; add providers here)."""

from app.config import get_settings


def get_llm():
    s = get_settings()
    if s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=s.llm_model, api_key=s.openai_api_key or None)
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider}")
