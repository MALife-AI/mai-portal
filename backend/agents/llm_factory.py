"""LLM 팩토리: provider 설정에 따라 적절한 ChatModel 인스턴스 반환.

지원 provider:
- "llama_server": llama-server OpenAI 호환 API (기본)
- "claude_wrapper": Claude Code API Wrapper HTTP 서버를 LangChain ChatModel로 래핑

모든 반환값은 LangChain BaseChatModel 인터페이스를 따르므로
기존 LangGraph 노드 코드 변경 없이 교체 가능합니다.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from backend.config import settings

logger = logging.getLogger(__name__)


class ClaudeWrapperChat(BaseChatModel):
    """Claude Code API Wrapper를 LangChain ChatModel로 래핑.

    동기/비동기 모두 지원. httpx를 사용하여 wrapper 서버에 HTTP 요청.
    """

    wrapper_url: str = ""
    model_name: str = "claude-wrapper"

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "claude-wrapper"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        import httpx

        prompt = self._messages_to_prompt(messages)
        payload = {
            "prompt": prompt,
            "allowedTools": [],
            "disallowedTools": ["Bash", "Edit", "Write", "WebSearch", "WebFetch"],
        }

        with httpx.Client(timeout=300.0) as client:
            response = client.post(f"{self.wrapper_url}/api/claude", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("result", "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        import httpx

        prompt = self._messages_to_prompt(messages)
        payload = {
            "prompt": prompt,
            "allowedTools": [],
            "disallowedTools": ["Bash", "Edit", "Write", "WebSearch", "WebFetch"],
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            response = await client.post(f"{self.wrapper_url}/api/claude", json=payload)
            response.raise_for_status()
            data = response.json()

        content = data.get("result", "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    @staticmethod
    def _messages_to_prompt(messages: list[BaseMessage]) -> str:
        """LangChain 메시지 리스트를 단일 프롬프트 문자열로 변환."""
        parts: list[str] = []
        for msg in messages:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", str(msg))
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            if role == "system":
                parts.append(f"[시스템 지시]\n{content}")
            elif role == "ai" or role == "assistant":
                parts.append(f"[이전 응답]\n{content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)


def create_chat_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0,
) -> BaseChatModel:
    """설정에 따라 적절한 LLM 인스턴스를 생성하여 반환.

    Args:
        provider: "llama_server", "claude_wrapper". None이면 settings.vlm_provider 사용.
        model: 모델명 오버라이드. None이면 settings.vlm_model 사용.
        temperature: 생성 온도. 기본 0 (결정적).

    Returns:
        LangChain BaseChatModel 인스턴스.
    """
    provider = provider or settings.vlm_provider
    model_name = model or settings.vlm_model

    if provider == "claude_wrapper":
        logger.info("LLM factory: using Claude wrapper at %s", settings.claude_wrapper_url)
        return ClaudeWrapperChat(
            wrapper_url=settings.claude_wrapper_url,
            model_name="claude-wrapper",
        )

    if provider == "llama_server":
        llama_url = getattr(settings, "llama_server_url", "http://localhost:8801/v1")
        logger.info("LLM factory: using llama-server at %s, model=%s", llama_url, model_name)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            api_key="sk-no-key-required",
            base_url=llama_url,
            temperature=temperature,
            max_tokens=4096,
        )


def get_routed_client(query: str) -> tuple[str, str]:
    """질문 복잡도에 따라 적절한 추론 서버 URL과 모델을 반환.

    라우팅 기준:
    - 간단한 질문 (< 50자, 인사/단순 조회) → light 서버 (4B)
    - 복잡한 질문 (긴 질문, 분석/비교/Thinking 필요) → heavy 서버 (9B+)

    Returns:
        (base_url, model_name) 튜플
    """
    if not getattr(settings, "smart_routing", False):
        url = getattr(settings, "llama_server_url", "http://localhost:8801/v1")
        return url, settings.vlm_model

    heavy_url = getattr(settings, "llama_server_heavy", "")
    light_url = getattr(settings, "llama_server_light", "") or getattr(settings, "llama_server_url", "http://localhost:8801/v1")

    if not heavy_url:
        return light_url, settings.vlm_model

    # 복잡도 판단
    is_complex = (
        len(query) > 100
        or any(kw in query for kw in ["분석", "비교", "왜", "어떻게", "차이", "요약", "정리", "계산", "추론"])
        or query.count("?") > 1
        or "think" in query.lower()
    )

    if is_complex:
        logger.info("Smart Router: complex query → heavy server (%s)", heavy_url)
        return heavy_url, settings.vlm_model
    else:
        logger.info("Smart Router: simple query → light server (%s)", light_url)
        return light_url, settings.vlm_model
