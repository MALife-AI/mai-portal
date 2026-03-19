"""Admin API: IAM 관리 + Audit Log."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_iam, get_current_user
from backend.core.iam import IAMEngine
from backend.agents.checkpointer import query_audit_logs
from backend.security.kill_switch import (
    activate_kill_switch,
    deactivate_kill_switch,
    get_kill_switch_status,
)

router = APIRouter()


def _require_admin(user_id: str, iam: IAMEngine) -> None:
    if "admin" not in iam.get_user_roles(user_id):
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("/iam")
async def get_iam_config(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    _require_admin(user_id, iam)
    iam.reload()
    return iam.as_dict()


@router.put("/iam")
async def update_iam_config(
    body: dict,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    _require_admin(user_id, iam)
    iam.save(body)
    return {"status": "updated"}


@router.get("/audit")
async def get_audit_logs(
    user_id: str = Depends(get_current_user),
    filter_user: str | None = None,
    limit: int = 50,
    iam: IAMEngine = Depends(get_iam),
):
    _require_admin(user_id, iam)
    return query_audit_logs(user_id=filter_user, limit=limit)


@router.post("/kill-switch/activate")
async def kill_switch_on(user_id: str = Depends(get_current_user), iam: IAMEngine = Depends(get_iam)):
    if "admin" not in iam.get_user_roles(user_id):
        raise HTTPException(status_code=403, detail="Admin role required")
    await activate_kill_switch()
    return {"status": "activated"}


@router.post("/kill-switch/deactivate")
async def kill_switch_off(user_id: str = Depends(get_current_user), iam: IAMEngine = Depends(get_iam)):
    if "admin" not in iam.get_user_roles(user_id):
        raise HTTPException(status_code=403, detail="Admin role required")
    await deactivate_kill_switch()
    return {"status": "deactivated"}


@router.get("/kill-switch/status")
async def kill_switch_status():
    return get_kill_switch_status()
