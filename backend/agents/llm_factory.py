"""LLM 팩토리: provider 설정에 따라 적절한 ChatModel 인스턴스 반환.

지원 provider:
- "openai": ChatOpenAI (기본, API 키 필요)
- "claude_wrapper": Claude Code API Wrapper HTTP 서버를 LangChain ChatModel로 래핑
- "ollama": Ollama 로컬 모델 (ChatOllama)

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
        provider: "openai", "claude_wrapper", "ollama". None이면 settings.vlm_provider 사용.
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

    if provider == "ollama":
        logger.info("LLM factory: using Ollama model=%s", model_name)
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise ImportError(
                "langchain-ollama 패키지가 필요합니다: pip install langchain-ollama"
            )
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=getattr(settings, "ollama_base_url", "http://localhost:11434"),
            num_ctx=4096,
            num_predict=1024,
        )

    # 기본: OpenAI
    logger.info("LLM factory: using OpenAI model=%s", model_name)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model_name,
        api_key=settings.openai_api_key,
        temperature=temperature,
    )
