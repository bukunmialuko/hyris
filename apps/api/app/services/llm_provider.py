"""LLM provider abstraction — model is replaceable (Anthropic, OpenAI, local...)."""

import os
from typing import Protocol


class LLMProvider(Protocol):
    async def complete_json(self, system: str, user: str, schema: dict) -> dict: ...


class AnthropicProvider:
    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.AsyncAnthropic()
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-5")

    async def complete_json(self, system: str, user: str, schema: dict) -> dict:
        # TODO: tool-use / structured output call returning validated JSON
        raise NotImplementedError


def get_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "anthropic")
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {name}")
