"""LLM provider factory — the model is replaceable (OpenAI now; add providers here)."""

from pydantic import SecretStr

from app.config import get_settings


def get_llm():
    s = get_settings()
    if s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        key = SecretStr(s.openai_api_key) if s.openai_api_key else None
        return ChatOpenAI(model=s.llm_model, api_key=key)
    raise ValueError(f"Unknown LLM_PROVIDER: {s.llm_provider}")
