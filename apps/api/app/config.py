"""Central settings — no magic numbers in node code."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    openai_api_key: str = ""
    llm_provider: str = "openai"
    llm_model: str = "gpt-5-mini"

    # persistence (Postgres backends wired when DATABASE_URL is set)
    database_url: str = ""

    # pipeline limits
    hard_cap: int = 20                 # absolute max questions per quiz
    max_words: int = 6000              # article words reaching the LLM
    notable_gap: float = 0.7           # flag user when delivered < 70% of requested
    max_repair_rounds: int = 2
    max_gen_retries: int = 2

    # planning thresholds
    mastered_at: float = 0.8
    weak_at: float = 0.4
    min_seen: int = 2
    mastery_alpha: float = 0.3         # EMA weight of the newest attempt


@lru_cache
def get_settings() -> Settings:
    return Settings()
