from __future__ import annotations

from fastapi import Header, HTTPException

from backend.core.iam import IAMEngine
from backend.config import settings

_iam = IAMEngine(settings.vault_root / "iam.yaml")


async def get_current_user(x_user_id: str = Header(...)) -> str:
    if not _iam.user_exists(x_user_id):
        raise HTTPException(status_code=401, detail="Unknown user")
    return x_user_id


async def get_iam() -> IAMEngine:
    return _iam
