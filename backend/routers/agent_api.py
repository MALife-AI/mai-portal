"""Agent Execution API."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.dependencies import get_current_user, get_iam
from backend.core.iam import IAMEngine
from backend.agents.graph import invoke_agent, invoke_agent_stream
from backend.agents.skill_parser import SkillRegistry
from backend.security.prompt_guard import sanitize_input
from backend.security.kill_switch import is_killed
from backend.core.task_manager import task_manager, TaskInfo
from backend.config import settings

router = APIRouter()
_registry = SkillRegistry()
_registry.load_all()


class HistoryMessage(BaseModel):
    role: str
    content: str

class AgentRequest(BaseModel):
    query: str
    thread_id: str | None = None
    server_url: str | None = None
    custom_prompt: str | None = None
    history: list[HistoryMessage] | None = None

    @classmethod
    def validate_server_url(cls, url: str | None) -> str | None:
        """등록된 GPU 서버 URL만 허용 (SSRF 방지)."""
        if url is None:
            return None
        from backend.admin.routes import _load_gpu_servers
        allowed = {s["url"] for s in _load_gpu_servers()}
        if url not in allowed:
            raise ValueError(f"Unregistered server URL: {url}")
        return url


@router.post("/run")
async def run_agent(
    body: AgentRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """백그라운드 태스크로 에이전트 실행. 즉시 task_id 반환."""
    if is_killed():
        return {"error": "System is in emergency shutdown mode"}

    safe_query = sanitize_input(body.query)
    roles = iam.get_user_roles(user_id)
    validated_url = AgentRequest.validate_server_url(body.server_url)

    async def _run(task: TaskInfo):
        task.message = "에이전트 실행 중..."
        task.total = 1

        response_text = ""
        metadata = {}
        async for event in invoke_agent_stream(
            query=safe_query,
            user_id=user_id,
            user_roles=roles,
            skill_registry=_registry,
            thread_id=body.thread_id,
            server_url=validated_url,
            custom_prompt=body.custom_prompt,
            history=[{"role": m.role, "content": m.content} for m in body.history] if body.history else None,
        ):
            if event.get("type") == "metadata":
                metadata = event
            elif event.get("type") == "token":
                response_text += event.get("content", "")
            elif event.get("type") == "done":
                break

        task.progress = 1
        task.result = {
            "response": response_text,
            "thread_id": metadata.get("thread_id", ""),
            "execution_log": metadata.get("execution_log", []),
            "reasoning": metadata.get("reasoning", ""),
            "source_nodes": metadata.get("source_nodes", []),
        }
        task.message = "완료"

    task_id = task_manager.submit(f"에이전트: {safe_query[:30]}", _run)
    return {"status": "accepted", "task_id": task_id}


@router.post("/stream")
async def stream_agent(
    body: AgentRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """SSE 스트리밍 에이전트 실행 (실시간 토큰 표시)."""
    if is_killed():
        return {"error": "System is in emergency shutdown mode"}

    safe_query = sanitize_input(body.query)
    roles = iam.get_user_roles(user_id)
    validated_url = AgentRequest.validate_server_url(body.server_url)

    async def event_generator():
        async for event in invoke_agent_stream(
            query=safe_query,
            user_id=user_id,
            user_roles=roles,
            skill_registry=_registry,
            thread_id=body.thread_id,
            server_url=validated_url,
            custom_prompt=body.custom_prompt,
            history=[{"role": m.role, "content": m.content} for m in body.history] if body.history else None,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
