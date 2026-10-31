"""Environment-backed settings (see .env.example / PRD section 10.3)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    port: int = 8000
    environment: str = "development"
    cors_origin: str = "http://localhost:3000"

    litellm_proxy_url: str = "http://localhost:4000"
    local_ollama_url: str = "http://localhost:11434"
    openai_api_key: str = "sk-placeholder-demo-key"
    tavily_api_key: str = "tvly-placeholder-demo-key"

    redis_host: str = "localhost"
    redis_port: int = 6379
    semantic_cache_similarity_threshold: float = 0.88
    semantic_cache_ttl_seconds: int = 3600

    max_budget_per_workflow_usd: float = 0.50
    max_concurrent_tasks: int = 8

    llm_offline_mode: bool = True
    telemetry_tick_ms: int = 100
    workflows_dir: Path = REPO_ROOT / "workflows"


@lru_cache
def get_settings() -> Settings:
    return Settings()
