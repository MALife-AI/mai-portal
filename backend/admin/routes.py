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
        "vlm_provider": settings.vlm_provider,
        "vlm_model": settings.vlm_model,
        "llama_server_url": settings.llama_server_url,
        "claude_wrapper_url": settings.claude_wrapper_url,
        "ollama_base_url": settings.ollama_base_url,
        "smart_routing": settings.smart_routing,
        "llama_server_light": settings.llama_server_light,
        "llama_server_heavy": settings.llama_server_heavy,
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

    # 런타임 즉시 반영
    settings.vlm_provider = body.vlm_provider
    settings.vlm_model = body.vlm_model
    settings.llama_server_url = body.llama_server_url
    settings.smart_routing = body.smart_routing
    settings.llama_server_light = body.llama_server_light
    settings.llama_server_heavy = body.llama_server_heavy

    return {"status": "updated"}


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


# ─── API 키 관리 ─────────────────────────────────────────────────────────────

import secrets as _secrets

_API_KEYS_PATH = Path(settings.vault_root).parent / "data" / "api_keys.json"


def _load_api_keys_full() -> list[dict[str, Any]]:
    if _API_KEYS_PATH.exists():
        return json.loads(_API_KEYS_PATH.read_text(encoding="utf-8")).get("keys", [])
    return []


