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
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

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

    from backend.agents.llm_factory import create_chat_llm
    llm = create_chat_llm()

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
    checkpointer = MemorySaver()
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


async def invoke_agent_stream(
    query: str,
    user_id: str,
    user_roles: list[str],
    skill_registry: SkillRegistry,
    thread_id: str | None = None,
    server_url: str | None = None,
):
    """Unsloth 스타일 auto-healing tool calling + GraphRAG + 스트리밍."""
    import json as _json
    from backend.config import settings as _settings

    _thread_id = thread_id or f"{user_id}-{datetime.now(timezone.utc).isoformat()}"

    # ── GraphRAG 컨텍스트 검색 ────────────────────────────────────────
    source_nodes: list[dict[str, Any]] = []
    graph_context: str = ""
    try:
        from backend.graph.store import GraphStore
        from backend.graph.graphrag import GraphRAGEngine
        from backend.core.iam import IAMEngine

        persist_path = _settings.vault_root / ".graph" / "knowledge_graph.json"
        store = GraphStore(persist_path=persist_path)
        iam = IAMEngine(_settings.vault_root / "iam.yaml")
        engine = GraphRAGEngine(graph_store=store, iam_engine=iam)

        rag_result = await engine.search(
            query=query, user_id=user_id, user_roles=user_roles,
            mode="hybrid", n_results=5,
        )

        seen_ids: set[str] = set()
        for e in rag_result.matched_entities + rag_result.related_entities:
            eid = e.get("id") or e.get("name", "")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            props = e.get("properties", {})
            source_nodes.append({
                "id": eid,
                "name": e.get("name", ""),
                "type": e.get("entity_type", ""),
                "description": props.get("description", ""),
                "source_titles": [
                    p.split("/")[-1].replace(".md", "")
                    for p in e.get("source_paths", [])
                ],
                "page_start": props.get("page_start"),
                "page_end": props.get("page_end"),
                "effective_date": props.get("effective_date"),
            })
            if len(source_nodes) >= 5:
                break

        graph_context = rag_result.combined_context or ""
    except Exception:
        logger.debug("GraphRAG search failed (non-fatal)", exc_info=True)

    # ── 메타데이터 전송 ──────────────────────────────────────────────
    yield {
        "type": "metadata",
        "thread_id": _thread_id,
        "execution_log": [],
        "reasoning": "",
        "source_nodes": source_nodes,
    }

    # ── OpenAI tool calling (Unsloth auto-healing loop) ──────────────
    from openai import AsyncOpenAI

    if server_url:
        routed_url = server_url
    else:
        from backend.agents.llm_factory import get_routed_client
        routed_url, _ = get_routed_client(query)
    client = AsyncOpenAI(base_url=routed_url, api_key="sk-no-key-required")
    model_name = _settings.vlm_model

    # 스킬을 OpenAI tool 형식으로 변환
    tools = []
    skill_map: dict[str, Any] = {}
    for skill in skill_registry.list_skills():
        tool_def = {
            "type": "function",
            "function": {
                "name": skill["name"],
                "description": skill.get("description", ""),
                "parameters": skill.get("params_schema", {"type": "object", "properties": {}}),
            },
        }
        tools.append(tool_def)
        skill_map[skill["name"]] = skill

    # 사용자 소속 정보 조회
    user_dept = ""
    try:
        iam_engine = IAMEngine(_settings.vault_root / "iam.yaml")
        iam_data = iam_engine.as_dict()
        for u in iam_data.get("users", []):
            if u.get("user_id") == user_id:
                dept_id = u.get("department", "")
                dept_info = iam_data.get("departments", {}).get(dept_id, {})
                user_dept = dept_info.get("name", dept_id)
                break
    except Exception:
        pass

    # 메시지 구성 — 번호 매긴 출처 + 인라인 인용 지시
    numbered_sources = []
    for i, sn in enumerate(source_nodes, 1):
        docs = ", ".join(sn.get("source_titles", []))
        page = ""
        if sn.get("page_start"):
            page = f" p.{sn['page_start']}"
            if sn.get("page_end") and sn["page_end"] != sn["page_start"]:
                page += f"-{sn['page_end']}"
        eff = sn.get("effective_date", "")
        eff_str = f" [{eff}]" if eff else ""
        desc = sn.get("description", "")
        numbered_sources.append(f"[{i}] {sn['name']} — {docs}{page}{eff_str}: {desc}")

    source_block = "\n".join(numbered_sources) if numbered_sources else ""

    system_prompt = (
        "당신은 금융/보험 도메인 전문 어시스턴트입니다. 한국어로 정확하고 친절하게 답변하세요.\n\n"
        "중요: 답변 시 정보의 출처를 [1], [2] 형태로 인라인 인용하세요.\n"
        "예: '보험료를 2회 이상 미납하면 계약이 해지될 수 있습니다[1].'\n"
        "답변 마지막에 '---' 구분선 후 출처 목록을 표기하세요.\n"
        "약관/규정의 시행일이 표기되어 있으면 해당 날짜를 명시하세요."
    )
    if user_dept:
        system_prompt += f"\n\n사용자 소속: {user_dept}. 해당 부서에 관련된 사규/매뉴얼이 있으면 우선 참고하세요."
    if source_block:
        system_prompt += f"\n\n참고 출처:\n{source_block}"
    if graph_context:
        system_prompt += (
            f"\n\n관련 컨텍스트:\n{graph_context[:2500]}"
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    # ── Auto-healing tool calling loop ────────────────────────────────
    max_iterations = 5
    for _ in range(max_iterations):
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=1024,
                temperature=0.7,
                stream=True,
            )

            # 스트리밍 응답 처리
            tool_calls_acc: list[dict[str, Any]] = []
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # 텍스트 토큰
                if delta.content:
                    yield {"type": "token", "content": delta.content}

                # tool call 누적
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        while len(tool_calls_acc) <= idx:
                            tool_calls_acc.append({"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc.function.arguments

            # tool call이 없으면 종료
            if not tool_calls_acc:
                break

            # tool call 실행
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls_acc
                ],
            })

            for tc in tool_calls_acc:
                try:
                    tool = skill_registry.get_tool(tc["name"])
                    if tool:
                        args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
                        result = await tool.ainvoke(args)
                        result_str = str(result)[:2000]
                    else:
                        result_str = f"Tool '{tc['name']}' not found"
                except Exception as exc:
                    result_str = f"Tool error: {exc}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": result_str,
                })

            yield {"type": "token", "content": f"\n\n> 🔧 {', '.join(tc['name'] for tc in tool_calls_acc)} 실행 완료\n\n"}

        except Exception as exc:
            logger.error("Tool calling loop error: %s", exc)
            yield {"type": "token", "content": f"\n\n오류: {exc}"}
            break

    yield {"type": "done"}


async def get_thread_history(thread_id: str) -> list[dict[str, Any]]:
    """Retrieve the full conversation history for *thread_id* from the cached checkpointer.

    Returns:
        Ordered list of checkpoint dicts (oldest first).  Returns an empty
        list if the thread is not found.
    """
    # Find the cached compiled graph's checkpointer
    if not _compiled_graph_cache:
        return []

    compiled = next(iter(_compiled_graph_cache.values()))
    checkpointer = getattr(compiled, "checkpointer", None)
    if checkpointer is None:
        return []

    config = {"configurable": {"thread_id": thread_id}}

    history: list[dict[str, Any]] = []
    try:
        async for checkpoint_tuple in checkpointer.alist(config):
            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            raw_messages = state.get("messages", [])

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

    history.reverse()
    return history
