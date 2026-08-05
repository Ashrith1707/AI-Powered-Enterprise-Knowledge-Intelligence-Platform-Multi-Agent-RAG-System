"""Central application configuration loaded from environment / .env file."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Enterprise Knowledge Intelligence Platform"
    app_env: str = "development"

    # Falls back to a local SQLite file so the project runs without PostgreSQL.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'knowledge.db'}"

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "models/text-embedding-004"

    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    storage_dir: Path = BACKEND_DIR / "storage"
    vector_index_dir: Path = BACKEND_DIR / "vector_index"
    reports_dir: Path = BACKEND_DIR / "generated_reports"

    max_upload_mb: int = 50
    allowed_extensions: tuple = (".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg")

    chunk_size: int = 1000
    chunk_overlap: int = 150
    retriever_top_k: int = 8
    reranker_top_k: int = 4

    # --- auth / security ---
    secret_key: str = "dev-secret-change-me-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    refresh_token_days_remember: int = 30
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    # in-memory rate limits (requests per minute per client IP)
    rate_limit_auth: int = 30
    rate_limit_ask: int = 20
    slow_request_ms: int = 3000


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
settings.vector_index_dir.mkdir(parents=True, exist_ok=True)
settings.reports_dir.mkdir(parents=True, exist_ok=True)
