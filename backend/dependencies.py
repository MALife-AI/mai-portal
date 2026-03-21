from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException

from backend.core.iam import IAMEngine
from backend.config import settings

_iam = IAMEngine(settings.vault_root / "iam.yaml")

# API 키 저장소
_API_KEYS_PATH = Path(settings.vault_root).parent / "data" / "api_keys.json"


def _load_api_keys() -> dict[str, str]:
    """API 키 맵 로드: {api_key: user_id}"""
    if _API_KEYS_PATH.exists():
        data = json.loads(_API_KEYS_PATH.read_text(encoding="utf-8"))
        return {entry["key"]: entry["user_id"] for entry in data.get("keys", [])}
    return {}


async def get_current_user(
    x_user_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> str:
    # 1. API 키 인증 (Bearer 토큰)
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
        keys = _load_api_keys()
        user_id = keys.get(api_key)
        if user_id and _iam.user_exists(user_id):
            return user_id
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 2. X-User-Id 헤더 인증
    if x_user_id:
        if not _iam.user_exists(x_user_id):
            raise HTTPException(status_code=401, detail="Unknown user")
        return x_user_id

    raise HTTPException(status_code=401, detail="X-User-Id header or Authorization Bearer required")


async def get_iam() -> IAMEngine:
    return _iam


def require_admin(user_id: str, iam: IAMEngine) -> None:
    """admin 역할 검증."""
    if "admin" not in iam.get_user_roles(user_id):
        raise HTTPException(status_code=403, detail="Admin role required")
