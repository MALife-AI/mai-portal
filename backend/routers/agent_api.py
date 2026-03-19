"""Agent Execution API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.dependencies import get_current_user, get_iam
from backend.core.iam import IAMEngine
from backend.agents.graph import invoke_agent
from backend.agents.skill_parser import SkillRegistry
from backend.security.prompt_guard import sanitize_input
from backend.security.kill_switch import is_killed
from backend.config import settings

router = APIRouter()
_registry = SkillRegistry()
_registry.load_all()


class AgentRequest(BaseModel):
    query: str
    thread_id: str | None = None


@router.post("/run")
async def run_agent(
    body: AgentRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    if is_killed():
        return {"error": "System is in emergency shutdown mode"}

    safe_query = sanitize_input(body.query)
    roles = iam.get_user_roles(user_id)

    result = await invoke_agent(
        query=safe_query,
        user_id=user_id,
        user_roles=roles,
        skill_registry=_registry,
        thread_id=body.thread_id,
    )
    return result
