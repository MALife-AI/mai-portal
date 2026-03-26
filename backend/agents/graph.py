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
    custom_prompt: str | None = None,
    history: list[dict[str, str]] | None = None,
):
    """Unsloth 스타일 auto-healing tool calling + GraphRAG + 스트리밍."""
    import json as _json
    from backend.config import settings as _settings

    _thread_id = thread_id or f"{user_id}-{datetime.now(timezone.utc).isoformat()}"

    # GraphRAG 스킬에 현재 사용자 ID 전달 (IAM 권한 체크용)
    if hasattr(skill_registry, '_set_graphrag_user'):
        skill_registry._set_graphrag_user(user_id)

    # ── GraphRAG 컨텍스트 검색 ────────────────────────────────────────
    source_nodes: list[dict[str, Any]] = []
    graph_context: str = ""
    _search_query = query  # rewrite 시 변경될 수 있음
    try:
        from backend.graph.store import GraphStore
        from backend.graph.graphrag import GraphRAGEngine
        from backend.core.iam import IAMEngine

        persist_path = _settings.vault_root / ".graph" / "knowledge_graph.json"
        store = GraphStore(persist_path=persist_path)
        iam = IAMEngine(_settings.vault_root / "iam.yaml")
        engine = GraphRAGEngine(graph_store=store, iam_engine=iam)

        # 쿼리에서 날짜 추출 (가입일/시행일 기준 필터)
        import re as _re_date
        _date_effective = None
        date_match = _re_date.search(r'(\d{4})[-./년](\d{1,2})[-./월](\d{1,2})', query)
        if date_match:
            _date_effective = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"

        rag_result = await engine.search(
            query=query, user_id=user_id, user_roles=user_roles,
            mode="hybrid", n_results=5,
            effective_after=_date_effective,
        )

        # ── Query Rewrite: 유사도 낮으면 LLM으로 쿼리 재작성 후 재검색 ──
        _SCORE_THRESHOLD = 0.35
        top_score = max((r.get("score", 0.0) for r in rag_result.vector_results), default=0.0)
        if top_score < _SCORE_THRESHOLD and rag_result.vector_results:
            logger.info("Low relevance (score=%.3f < %.2f) — attempting query rewrite", top_score, _SCORE_THRESHOLD)
            try:
                from openai import AsyncOpenAI as _RewriteClient
                _rw_url = server_url or getattr(_settings, "llama_server_url", "http://localhost:8801/v1")
                _rw_client = _RewriteClient(base_url=_rw_url, api_key="sk-local")
                _rw_model = getattr(_settings, "vlm_model", "qwen3.5-4b")
                _rw_resp = await _rw_client.chat.completions.create(
                    model=_rw_model,
                    messages=[
                        {"role": "system", "content": (
                            "사용자의 검색 쿼리를 보험/금융 도메인에 맞게 재작성하세요. "
                            "핵심 키워드를 추출하고, 동의어/관련어를 포함하여 검색 정확도를 높이세요. "
                            "재작성된 쿼리만 출력하세요. 설명 없이 한 줄로."
                        )},
                        {"role": "user", "content": query},
                    ],
                    max_tokens=100,
                    temperature=0.3,
                )
                rewritten = (_rw_resp.choices[0].message.content or "").strip()
                if rewritten and rewritten != query:
                    logger.info("Query rewrite: '%s' → '%s'", query, rewritten)
                    _search_query = rewritten
                    rag_result = await engine.search(
                        query=rewritten, user_id=user_id, user_roles=user_roles,
                        mode="hybrid", n_results=5,
                        effective_after=_date_effective,
                    )
            except Exception:
                logger.debug("Query rewrite failed (non-fatal)", exc_info=True)

        # ── 검색 품질 검증: vector score + graph entity 매칭 동시 확인 ──
        final_top_score = max((r.get("score", 0.0) for r in rag_result.vector_results), default=0.0)
        has_graph_match = bool(rag_result.matched_entities)
        _insufficient = (final_top_score < _SCORE_THRESHOLD) and (not has_graph_match)
        if _insufficient:
            logger.info(
                "Insufficient context after search (score=%.3f, graph_match=%s) — early return",
                final_top_score, has_graph_match,
            )

        matched_ids = {(e.get("id") or e.get("name", "")) for e in rag_result.matched_entities}

        seen_ids: set[str] = set()
        for e in rag_result.matched_entities + rag_result.related_entities:
            eid = e.get("id") or e.get("name", "")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            props = e.get("properties", {})

            # 참조 이유 결정
            if eid in matched_ids:
                reason = f"'{query[:20]}' 키워드 직접 매칭"
            else:
                # 관계 경로에서 어떤 관계로 연결되었는지 찾기
                rel_type = ""
                connected_from = ""
                for rp in rag_result.relationship_paths:
                    if rp["target"] == eid:
                        rel_type = rp["type"]
                        connected_from = rp["source"]
                        break
                    elif rp["source"] == eid:
                        rel_type = rp["type"]
                        connected_from = rp["target"]
                        break
                if rel_type:
                    rel_labels = {
                        "covers": "보장", "includes": "포함", "excludes": "면책",
                        "requires": "요건", "depends_on": "의존", "regulates": "규제",
                        "belongs_to": "소속", "references": "참조", "defines": "정의",
                        "diagnoses": "진단", "pays": "지급", "renews_as": "갱신",
                        "supersedes": "대체", "must_coexist": "의무동시가입",
                    }
                    label = rel_labels.get(rel_type, rel_type)
                    reason = f"'{connected_from[:20]}' → [{label}] 관계로 탐색"
                else:
                    reason = "관련 엔티티 (그래프 탐색)"

            source_nodes.append({
                "id": eid,
                "name": e.get("name", ""),
                "type": e.get("entity_type", ""),
                "description": props.get("description", ""),
                "match_reason": reason,
                "source_titles": [
                    p.split("/")[-1].replace(".md", "").split("@")[0]
                    for p in e.get("source_paths", [])
                ],
                "page_start": props.get("page_start"),
                "page_end": props.get("page_end"),
                "section_ref": props.get("section_ref", ""),
                "effective_date": props.get("effective_date"),
                "version_hash": props.get("version_hash"),
                "version_date": props.get("version_date"),
                "version_label": props.get("version_label"),
                "is_historical": props.get("is_historical", False),
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

    # ── 검색 품질 미달 시 조기 반환 (할루시네이션 방지) ──────────────
    if _insufficient:
        yield {
            "type": "token",
            "content": (
                "현재 등록된 자료에서 관련 정보를 찾지 못했습니다. "
                "질문을 다른 표현으로 바꿔보시거나, 관련 문서가 업로드되어 있는지 확인해 주세요."
            ),
        }
        yield {"type": "done"}
        return

    # ── OpenAI tool calling (Unsloth auto-healing loop) ──────────────
    from openai import AsyncOpenAI

    if server_url:
        routed_url = server_url
    else:
        from backend.agents.llm_factory import get_routed_client
        routed_url, _ = get_routed_client(query)
    client = AsyncOpenAI(base_url=routed_url, api_key="sk-no-key-required")
    model_name = _settings.vlm_model

    # 내장 도구: ask_user (멀티턴 clarification)
    ask_user_tool = {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "사용자에게 추가 정보를 요청할 때 사용합니다. "
                "필수 파라미터가 부족하거나 여러 선택지 중 하나를 골라야 할 때 호출하세요. "
                "options에 선택지 목록을 제공하면 사용자가 버튼으로 선택할 수 있습니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "사용자에게 보여줄 질문 메시지",
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "버튼에 표시할 텍스트"},
                                "value": {"type": "string", "description": "선택 시 전송할 값"},
                                "description": {"type": "string", "description": "부가 설명 (선택)"},
                            },
                            "required": ["label", "value"],
                        },
                        "description": "사용자에게 제시할 선택지 목록",
                    },
                    "allow_custom_input": {
                        "type": "boolean",
                        "description": "직접 입력 옵션 표시 여부 (기본: true)",
                    },
                },
                "required": ["message", "options"],
            },
        },
    }

    # 내장 도구: save_memory (대화 중 중요 정보 저장)
    save_memory_tool = {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "대화 중 중요한 정보를 기억합니다. "
                "고객 정보, 상품 선택, 계산 결과 등 이후 대화에서 참조해야 할 내용을 저장하세요. "
                "예: 고객이 '무배당 건강보험 가입 중'이라고 했으면 저장."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "한 줄 요약 (예: '고객 무배당 건강보험 가입 중')",
                    },
                    "content": {
                        "type": "string",
                        "description": "상세 내용",
                    },
                    "category": {
                        "type": "string",
                        "description": "분류: customer_info, product_choice, calculation, context",
                    },
                },
                "required": ["summary", "content"],
            },
        },
    }

    # 내장 도구: recall_memory (저장된 기억 조회)
    recall_memory_tool = {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": (
                "이 대화에서 이전에 저장한 기억을 조회합니다. "
                "keyword를 지정하면 관련 기억만 검색하고, 없으면 전체 목록을 반환합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "검색할 키워드 (비우면 전체 목록)",
                    },
                },
            },
        },
    }

    # 세션 메모리 초기화
    from backend.agents.session_memory import SessionMemory
    session_mem = SessionMemory(_thread_id)

    # 스킬을 OpenAI tool 형식으로 변환
    tools = [ask_user_tool, save_memory_tool, recall_memory_tool]
    skill_map: dict[str, Any] = {}
    for skill in skill_registry.list_skills():
        # 내장 스킬(__prompt__, __code__)만 tools에 포함 (토큰 절약)
        # 외부 API 스킬은 endpoint가 http URL이므로 제외
        skill_meta = skill_registry.get_skill(skill["name"])
        endpoint = skill_meta.get("endpoint", "") if skill_meta else ""
        if endpoint.startswith("http"):
            continue  # 외부 API 스킬 제외

        tool_def = {
            "type": "function",
            "function": {
                "name": skill["name"],
                "description": skill.get("description", "")[:100],
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
    has_multiple_versions = False
    version_docs: dict[str, list[str]] = {}  # doc_name → [version_labels]
    for i, sn in enumerate(source_nodes, 1):
        docs = ", ".join(sn.get("source_titles", []))
        page = ""
        if sn.get("page_start"):
            page = f" p.{sn['page_start']}"
            if sn.get("page_end") and sn["page_end"] != sn["page_start"]:
                page += f"-{sn['page_end']}"
        eff = sn.get("effective_date", "")
        eff_str = f" [{eff}]" if eff else ""
        ver = sn.get("version_label", "")
        ver_str = f" (버전: {ver})" if ver else " (현재 버전)"
        desc = sn.get("description", "")
        numbered_sources.append(f"[{i}] {sn['name']} — {docs}{page}{eff_str}{ver_str}: {desc}")

        # 버전 다양성 추적
        for doc in sn.get("source_titles", []):
            version_docs.setdefault(doc, []).append(ver or "현재")

    # 같은 문서에 여러 버전이 있는지 체크
    for doc, vers in version_docs.items():
        if len(set(vers)) > 1:
            has_multiple_versions = True
            break

    source_block = "\n".join(numbered_sources) if numbered_sources else ""

    system_prompt = (
        "당신은 금융/보험 도메인 전문 어시스턴트입니다. 한국어로 정확하고 친절하게 답변하세요.\n"
        "답변은 핵심만 간결하게 작성하세요. 불필요한 배경 설명이나 반복을 피하고, 질문에 직접 답하세요.\n\n"
        "## 최우선 규칙: 도구 호출 의무\n"
        "당신은 도구를 직접 호출하는 주체입니다. 사용자에게 절대로 도구/함수 사용법을 설명하지 마세요.\n"
        "금지 표현: '~함수를 사용하면', '~를 호출하면', '~코드를 입력하면', '~를 통해 확인할 수 있습니다'\n\n"
        "## ask_user 도구 사용 원칙 (최소화)\n"
        "ask_user는 정말 핵심 정보가 없어서 답변 자체가 불가능할 때만 1회 사용하세요.\n"
        "- 참고 출처나 대화 맥락에서 추론 가능한 정보는 직접 판단하여 바로 답변하세요.\n"
        "- 상품이 1~2개뿐이면 묻지 말고 모두 포함하여 답변하세요.\n"
        "- ask_user 호출 시 options에는 구체적 선택지를 넣되, 한 대화에서 ask_user는 최대 1회만 사용하세요.\n"
        "- 사용자가 선택/입력하면 즉시 해당 도구를 호출하세요.\n\n"
        "## 질문 의도 분류\n"
        "사용자 질문을 먼저 분류한 뒤 적절한 도구를 호출하세요:\n\n"
        "**정의/개념 질문** (~이 뭐야, ~이 뭔지, ~란, ~의 의미, ~설명해줘):\n"
        "→ explain-term 바로 호출. 상품 정보 불필요. ask_user 하지 마세요.\n"
        "예: '해약환급금이 뭐야?' → explain-term(term='해약환급금')\n"
        "예: '보험계약대출이란?' → explain-term(term='보험계약대출')\n\n"
        "**구체적 조회 질문** (~얼마야, ~받을 수 있어, ~계산해줘, ~조회해줘, ~내 보험):\n"
        "→ 상품/고객 정보가 필요. 이미 언급했으면 바로 호출, 없으면 ask_user.\n"
        "예: '무배당 건강보험 해약환급금 얼마야?' → get-product-spec(product_name='무배당 건강보험')\n"
        "예: '해약환급금 얼마야?' (상품 미지정) → ask_user로 상품 선택\n\n"
        "**비교/분석 질문** (~비교해줘, ~차이, ~뭐가 나아):\n"
        "→ compare-riders 또는 get-coverage 호출\n\n"
        "**규정/절차 질문** (~규정, ~절차, ~조건, ~방법, ~할 수 있어):\n"
        "→ search-regulation 호출\n\n"
        "## 문서 버전 규칙\n"
        "- 참고 출처에 같은 문서의 여러 버전이 있으면, 기본적으로 최신 버전을 기준으로 답변하세요.\n"
        "- 사용자가 특정 날짜를 언급한 경우에만 해당 버전을 인용하세요.\n"
        "- 버전 선택을 위해 ask_user를 호출하지 마세요.\n\n"
        "## 사내 전용 가드레일\n"
        "- 당신은 우리 회사(사내) 전용 어시스턴트입니다. 참고 출처에 있는 문서만 기반으로 답변하세요.\n"
        "- 타사(삼성생명, KB손해보험, DB손해보험, 현대해상, 메리츠 등) 상품을 언급하거나 선택지로 제시하지 마세요.\n"
        "- ask_user의 options에는 반드시 참고 출처에 존재하는 엔티티만 넣으세요. 출처에 없는 보험사/상품을 생성하지 마세요.\n"
        "- 출처에서 해당 정보를 찾을 수 없으면 반드시 '현재 등록된 자료에서 관련 정보를 찾지 못했습니다'라고 안내하세요.\n"
        "- 일반 상식이나 학습된 지식으로 보험 상품/약관을 설명하지 마세요. 오직 참고 출처만 사용하세요.\n\n"
        "## 인용 규칙\n"
        "- 답변 시 정보의 출처를 [1], [2] 형태로 인라인 인용하세요.\n"
        "- 답변 마지막에 '---' 구분선 후 출처 목록을 표기하세요.\n"
        "- 약관/규정의 시행일이 표기되어 있으면 해당 날짜를 명시하세요."
    )
    if user_dept:
        system_prompt += f"\n\n사용자 소속: {user_dept}. 해당 부서에 관련된 사규/매뉴얼이 있으면 우선 참고하세요."
    if source_block:
        system_prompt += f"\n\n참고 출처:\n{source_block}"
    if has_multiple_versions:
        system_prompt += (
            "\n\n참고: 출처에 같은 문서의 여러 버전이 있습니다. 최신 버전을 기준으로 답변하세요."
        )
    if graph_context:
        system_prompt += (
            f"\n\n관련 컨텍스트:\n{graph_context[:1000]}"
        )

    # 세션 메모리 주입
    memory_context = session_mem.get_context_summary(max_entries=5)
    if memory_context:
        system_prompt += f"\n\n{memory_context}"
        system_prompt += (
            "\n\n위는 이 대화에서 이전에 기억한 정보입니다. 답변 시 참고하세요. "
            "대화 중 새로운 중요 정보(고객 정보, 상품 선택, 조건 등)가 나오면 save_memory로 저장하세요."
        )

    # 사용자 커스텀 프롬프트 주입 (글자수 제한 200자)
    if custom_prompt:
        truncated = custom_prompt[:200]
        system_prompt += f"\n\n[사용자 지시사항]\n{truncated}"

    # 시스템 프롬프트 길이 제한 (토큰 ≈ 글자수/2 기준, 여유분 확보)
    if len(system_prompt) > 3000:
        system_prompt = system_prompt[:3000] + "\n\n(컨텍스트 축소됨)"
        logger.info("System prompt truncated to 3000 chars")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    # 이전 대화 히스토리 주입: 롤링 요약 + 최근 턴 (Summary Buffer 패턴)
    if history:
        # 클라이언트가 보낸 history 우선 (기존 호환)
        for h in history[-6:]:
            content = h.get("content", "")
            if len(content) > 300:
                content = content[:300] + "..."
            messages.append({"role": h.get("role", "user"), "content": content})
    else:
        # 서버 저장본에서 요약 + 최근 턴 로드
        _summary, _recent_turns = session_mem.get_history_for_context(recent_k=3)
        if _summary:
            messages.append({
                "role": "user",
                "content": f"[이전 대화 요약]\n{_summary}",
            })
            messages.append({
                "role": "assistant",
                "content": "네, 이전 대화 내용을 참고하겠습니다.",
            })
        for h in _recent_turns:
            content = h.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            messages.append({"role": h.get("role", "user"), "content": content})
    messages.append({"role": "user", "content": query})

    # 사용자 질문을 히스토리에 자동 저장
    session_mem.append_turn("user", query)

    # ── Auto-healing tool calling loop ────────────────────────────────
    max_iterations = 5
    _is_continuation = False
    _full_response_text = ""  # 전체 응답 누적 (히스토리 저장용)
    for _ in range(max_iterations):
        try:
            # continuation 시에는 tools 없이 텍스트만 생성
            _use_tools = tools if (tools and not _is_continuation) else None
            logger.info(
                "LLM request: model=%s, tools=%d, messages=%d, continuation=%s",
                model_name, len(tools), len(messages), _is_continuation,
            )
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=_use_tools,
                tool_choice="auto" if _use_tools else None,
                max_tokens=4096,
                temperature=0.3,
                stream=True,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            _is_continuation = False

            # 스트리밍 응답 처리
            tool_calls_acc: list[dict[str, Any]] = []
            text_acc = ""  # 텍스트 누적 (ask_user fallback 파싱용)
            pending_tokens: list[dict[str, Any]] = []  # 지연 전송 버퍼
            finish_reason: str | None = None
            async for chunk in response:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if not delta:
                    continue

                # 텍스트 토큰 — 즉시 전송하지 않고 버퍼에 누적
                if delta.content:
                    text_acc += delta.content
                    _full_response_text += delta.content
                    pending_tokens.append({"type": "token", "content": delta.content})

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

            # ── 텍스트에서 ask_user 패턴 fallback 파싱 ──
            import re as _re
            _ask_user_pattern = _re.compile(
                r"ask_user\s*(?:호출|call)?\s*[:：]?\s*message\s*=\s*['\"](.+?)['\"]"
                r".*?options\s*=\s*\[(.+?)\]",
                _re.DOTALL,
            )
            text_match = _ask_user_pattern.search(text_acc) if text_acc else None

            if text_match and not tool_calls_acc:
                # LLM이 텍스트로 ask_user를 출력한 경우 → clarification으로 변환
                logger.info("ask_user detected in text output (fallback parsing)")
                msg = text_match.group(1).strip()
                opts_raw = text_match.group(2).strip()

                # options 파싱: {label:'...', value:'...'} 패턴
                opt_pattern = _re.compile(
                    r"\{[^}]*label\s*[:：]\s*['\"]([^'\"]+)['\"]"
                    r"[^}]*value\s*[:：]\s*['\"]([^'\"]+)['\"][^}]*\}"
                )
                options = [
                    {"label": m.group(1), "value": m.group(2)}
                    for m in opt_pattern.finditer(opts_raw)
                ]

                yield {
                    "type": "clarification",
                    "message": msg,
                    "options": options,
                    "allow_custom_input": True,
                }
                session_mem.append_turn("assistant", msg)
                yield {"type": "done"}
                return

            # tool call도 없고 텍스트 fallback도 없으면 → 텍스트 토큰 전송
            if not tool_calls_acc:
                for tok in pending_tokens:
                    yield tok

                # finish_reason이 "length"면 답변이 잘린 것 → 이어서 생성
                if finish_reason == "length" and text_acc:
                    logger.info("Response truncated (finish_reason=length) — continuing")
                    messages.append({"role": "assistant", "content": text_acc})
                    messages.append({"role": "user", "content": "이어서 답변해 주세요."})
                    _is_continuation = True
                    continue  # 루프 재진입 → LLM 재호출 (tools 없이)

                logger.info("No tool calls detected — finishing stream")
                break

            logger.info(
                "Tool calls detected: %s",
                [tc["name"] for tc in tool_calls_acc],
            )

            # ── ask_user 내장 도구 감지 → clarification 이벤트 ──
            ask_user_calls = [tc for tc in tool_calls_acc if tc["name"] == "ask_user"]
            if ask_user_calls:
                tc = ask_user_calls[0]
                try:
                    args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
                except _json.JSONDecodeError:
                    args = {}
                clarification_msg = args.get("message", "추가 정보가 필요합니다.")
                yield {
                    "type": "clarification",
                    "message": clarification_msg,
                    "options": args.get("options", []),
                    "allow_custom_input": args.get("allow_custom_input", True),
                }
                # clarification도 assistant 턴으로 히스토리에 저장
                session_mem.append_turn("assistant", clarification_msg)
                yield {"type": "done"}
                return  # 사용자 응답 대기 — 루프 종료

            # ── 메모리 도구 처리 (save_memory / recall_memory) ──
            memory_calls = [tc for tc in tool_calls_acc if tc["name"] in ("save_memory", "recall_memory")]
            non_memory_calls = [tc for tc in tool_calls_acc if tc["name"] not in ("save_memory", "recall_memory", "ask_user")]

            if memory_calls:
                for mc in memory_calls:
                    try:
                        args = _json.loads(mc["arguments"]) if mc["arguments"] else {}
                    except _json.JSONDecodeError:
                        args = {}

                    if mc["name"] == "save_memory":
                        result = session_mem.save(
                            summary=args.get("summary", "메모"),
                            content=args.get("content", ""),
                            category=args.get("category", "general"),
                        )
                        tool_result = f"기억 저장 완료: #{result['id']} {result['summary']}"
                    else:  # recall_memory
                        keyword = args.get("keyword", "")
                        if keyword:
                            tool_result = session_mem.recall_by_keyword(keyword)
                        else:
                            tool_result = session_mem.recall_all()

                    # assistant message에 tool_call을 넣고 tool result 추가
                    messages.append({
                        "role": "assistant",
                        "tool_calls": [{
                            "id": mc["id"],
                            "type": "function",
                            "function": {"name": mc["name"], "arguments": mc["arguments"]},
                        }],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": mc["id"],
                        "name": mc["name"],
                        "content": tool_result[:500],
                    })

                # 메모리 도구만 호출된 경우 → 루프 재진입하여 답변 생성
                if not non_memory_calls:
                    continue
                # 메모리 + 다른 스킬도 함께 호출된 경우 → 다른 스킬은 아래에서 처리
                tool_calls_acc = non_memory_calls

            # 스킬 한글 이름 매핑
            _SKILL_DISPLAY_NAMES: dict[str, str] = {
                "get-product-spec": "상품 사양 조회",
                "get-coverage": "보장 내용 조회",
                "explain-term": "약관 용어 설명",
                "compare-riders": "특약 비교",
                "search-regulation": "규정/약관 검색",
                "underwriting": "언더라이팅 사전심사",
                "multi-source-rag": "멀티소스 검색",
                "graphrag-search": "지식그래프 검색",
                "vault-search": "문서 검색",
                "vault-read": "문서 읽기",
                "insurance-calculator": "보험료 계산",
                "document-summary": "문서 요약",
                "translate": "번역",
                "draft-email": "이메일 초안",
                "calculate-simple": "간단 계산",
                "translator": "번역",
                "check-claim-status": "청구 상태 조회",
                "validate-customer-info": "고객 정보 검증",
                "send-notification": "알림 발송",
                "generate-report": "리포트 생성",
                "skill-maker": "스킬 생성",
                "calculate-insurance-premium": "보험료 산출",
                "compound-interest": "복리 계산기",
                "save_memory": "기억 저장",
                "recall_memory": "기억 조회",
            }

            def _display_name(name: str) -> str:
                if name in _SKILL_DISPLAY_NAMES:
                    return _SKILL_DISPLAY_NAMES[name]
                # 스킬 레지스트리에서 display_name 조회
                skill_meta = skill_registry.get_skill(name)
                if skill_meta and skill_meta.get("display_name"):
                    return skill_meta["display_name"]
                return name

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

            # 실행 시작 알림
            running_names = [_display_name(tc["name"]) for tc in tool_calls_acc]
            yield {
                "type": "skill_status",
                "status": "running",
                "skills": running_names,
            }

            for tc in tool_calls_acc:
                try:
                    tool = skill_registry.get_tool(tc["name"])
                    if tool:
                        args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
                        result = await tool.ainvoke(args)
                        result_str = str(result)[:1200]
                    else:
                        result_str = (
                            f"'{_display_name(tc['name'])}' 스킬을 사용할 수 없습니다. "
                            "이미 보유한 지식그래프 정보를 활용하여 답변해 주세요."
                        )
                except Exception as exc:
                    logger.warning("Skill %s failed: %s", tc["name"], exc)
                    err_msg = str(exc)
                    if "401" in err_msg or "403" in err_msg or "Unauthorized" in err_msg:
                        result_str = (
                            f"'{_display_name(tc['name'])}' 외부 시스템에 연결할 수 없습니다 (인증 오류). "
                            "이미 보유한 지식그래프 정보를 활용하여 답변해 주세요."
                        )
                    elif "ConnectError" in err_msg or "ConnectionRefused" in err_msg or "timeout" in err_msg.lower():
                        result_str = (
                            f"'{_display_name(tc['name'])}' 외부 시스템에 연결할 수 없습니다 (서버 오프라인). "
                            "이미 보유한 지식그래프 정보를 활용하여 답변해 주세요."
                        )
                    else:
                        result_str = (
                            f"'{_display_name(tc['name'])}' 실행 중 오류가 발생했습니다. "
                            "이미 보유한 지식그래프 정보를 활용하여 답변해 주세요."
                        )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": result_str,
                })

            # 실행 완료 알림
            yield {
                "type": "skill_status",
                "status": "done",
                "skills": running_names,
            }

        except Exception as exc:
            err_str = str(exc)
            logger.error("Tool calling loop error: %s", exc, exc_info=True)
            if "exceed" in err_str.lower() or "context" in err_str.lower() or "n_ctx" in err_str.lower():
                # 컨텍스트 크기 초과 → 메시지 축소 후 재시도
                logger.warning("Context size exceeded — trimming messages and retrying")
                # system prompt 외 오래된 메시지 제거
                if len(messages) > 3:
                    messages = [messages[0]] + messages[-2:]
                    continue
                yield {"type": "token", "content": "\n\n답변이 너무 길어져 요약하여 안내드리겠습니다."}
            else:
                yield {"type": "token", "content": "\n\n죄송합니다. 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."}
            break

    # ── 어시스턴트 응답을 히스토리에 자동 저장 ──────────────────────
    if _full_response_text:
        session_mem.append_turn("assistant", _full_response_text)

    # ── 롤링 요약 생성 (비동기, 백그라운드) ──────────────────────────
    if session_mem.needs_summarization(threshold=6):
        try:
            old_summary, turns_to_summarize = session_mem.get_turns_to_summarize(keep_recent=3)
            if turns_to_summarize:
                await _generate_rolling_summary(client, model_name, old_summary, turns_to_summarize, session_mem)
        except Exception:
            logger.debug("Rolling summary generation failed (non-fatal)", exc_info=True)

    # ── 감사 로그 기록 ──────────────────────────────────────────────
    try:
        from backend.security.audit_trail import log_agent_response
        log_agent_response(
            thread_id=_thread_id,
            user_id=user_id,
            user_roles=user_roles,
            query=query,
            referenced_sources=source_nodes,
            skills_used=[],
            security_grades=[
                sn.get("security_grade", 1) for sn in source_nodes
                if sn.get("security_grade")
            ],
        )
    except Exception:
        logger.debug("Audit log failed (non-fatal)", exc_info=True)

    yield {"type": "done"}


