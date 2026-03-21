from __future__ import annotations

import json
import secrets
import contextvars
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request

from backend.core.iam import IAMEngine
from backend.config import settings

_iam = IAMEngine(settings.vault_root / "iam.yaml")

# API 키 저장소
_API_KEYS_PATH = Path(settings.vault_root).parent / "data" / "api_keys.json"

# 현재 요청의 API 키 정보 (감사 로그 추적용)
current_api_key_info: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "current_api_key_info", default=None
)


def _load_api_keys() -> dict[str, dict]:
    """API 키 맵 로드: {api_key: {user_id, label, key_prefix}}"""
    if _API_KEYS_PATH.exists():
        data = json.loads(_API_KEYS_PATH.read_text(encoding="utf-8"))
        return {
            entry["key"]: {
                "user_id": entry["user_id"],
                "label": entry.get("label", ""),
                "key_prefix": entry["key"][:8],
            }
            for entry in data.get("keys", [])
        }
    return {}


async def get_current_user(
    x_user_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> str:
    # 1. API 키 인증 (Bearer 토큰)
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
        keys = _load_api_keys()
        key_info = keys.get(api_key)
        if key_info and _iam.user_exists(key_info["user_id"]):
            # 감사 로그 추적용 컨텍스트 저장
            current_api_key_info.set({
                "key_prefix": key_info["key_prefix"],
                "label": key_info["label"],
                "auth_method": "api_key",
            })
            return key_info["user_id"]
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 2. X-User-Id 헤더 인증
    if x_user_id:
        if not _iam.user_exists(x_user_id):
            raise HTTPException(status_code=401, detail="Unknown user")
        current_api_key_info.set({"auth_method": "header"})
        return x_user_id

    raise HTTPException(status_code=401, detail="X-User-Id header or Authorization Bearer required")


async def get_iam() -> IAMEngine:
    return _iam


def require_admin(user_id: str, iam: IAMEngine) -> None:
    """admin 역할 검증."""
    if "admin" not in iam.get_user_roles(user_id):
        raise HTTPException(status_code=403, detail="Admin role required")
