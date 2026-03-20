"""LangGraph 노드 구현."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.language_models.chat_models import BaseChatModel

from backend.agents.skill_parser import SkillRegistry
from backend.security.prompt_guard import sanitize_input

logger = logging.getLogger(__name__)

# ── Retry constants ────────────────────────────────────────────────────────────
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 1.0  # seconds; doubled on each retry


async def route_node(state: dict, llm: BaseChatModel, registry: SkillRegistry) -> dict:
    """사용자 의도를 파악하고 필요한 스킬을 식별.

    Runs prompt injection detection on the latest user message before forwarding
    to the LLM.  If injection is detected the node short-circuits with an error
    state so the graph can respond gracefully without calling the model.
    """
    # ── Prompt injection guard ─────────────────────────────────────────────
    last_message = state["messages"][-1] if state.get("messages") else None
    raw_text = getattr(last_message, "content", "") if last_message else ""
    try:
        sanitize_input(raw_text)
    except ValueError as exc:
        logger.warning("Prompt injection detected for user=%s: %s", state.get("user_id"), exc)
        return {
            **state,
            "error": f"Prompt injection detected: {exc}",
            "reasoning": "{}",
        }

    available = registry.list_skills()
    skill_desc = "\n".join(f"- {s['name']}: {s['description']}" for s in available)

    prompt = (
        f"사용 가능한 스킬:\n{skill_desc}\n\n"
        f"사용자 요청을 분석하여 필요한 스킬과 실행 순서를 JSON으로 응답하세요.\n"
        f'형식: {{"skills": [{{"name": "...", "params": {{}}, "reason": "..."}}]}}'
    )
    messages = state["messages"] + [{"role": "system", "content": prompt}]
    response = await llm.ainvoke(messages)

    return {**state, "reasoning": response.content}


def _topological_sort(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *nodes* ordered so that each skill's dependencies appear before it.

    Uses Kahn's algorithm (BFS-based).  Nodes whose ``depends_on`` list
    references skills not present in the current plan are treated as having no
    dependency on those missing skills (best-effort).

    Args:
        nodes: List of plan dicts each containing ``skill_name`` and
               ``depends_on`` (list of skill name strings).

    Returns:
        Topologically sorted list.  If a cycle is detected the original order
        is returned and a warning is logged.
    """
    name_to_node: dict[str, dict[str, Any]] = {n["skill_name"]: n for n in nodes}
    known = set(name_to_node)

    # Build in-degree map and adjacency list
    in_degree: dict[str, int] = {n: 0 for n in known}
    dependents: dict[str, list[str]] = defaultdict(list)  # dep -> [skill that needs dep]

    for node in nodes:
        for dep in node.get("depends_on", []):
            if dep in known:
                in_degree[node["skill_name"]] += 1
                dependents[dep].append(node["skill_name"])

    queue: deque[str] = deque(name for name, deg in in_degree.items() if deg == 0)
    sorted_names: list[str] = []

    while queue:
        current = queue.popleft()
        sorted_names.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(sorted_names) != len(nodes):
        logger.warning(
            "Dependency cycle detected in skill plan; falling back to original order. "
            "Involved skills: %s",
            [n for n in known if n not in sorted_names],
        )
        return nodes

    return [name_to_node[name] for name in sorted_names]


async def plan_node(state: dict, llm: BaseChatModel, registry: SkillRegistry) -> dict:
    """의존성 그래프를 해석하여 실행 계획을 수립.

    Parses the LLM reasoning JSON, resolves each skill via the registry (which
    carries authoritative ``depends_on`` metadata), then runs a topological sort
    so that dependency skills are always executed before the skills that require
    them.
    """
    import json  # noqa: PLC0415 — avoid circular import at module level

    # Short-circuit if an upstream error was already set (e.g. prompt injection)
    if state.get("error"):
        return {**state, "plan": [], "current_step": 0}

    try:
        reasoning = state.get("reasoning", "{}")
        plan_data = json.loads(reasoning)
        skills = plan_data.get("skills", [])
    except (json.JSONDecodeError, KeyError):
        skills = []

    # Build raw plan using registry metadata for authoritative depends_on
    raw_plan: list[dict[str, Any]] = []
    for skill_info in skills:
        skill_meta = registry.get_skill(skill_info.get("name", ""))
        if skill_meta:
            raw_plan.append({
                "skill_name": skill_meta["name"],
                "params": skill_info.get("params", {}),
                "depends_on": skill_meta.get("depends_on", []),
                "endpoint": skill_meta.get("endpoint", ""),
            })

    # Apply topological sort to honour dependency order
    sorted_plan = _topological_sort(raw_plan)
    logger.info(
        "Execution plan for user=%s: %s",
        state.get("user_id"),
        [s["skill_name"] for s in sorted_plan],
    )

    return {**state, "plan": sorted_plan, "current_step": 0}


