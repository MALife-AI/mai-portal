from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    vault_root: Path = Path("./vault")
    openai_api_key: str = ""
    vlm_model: str = "gpt-4o-mini"
    chroma_persist_dir: Path = Path("./data/chroma")
    sqlite_checkpoint_path: Path = Path("./data/checkpoints.db")
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
