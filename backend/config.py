from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    vault_root: Path = Path("./vault")
    openai_api_key: str = ""
    vlm_model: str = "qwen3-14b"
    vlm_provider: str = "llama_server"  # "llama_server" | "claude_wrapper"
    claude_wrapper_url: str = "http://localhost:3000"  # claude-code-api-wrapper 서버
    llama_server_url: str = "http://localhost:8801/v1"  # llama-server OpenAI endpoint
    # Smart Router: 질문 복잡도에 따라 다른 서버로 라우팅
    llama_server_light: str = "http://localhost:8801/v1"   # 간단한 질문 (4B)
    llama_server_heavy: str = ""                           # 복잡한 질문 (9B+ GPU 서버, 비어있으면 light와 동일)
    smart_routing: bool = False                            # True면 자동 라우팅
    graph_extract_model: str = ""                            # 그래프 추출 전용 모델 (비어있으면 vlm_model 사용)
    chroma_persist_dir: Path = Path("./data/chroma")
    sqlite_checkpoint_path: Path = Path("./data/checkpoints.db")
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