async def execute_skill_node(state: dict, registry: SkillRegistry) -> dict:
    """현재 단계의 스킬을 실행.

    Retry policy:
        Up to ``_MAX_RETRIES`` attempts with exponential backoff
        (``_RETRY_BACKOFF_BASE * 2^attempt`` seconds between tries).

    Tracking:
        ``input_size_bytes`` and ``output_size_bytes`` are added to every log
        entry so downstream analytics can detect unexpectedly large payloads.
    """
    plan = state.get("plan", [])
    step = state.get("current_step", 0)
    log = list(state.get("execution_log", []))

    if step >= len(plan):
        return state

    current = plan[step]
    params = current.get("params", {})
    start_time = datetime.now(timezone.utc)

    # ── Resolve tool ───────────────────────────────────────────────────────
    tool = registry.get_tool(current["skill_name"])
    if tool is None:
        err_msg = f"Skill not found: {current['skill_name']}"
        logger.error(err_msg)
        log.append({
            "step": step,
            "skill": current["skill_name"],
            "input": params,
            "input_size_bytes": len(str(params).encode()),
            "output": None,
            "output_size_bytes": 0,
            "status": "error",
            "error": err_msg,
            "attempts": 0,
            "started_at": start_time.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "executor": state.get("user_id", "unknown"),
        })
        return {**state, "execution_log": log, "error": err_msg}

    # ── Execute with retries ───────────────────────────────────────────────
    last_exc: Exception | None = None
    result_str: str | None = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt > 0:
            backoff = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                "Retrying skill %s (attempt %d/%d) after %.1fs backoff",
                current["skill_name"], attempt, _MAX_RETRIES, backoff,
            )
            await asyncio.sleep(backoff)

        try:
            result = await tool.ainvoke(params)
            result_str = str(result)
            last_exc = None
            break  # success – exit retry loop
        except Exception as exc:
            logger.error(
                "Skill %s attempt %d failed: %s",
                current["skill_name"], attempt + 1, exc,
            )
            last_exc = exc

    completed_at = datetime.now(timezone.utc).isoformat()
    input_size = len(str(params).encode())

    if last_exc is not None:
        # All attempts exhausted
        log.append({
            "step": step,
            "skill": current["skill_name"],
            "input": params,
            "input_size_bytes": input_size,
            "output": None,
            "output_size_bytes": 0,
            "status": "error",
            "error": str(last_exc),
            "attempts": _MAX_RETRIES + 1,
            "started_at": start_time.isoformat(),
            "completed_at": completed_at,
            "executor": state.get("user_id", "unknown"),
        })
        return {**state, "execution_log": log, "error": str(last_exc)}

    log.append({
        "step": step,
        "skill": current["skill_name"],
        "input": params,
        "input_size_bytes": input_size,
        "output": result_str,
        "output_size_bytes": len((result_str or "").encode()),
        "status": "success",
        "attempts": attempt + 1,
        "started_at": start_time.isoformat(),
        "completed_at": completed_at,
        "executor": state.get("user_id", "unknown"),
    })
    return {**state, "execution_log": log, "current_step": step + 1}


def should_continue(state: dict) -> str:
    """다음 스킬 실행 여부 판단."""
    if state.get("error"):
        return "error"
    plan = state.get("plan", [])
    step = state.get("current_step", 0)
    return "continue" if step < len(plan) else "done"


