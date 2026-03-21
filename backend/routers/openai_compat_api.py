"""OpenAI Compatible API — /v1/chat/completions 래퍼.

외부 툴(Continue, Cursor, Open WebUI 등)에서 M:AI Portal을
OpenAI API처럼 사용할 수 있게 합니다.

인증:
  Authorization: Bearer mlk_... (API 키)

사용 예:
  curl http://host:9001/v1/chat/completions \\
    -H "Authorization: Bearer mlk_abc..." \\
    -H "Content-Type: application/json" \\
    -d '{"model": "mai-portal", "messages": [{"role": "user", "content": "건강보험 보장 내용"}]}'
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_current_user, get_iam, current_api_key_info
from backend.core.iam import IAMEngine
from backend.agents.checkpointer import write_audit_record

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Request/Response Models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = "mai-portal"
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    n: int = 1


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models(user_id: str = Depends(get_current_user)):
    """OpenAI /v1/models 호환."""
    return {
        "object": "list",
        "data": [
            {
                "id": "mai-portal",
                "object": "model",
                "created": 1700000000,
                "owned_by": "mai-portal",
            },
            {
                "id": "mai-portal-fast",
                "object": "model",
                "created": 1700000000,
                "owned_by": "mai-portal",
            },
        ],
    }


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """OpenAI /v1/chat/completions 호환.

    내부적으로 M:AI Portal 에이전트를 호출하고,
    OpenAI 형식으로 응답을 래핑합니다.
    """
    if not body.messages:
        raise HTTPException(400, "messages is required")

    # 마지막 user 메시지를 쿼리로 사용
    query = ""
    for msg in reversed(body.messages):
        if msg.role == "user":
            query = msg.content
            break

    if not query:
        raise HTTPException(400, "No user message found")

    # API 키 추적 정보
    key_info = current_api_key_info.get()
    thread_id = f"openai-compat-{uuid.uuid4().hex[:8]}"

    # 감사 로그
    try:
        from datetime import datetime, timezone
        write_audit_record({
            "thread_id": thread_id,
            "user_id": user_id,
            "step": 0,
            "skill_name": "openai_compat.chat",
            "input_payload": {
                "model": body.model,
                "query": query[:200],
                "auth_method": key_info.get("auth_method") if key_info else "unknown",
                "api_key_prefix": key_info.get("key_prefix") if key_info else None,
                "api_key_label": key_info.get("label") if key_info else None,
            },
            "output_payload": None,
            "status": "started",
            "reasoning": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        })
    except Exception:
        logger.debug("Failed to write audit log", exc_info=True)

    if body.stream:
        return StreamingResponse(
            _stream_response(query, user_id, iam, body, thread_id),
            media_type="text/event-stream",
        )

    # Non-streaming
    response_text = await _get_agent_response(query, user_id, iam)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(query),
            "completion_tokens": len(response_text),
            "total_tokens": len(query) + len(response_text),
        },
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _get_agent_response(query: str, user_id: str, iam: IAMEngine) -> str:
    """에이전트를 호출하여 전체 응답 텍스트를 반환."""
    try:
        from backend.agents.graph import run_agent
        result = await run_agent(query=query, user_id=user_id, thread_id=f"compat-{uuid.uuid4().hex[:8]}")
        return result.get("output", result.get("response", str(result)))
    except Exception as exc:
        logger.error("Agent call failed: %s", exc)
        # 폴백: GraphRAG 검색 결과만 반환
        try:
            from backend.indexer.search import hybrid_search
            results = hybrid_search(query=query, user_id=user_id, iam=iam, n_results=5)
            if results:
                parts = []
                for i, r in enumerate(results, 1):
                    doc = r.get("document", "")[:300]
                    source = r.get("metadata", {}).get("source_path", "")
                    parts.append(f"[{i}] {source}\n{doc}")
                return "검색 결과:\n\n" + "\n\n".join(parts)
        except Exception:
            pass
        return f"죄송합니다. 요청을 처리할 수 없습니다: {exc}"


async def _stream_response(
    query: str,
    user_id: str,
    iam: IAMEngine,
    body: ChatCompletionRequest,
    thread_id: str,
) -> AsyncIterator[str]:
    """SSE 스트리밍 응답 (OpenAI 형식)."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # 에이전트 응답 가져오기
    response_text = await _get_agent_response(query, user_id, iam)

    # 토큰 단위 시뮬레이션 (실제로는 에이전트 SSE를 래핑)
    words = response_text.split()
    for i, word in enumerate(words):
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": word + (" " if i < len(words) - 1 else "")},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.02)

    # 종료 청크
    end_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(end_chunk)}\n\n"
    yield "data: [DONE]\n\n"
