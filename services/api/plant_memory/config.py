from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str | None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            return str(candidate)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_env_file(), env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://pm_app:pm_app@localhost:5432/plant_memory"
    database_admin_url: str = "postgresql+psycopg://pm_admin:pm_admin@localhost:5432/plant_memory"
    valkey_url: str | None = "redis://localhost:6379/0"

    storage_backend: str = "local"
    storage_local_root: str = ".data/storage"
    s3_bucket_originals: str = "plant-memory-originals"
    s3_bucket_derived: str = "plant-memory-derived"
    s3_bucket_reports: str = "plant-memory-reports"
    s3_bucket_assets: str = "plant-memory-assets"
    s3_endpoint_url: str | None = None
    aws_region: str = "us-east-1"

    queue_backend: str = "postgres"
    sqs_queue_url: str | None = None
    sqs_dlq_url: str | None = None

    auth_backend: str = "dev"
    auth_dev_secret: str = "change-me-dev-secret-at-least-32-chars-long"
    cognito_user_pool_id: str | None = None
    cognito_region: str | None = None
    cognito_client_id: str | None = None

    agent_jwt_secret: str = "change-me-agent-secret-at-least-32-chars-long"
    agent_jwt_issuer: str = "https://plant-memory.local/api"
    agent_jwt_audience: str = "plant-memory-agent"
    agent_base_url: str = "http://localhost:2000"
    # gateway = in-process agent that calls the model gateway and the same tools.
    # eve = external eve runtime. local = fixed tool order with no model.
    # When the gateway has no API key, a gateway run says so and follows the fixed checklist.
    agent_backend: str = "gateway"
    agent_fallback_to_local: bool = True
    api_internal_base_url: str = "http://localhost:8000"

    ai_gateway_api_key: str | None = None
    ai_gateway_base_url: str = "https://ai-gateway.vercel.sh/v1"
    model_fast: str = "anthropic/claude-haiku-5.5"
    model_reasoning: str = "anthropic/claude-sonnet-5.5"
    model_escalation: str = "anthropic/claude-opus-5.5"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_backend: str = "fastembed"
    embedding_dim: int = 384

    run_max_concurrent_llm_calls: int = 3
    env_max_active_llm_calls: int = 8
    run_max_tool_invocations: int = 20
    run_max_clarification_cycles: int = 2
    run_active_deadline_seconds: int = 600
    run_max_cost_usd: float = 1.5
    run_max_output_tokens: int = 40000
    env_max_concurrent_runs: int = 3
    monthly_model_budget_usd: float = 200.0

    max_files_per_project: int = 50
    max_pdf_pages_per_project: int = 300
    max_file_bytes: int = 25 * 1024 * 1024

    search_lexical_candidates: int = 20
    search_vector_candidates: int = 20
    search_passages_to_model: int = 12
    trace_default_depth: int = 3
    trace_max_depth: int = 6
    price_max_age_days: int = 365

    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "plant-memory-api"
    log_level: str = "INFO"
    environment: str = Field(default="development")


@lru_cache
def get_settings() -> Settings:
    return Settings()