async def audit_node(state: dict) -> dict:
    """실행 결과를 감사 로그로 기록.

    Writes one ``agent_audit_log`` row per execution log entry directly to
    SQLite via :func:`~backend.agents.checkpointer.write_audit_record`.
    The table is created on first use by
    :func:`~backend.agents.checkpointer.init_audit_db`.

    The write is non-fatal: failures are logged as errors but the graph
    continues so that a DB hiccup never blocks the user response.
    """
    # Import here to avoid circular imports at module load time
    from backend.agents.checkpointer import write_audit_records  # noqa: PLC0415

    execution_log = state.get("execution_log", [])
    user_id = state.get("user_id", "unknown")
    thread_id = state.get("thread_id", "")
    reasoning = state.get("reasoning", "")

    logger.info(
        "Audit: user=%s thread=%s steps=%d",
        user_id,
        thread_id,
        len(execution_log),
    )

    try:
        records = [
            {
                "thread_id": thread_id,
                "user_id": user_id,
                "step": entry.get("step", 0),
                "skill_name": entry.get("skill"),
                "input_payload": entry.get("input"),
                "output_payload": entry.get("output"),
                "status": entry.get("status", "unknown"),
                "reasoning": reasoning,
                "started_at": entry.get("started_at"),
                "completed_at": entry.get("completed_at"),
            }
            for entry in execution_log
        ]
        if records:
            write_audit_records(records)
    except Exception as exc:  # noqa: BLE001
        logger.error("Audit DB write failed (non-fatal): %s", exc)

    return state


async def respond_node(state: dict, llm: BaseChatModel) -> dict:
    """실행 결과를 자연어 응답으로 변환.

    When failures are present in the execution log this node builds a
    structured error report section that:

    * Lists every failed step with its skill name and error message.
    * Gives the user explicit actionable guidance (retry hint, permission
      note, or injection-blocked notice).
    * Passes the full context to the LLM so it can synthesise a natural
      language explanation.
    """
    log = state.get("execution_log", [])
    error = state.get("error")

    # ── Build execution summary ────────────────────────────────────────────
    summary_lines: list[str] = ["실행 결과 요약:"]
    failed_steps: list[dict[str, Any]] = []

    for entry in log:
        ok = entry["status"] == "success"
        marker = "OK" if ok else "FAIL"
        attempts = entry.get("attempts", 1)
        input_sz = entry.get("input_size_bytes", 0)
        output_sz = entry.get("output_size_bytes", 0)
        summary_lines.append(
            f"[{marker}] Step {entry['step']}: {entry['skill']} "
            f"(attempts={attempts}, in={input_sz}B, out={output_sz}B)"
        )
        if ok and entry.get("output"):
            summary_lines.append(f"  Output: {str(entry['output'])[:200]}")
        if not ok:
            summary_lines.append(f"  Error: {entry.get('error', 'unknown error')}")
            failed_steps.append(entry)

    summary = "\n".join(summary_lines)

    # ── Structured error report ────────────────────────────────────────────
    error_report = ""
    if failed_steps or error:
        report_lines: list[str] = [
            "",
            "=== 오류 보고서 ===",
        ]

        # Prompt injection is a special case with its own user guidance
        if error and "Prompt injection" in error:
            report_lines += [
                "보안 경고: 입력에 금지된 패턴이 감지되어 실행이 차단되었습니다.",
                "조치 방법:",
                "  - 요청을 다시 작성하여 명령 지시 패턴을 제거하세요.",
                "  - 일반 질문이나 작업 요청 형식으로 입력하세요.",
            ]
        else:
            for fs in failed_steps:
                report_lines.append(
                    f"- 스킬 '{fs['skill']}' (Step {fs['step']}) 실패: {fs.get('error', '알 수 없는 오류')}"
                )
            if error:
                report_lines.append(f"- 최종 오류: {error}")
            report_lines += [
                "",
                "권장 조치:",
                "  1. 잠시 후 다시 시도하세요 (일시적 오류일 수 있습니다).",
                "  2. 요청한 스킬에 대한 권한이 있는지 확인하세요.",
                "  3. 입력 매개변수가 올바른지 검토하세요.",
                "  4. 문제가 지속되면 관리자에게 문의하세요.",
            ]

        error_report = "\n".join(report_lines)

    # ── LLM synthesis ─────────────────────────────────────────────────────
    system_content = (
        f"다음 실행 결과를 사용자에게 자연어로 친절하게 설명하세요.\n"
        f"오류가 있을 경우 사용자가 무엇을 해야 하는지 명확하게 안내하세요.\n\n"
        f"{summary}{error_report}"
    )
    messages = state["messages"] + [{"role": "system", "content": system_content}]
    response = await llm.ainvoke(messages)

    return {
        **state,
        "messages": state["messages"] + [AIMessage(content=response.content)],
    }
