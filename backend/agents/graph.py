"""
LangGraph Orchestrator & Audit Trail
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Multi-Agent 오케스트레이터: 스킬 의존성 해석 → 연쇄 호출 → 완전 감사 로깅

Graph Structure:
  [route] → [guard] → [plan] → [execute_skill] → [audit] → [respond]
                                    ↑          ↓
                                    ←── (depends_on loop)

Guard node responsibilities:
  - Kill-switch check (immediate abort if activated)
  - User permission validation for requested skills
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.config import settings
from backend.agents.skill_parser import SkillRegistry
from backend.agents.nodes import (
    route_node,
    plan_node,
    execute_skill_node,
    audit_node,
    respond_node,
    should_continue,
)
from backend.security.kill_switch import is_killed

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """LangGraph 상태 스키마."""
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    user_roles: list[str]
    plan: list[dict[str, Any]]         # 실행 계획: [{skill_name, params, depends_on}]
    execution_log: list[dict[str, Any]] # 실행 결과 누적
    current_step: int
    reasoning: str                      # LLM 판단 논리
    error: str | None


async def _guard_node(state: AgentState, skill_registry: SkillRegistry) -> AgentState:
    """Kill-switch check and per-skill permission validation.

    Blocks execution in two scenarios:

    1. **Kill switch active** – the global emergency stop has been triggered.
       All agent activity is halted immediately.

    2. **Insufficient permissions** – the LLM routing identified skills that
       require roles the current user does not hold.  The skill registry is
       expected to expose an optional ``required_roles`` list in each skill's
       metadata; if absent the skill is considered open to all roles.

    In both blocking cases the node sets ``state["error"]`` and empties
    ``state["plan"]`` so downstream nodes short-circuit gracefully.
    """
    # ── Kill-switch check ──────────────────────────────────────────────────
    if is_killed():
        logger.critical(
            "Guard: kill switch is active – blocking request for user=%s",
            state.get("user_id"),
        )
        return {
            **state,
            "error": (
                "서비스가 긴급 중단되었습니다 (Kill Switch). "
                "관리자에게 문의하세요."
            ),
            "plan": [],
        }

    # ── Permission validation ──────────────────────────────────────────────
    import json

    user_roles: set[str] = set(state.get("user_roles", []))
    denied_skills: list[str] = []

    try:
        reasoning = state.get("reasoning", "{}")
        plan_data = json.loads(reasoning)
        requested_skill_names = [s.get("name", "") for s in plan_data.get("skills", [])]
    except (json.JSONDecodeError, KeyError):
        requested_skill_names = []

    for skill_name in requested_skill_names:
        skill_meta = skill_registry.get_skill(skill_name)
        if not skill_meta:
            continue
        required_roles: list[str] = skill_meta.get("required_roles", [])
        if required_roles and not user_roles.intersection(required_roles):
            denied_skills.append(skill_name)
            logger.warning(
                "Guard: user=%s (roles=%s) denied access to skill=%s (requires=%s)",
                state.get("user_id"),
                sorted(user_roles),
                skill_name,
                required_roles,
            )

    if denied_skills:
        return {
            **state,
            "error": (
                f"권한 없음: 다음 스킬에 대한 접근이 거부되었습니다: "
                f"{', '.join(denied_skills)}. "
                f"필요한 역할을 관리자에게 요청하세요."
            ),
            "plan": [],
        }

    return state


async def build_graph(skill_registry: SkillRegistry) -> StateGraph:
    """LangGraph 워크플로우를 구성하고 반환."""

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=0,
    )

    # ── 노드 정의 ──────────────────────────────────────
    async def _route(state: AgentState) -> AgentState:
        return await route_node(state, llm, skill_registry)

    async def _guard(state: AgentState) -> AgentState:
        return await _guard_node(state, skill_registry)

    async def _plan(state: AgentState) -> AgentState:
        return await plan_node(state, llm, skill_registry)

    async def _execute(state: AgentState) -> AgentState:
        return await execute_skill_node(state, skill_registry)

    async def _audit(state: AgentState) -> AgentState:
        return await audit_node(state)

    async def _respond(state: AgentState) -> AgentState:
        return await respond_node(state, llm)

    # ── 그래프 조립 ──────────────────────────────────────
    graph = StateGraph(AgentState)
    graph.add_node("route", _route)
    graph.add_node("guard", _guard)
    graph.add_node("plan", _plan)
    graph.add_node("execute_skill", _execute)
    graph.add_node("audit", _audit)
    graph.add_node("respond", _respond)

    graph.set_entry_point("route")
    graph.add_edge("route", "guard")
    graph.add_conditional_edges(
        "guard",
        lambda s: "blocked" if s.get("error") else "plan",
        {
            "plan": "plan",
            "blocked": "audit",  # Skip execution, go straight to audit + respond
        },
    )
    graph.add_edge("plan", "execute_skill")
    graph.add_conditional_edges(
        "execute_skill",
        should_continue,
        {
            "continue": "execute_skill",
            "done": "audit",
            "error": "audit",
        },
    )
    graph.add_edge("audit", "respond")
    graph.add_edge("respond", END)

    return graph


_compiled_graph_cache: dict[int, Any] = {}


async def get_compiled_graph(skill_registry: SkillRegistry):
    """체크포인터 포함 컴파일된 그래프 반환 (캐싱)."""
    cache_key = id(skill_registry)
    if cache_key in _compiled_graph_cache:
        return _compiled_graph_cache[cache_key]

    graph = await build_graph(skill_registry)
    settings.sqlite_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpointer = AsyncSqliteSaver.from_conn_string(
        str(settings.sqlite_checkpoint_path)
    )
    compiled = graph.compile(checkpointer=checkpointer)
    _compiled_graph_cache[cache_key] = compiled
    return compiled


async def invoke_agent(
    query: str,
    user_id: str,
    user_roles: list[str],
    skill_registry: SkillRegistry,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """에이전트 실행 진입점."""
    compiled = await get_compiled_graph(skill_registry)

    _thread_id = thread_id or f"{user_id}-{datetime.now(timezone.utc).isoformat()}"

    initial_state: AgentState = {
        "messages": [HumanMessage(content=query)],
        "user_id": user_id,
        "user_roles": user_roles,
        "plan": [],
        "execution_log": [],
        "current_step": 0,
        "reasoning": "",
        "error": None,
    }

    config = {"configurable": {"thread_id": _thread_id}}

    result = await compiled.ainvoke(initial_state, config=config)

    return {
        "thread_id": _thread_id,
        "response": result["messages"][-1].content if result["messages"] else "",
        "execution_log": result.get("execution_log", []),
        "reasoning": result.get("reasoning", ""),
        "error": result.get("error"),
    }


async def get_thread_history(thread_id: str) -> list[dict[str, Any]]:
    """Retrieve the full conversation history for *thread_id* from the checkpointer.

    Each item in the returned list represents one LangGraph checkpoint state
    and contains:

    * ``checkpoint_id`` – unique identifier for this checkpoint snapshot.
    * ``messages`` – list of ``{"role": ..., "content": ...}`` dicts derived
      from the serialised LangChain message objects.
    * ``execution_log`` – skill execution records captured in that state.
    * ``reasoning`` – LLM reasoning string from that state.
    * ``error`` – error string if the step ended in failure, else ``None``.

    Args:
        thread_id: The thread identifier used when calling :func:`invoke_agent`.

    Returns:
        Ordered list of checkpoint dicts (oldest first).  Returns an empty
        list if the thread is not found or the DB does not exist.
    """
    db_path = settings.sqlite_checkpoint_path
    if not db_path.exists():
        logger.warning("get_thread_history: checkpoint DB not found at %s", db_path)
        return []

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: PLC0415

    checkpointer = AsyncSqliteSaver.from_conn_string(str(db_path))
    config = {"configurable": {"thread_id": thread_id}}

    history: list[dict[str, Any]] = []
    try:
        async for checkpoint_tuple in checkpointer.alist(config):
            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            raw_messages = state.get("messages", [])

            # Normalise messages to plain dicts regardless of LangChain type
            serialised_messages: list[dict[str, Any]] = []
            for msg in raw_messages:
                if hasattr(msg, "type") and hasattr(msg, "content"):
                    serialised_messages.append({"role": msg.type, "content": msg.content})
                elif isinstance(msg, dict):
                    serialised_messages.append(msg)
                else:
                    serialised_messages.append({"role": "unknown", "content": str(msg)})

            history.append({
                "checkpoint_id": checkpoint_tuple.checkpoint.get("id", ""),
                "messages": serialised_messages,
                "execution_log": state.get("execution_log", []),
                "reasoning": state.get("reasoning", ""),
                "error": state.get("error"),
            })
    except Exception as exc:  # noqa: BLE001
        logger.error("get_thread_history failed for thread_id=%s: %s", thread_id, exc)

    # alist returns newest-first; reverse to chronological order
    history.reverse()
    return history
