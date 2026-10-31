"""Environment-backed settings (see .env.example / PRD section 10.3)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    # Cosine floor for serving a cached response. Held inside the PRD's
    # 0.85-0.90 band: below it the cache answers questions it was not asked,
    # above it paraphrases stop matching and the cache stops earning its keep.
    # Distinct from the IR's min_semantic_similarity (0.95), which is the
    # output-invariance gate, not an admission threshold.
    semantic_cache_similarity_threshold: float = Field(default=0.88, ge=0.85, le=0.90)
    semantic_cache_ttl_seconds: int = 3600

    # Deployment ceiling: a workflow's budget_limit_usd is clamped to this.
    max_budget_per_workflow_usd: float = Field(default=0.50, gt=0.0)
    max_concurrent_tasks: int = 8

    llm_offline_mode: bool = True
    telemetry_tick_ms: int = 100
    workflows_dir: Path = REPO_ROOT / "workflows"


@lru_cache
def get_settings() -> Settings:
    return Settings()