async def _generate_rolling_summary(
    client: Any,
    model_name: str,
    old_summary: str,
    turns: list[dict[str, str]],
    session_mem: Any,
) -> None:
    """오래된 대화 턴들을 요약하여 session_mem에 저장합니다."""
    # 요약 대상 대화를 텍스트로 변환
    conversation_text = ""
    for t in turns:
        role = "사용자" if t.get("role") == "user" else "어시스턴트"
        content = t.get("content", "")[:500]
        conversation_text += f"{role}: {content}\n"

    prompt_parts = ["아래 대화 내용을 핵심만 간결하게 요약해주세요. 200자 이내로 작성하세요.\n"]
    if old_summary:
        prompt_parts.append(f"[기존 요약]\n{old_summary}\n")
    prompt_parts.append(f"[새 대화]\n{conversation_text}")
    prompt_parts.append("\n요약:")

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "당신은 대화를 간결하게 요약하는 어시스턴트입니다. 핵심 정보만 200자 이내로 요약하세요."},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            max_tokens=256,
            temperature=0.1,
            stream=False,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        summary = response.choices[0].message.content.strip()
        if summary:
            session_mem.save_summary(summary)
            logger.info("Rolling summary generated: thread=%s, len=%d", session_mem.thread_id, len(summary))
    except Exception as exc:
        logger.warning("Rolling summary LLM call failed: %s", exc)


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
