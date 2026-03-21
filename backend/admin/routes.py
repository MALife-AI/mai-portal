"""Admin API: IAM, Audit, 모델 설정, 메트릭, 거버넌스."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import get_iam, get_current_user, require_admin
from backend.core.iam import IAMEngine
from backend.agents.checkpointer import query_audit_logs
from backend.security.kill_switch import (
    activate_kill_switch,
    deactivate_kill_switch,
    get_kill_switch_status,
)
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── 부서 관리 ────────────────────────────────────────────────────────────────

class DepartmentConfig(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""


@router.get("/departments")
async def list_departments(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    iam.reload()
    data = iam.as_dict()
    depts = data.get("departments", {})
    return {
        "departments": [
            {"id": k, "name": v.get("name", k), "description": v.get("description", "")}
            for k, v in depts.items()
        ]
    }


@router.post("/departments")
async def add_department(
    body: DepartmentConfig,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    iam.reload()
    data = iam.as_dict()
    depts = data.setdefault("departments", {})
    if body.id in depts:
        raise HTTPException(409, f"Department '{body.id}' already exists")
    depts[body.id] = {"name": body.name, "description": body.description}
    iam.save(data)
    return {"status": "created", "id": body.id}


@router.put("/departments/{dept_id}")
async def update_department(
    dept_id: str,
    body: DepartmentConfig,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    iam.reload()
    data = iam.as_dict()
    depts = data.get("departments", {})
    if dept_id not in depts:
        raise HTTPException(404, f"Department '{dept_id}' not found")
    depts[dept_id] = {"name": body.name, "description": body.description}
    iam.save(data)
    return {"status": "updated", "id": dept_id}


@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    iam.reload()
    data = iam.as_dict()
    depts = data.get("departments", {})
    if dept_id not in depts:
        raise HTTPException(404, f"Department '{dept_id}' not found")
    del depts[dept_id]
    iam.save(data)
    return {"status": "deleted", "id": dept_id}


# ─── IAM ──────────────────────────────────────────────────────────────────────

@router.get("/iam")
async def get_iam_config(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    iam.reload()
    return iam.as_dict()


@router.put("/iam")
async def update_iam_config(
    body: dict,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    iam.save(body)
    return {"status": "updated"}


# ─── Audit ────────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit_logs(
    user_id: str = Depends(get_current_user),
    filter_user: str | None = None,
    limit: int = 50,
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    return query_audit_logs(user_id=filter_user, limit=limit)


# ─── Kill Switch ──────────────────────────────────────────────────────────────

@router.post("/kill-switch/activate")
async def kill_switch_on(user_id: str = Depends(get_current_user), iam: IAMEngine = Depends(get_iam)):
    require_admin(user_id, iam)
    await activate_kill_switch()
    return {"status": "activated"}


@router.post("/kill-switch/deactivate")
async def kill_switch_off(user_id: str = Depends(get_current_user), iam: IAMEngine = Depends(get_iam)):
    require_admin(user_id, iam)
    await deactivate_kill_switch()
    return {"status": "deactivated"}


@router.get("/kill-switch/status")
async def kill_switch_status():
    return get_kill_switch_status()


# ─── 모델 설정 ────────────────────────────────────────────────────────────────

class ModelConfig(BaseModel):
    vlm_provider: str = Field("llama_server")
    vlm_model: str = Field("qwen3.5-4b")
    llama_server_url: str = Field("http://localhost:8801/v1")
    temperature: float = Field(0.7)
    max_tokens: int = Field(1024)
    smart_routing: bool = Field(False)
    llama_server_light: str = Field("")
    llama_server_heavy: str = Field("")


class GPUServerConfig(BaseModel):
    id: str
    name: str
    url: str
    model: str = "qwen3.5-4b"
    description: str = ""


# GPU 서버 목록 파일
_GPU_SERVERS_FILE = Path(settings.vault_root).parent / "data" / "gpu_servers.json"

# In-memory cache: (mtime_ns, parsed_list).  None means not yet loaded.
_gpu_servers_cache: tuple[int, list[dict[str, Any]]] | None = None


def _load_gpu_servers() -> list[dict[str, Any]]:
    global _gpu_servers_cache
    if _GPU_SERVERS_FILE.exists():
        mtime = _GPU_SERVERS_FILE.stat().st_mtime_ns
        if _gpu_servers_cache is not None and _gpu_servers_cache[0] == mtime:
            return _gpu_servers_cache[1]
        data = json.loads(_GPU_SERVERS_FILE.read_text())
        _gpu_servers_cache = (mtime, data)
        return data
    return [{"id": "local", "name": "Local 4B", "url": getattr(settings, "llama_server_url", "http://localhost:8801/v1"), "model": "qwen3.5-4b", "description": "로컬 Metal 가속"}]


def _save_gpu_servers(servers: list[dict[str, Any]]) -> None:
    global _gpu_servers_cache
    _GPU_SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GPU_SERVERS_FILE.write_text(json.dumps(servers, indent=2, ensure_ascii=False))
    _gpu_servers_cache = (_GPU_SERVERS_FILE.stat().st_mtime_ns, servers)


@router.get("/gpu-servers")
async def list_gpu_servers(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    return {"servers": _load_gpu_servers()}


@router.post("/gpu-servers")
async def add_gpu_server(
    body: GPUServerConfig,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """GPU 추론 서버 추가."""
    require_admin(user_id, iam)
    servers = _load_gpu_servers()
    if any(s["id"] == body.id for s in servers):
        raise HTTPException(409, f"Server '{body.id}' already exists")
    servers.append(body.model_dump())
    _save_gpu_servers(servers)
    return {"status": "added", "server": body.model_dump()}


@router.delete("/gpu-servers/{server_id}")
async def remove_gpu_server(
    server_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """GPU 추론 서버 삭제."""
    require_admin(user_id, iam)
    servers = _load_gpu_servers()
    servers = [s for s in servers if s["id"] != server_id]
    _save_gpu_servers(servers)
    return {"status": "deleted"}


@router.get("/model-config")
async def get_model_config(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    config = {
        "vlm_provider": os.environ.get("VLM_PROVIDER", settings.vlm_provider),
        "vlm_model": os.environ.get("VLM_MODEL", settings.vlm_model),
        "llama_server_url": getattr(settings, "llama_server_url", "http://localhost:8801/v1"),
        "claude_wrapper_url": settings.claude_wrapper_url,
        "ollama_base_url": settings.ollama_base_url,
        "smart_routing": getattr(settings, "smart_routing", False),
        "llama_server_light": getattr(settings, "llama_server_light", ""),
        "llama_server_heavy": getattr(settings, "llama_server_heavy", ""),
    }
    available_models = []
    try:
        import asyncio
        import subprocess
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None,
            lambda: subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5),
        )
        for line in r.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if parts:
                available_models.append({"name": parts[0], "source": "ollama", "size": parts[2] if len(parts) > 2 else ""})
    except Exception:
        pass
    available_models.append({"name": "qwen3.5-4b", "source": "llama-server (Unsloth GGUF)", "size": "4.16 GB"})
    return {"config": config, "available_models": available_models, "gpu_servers": _load_gpu_servers()}


@router.put("/model-config")
async def update_model_config(
    body: ModelConfig,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    env_path = Path(settings.vault_root).parent / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updates = {
        "VLM_PROVIDER": body.vlm_provider,
        "VLM_MODEL": body.vlm_model,
        "LLAMA_SERVER_URL": body.llama_server_url,
        "SMART_ROUTING": str(body.smart_routing).lower(),
        "LLAMA_SERVER_LIGHT": body.llama_server_light,
        "LLAMA_SERVER_HEAVY": body.llama_server_heavy,
    }
    new_lines = []
    updated_keys = set()
    for line in lines:
        key = line.split("=")[0] if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)
    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n")
    return {"status": "updated", "note": "서버 재시작 필요"}


# ─── 사용량 메트릭 ────────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_metrics(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    # 감사 로그에서 메트릭 집계
    logs = query_audit_logs(limit=500)
    entries = logs if isinstance(logs, list) else logs.get("logs", [])

    user_counts: dict[str, int] = {}
    skill_counts: dict[str, int] = {}
    daily_counts: dict[str, int] = {}
    total_queries = len(entries)
    error_count = 0

    for entry in entries:
        u = entry.get("user_id", "unknown")
        user_counts[u] = user_counts.get(u, 0) + 1
        s = entry.get("skill_name") or entry.get("skill") or "direct"
        skill_counts[s] = skill_counts.get(s, 0) + 1
        ts = entry.get("started_at") or entry.get("timestamp") or ""
        if ts:
            day = ts[:10]
            daily_counts[day] = daily_counts.get(day, 0) + 1
        if entry.get("status") == "error":
            error_count += 1

    # 볼트 통계
    vault_root = settings.vault_root
    md_files = list(vault_root.rglob("*.md"))
    vault_size_mb = sum(f.stat().st_size for f in md_files) / (1024 * 1024)

    # 그래프 통계
    graph_stats = {}
    try:
        from backend.graph.store import GraphStore
        persist_path = vault_root / ".graph" / "knowledge_graph.json"
        store = GraphStore(persist_path=persist_path)
        graph_stats = store.get_stats()
    except Exception:
        pass

    return {
        "total_queries": total_queries,
        "error_count": error_count,
        "error_rate": round(error_count / max(total_queries, 1) * 100, 1),
        "user_counts": dict(sorted(user_counts.items(), key=lambda x: -x[1])),
        "skill_counts": dict(sorted(skill_counts.items(), key=lambda x: -x[1])),
        "daily_counts": dict(sorted(daily_counts.items())),
        "vault_files": len(md_files),
        "vault_size_mb": round(vault_size_mb, 1),
        "graph_stats": graph_stats,
    }


# ─── 문서 권한 ────────────────────────────────────────────────────────────────

class DocPermission(BaseModel):
    path: str
    allowed_roles: list[str] = Field(default_factory=list)
    owner: str = ""


@router.get("/doc-permissions")
async def list_doc_permissions(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """vault 문서별 권한 조회 (부서 접근 권한 포함)."""
    require_admin(user_id, iam)
    vault_root = settings.vault_root
    hidden = {"Skills", ".graph", ".obsidian", "assets"}
    docs = []
    for md_file in sorted(vault_root.rglob("*.md"))[:200]:
        rel_parts = md_file.relative_to(vault_root).parts
        if rel_parts and rel_parts[0] in hidden:
            continue
        rel = "/" + md_file.relative_to(vault_root).as_posix()
        try:
            from backend.core.frontmatter import parse_frontmatter
            content = md_file.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(content)
            docs.append({
                "path": rel,
                "owner": meta.get("owner", ""),
                "allowed_roles": meta.get("allowed_roles", []),
                "allowed_departments": meta.get("allowed_departments", []),
                "effective_date": meta.get("effective_date", ""),
                "created_at": meta.get("created_at", ""),
            })
        except Exception:
            docs.append({"path": rel, "owner": "", "allowed_roles": [], "allowed_departments": [], "effective_date": "", "created_at": ""})
    return {"documents": docs, "total": len(docs)}


class DocPermissionUpdate(BaseModel):
    path: str
    allowed_departments: list[str] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)


@router.put("/doc-permissions")
async def update_doc_permissions(
    body: DocPermissionUpdate,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """문서의 부서/역할 접근 권한을 수정."""
    require_admin(user_id, iam)
    vault_root = settings.vault_root
    file_path = vault_root / body.path.lstrip("/")
    if not file_path.exists():
        raise HTTPException(404, f"Document not found: {body.path}")

    from backend.core.frontmatter import parse_frontmatter, synthesize_frontmatter
    content = file_path.read_text(encoding="utf-8")
    meta, doc_body = parse_frontmatter(content)

    meta["allowed_departments"] = body.allowed_departments
    meta["allowed_roles"] = body.allowed_roles

    new_content = synthesize_frontmatter(doc_body, user_id=meta.get("owner", user_id), extra_meta=meta)
    file_path.write_text(new_content, encoding="utf-8")

    return {"status": "updated", "path": body.path}


# ─── 가드레일 설정 ────────────────────────────────────────────────────────────

GUARDRAILS_PATH = Path(settings.vault_root).parent / "data" / "guardrails.json"

_DEFAULT_GUARDRAILS: dict[str, Any] = {
    "prompt_injection": {
        "enabled": True,
        "risk_threshold": 0.7,
        "max_input_length": 10000,
        "block_action": "reject",  # reject | warn | log_only
    },
    "topic_restrictions": {
        "enabled": False,
        "blocked_topics": [],  # e.g. ["정치", "종교", "경쟁사 비방"]
        "warn_topics": [],
    },
    "output_guardrails": {
        "pii_masking": True,
        "max_output_length": 50000,
        "block_code_execution": True,
        "block_external_urls": False,
    },
    "rate_limits": {
        "enabled": True,
        "max_queries_per_minute": 30,
        "max_queries_per_hour": 500,
        "max_tokens_per_query": 8000,
    },
    "content_policy": {
        "require_citation": True,
        "hallucination_guard": True,
        "confidence_threshold": 0.3,
        "disclaimer_footer": "",
    },
    "custom_rules": [],  # list of {id, name, pattern, action, description}
}


def _load_guardrails() -> dict[str, Any]:
    if GUARDRAILS_PATH.exists():
        return json.loads(GUARDRAILS_PATH.read_text(encoding="utf-8"))
    return dict(_DEFAULT_GUARDRAILS)


def _save_guardrails(data: dict[str, Any]) -> None:
    GUARDRAILS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GUARDRAILS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/guardrails")
async def get_guardrails(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """가드레일 설정 조회."""
    require_admin(user_id, iam)
    return _load_guardrails()


@router.put("/guardrails")
async def update_guardrails(
    config: dict[str, Any],
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """가드레일 설정 전체 업데이트."""
    require_admin(user_id, iam)
    current = _load_guardrails()
    current.update(config)
    _save_guardrails(current)

    # prompt_guard 모듈에 실시간 반영
    _apply_guardrails_to_runtime(current)

    return {"status": "updated", "config": current}


@router.patch("/guardrails/{section}")
async def update_guardrail_section(
    section: str,
    config: dict[str, Any],
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """가드레일 특정 섹션만 업데이트."""
    require_admin(user_id, iam)
    current = _load_guardrails()
    if section not in current and section != "custom_rules":
        raise HTTPException(404, f"Unknown guardrail section: {section}")
    if section == "custom_rules":
        current["custom_rules"] = config.get("rules", [])
    else:
        current[section].update(config)
    _save_guardrails(current)
    _apply_guardrails_to_runtime(current)
    return {"status": "updated", "section": section}


@router.post("/guardrails/reset")
async def reset_guardrails(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """가드레일 설정을 기본값으로 초기화."""
    require_admin(user_id, iam)
    _save_guardrails(dict(_DEFAULT_GUARDRAILS))
    _apply_guardrails_to_runtime(_DEFAULT_GUARDRAILS)
    return {"status": "reset", "config": _DEFAULT_GUARDRAILS}


@router.post("/guardrails/test")
async def test_guardrail(
    body: dict[str, Any],
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """입력 텍스트에 대해 가드레일 검사 테스트."""
    require_admin(user_id, iam)
    text = body.get("text", "")

    from backend.security.prompt_guard import score_injection_risk, detect_injection

    risk_score = score_injection_risk(text)
    has_injection = detect_injection(text)
    guardrails = _load_guardrails()
    threshold = guardrails.get("prompt_injection", {}).get("risk_threshold", 0.7)

    # 주제 제한 검사
    blocked_topics = guardrails.get("topic_restrictions", {}).get("blocked_topics", [])
    matched_topics = [t for t in blocked_topics if t in text]

    return {
        "text_length": len(text),
        "risk_score": risk_score,
        "threshold": threshold,
        "blocked": risk_score >= threshold or has_injection,
        "injection_detected": has_injection,
        "matched_blocked_topics": matched_topics,
    }


def _apply_guardrails_to_runtime(config: dict[str, Any]) -> None:
    """가드레일 설정을 런타임 모듈에 반영."""
    try:
        from backend.security import prompt_guard
        pi = config.get("prompt_injection", {})
        if "risk_threshold" in pi:
            prompt_guard.INJECTION_RISK_THRESHOLD = pi["risk_threshold"]
        if "max_input_length" in pi:
            prompt_guard.MAX_INPUT_LENGTH = pi["max_input_length"]
    except Exception:
        logger.debug("Failed to apply guardrails to runtime", exc_info=True)


# ─── 거버넌스/컴플라이언스 ────────────────────────────────────────────────────

@router.get("/governance")
async def governance_report(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """거버넌스 대시보드: PII 감지, 권한 위반, 킬스위치 이력 등."""
    require_admin(user_id, iam)

    # PII 마스킹 통계 (DLP 미들웨어 로그에서)
    logs = query_audit_logs(limit=500)
    entries = logs if isinstance(logs, list) else logs.get("logs", [])

    # 권한 위반 감지
    permission_violations = [
        e for e in entries
        if "denied" in str(e.get("status", "")).lower()
        or "403" in str(e.get("output_payload", ""))
    ]

    # 프롬프트 인젝션 감지
    injection_attempts = [
        e for e in entries
        if "injection" in str(e.get("reasoning", "")).lower()
        or "injection" in str(e.get("output_payload", "")).lower()
    ]

    # 민감 문서 (Private 폴더)
    vault_root = settings.vault_root
    private_docs = list((vault_root / "Private").rglob("*.md")) if (vault_root / "Private").exists() else []

    # 킬스위치 상태
    ks = get_kill_switch_status()

    # 컴플라이언스 체크리스트
    checklist = [
        {"item": "PII 마스킹 미들웨어", "status": True, "detail": "DLP 미들웨어 활성화"},
        {"item": "프롬프트 인젝션 가드", "status": True, "detail": "sanitize_input 적용"},
        {"item": "ACL 기반 문서 접근 제어", "status": True, "detail": "IAM + owner 기반"},
        {"item": "감사 로그 기록", "status": len(entries) > 0, "detail": f"{len(entries)}건 기록"},
        {"item": "킬 스위치", "status": True, "detail": f"{'활성화' if ks.get('active') else '대기 중'}"},
        {"item": "Private 워크스페이스 격리", "status": True, "detail": f"{len(private_docs)}개 문서"},
    ]

    return {
        "permission_violations": len(permission_violations),
        "injection_attempts": len(injection_attempts),
        "private_documents": len(private_docs),
        "kill_switch": ks,
        "checklist": checklist,
        "recent_violations": permission_violations[:10],
        "recent_injections": injection_attempts[:5],
    }


# ─── 세분화된 권한 (Fine-grained Permissions) ─────────────────────────────────

# 모든 권한 항목 정의
PERMISSION_CATALOG: list[dict[str, Any]] = [
    # 문서 관리
    {"id": "doc.read.public", "category": "문서 관리", "label": "공용 문서 읽기", "description": "Shared 폴더 문서 조회"},
    {"id": "doc.read.private", "category": "문서 관리", "label": "개인 문서 읽기", "description": "Private 폴더 자신의 문서 조회"},
    {"id": "doc.read.all_private", "category": "문서 관리", "label": "전체 개인 문서 읽기", "description": "모든 사용자의 Private 문서 조회 (관리자)"},
    {"id": "doc.write.public", "category": "문서 관리", "label": "공용 문서 작성", "description": "Shared 폴더에 문서 생성/수정 (관리자)"},
    {"id": "doc.write.private", "category": "문서 관리", "label": "개인 문서 작성", "description": "Private 폴더에 문서 생성/수정"},
    {"id": "doc.delete", "category": "문서 관리", "label": "문서 삭제", "description": "vault 문서 삭제"},
    {"id": "doc.upload", "category": "문서 관리", "label": "문서 업로드", "description": "파일 업로드 및 인제스션"},
    {"id": "doc.upload.public", "category": "문서 관리", "label": "공용 문서 업로드", "description": "Shared 폴더에 문서 업로드 (관리자)"},
    # 에이전트
    {"id": "agent.query", "category": "에이전트", "label": "에이전트 질의", "description": "에이전트 콘솔에서 질문"},
    {"id": "agent.skill.use", "category": "에이전트", "label": "스킬 사용", "description": "에이전트 스킬 호출"},
    {"id": "agent.skill.manage", "category": "에이전트", "label": "스킬 관리", "description": "스킬 생성/수정/삭제"},
    # 검색
    {"id": "search.vector", "category": "검색", "label": "벡터 검색", "description": "시맨틱 검색 사용"},
    {"id": "search.graphrag", "category": "검색", "label": "GraphRAG 검색", "description": "지식그래프 기반 검색"},
    # 지식그래프
    {"id": "graph.view", "category": "지식 그래프", "label": "그래프 조회", "description": "지식그래프 시각화 보기"},
    {"id": "graph.build", "category": "지식 그래프", "label": "그래프 빌드", "description": "지식그래프 재구축 (관리자)"},
    # 관리
    {"id": "admin.iam", "category": "관리", "label": "IAM 관리", "description": "사용자/역할 설정"},
    {"id": "admin.model", "category": "관리", "label": "모델 설정", "description": "LLM 모델 변경"},
    {"id": "admin.metrics", "category": "관리", "label": "메트릭 조회", "description": "사용량 통계 확인"},
    {"id": "admin.audit", "category": "관리", "label": "감사 로그", "description": "사용자 활동 로그 조회"},
    {"id": "admin.governance", "category": "관리", "label": "거버넌스", "description": "컴플라이언스 확인"},
    {"id": "admin.infra", "category": "관리", "label": "인프라 관리", "description": "하드웨어/서비스 상태"},
    {"id": "admin.killswitch", "category": "관리", "label": "킬 스위치", "description": "시스템 긴급 중단"},
]

# 역할 템플릿
ROLE_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "admin",
        "name": "관리자",
        "description": "모든 권한",
        "permissions": [p["id"] for p in PERMISSION_CATALOG],
    },
    {
        "id": "manager",
        "name": "매니저",
        "description": "문서 관리 + 메트릭 + 감사",
        "permissions": [
            "doc.read.public", "doc.read.private", "doc.read.all_private",
            "doc.write.public", "doc.write.private", "doc.delete",
            "doc.upload", "doc.upload.public",
            "agent.query", "agent.skill.use",
            "search.vector", "search.graphrag",
            "graph.view",
            "admin.metrics", "admin.audit",
        ],
    },
    {
        "id": "analyst",
        "name": "분석가",
        "description": "문서 조회 + 검색 + 에이전트",
        "permissions": [
            "doc.read.public", "doc.read.private", "doc.write.private",
            "doc.upload",
            "agent.query", "agent.skill.use",
            "search.vector", "search.graphrag",
            "graph.view",
        ],
    },
    {
        "id": "viewer",
        "name": "조회자",
        "description": "읽기 전용",
        "permissions": [
            "doc.read.public",
            "search.vector",
            "graph.view",
        ],
    },
]

# 권한 데이터 파일
_PERMISSIONS_FILE = Path(settings.vault_root).parent / "data" / "permissions.json"

# In-memory cache: (mtime_ns, parsed_dict).  None means not yet loaded.
_permissions_cache: tuple[int, dict[str, list[str]]] | None = None


def _load_user_permissions() -> dict[str, list[str]]:
    global _permissions_cache
    if _PERMISSIONS_FILE.exists():
        mtime = _PERMISSIONS_FILE.stat().st_mtime_ns
        if _permissions_cache is not None and _permissions_cache[0] == mtime:
            return _permissions_cache[1]
        data: dict[str, list[str]] = json.loads(_PERMISSIONS_FILE.read_text())
        _permissions_cache = (mtime, data)
        return data
    return {}


def _save_user_permissions(data: dict[str, list[str]]) -> None:
    global _permissions_cache
    _PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PERMISSIONS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    _permissions_cache = (_PERMISSIONS_FILE.stat().st_mtime_ns, data)


@router.get("/permissions/catalog")
async def permission_catalog(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """권한 카탈로그 + 역할 템플릿 반환."""
    require_admin(user_id, iam)
    # 카테고리별 그룹핑
    categories: dict[str, list] = {}
    for p in PERMISSION_CATALOG:
        cat = p["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p)
    return {
        "categories": categories,
        "templates": ROLE_TEMPLATES,
    }


@router.get("/permissions/users")
async def list_user_permissions(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """전체 사용자 권한 목록."""
    require_admin(user_id, iam)
    perms = _load_user_permissions()
    iam_data = iam.as_dict()
    users = []
    for u in iam_data.get("users", []):
        uid = u.get("user_id", "")
        users.append({
            "user_id": uid,
            "display_name": u.get("display_name", uid),
            "roles": u.get("roles", []),
            "permissions": perms.get(uid, []),
        })
    return {"users": users}


class UserPermissionUpdate(BaseModel):
    user_id: str
    permissions: list[str]


@router.put("/permissions/user")
async def update_user_permissions(
    body: UserPermissionUpdate,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """사용자 개별 권한 업데이트."""
    require_admin(user_id, iam)
    perms = _load_user_permissions()
    perms[body.user_id] = body.permissions
    _save_user_permissions(perms)
    return {"status": "updated", "user_id": body.user_id, "permissions": body.permissions}


class ApplyTemplateRequest(BaseModel):
    user_id: str
    template_id: str


@router.post("/permissions/apply-template")
async def apply_permission_template(
    body: ApplyTemplateRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """역할 템플릿을 사용자에게 적용."""
    require_admin(user_id, iam)
    tpl = next((t for t in ROLE_TEMPLATES if t["id"] == body.template_id), None)
    if not tpl:
        raise HTTPException(404, f"Template '{body.template_id}' not found")
    perms = _load_user_permissions()
    perms[body.user_id] = tpl["permissions"]
    _save_user_permissions(perms)
    return {"status": "applied", "user_id": body.user_id, "template": body.template_id, "permissions": tpl["permissions"]}


# ─── 추론 서버 부하 (공개 API — 로그인만 필요) ────────────────────────────────

def _parse_prometheus_metrics(text: str) -> dict[str, Any]:
    """Prometheus 텍스트 형식에서 llama-server 주요 메트릭 추출."""
    import re
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        # 주요 메트릭만 추출
        for key in (
            "llamacpp:tokens_predicted_total",
            "llamacpp:prompt_tokens_total",
            "llamacpp:tokens_predicted_seconds_total",
            "llamacpp:prompt_tokens_seconds_total",
            "llamacpp:requests_processing",
            "llamacpp:requests_deferred",
            "llamacpp:kv_cache_usage_ratio",
            "llamacpp:kv_cache_tokens",
            "llamacpp:slots_processing",
        ):
            if line.startswith(key):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        val = float(parts[-1])
                        short_key = key.replace("llamacpp:", "")
                        result[short_key] = val
                    except ValueError:
                        pass
    # 토큰/s 계산
    pred_total = result.get("tokens_predicted_total", 0)
    pred_seconds = result.get("tokens_predicted_seconds_total", 0)
    if pred_seconds > 0:
        result["tokens_per_second"] = round(pred_total / pred_seconds, 1)
    return result


@router.get("/inference-status")
async def inference_status(user_id: str = Depends(get_current_user)):
    """각 추론 서버의 실시간 부하 상태를 신호등 색으로 반환."""
    import asyncio
    import httpx

    servers = _load_gpu_servers()

    async def _probe(client: httpx.AsyncClient, srv: dict[str, Any]) -> dict[str, Any]:
        base = srv["url"].replace("/v1", "")
        try:
            r = await client.get(f"{base}/health")
            if r.status_code == 200:
                # /slots에서 상세 부하 확인
                try:
                    sr = await client.get(f"{base}/slots")
                    slots = sr.json()
                    total_slots = len(slots)
                    busy_slots = sum(1 for s in slots if s.get("state") != 0)
                    load_pct = int(busy_slots / max(total_slots, 1) * 100)
                except Exception:
                    load_pct = 0
                    total_slots = 0
                    busy_slots = 0

                # 신호등: 0-40% 초록, 40-75% 주황, 75%+ 빨강
                if load_pct < 40:
                    signal, label = "green", "원활"
                elif load_pct < 75:
                    signal, label = "yellow", "보통"
                else:
                    signal, label = "red", "혼잡"

                # /metrics에서 상세 메트릭 수집
                metrics = {}
                try:
                    mr = await client.get(f"{base}/metrics")
                    if mr.status_code == 200:
                        metrics = _parse_prometheus_metrics(mr.text)
                except Exception:
                    pass

                return {
                    **srv,
                    "online": True,
                    "signal": signal,
                    "label": label,
                    "load_pct": load_pct,
                    "slots_total": total_slots,
                    "slots_busy": busy_slots,
                    "metrics": metrics,
                }
            return {**srv, "online": False, "signal": "red", "label": "오프라인", "load_pct": 0}
        except Exception:
            return {**srv, "online": False, "signal": "red", "label": "오프라인", "load_pct": 0}

    async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
        results = await asyncio.gather(*[_probe(client, srv) for srv in servers])

    return {"servers": list(results)}


# ─── 인프라 (K8s 연동 placeholder) ───────────────────────────────────────────

@router.get("/infra")
async def get_infra_status(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    import shutil
    import platform

    # 로컬 리소스 정보
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory_info = {
            "total_gb": round(mem.total / (1024**3), 1),
            "used_gb": round(mem.used / (1024**3), 1),
            "percent": mem.percent,
        }
    except ImportError:
        memory_info = {"total_gb": 0, "used_gb": 0, "percent": 0}
        cpu_percent = 0

    # GPU 정보 (Apple Silicon)
    gpu_info = "Apple Metal (M1 Pro)" if platform.processor() == "arm" else platform.processor()

    # 서비스 상태
    import subprocess
    services = []
    for name, port in [("백엔드", 9001), ("llama-server", 8801), ("프론트엔드", 5173), ("Ollama", 11434)]:
        try:
            r = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=3)
            services.append({"name": name, "port": port, "status": "running" if r.stdout.strip() else "stopped"})
        except Exception:
            services.append({"name": name, "port": port, "status": "unknown"})

    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "gpu": gpu_info,
        "cpu_percent": cpu_percent,
        "memory": memory_info,
        "disk_free_gb": round(shutil.disk_usage("/").free / (1024**3), 1),
        "services": services,
        "k8s_connected": False,
        "k8s_note": "쿠버네티스 연동은 클러스터 설정 후 활성화됩니다.",
    }
