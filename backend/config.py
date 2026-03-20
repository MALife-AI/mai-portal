from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    vault_root: Path = Path("./vault")
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    vlm_model: str = "gpt-4o-mini"
    vlm_provider: str = "auto"  # "auto" | "anthropic" | "openai" | "claude_wrapper"
    claude_wrapper_url: str = "http://localhost:3000"  # claude-code-api-wrapper 서버
    ollama_base_url: str = "http://localhost:11434"  # Ollama 서버
    chroma_persist_dir: Path = Path("./data/chroma")
    sqlite_checkpoint_path: Path = Path("./data/checkpoints.db")
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
