"""Legacy Adapter API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.dependencies import get_current_user

router = APIRouter()


class LegacyRequest(BaseModel):
    system: str
    path: str
    payload: dict


@router.post("/call")
async def call_legacy(
    body: LegacyRequest,
    user_id: str = Depends(get_current_user),
):
    from backend.adapters.legacy import LegacyAdapter

    # 실제 환경에서는 system별 base_url을 config에서 조회
    adapter = LegacyAdapter(base_url=f"http://legacy-{body.system}:8080")
    result = await adapter.call(body.path, body.payload)
    return result
