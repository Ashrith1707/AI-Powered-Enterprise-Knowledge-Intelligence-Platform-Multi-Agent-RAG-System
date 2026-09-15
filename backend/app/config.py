"""Application configuration.

All settings are read from environment variables (and an optional `.env` file).
Secrets are NEVER hard-coded. See `.env.example` for the full list.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "KnowledgeIQ"
    app_env: str = Field(default="development", description="development | production")
    debug: bool = False
    api_prefix: str = "/api"

    # --- Database ---
    # SQLite for development, PostgreSQL for production.
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'data' / 'knowledgeiq.db'}",
        description="SQLAlchemy database URL",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True

    # --- Security ---
    secret_key: str = Field(default="change-me-in-production", description="JWT signing key")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated list of allowed CORS origins",
    )
    rate_limit_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10

    # --- Uploads ---
    max_upload_mb: int = 25
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    allowed_extensions: str = "pdf,docx,txt,md,png,jpg,jpeg,tiff"

    # --- Gemini / AI -------------------------------------------------------
    # NOTE: `text-embedding-004` is DEPRECATED and returns
    # "404 models/text-embedding-004 is not found for API version v1beta".
    # The modern replacement is `gemini-embedding-001`, used via the new
    # `google-genai` SDK (the legacy `google.generativeai` package is not used
    # anywhere in this codebase).
    gemini_api_key: str = Field(default="", description="Set via GEMINI_API_KEY env var")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Generation model")
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001",
        description="Embedding model (replaces deprecated text-embedding-004)",
    )
    embedding_dimensions: int = 768
    # auto | gemini | local  (local = deterministic offline fallback)
    embedding_provider: str = "auto"
    # auto | gemini | mock    (mock = deterministic offline extractive answerer)
    llm_provider: str = "auto"
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 2048
    llm_temperature: float = 0.2

    # --- OCR ---
    tesseract_cmd: str = Field(default="", description="Optional path to tesseract binary")

    # --- RAG tuning ---
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 8
    rerank_top_n: int = 5
    max_evidence_chars: int = 6000
    hybrid_rrf_k: int = 60
    dedup_jaccard_threshold: float = 0.80
    # Absolute relevance floor (reranker v2 scores are absolute, not normalized).
    # Chunks below this never become evidence — enables honest refusal for
    # questions the knowledge base cannot answer.
    min_relevance_score: float = 0.30

    # --- Memory ---
    memory_recent_messages: int = 6
    memory_max_chars: int = 2400
    memory_summarize_every: int = 10

    # --- Agents ---
    agent_timeout_default: float = 20.0
    agent_timeout_generator: float = 90.0
    verification_use_llm: bool = False
    reranker_use_llm: bool = False  # keep local reranking by default (cost control)
    max_regeneration_attempts: int = 1

    # --- Storage ---
    vector_dir: Path = BASE_DIR / "data" / "vectors"
    data_dir: Path = BASE_DIR / "data"

    @field_validator("upload_dir", "vector_dir", "data_dir", mode="after")
    @classmethod
    def _ensure_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    # --- Convenience accessors ---
    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",")}

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate_environment(self) -> List[str]:
        """Return a list of configuration problems (fail fast at startup)."""
        problems: List[str] = []
        if self.is_production:
            if self.database_url.startswith("sqlite"):
                problems.append(
                    "Production must not use SQLite. Set DATABASE_URL to a PostgreSQL URL."
                )
            if self.secret_key in ("", "change-me-in-production"):
                problems.append("SECRET_KEY must be set to a strong value in production.")
            if not self.gemini_api_key:
                problems.append("GEMINI_API_KEY is not set; AI features will run in mock mode.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
