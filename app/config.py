"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe config with .env file support.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Global application settings."""

    # --- LLM Configuration ---
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TEMPERATURE: float = 0.0

    # --- Database ---
    DEMO_DB_PATH: str = "./data/demo_ecommerce.db"

    # --- RAG ---
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    SCHEMA_TOP_K: int = 5
    FEWSHOT_TOP_K: int = 3

    # --- Production Guardrails ---
    MAX_CORRECTION_RETRIES: int = 3
    QUERY_TIMEOUT_SECONDS: int = 10
    MAX_RESULT_ROWS: int = 100

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Paths ---
    BASE_DIR: str = str(Path(__file__).resolve().parent.parent)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "allow",
    }


settings = Settings()