def _save_api_keys_full(keys: list[dict[str, Any]]) -> None:
    _API_KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _API_KEYS_PATH.write_text(
        json.dumps({"keys": keys}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@router.get("/api-keys")
async def list_api_keys(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """API 키 목록 조회 (관리자: 전체, 일반 사용자: 본인만)."""
    keys = _load_api_keys_full()
    is_admin = "admin" in iam.get_user_roles(user_id)
    if not is_admin:
        keys = [k for k in keys if k["user_id"] == user_id]
    # 키 값은 마스킹 (앞 8자만 표시)
    return {
        "keys": [
            {**k, "key": k["key"][:8] + "..." + k["key"][-4:]}
            for k in keys
        ]
    }


@router.post("/api-keys")
async def create_api_key(
    body: dict[str, Any],
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """API 키 발급. 관리자는 다른 사용자용도 발급 가능."""
    target_user = body.get("user_id", user_id)
    is_admin = "admin" in iam.get_user_roles(user_id)

    if target_user != user_id and not is_admin:
        raise HTTPException(403, "다른 사용자의 API 키는 관리자만 발급 가능합니다")

    if not iam.user_exists(target_user):
        raise HTTPException(404, f"사용자 '{target_user}'를 찾을 수 없습니다")

    api_key = f"mlk_{_secrets.token_urlsafe(32)}"
    label = body.get("label", "default")

    keys = _load_api_keys_full()
    keys.append({
        "key": api_key,
        "user_id": target_user,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user_id,
    })
    _save_api_keys_full(keys)

    return {"api_key": api_key, "user_id": target_user, "label": label}


@router.delete("/api-keys/{key_prefix}")
async def revoke_api_key(
    key_prefix: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """API 키 폐기. key_prefix는 앞 8자."""
    keys = _load_api_keys_full()
    is_admin = "admin" in iam.get_user_roles(user_id)

    new_keys = []
    revoked = False
    for k in keys:
        if k["key"].startswith(key_prefix):
            if k["user_id"] != user_id and not is_admin:
                raise HTTPException(403, "다른 사용자의 키는 관리자만 폐기 가능합니다")
            revoked = True
        else:
            new_keys.append(k)

    if not revoked:
        raise HTTPException(404, "해당 키를 찾을 수 없습니다")

    _save_api_keys_full(new_keys)
    return {"status": "revoked", "key_prefix": key_prefix}


# ─── 에이전트 UI 설정 ─────────────────────────────────────────────────────────

_AGENT_UI_PATH = Path(settings.vault_root).parent / "data" / "agent_ui.json"

_DEFAULT_AGENT_UI: dict[str, Any] = {
    "suggestions": [
        "보험 약관에서 면책 조항 추출해줘",
        "최근 투자 보고서 요약해줘",
        "고객 민원 데이터 분석해줘",
        "스킬 목록 보여줘",
    ],
    "welcome_title": "M:AI 에이전트",
    "welcome_subtitle": "금융 문서 분석, RAG 검색, 스킬 실행까지. 무엇이든 물어보세요.",
}


@router.get("/agent-ui")
async def get_agent_ui(user_id: str = Depends(get_current_user)):
    """에이전트 콘솔 UI 설정 조회 (인증된 사용자 모두 접근 가능)."""
    if _AGENT_UI_PATH.exists():
        return json.loads(_AGENT_UI_PATH.read_text(encoding="utf-8"))
    return dict(_DEFAULT_AGENT_UI)


@router.put("/agent-ui")
async def update_agent_ui(
    body: dict[str, Any],
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """에이전트 콘솔 UI 설정 수정 (관리자 전용)."""
    require_admin(user_id, iam)
    current = dict(_DEFAULT_AGENT_UI)
    if _AGENT_UI_PATH.exists():
        current = json.loads(_AGENT_UI_PATH.read_text(encoding="utf-8"))
    current.update(body)
    _AGENT_UI_PATH.parent.mkdir(parents=True, exist_ok=True)
    _AGENT_UI_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


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
        "templates": _all_templates(),
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

    # 역할 → 템플릿 매핑 (기본 권한 유추)
    role_to_template: dict[str, list[str]] = {}
    for tpl in ROLE_TEMPLATES:
        role_to_template[tpl["id"]] = tpl["permissions"]

    users = []
    for u in iam_data.get("users", []):
        uid = u.get("user_id", "")
        user_perms = perms.get(uid)
        if user_perms is None:
            # permissions.json에 없으면 역할 기반 기본 권한 제공
            user_roles = u.get("roles", [])
            default_perms: set[str] = set()
            for role in user_roles:
                default_perms.update(role_to_template.get(role, []))
            user_perms = sorted(default_perms)
        users.append({
            "user_id": uid,
            "display_name": u.get("display_name", uid),
            "roles": u.get("roles", []),
            "department": u.get("department", ""),
            "permissions": user_perms,
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
    tpl = next((t for t in _all_templates() if t["id"] == body.template_id), None)
    if not tpl:
        raise HTTPException(404, f"Template '{body.template_id}' not found")
    perms = _load_user_permissions()
    perms[body.user_id] = tpl["permissions"]
    _save_user_permissions(perms)
    return {"status": "applied", "user_id": body.user_id, "template": body.template_id, "permissions": tpl["permissions"]}


# 커스텀 역할 템플릿 저장소
_CUSTOM_TEMPLATES_PATH = Path(settings.vault_root).parent / "data" / "role_templates.json"


def _load_custom_templates() -> list[dict[str, Any]]:
    if _CUSTOM_TEMPLATES_PATH.exists():
        return json.loads(_CUSTOM_TEMPLATES_PATH.read_text(encoding="utf-8"))
    return []


def _save_custom_templates(templates: list[dict[str, Any]]) -> None:
    _CUSTOM_TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_TEMPLATES_PATH.write_text(json.dumps(templates, indent=2, ensure_ascii=False), encoding="utf-8")


def _all_templates() -> list[dict[str, Any]]:
    return ROLE_TEMPLATES + _load_custom_templates()


@router.post("/permissions/template")
async def create_custom_template(
    body: dict[str, Any],
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """커스텀 역할 템플릿 생성."""
    require_admin(user_id, iam)
    tpl_id = body.get("id", "")
    if not tpl_id or not body.get("name"):
        raise HTTPException(400, "id와 name은 필수입니다")
    # 기본 템플릿과 중복 체크
    if any(t["id"] == tpl_id for t in ROLE_TEMPLATES):
        raise HTTPException(409, f"기본 템플릿 '{tpl_id}'와 중복됩니다")
    templates = _load_custom_templates()
    templates = [t for t in templates if t["id"] != tpl_id]  # 같은 id 덮어쓰기
    templates.append({
        "id": tpl_id,
        "name": body["name"],
        "description": body.get("description", ""),
        "permissions": body.get("permissions", []),
        "custom": True,
    })
    _save_custom_templates(templates)
    return {"status": "created", "template": tpl_id}


@router.delete("/permissions/template/{template_id}")
async def delete_custom_template(
    template_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """커스텀 역할 템플릿 삭제."""
    require_admin(user_id, iam)
    if any(t["id"] == template_id for t in ROLE_TEMPLATES):
        raise HTTPException(400, "기본 템플릿은 삭제할 수 없습니다")
    templates = _load_custom_templates()
    new_templates = [t for t in templates if t["id"] != template_id]
    if len(new_templates) == len(templates):
        raise HTTPException(404, f"템플릿 '{template_id}'를 찾을 수 없습니다")
    _save_custom_templates(new_templates)
    return {"status": "deleted", "template": template_id}


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


# ─── 감사 로그 ───────────────────────────────────────────────────────────────

@router.get("/audit/logs")
async def get_audit_logs_api(
    date: str | None = None,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    require_admin(user_id, iam)
    from backend.security.audit_trail import get_audit_logs
    logs = get_audit_logs(date=date, limit=100)
    return {"logs": logs, "total": len(logs)}


# ─── 베어메탈 호스트 / 머신 관리 ─────────────────────────────────────────────

import json as _json
from pathlib import Path as _Path

_HOSTS_PATH = _Path(settings.vault_root).parent / "data" / "hosts.json"


def _load_hosts() -> list[dict]:
    if _HOSTS_PATH.exists():
        return _json.loads(_HOSTS_PATH.read_text(encoding="utf-8"))
    return []


def _save_hosts(hosts: list[dict]) -> None:
    _HOSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HOSTS_PATH.write_text(_json.dumps(hosts, ensure_ascii=False, indent=2), encoding="utf-8")


async def _agent_request(host: dict, path: str, method: str = "GET", body: dict | None = None) -> dict:
    """베어메탈 Agent 데몬에 HTTP 요청을 보냅니다."""
    import httpx
    url = f"http://{host['host']}:{host.get('agent_port', 9090)}{path}"
    headers = {"Authorization": f"Bearer {host.get('agent_token', '')}"}
    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        else:
            resp = await client.post(url, headers=headers, json=body or {})
        resp.raise_for_status()
        return resp.json()


@router.get("/hosts")
async def list_hosts(
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """등록된 베어메탈 호스트 목록을 반환합니다."""
    require_admin(user_id, iam)
    return {"hosts": _load_hosts()}


class HostCreateRequest(BaseModel):
    id: str
    name: str
    host: str
    agent_port: int = 9090
    agent_token: str = ""
    description: str = ""


@router.post("/hosts")
async def add_host(
    body: HostCreateRequest,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """베어메탈 호스트를 등록합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    if any(h["id"] == body.id for h in hosts):
        raise HTTPException(409, f"호스트 '{body.id}' 이미 존재")
    hosts.append(body.model_dump())
    _save_hosts(hosts)
    return {"status": "added", "id": body.id}


@router.delete("/hosts/{host_id}")
async def remove_host(
    host_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """호스트를 제거합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    hosts = [h for h in hosts if h["id"] != host_id]
    _save_hosts(hosts)
    return {"status": "removed", "id": host_id}


@router.get("/hosts/{host_id}/status")
async def get_host_status(
    host_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """호스트의 실시간 리소스 상태를 조회합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404, f"호스트 '{host_id}' 없음")
    try:
        return await _agent_request(host, "/status")
    except Exception as e:
        return {"error": str(e), "hostname": host.get("name", host_id), "offline": True}


@router.get("/hosts/{host_id}/machines")
async def list_host_machines(
    host_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """호스트에서 실행 중인 머신 목록을 조회합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404, f"호스트 '{host_id}' 없음")
    try:
        return await _agent_request(host, "/machines")
    except Exception as e:
        return {"machines": [], "error": str(e)}


class MachineCreateBody(BaseModel):
    name: str
    model_path: str
    model_alias: str = "model"
    port: int = 8801
    ctx_size: int = 16384
    n_gpu_layers: int = 999
    cpus: float = 4.0
    memory_gb: float = 16.0
    gpu_device: str = "all"
    extra_args: str = ""


@router.post("/hosts/{host_id}/machines/create")
async def create_host_machine(
    host_id: str,
    body: MachineCreateBody,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """호스트에 새 추론 머신을 생성합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404, f"호스트 '{host_id}' 없음")
    try:
        return await _agent_request(host, "/machines/create", method="POST", body=body.model_dump())
    except Exception as e:
        raise HTTPException(500, f"머신 생성 실패: {e}")


@router.post("/hosts/{host_id}/machines/{machine_name}/stop")
async def stop_host_machine(
    host_id: str,
    machine_name: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """머신을 중지합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404, f"호스트 '{host_id}' 없음")
    try:
        return await _agent_request(host, f"/machines/{machine_name}/stop", method="POST")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/hosts/{host_id}/machines/{machine_name}/restart")
async def restart_host_machine(
    host_id: str,
    machine_name: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """머신을 재시작합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404, f"호스트 '{host_id}' 없음")
    try:
        return await _agent_request(host, f"/machines/{machine_name}/restart", method="POST")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/hosts/{host_id}/machines/{machine_name}/logs")
async def get_host_machine_logs(
    host_id: str,
    machine_name: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """머신 로그를 조회합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404)
    try:
        return await _agent_request(host, f"/machines/{machine_name}/logs")
    except Exception as e:
        return {"logs": "", "error": str(e)}


@router.get("/hosts/{host_id}/models")
async def list_host_models(
    host_id: str,
    user_id: str = Depends(get_current_user),
    iam: IAMEngine = Depends(get_iam),
):
    """호스트에서 사용 가능한 모델 목록을 조회합니다."""
    require_admin(user_id, iam)
    hosts = _load_hosts()
    host = next((h for h in hosts if h["id"] == host_id), None)
    if not host:
        raise HTTPException(404)
    try:
        return await _agent_request(host, "/models")
    except Exception as e:
        return {"models": [], "error": str(e)}
